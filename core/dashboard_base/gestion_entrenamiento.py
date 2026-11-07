"""Apartado de Gestion para los modelos de pronostico. Solo perfil de
administracion (PERMISO_GESTIONAR_PRONOSTICO) y solo para patologias cuyo plugin
declara un modulo de pronostico (PathologyPlugin.obtener_pronostico). El
personal del CITES (Editor) no lo ve.

Es el UNICO lugar donde se entrenan, suben, activan o eliminan modelos: la
pestana Pronostico solo muestra. Cada modelo tiene sus propias versiones y cada
familia una version activa (core/storage/modelos.py). El nucleo no sabe que
modelos ni familias hay: los pide al modulo de pronostico del plugin.

Entrenar y subir corren en el worker (misma cola que las cargas, ver
core/ingestion/entrenamiento.py); el aviso de terminado llega igual que el de
una carga: st.toast desde el fragmento raiz de avisos (ver
gestion_subida.fragmento_avisos_subida). Activar y eliminar son instantaneos.
"""

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from core.audit.entrenamientos import (
    ACCION_ACTIVAR,
    ACCION_ELIMINAR,
    ACCION_ENTRENAR,
    ACCION_SUBIR,
    ACCIONES_DEL_WORKER,
    listar_entrenamientos,
    registrar_accion_inmediata,
)
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.seleccion_cruzada import recargar_seccion
from core.ingestion.entrenamiento import describir_rango, encolar_entrenamiento, encolar_importacion
from core.registry import obtener_patologia
from core.storage import modelos

CLAVE_TRABAJOS_PENDIENTES = "modelos_pronostico_pendientes_por_usuario"
CLAVE_AVISO_ENVIADO = "modelos_pronostico_aviso_enviado"
CLAVE_CONTADOR_UPLOADER = "modelos_pronostico_contador_uploader"

_TODAS_LAS_FAMILIAS = "todas"

NOMBRE_PERSISTENCIA = "Persistencia (línea base)"

_ORIGENES = {
    "sistema": "Entrenado en la app",
    "subido": "Subido (.zip)",
}

_ACCIONES = {
    ACCION_ENTRENAR: "Entrenar",
    ACCION_SUBIR: "Subir .zip",
    ACCION_ACTIVAR: "Activar",
    ACCION_ELIMINAR: "Eliminar",
}

# Hora de Colombia para mostrar cuando entro cada version (los nombres de
# version y las fechas del manifest estan en UTC).
_ZONA_HORARIA_LOCAL = ZoneInfo("America/Bogota")

_MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ---------------------------------------------------------------------------
# Utilidades compartidas con la pestana Pronostico
# ---------------------------------------------------------------------------

def formatear_fecha_larga(fecha_iso: str) -> str:
    """'12 de noviembre de 2026' a partir de una fecha ISO."""
    fecha = datetime.fromisoformat(fecha_iso)
    return f"{fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"


def _fecha_de_version(version: str) -> datetime | None:
    """La version es la hora UTC en que entro al sistema (AAAAMMDDTHHMMSSZ,
    a veces con sufijo _2, _3...)."""
    try:
        fecha = datetime.strptime(version[:16], "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return fecha.replace(tzinfo=timezone.utc)


def formatear_fecha_hora_corta(fecha: datetime) -> str:
    """'6 nov 2026, 3:37 a. m.' en hora de Colombia."""
    local = fecha.astimezone(_ZONA_HORARIA_LOCAL)
    hora = local.hour % 12
    if hora == 0:
        hora = 12
    if local.hour < 12:
        sufijo = "a. m."
    else:
        sufijo = "p. m."
    return f"{local.day} {_MESES_CORTOS[local.month - 1]} {local.year}, {hora}:{local.minute:02d} {sufijo}"


def _anios_del_rango(rango: dict) -> str:
    if not rango:
        return "-"
    return f"{rango['anio_inicio']}-{rango['anio_fin']}"


# Presentacion: los calculos guardan los valores sin redondear; las tablas los
# muestran con 1 decimal (R2 con 2, porque no esta en casos).
FORMATO_COLUMNAS_METRICAS = {
    "RMSE": st.column_config.NumberColumn("RMSE", format="%.1f"),
    "RMSE H4": st.column_config.NumberColumn("RMSE H4", format="%.1f"),
    "MAE": st.column_config.NumberColumn("MAE", format="%.1f"),
    "MAPE (%)": st.column_config.NumberColumn("MAPE (%)", format="%.1f"),
    "R²": st.column_config.NumberColumn("R²", format="%.2f"),
    "RMSE persistencia": st.column_config.NumberColumn("RMSE persistencia", format="%.1f"),
    "MAE persistencia": st.column_config.NumberColumn("MAE persistencia", format="%.1f"),
    "Razón RMSE vs persistencia": st.column_config.NumberColumn("Razón RMSE vs persistencia", format="%.2f"),
}


def _fila_metricas(etiqueta: str, valor_etiqueta, del_modelo: dict, de_persistencia: dict) -> dict:
    rmse = del_modelo.get("RMSE")
    rmse_persistencia = de_persistencia.get("RMSE")
    razon = None
    if rmse is not None and rmse_persistencia:
        razon = rmse / rmse_persistencia
    return {
        etiqueta: valor_etiqueta,
        "n": del_modelo.get("n"),
        "RMSE": rmse,
        "MAE": del_modelo.get("MAE"),
        "MAPE (%)": del_modelo.get("MAPE"),
        "n MAPE": del_modelo.get("n_mape"),
        "R²": del_modelo.get("R2"),
        "RMSE persistencia": rmse_persistencia,
        "MAE persistencia": de_persistencia.get("MAE"),
        "Razón RMSE vs persistencia": razon,
    }


def tabla_metricas(manifest: dict) -> pd.DataFrame:
    """Metricas acumuladas por horizonte de la prueba (manifest.metricas_prueba,
    calculadas desde el CSV), con la persistencia en los mismos registros y la
    razon entre ambos RMSE (menos de 1 = el modelo le gana). Vacia si la
    version no tiene metricas en el formato vigente."""
    metricas = manifest.get("metricas_prueba", {}).get("por_horizonte", {})
    filas = []
    for horizonte in sorted(metricas, key=int):
        por_pronosticador = metricas[horizonte]
        filas.append(_fila_metricas(
            "Horizonte", f"H{horizonte}", por_pronosticador["modelo"], por_pronosticador["persistencia"]
        ))
    return pd.DataFrame(filas)


def tabla_metricas_global(manifest: dict) -> pd.DataFrame:
    """Metricas acumuladas globales de la prueba: todos los registros de todos
    los horizontes a la vez (no el promedio de las seis por horizonte)."""
    metricas = manifest.get("metricas_prueba", {}).get("global")
    if not metricas:
        return pd.DataFrame()
    fila = _fila_metricas("Alcance", "Global (H1 a H6)", metricas["modelo"], metricas["persistencia"])
    return pd.DataFrame([fila])


def mostrar_metricas_de_version(manifest: dict) -> None:
    """Metricas acumuladas de una version con su alcance explicito."""
    metricas = manifest.get("metricas_prueba")
    if not metricas:
        st.markdown("Esta versión es del esquema anterior: no tiene métricas acumuladas por registros.")
        return
    st.markdown(metricas.get("alcance", ""))
    st.dataframe(tabla_metricas_global(manifest), hide_index=True, width="stretch", column_config=FORMATO_COLUMNAS_METRICAS)
    st.dataframe(tabla_metricas(manifest), hide_index=True, width="stretch", column_config=FORMATO_COLUMNAS_METRICAS)
    st.caption(
        "n: registros de la prueba usados en cada cálculo. n MAPE: los que tienen casos reales "
        "distintos de 0 (el MAPE no está definido con 0 casos reales). Valores mostrados con 1 "
        "decimal; los cálculos usan los valores sin redondear."
    )


def nombre_modelo(manifest: dict, clave: str) -> str:
    return manifest.get("nombre") or clave


# ---------------------------------------------------------------------------
# Apartado
# ---------------------------------------------------------------------------

def mostrar_gestion_pronostico(patologia: str, usuario) -> None:
    modulo_pronostico = obtener_patologia(patologia).obtener_pronostico()
    familias = modulo_pronostico.familias()

    st.subheader(":material/model_training: Modelos de pronóstico")
    st.markdown(
        "Solo perfil de administración. La pestaña Pronóstico muestra la versión activa de cada "
        "familia. Aquí se entrena una versión nueva en la app, se sube una entrenada en otro "
        "equipo, se cambia la versión activa o se elimina una que ya no sirve. Todo queda en el "
        "historial."
    )

    _mostrar_aviso_enviado(patologia)
    _mostrar_activos(patologia, familias)

    pestana_entrenar, pestana_subir, pestana_versiones, pestana_historial = st.tabs([
        ":material/model_training: Entrenar",
        ":material/upload: Subir modelo",
        ":material/inventory_2: Versiones",
        ":material/receipt_long: Historial",
    ])
    with pestana_entrenar:
        _mostrar_entrenar(patologia, usuario, modulo_pronostico, familias)
    with pestana_subir:
        _mostrar_subir(patologia, usuario)
    with pestana_versiones:
        _mostrar_versiones(patologia, usuario, familias)
    with pestana_historial:
        _mostrar_historial(patologia, familias)


def _mostrar_aviso_enviado(patologia: str) -> None:
    avisos = st.session_state.setdefault(CLAVE_AVISO_ENVIADO, {})
    mensaje = avisos.get(patologia)
    if not mensaje:
        return
    columna_mensaje, columna_cerrar = st.columns([10, 1])
    with columna_mensaje:
        st.info(f":material/hourglass_top: {mensaje}")
    with columna_cerrar:
        if st.button("", icon=":material/close:", help="Cerrar este aviso", key=f"cerrar_aviso_modelos_{patologia}"):
            avisos.pop(patologia, None)
            recargar_seccion()


def _fin_del_consolidado(patologia: str) -> pd.Timestamp | None:
    """Inicio de la ultima semana del consolidado cargado en la sesion."""
    try:
        datos = modulo_datos.obtener_datos(patologia)
    except KeyError:
        return None
    modulo_pronostico = obtener_patologia(patologia).obtener_pronostico()
    semanas = modulo_pronostico.semanas_disponibles(datos)
    if semanas.empty:
        return None
    return pd.Timestamp(semanas["fecha_semana"].max())


def _mostrar_activos(patologia: str, familias: dict[str, str]) -> None:
    activos = modelos.leer_activos(patologia)
    fin_consolidado = _fin_del_consolidado(patologia)
    columnas = st.columns(len(familias))
    for columna, (familia, rotulo_familia) in zip(columnas, familias.items()):
        with columna:
            with st.container(border=True):
                st.markdown(f"**{rotulo_familia}**")
                puntero = activos.get(familia)
                if puntero is None:
                    st.markdown("#### Sin modelo activo")
                    st.markdown("Entrena o sube uno: la pestaña no muestra esta familia hasta entonces.")
                    continue
                manifest = modelos.leer_manifest(patologia, puntero["modelo"], puntero["version"]) or {}
                rango = manifest.get("rango", {})
                st.markdown(f"#### {nombre_modelo(manifest, puntero['modelo'])}")
                fecha_version = _fecha_de_version(puntero["version"])
                cuando = formatear_fecha_hora_corta(fecha_version) if fecha_version else puntero["version"]
                st.markdown(
                    f"Datos: {describir_rango(rango) if rango else '-'}  \n"
                    f"{_ORIGENES.get(manifest.get('origen'), '-')} · {cuando}"
                )
                st.caption(f"Versión {puntero['version']}")
                fecha_ultima = rango.get("fecha_ultima_semana")
                if fin_consolidado is not None and fecha_ultima and fin_consolidado > pd.Timestamp(fecha_ultima):
                    st.markdown(":material/update: El consolidado tiene datos más recientes que este modelo.")


# ---------------------------------------------------------------------------
# Entrenar en la app
# ---------------------------------------------------------------------------

def _etiqueta_semana(fila) -> str:
    return f"{int(fila['ano'])} · sem. {int(fila['semana'])}"


def _hiperparametros_de_partida(patologia: str, clase) -> tuple[dict, str]:
    """Los de la version activa de ese modelo si la hay; si no, los de su
    version mas reciente; si no, los por defecto. Asi reentrenar en la app no
    pierde lo que se ajusto en la experimentacion."""
    activos = modelos.leer_activos(patologia)
    puntero = activos.get(clase.familia)
    if puntero is not None and puntero["modelo"] == clase.clave:
        manifest = modelos.leer_manifest(patologia, clase.clave, puntero["version"]) or {}
        if manifest.get("hiperparametros"):
            return manifest["hiperparametros"], f"los de la versión activa ({puntero['version']})"
    versiones = modelos.listar_versiones(patologia, clase.clave)
    if versiones:
        mas_reciente = versiones[0]
        hiperparametros = mas_reciente["manifest"].get("hiperparametros")
        if hiperparametros:
            return hiperparametros, f"los de su versión más reciente ({mas_reciente['version']})"
    return clase(None).hiperparametros, "los valores por defecto del modelo"


def _mostrar_entrenar(patologia: str, usuario, modulo_pronostico, familias: dict[str, str]) -> None:
    st.markdown(
        "Entrena una versión nueva en el procesador, con las semanas del rango elegido. La "
        "validación usa el último 15 % del rango como prueba (error por horizonte de 1 a 6 "
        "semanas); después el modelo se entrena con todo el rango."
    )
    catalogo = modulo_pronostico.catalogo()

    columna_familia, columna_modelo = st.columns(2)
    with columna_familia:
        familia = st.selectbox(
            "Familia",
            list(familias),
            format_func=lambda clave: familias[clave],
            key=f"entrenar_familia_{patologia}",
        )
    candidatos = sorted(
        [clase for clase in catalogo.values() if clase.familia == familia],
        key=lambda clase: clase.nombre,
    )
    if not candidatos:
        st.info("Esta familia no tiene modelos en el catálogo.")
        return

    def _rotulo_modelo(clave: str) -> str:
        clase = catalogo[clave]
        faltantes = clase.paquetes_faltantes()
        if faltantes:
            return f"{clase.nombre} (no disponible: falta {', '.join(faltantes)})"
        return clase.nombre

    with columna_modelo:
        clave_modelo = st.selectbox(
            "Modelo",
            [clase.clave for clase in candidatos],
            format_func=_rotulo_modelo,
            key=f"entrenar_modelo_{patologia}_{familia}",
        )
    clase = catalogo[clave_modelo]
    faltantes = clase.paquetes_faltantes()

    try:
        datos = modulo_datos.obtener_datos(patologia)
    except KeyError:
        st.warning("No hay consolidado cargado en la sesión.")
        return
    semanas = modulo_pronostico.semanas_disponibles(datos).reset_index(drop=True)
    if semanas.empty:
        st.warning("No hay semanas con datos para entrenar.")
        return
    etiquetas = [_etiqueta_semana(fila) for _, fila in semanas.iterrows()]
    desde_etiqueta, hasta_etiqueta = st.select_slider(
        "Rango de entrenamiento",
        options=etiquetas,
        value=(etiquetas[0], etiquetas[-1]),
        key=f"entrenar_rango_{patologia}",
        help=(
            "Semanas con las que se valida y entrena el modelo. Por ejemplo, para dejar fuera "
            "semanas recientes todavía incompletas, o para comparar cómo cambia el error al "
            "incluir un año atípico."
        ),
    )
    posicion_desde = etiquetas.index(desde_etiqueta)
    posicion_hasta = etiquetas.index(hasta_etiqueta)
    desde = pd.Timestamp(semanas.loc[posicion_desde, "fecha_semana"])
    hasta = pd.Timestamp(semanas.loc[posicion_hasta, "fecha_semana"])
    cantidad_semanas = posicion_hasta - posicion_desde + 1
    st.caption(f"{cantidad_semanas} semanas ({cantidad_semanas / 52:.1f} años).")

    hiperparametros_base, procedencia = _hiperparametros_de_partida(patologia, clase)
    texto_base = json.dumps(hiperparametros_base, ensure_ascii=False, indent=2)
    with st.expander("Hiperparámetros (avanzado)"):
        st.caption(f"Se parte de {procedencia}. Se pueden editar en formato JSON.")
        texto_hiperparametros = st.text_area(
            "Hiperparámetros",
            value=texto_base,
            height=260,
            label_visibility="collapsed",
            key=f"entrenar_hiperparametros_{patologia}_{clave_modelo}_{hash(texto_base)}",
        )

    activar = st.toggle(
        "Dejarla como activa de su familia al terminar",
        value=True,
        key=f"entrenar_activar_{patologia}",
        help="Si la familia todavía no tiene modelo activo, la versión nueva queda activa igual.",
    )

    if faltantes:
        st.warning(f"No se puede entrenar {clase.nombre}: falta instalar {', '.join(faltantes)}.")
    if st.button(
        "Entrenar",
        type="primary",
        icon=":material/model_training:",
        disabled=bool(faltantes),
        key=f"entrenar_boton_{patologia}",
    ):
        try:
            hiperparametros = json.loads(texto_hiperparametros)
        except json.JSONDecodeError as error:
            st.error(f"Los hiperparámetros no son un JSON válido: {error}")
            return
        if not isinstance(hiperparametros, dict):
            st.error("Los hiperparámetros deben ser un objeto JSON ({...}).")
            return
        solicitud = {
            "modelo": clave_modelo,
            "nombre": clase.nombre,
            "desde": desde,
            "hasta": hasta,
            "rango_texto": f"{desde_etiqueta} a {hasta_etiqueta}",
            "hiperparametros": hiperparametros,
            "activar": activar,
        }
        _dialogo_confirmar_entrenamiento(patologia, usuario, solicitud)


@st.dialog("Entrenar una versión nueva")
def _dialogo_confirmar_entrenamiento(patologia: str, usuario, solicitud: dict) -> None:
    texto_activar = "y quedará como activa de su familia" if solicitud["activar"] else "sin cambiar la versión activa"
    st.markdown(
        f"Se entrena {solicitud['nombre']} con datos de {solicitud['rango_texto']} {texto_activar}. "
        "Las versiones anteriores se conservan."
    )
    st.caption("Corre en segundo plano en el procesador (puede tardar varios minutos): puedes seguir usando el tablero.")
    columna_cancelar, columna_confirmar = st.columns(2)
    with columna_cancelar:
        if st.button("Cancelar", width="stretch", key=f"cancelar_entrenar_{patologia}"):
            st.rerun()
    with columna_confirmar:
        if st.button("Sí, entrenar", type="primary", width="stretch", key=f"confirmar_entrenar_{patologia}"):
            fecha_solicitud = datetime.now(timezone.utc).isoformat()
            try:
                encolar_entrenamiento(
                    patologia,
                    solicitud["modelo"],
                    solicitud["desde"],
                    solicitud["hasta"],
                    solicitud["hiperparametros"],
                    solicitud["activar"],
                    usuario.nombre_usuario,
                    fecha_solicitud,
                )
            except Exception as error:
                st.error(f"No se pudo enviar el entrenamiento a la cola de trabajos: {error}")
                return
            _registrar_pendiente(
                patologia,
                usuario.nombre_usuario,
                fecha_solicitud,
                f"Entrenamiento de {solicitud['nombre']} enviado al procesador. Te avisamos cuando "
                "termine; el resultado queda también en el historial.",
            )
            st.rerun()


# ---------------------------------------------------------------------------
# Subir un modelo entrenado afuera
# ---------------------------------------------------------------------------

def _key_uploader(patologia: str) -> str:
    """Cambiar la key del file_uploader lo deja vacio despues de enviar."""
    contador = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER, {}).get(patologia, 0)
    return f"subir_modelo_{patologia}_{contador}"


def _mostrar_subir(patologia: str, usuario) -> None:
    st.markdown(
        "Sube un modelo entrenado en otro equipo (por ejemplo, con los notebooks de producción "
        "del repositorio de experimentación en un equipo con más cómputo). El procesador revisa el "
        "paquete antes de guardarlo; si algo falla, no se guarda nada y el motivo queda en el "
        "historial."
    )
    if st.button(
        "Ver estructura del paquete",
        icon=":material/folder_zip:",
        key=f"estructura_paquete_{patologia}",
    ):
        _dialogo_estructura_paquete(patologia)
    archivo = st.file_uploader(
        "Paquete del modelo (.zip)",
        type=["zip"],
        key=_key_uploader(patologia),
    )
    activar = st.toggle(
        "Dejarlo como activo de su familia si pasa la revisión",
        value=True,
        key=f"subir_activar_{patologia}",
    )
    if archivo is None:
        return

    tamano_mb = archivo.size / (1024 * 1024)
    if tamano_mb > modelos.TAMANO_MAXIMO_ZIP_MB:
        st.error(f"El .zip pesa {tamano_mb:.0f} MB; el máximo es {modelos.TAMANO_MAXIMO_ZIP_MB} MB.")
        return

    if st.button("Subir y revisar", type="primary", icon=":material/upload:", key=f"subir_modelo_boton_{patologia}"):
        fecha_solicitud = datetime.now(timezone.utc).isoformat()
        directorio = modelos.directorio_subidas(patologia)
        directorio.mkdir(parents=True, exist_ok=True)
        marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        ruta_zip = directorio / f"{marca}.zip"
        ruta_zip.write_bytes(archivo.getvalue())
        try:
            encolar_importacion(
                patologia, ruta_zip, archivo.name, activar, usuario.nombre_usuario, fecha_solicitud
            )
        except Exception as error:
            ruta_zip.unlink(missing_ok=True)
            st.error(f"No se pudo enviar el modelo a la cola de trabajos: {error}")
            return
        contadores = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER, {})
        contadores[patologia] = contadores.get(patologia, 0) + 1
        _registrar_pendiente(
            patologia,
            usuario.nombre_usuario,
            fecha_solicitud,
            f"{archivo.name} enviado al procesador para revisión. Te avisamos cuando termine; "
            "el resultado queda también en el historial.",
        )
        st.rerun()


@st.dialog("Estructura del paquete .zip", width="large")
def _dialogo_estructura_paquete(patologia: str) -> None:
    """La documentacion del paquete (la misma de la documentacion tecnica de la
    patologia) y una muestra real de cada archivo de los modelos activos
    (ModuloPronostico.describir_paquete). Las reglas de descompresion del .zip
    son del nucleo."""
    descripcion = obtener_patologia(patologia).obtener_pronostico().describir_paquete() or {}

    st.markdown(
        f"Reglas del núcleo para cualquier paquete: máximo {modelos.TAMANO_MAXIMO_ZIP_MB} MB y "
        "archivos en la raíz del .zip o dentro de una sola carpeta, sin subcarpetas."
    )
    for seccion in descripcion.get("secciones", []):
        st.markdown(f"#### {seccion['titulo']}")
        st.markdown(seccion["markdown"])

    ejemplos_por_modelo = descripcion.get("ejemplos_por_modelo", {})
    if ejemplos_por_modelo:
        st.markdown("#### Ejemplo real: paquete de un modelo activo")
        nombre_elegido = st.selectbox(
            "Modelo",
            list(ejemplos_por_modelo),
            key=f"estructura_paquete_modelo_{patologia}",
        )
        ejemplo = ejemplos_por_modelo[nombre_elegido]
        st.code(ejemplo["arbol"], language="text")
        for archivo in ejemplo["archivos"]:
            with st.expander(archivo["titulo"]):
                st.code(archivo["contenido"], language=archivo["lenguaje"])

    if st.button("Cerrar", width="stretch", key=f"cerrar_estructura_{patologia}"):
        st.rerun()


# ---------------------------------------------------------------------------
# Versiones: activar y eliminar
# ---------------------------------------------------------------------------

def _rotulo_version(elemento: dict, activas: set) -> str:
    """'XGBoost · 6 nov 2026, 3:37 a. m. · datos 2007-2025 · entrenado en la app
    · ACTIVA': lo que hace falta para reconocer una version sin leer su codigo."""
    manifest = elemento["manifest"]
    partes = [nombre_modelo(manifest, elemento["modelo"])]
    fecha = _fecha_de_version(elemento["version"])
    if fecha is not None:
        partes.append(formatear_fecha_hora_corta(fecha))
    else:
        partes.append(elemento["version"])
    partes.append(f"datos {_anios_del_rango(manifest.get('rango', {}))}")
    partes.append(_ORIGENES.get(manifest.get("origen"), "-").lower())
    if (elemento["modelo"], elemento["version"]) in activas:
        partes.append("ACTIVA")
    return " · ".join(partes)


def _tabla_versiones(versiones: list[dict], activas: set, familias: dict[str, str]) -> pd.DataFrame:
    filas = []
    for elemento in versiones:
        manifest = elemento["manifest"]
        rango = manifest.get("rango", {})
        horizonte_4 = manifest.get("metricas_prueba", {}).get("por_horizonte", {}).get("4", {})
        rmse_4 = horizonte_4.get("modelo", {}).get("RMSE")
        rmse_persistencia_4 = horizonte_4.get("persistencia", {}).get("RMSE")
        razon_4 = None
        if rmse_4 is not None and rmse_persistencia_4:
            razon_4 = rmse_4 / rmse_persistencia_4
        es_activa = (elemento["modelo"], elemento["version"]) in activas
        fecha = manifest.get("fecha_entrenamiento")
        filas.append({
            "Familia": familias.get(manifest.get("familia"), manifest.get("familia", "-")),
            "Modelo": nombre_modelo(manifest, elemento["modelo"]),
            "Versión": elemento["version"],
            "Activa": "Sí" if es_activa else "",
            "Origen": _ORIGENES.get(manifest.get("origen"), "-"),
            "Datos": describir_rango(rango) if rango else "-",
            "Entrenada el": formatear_fecha_larga(fecha) if fecha else "-",
            "Por": manifest.get("usuario", "-"),
            "RMSE": rmse_4,
            "Razón RMSE vs persistencia": razon_4,
        })
    tabla = pd.DataFrame(filas)
    return tabla.rename(columns={"RMSE": "RMSE H4"})


def _mostrar_versiones(patologia: str, usuario, familias: dict[str, str]) -> None:
    versiones = modelos.listar_versiones(patologia)
    if not versiones:
        st.caption("Sin versiones todavía.")
        return
    # Agrupadas por familia (en el orden de la patologia) y por modelo; dentro
    # de cada modelo, la mas reciente primero (listar_versiones ya las ordena).
    orden_familias = list(familias)

    def _clave_orden(elemento: dict) -> tuple:
        familia = elemento["manifest"].get("familia")
        posicion = orden_familias.index(familia) if familia in orden_familias else len(orden_familias)
        return (posicion, elemento["modelo"])

    versiones = sorted(versiones, key=_clave_orden)

    opciones_familia = [_TODAS_LAS_FAMILIAS] + list(familias)

    def _rotulo_familia(opcion: str) -> str:
        if opcion == _TODAS_LAS_FAMILIAS:
            return "Todas"
        return familias[opcion]

    familia_elegida = st.segmented_control(
        "Familia",
        opciones_familia,
        default=_TODAS_LAS_FAMILIAS,
        required=True,
        format_func=_rotulo_familia,
        key=f"versiones_familia_{patologia}",
    )
    if familia_elegida != _TODAS_LAS_FAMILIAS:
        versiones = [
            elemento for elemento in versiones if elemento["manifest"].get("familia") == familia_elegida
        ]
    if not versiones:
        st.markdown("Esta familia no tiene versiones todavía.")
        return

    activos = modelos.leer_activos(patologia)
    activas = {(puntero["modelo"], puntero["version"]) for puntero in activos.values()}
    modulo_pronostico = obtener_patologia(patologia).obtener_pronostico()
    vigentes = [elemento for elemento in versiones if modulo_pronostico.es_version_vigente(elemento["manifest"])]
    historicas = [elemento for elemento in versiones if not modulo_pronostico.es_version_vigente(elemento["manifest"])]

    if vigentes:
        st.dataframe(
            _tabla_versiones(vigentes, activas, familias),
            hide_index=True,
            width="stretch",
            column_config=FORMATO_COLUMNAS_METRICAS,
        )
        st.caption(
            "RMSE H4: métrica acumulada de los pronósticos a 4 semanas en la prueba. Razón: RMSE del "
            "modelo dividido por el de la persistencia en los mismos registros; menos de 1 = el "
            "modelo le gana."
        )
    else:
        st.markdown("No hay versiones del esquema vigente en esta familia.")
    if historicas:
        with st.expander(f"Versiones del esquema anterior (histórico, no se pueden activar): {len(historicas)}"):
            st.dataframe(_tabla_versiones(historicas, activas, familias), hide_index=True, width="stretch")

    versiones = vigentes + historicas
    indices = list(range(len(versiones)))
    indice_elegido = st.selectbox(
        "Elegir versión",
        indices,
        format_func=lambda indice: _rotulo_version(versiones[indice], activas),
        key=f"version_elegida_{patologia}_{familia_elegida}",
    )
    elegida = versiones[indice_elegido]
    es_activa = (elegida["modelo"], elegida["version"]) in activas
    es_vigente = modulo_pronostico.es_version_vigente(elegida["manifest"])
    if es_activa:
        ayuda_activar = "Ya es la versión activa de su familia."
    elif not es_vigente:
        ayuda_activar = "Versión del esquema anterior: se conserva como histórico y no se puede activar."
    else:
        ayuda_activar = None

    columna_activar, columna_eliminar = st.columns(2)
    with columna_activar:
        if st.button(
            "Activar en su familia",
            icon=":material/check_circle:",
            width="stretch",
            disabled=es_activa or not es_vigente,
            help=ayuda_activar,
            key=f"activar_version_{patologia}",
        ):
            _dialogo_confirmar_activacion(patologia, elegida, usuario, familias)
    with columna_eliminar:
        if st.button(
            "Eliminar",
            icon=":material/delete_forever:",
            width="stretch",
            disabled=es_activa,
            help="La versión activa no se puede eliminar: activa primero otra de su familia." if es_activa else None,
            key=f"eliminar_version_{patologia}",
        ):
            _dialogo_confirmar_eliminacion(patologia, elegida, usuario, familias)

    with st.expander("Métricas de la prueba, librerías e hiperparámetros de esta versión"):
        manifest = elegida["manifest"]
        prueba = manifest.get("prueba", {})
        st.markdown(f"Serie: {manifest.get('serie', 'no declarada')}.")
        if prueba.get("inicio_prueba"):
            st.markdown(
                f"Prueba: {prueba['inicio_prueba']} a {prueba.get('fin_prueba', '-')}, "
                f"{prueba.get('registros', '-')} registros desde {prueba.get('cantidad_origenes', '-')} "
                "semanas de origen."
            )
        mostrar_metricas_de_version(manifest)
        compatibilidad = manifest.get("compatibilidad")
        librerias = manifest.get("librerias", {})
        if compatibilidad:
            filas_librerias = []
            for paquete, datos in compatibilidad.items():
                filas_librerias.append({"Librería": paquete, "Exportado con": datos["exportado"], "Instalada": datos["instalado"], "Estado": datos["estado"]})
            st.dataframe(pd.DataFrame(filas_librerias), hide_index=True, width="stretch")
        elif librerias:
            st.markdown("Librerías: " + ", ".join(f"{paquete} {version}" for paquete, version in librerias.items()))
        with st.popover("Hiperparámetros"):
            st.json(manifest.get("hiperparametros", {}))


@st.dialog("Cambiar la versión activa")
def _dialogo_confirmar_activacion(patologia: str, elemento: dict, usuario, familias: dict[str, str]) -> None:
    manifest = elemento["manifest"]
    rango = manifest.get("rango", {})
    familia = familias.get(manifest.get("familia"), manifest.get("familia", "-"))
    st.markdown(
        f"La pestaña Pronóstico pasará a usar {nombre_modelo(manifest, elemento['modelo'])} "
        f"(versión {elemento['version']}, datos de {describir_rango(rango) if rango else 'rango desconocido'}) "
        f"en la familia {familia}, para todas las personas."
    )
    columna_cancelar, columna_confirmar = st.columns(2)
    with columna_cancelar:
        if st.button("Cancelar", width="stretch", key=f"cancelar_activar_{patologia}"):
            st.rerun()
    with columna_confirmar:
        if st.button("Sí, activar", type="primary", width="stretch", key=f"confirmar_activar_{patologia}"):
            familia_activada = modelos.activar_version(
                patologia, elemento["modelo"], elemento["version"], usuario.nombre_usuario
            )
            registrar_accion_inmediata(
                patologia,
                ACCION_ACTIVAR,
                usuario.nombre_usuario,
                datetime.now(timezone.utc).isoformat(),
                elemento["modelo"],
                familia_activada,
                elemento["version"],
                describir_rango(rango) if rango else None,
            )
            st.rerun()


@st.dialog("Eliminar una versión")
def _dialogo_confirmar_eliminacion(patologia: str, elemento: dict, usuario, familias: dict[str, str]) -> None:
    manifest = elemento["manifest"]
    rango = manifest.get("rango", {})
    st.markdown(
        f"Se elimina para siempre la versión {elemento['version']} de "
        f"{nombre_modelo(manifest, elemento['modelo'])}. No se puede deshacer; queda la traza en el "
        "historial."
    )
    if manifest.get("origen") == "subido":
        st.warning(
            "Este modelo se entrenó en otro equipo: si no conservas el .zip, no hay forma de recuperarlo.",
            icon=":material/warning:",
        )
    columna_cancelar, columna_confirmar = st.columns(2)
    with columna_cancelar:
        if st.button("Cancelar", width="stretch", key=f"cancelar_eliminar_{patologia}"):
            st.rerun()
    with columna_confirmar:
        if st.button("Sí, eliminar", type="primary", width="stretch", key=f"confirmar_eliminar_{patologia}"):
            try:
                modelos.eliminar_version(patologia, elemento["modelo"], elemento["version"])
            except ValueError as error:
                st.error(str(error))
                return
            registrar_accion_inmediata(
                patologia,
                ACCION_ELIMINAR,
                usuario.nombre_usuario,
                datetime.now(timezone.utc).isoformat(),
                elemento["modelo"],
                manifest.get("familia"),
                elemento["version"],
                describir_rango(rango) if rango else None,
                detalle={"manifest_eliminado": manifest},
            )
            st.rerun()


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------

def _mostrar_historial(patologia: str, familias: dict[str, str]) -> None:
    movimientos = listar_entrenamientos(patologia)
    if not movimientos:
        st.caption("Todavía no hay movimientos registrados.")
        return
    filas = []
    for movimiento in movimientos:
        if movimiento["estado"] == "listo":
            estado = "Listo"
        else:
            estado = "Falló"
        modelo = movimiento.get("modelo") or "-"
        familia = familias.get(movimiento.get("familia"), movimiento.get("familia") or "-")
        duracion = movimiento.get("duracion_segundos")
        filas.append({
            "Fecha": formatear_fecha_larga(movimiento["fecha_fin"]),
            "Acción": _ACCIONES.get(movimiento["accion"], movimiento["accion"]),
            "Estado": estado,
            "Modelo": modelo,
            "Familia": familia,
            "Versión": movimiento.get("version") or "-",
            "Usuario": movimiento["usuario"],
            "Datos": movimiento.get("rango_datos") or "-",
            "Duración (s)": round(duracion, 1) if duracion else None,
            "Archivo": (movimiento.get("detalle") or {}).get("archivo", ""),
            "Motivo del fallo": movimiento.get("motivo_fallo") or "",
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")

    con_detalle = [movimiento for movimiento in movimientos if movimiento.get("detalle")]
    if not con_detalle:
        return
    with st.expander("Ver el detalle de un movimiento"):
        st.caption(
            "Entrenar: rango e hiperparámetros pedidos. Subir: nombre del .zip. Eliminar: copia del "
            "manifest de la versión eliminada (hiperparámetros, métricas, rango)."
        )
        indice = st.selectbox(
            "Movimiento",
            list(range(len(con_detalle))),
            format_func=lambda posicion: _rotulo_movimiento(con_detalle[posicion]),
            key=f"detalle_movimiento_{patologia}",
        )
        st.json(con_detalle[indice]["detalle"], expanded=1)


def _rotulo_movimiento(movimiento: dict) -> str:
    accion = _ACCIONES.get(movimiento["accion"], movimiento["accion"])
    modelo = movimiento.get("modelo") or "-"
    version = movimiento.get("version") or "sin versión"
    fecha = formatear_fecha_larga(movimiento["fecha_fin"])
    return f"{fecha} · {accion} · {modelo} · {version}"


# ---------------------------------------------------------------------------
# Avisos de trabajos del worker
# ---------------------------------------------------------------------------

def _registrar_pendiente(patologia: str, usuario_nombre: str, fecha_solicitud: str, mensaje: str) -> None:
    pendientes = st.session_state.setdefault(CLAVE_TRABAJOS_PENDIENTES, [])
    pendientes.append({
        "patologia": patologia,
        "usuario": usuario_nombre,
        "fecha_solicitud": fecha_solicitud,
    })
    st.session_state.setdefault(CLAVE_AVISO_ENVIADO, {})[patologia] = mensaje


def verificar_entrenamientos_pendientes(usuario_nombre: str) -> None:
    """Igual que verificar_y_resolver_pendientes de las cargas: si el worker ya
    termino un entrenamiento o una subida que lanzo esta persona, avisa con
    st.toast."""
    pendientes = st.session_state.get(CLAVE_TRABAJOS_PENDIENTES, [])
    propios = [pendiente for pendiente in pendientes if pendiente["usuario"] == usuario_nombre]
    if not propios:
        return

    aun_pendientes = []
    for pendiente in propios:
        resultado = _buscar_resultado(pendiente)
        if resultado is None:
            aun_pendientes.append(pendiente)
            continue
        if resultado["accion"] == ACCION_SUBIR:
            que = "La subida del modelo"
        else:
            que = "El entrenamiento"
        if resultado["estado"] == "listo":
            st.toast(
                f"{que} terminó: versión {resultado['version']} de {resultado['modelo']} guardada.",
                icon=":material/check_circle:",
            )
        else:
            motivo = resultado.get("motivo_fallo") or "motivo desconocido"
            st.toast(f"{que} falló. {motivo}", icon=":material/error:", duration="long")

    otros = [pendiente for pendiente in pendientes if pendiente["usuario"] != usuario_nombre]
    st.session_state[CLAVE_TRABAJOS_PENDIENTES] = aun_pendientes + otros


def _buscar_resultado(pendiente: dict) -> dict | None:
    movimientos = listar_entrenamientos(patologia=pendiente["patologia"], usuario=pendiente["usuario"])
    for movimiento in movimientos:
        if movimiento["accion"] not in ACCIONES_DEL_WORKER:
            continue
        if movimiento.get("fecha_solicitud") == pendiente["fecha_solicitud"]:
            return movimiento
    return None
