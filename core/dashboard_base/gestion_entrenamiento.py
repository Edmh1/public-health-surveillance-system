"""Apartado de Gestion para reentrenar el pronostico. Solo perfil de
administracion (PERMISO_REENTRENAR_PRONOSTICO) y solo para patologias cuyo
plugin declara un modulo de pronostico (PathologyPlugin.obtener_pronostico).

El modelo ya no se entrena solo dentro de la pestana: el equipo del CITES
decide cuando reentrenar, queda registrado quien lo hizo y con que datos, y se
puede volver a una version anterior. El entrenamiento corre en el worker (misma
cola que las cargas, ver core/ingestion/entrenamiento.py) y el aviso de
terminado llega igual que el de una carga: st.toast desde el fragmento raiz de
avisos (ver gestion_subida.fragmento_avisos_subida).
"""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from core.audit.entrenamientos import listar_entrenamientos, registrar_activacion
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.seleccion_cruzada import recargar_seccion
from core.ingestion.entrenamiento import describir_rango, encolar_entrenamiento
from core.registry import obtener_patologia
from core.storage import modelos

CLAVE_ENTRENAMIENTOS_PENDIENTES = "entrenamientos_pendientes_por_usuario"
CLAVE_AVISO_ENVIADO = "entrenamiento_aviso_enviado"

NOMBRE_PERSISTENCIA = "Persistencia (línea base)"

_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def formatear_fecha_larga(fecha_iso: str) -> str:
    """'12 de noviembre de 2026' a partir de una fecha ISO."""
    fecha = datetime.fromisoformat(fecha_iso)
    return f"{fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"


def tabla_metricas(manifest: dict) -> pd.DataFrame:
    """Tabla larga de error por modelo y horizonte, a partir del manifest."""
    nombres = dict(manifest.get("modelos", {}))
    nombres["persistencia"] = NOMBRE_PERSISTENCIA
    filas = []
    for clave_modelo, por_horizonte in manifest.get("metricas", {}).items():
        for horizonte, metricas in por_horizonte.items():
            filas.append({
                "Modelo": nombres.get(clave_modelo, clave_modelo),
                "Horizonte (semanas)": int(horizonte),
                "RMSE": metricas.get("RMSE"),
                "MAE": metricas.get("MAE"),
                "MAPE (%)": metricas.get("MAPE"),
                "R²": metricas.get("R2"),
            })
    return pd.DataFrame(filas)


def mostrar_reentrenamiento(patologia: str, usuario) -> None:
    st.subheader(":material/model_training: Reentrenamiento del pronóstico")
    st.caption(
        "Solo perfil de administración. Reentrenar cambia lo que el tablero pronostica para "
        "todas las personas: entrena los modelos con todo el histórico cargado, corre la "
        "validación walk-forward (error por horizonte de 1 a 6 semanas) y deja la versión nueva "
        "como activa. Las versiones anteriores se conservan y se puede volver a cualquiera."
    )

    _mostrar_aviso_enviado(patologia)
    _mostrar_estado_actual(patologia)

    st.space("small")
    if st.button(
        "Reentrenar con el histórico cargado",
        icon=":material/model_training:",
        type="primary",
        key=f"reentrenar_{patologia}",
    ):
        dialogo_confirmar_reentrenamiento(patologia, usuario)

    st.divider()
    _mostrar_versiones(patologia, usuario)

    st.divider()
    _mostrar_historial(patologia)


def _mostrar_aviso_enviado(patologia: str) -> None:
    avisos = st.session_state.setdefault(CLAVE_AVISO_ENVIADO, {})
    if not avisos.get(patologia):
        return
    columna_mensaje, columna_cerrar = st.columns([10, 1])
    with columna_mensaje:
        st.info(
            ":material/hourglass_top: Reentrenamiento enviado al procesador. Te avisamos cuando "
            "termine; el resultado queda también en el historial de abajo."
        )
    with columna_cerrar:
        if st.button("", icon=":material/close:", help="Cerrar este aviso", key=f"cerrar_aviso_entrenamiento_{patologia}"):
            avisos.pop(patologia, None)
            recargar_seccion()


def _fin_del_consolidado(patologia: str) -> tuple[int, int] | None:
    """Ultimo anio y semana del consolidado cargado en la sesion."""
    try:
        datos = modulo_datos.obtener_datos(patologia)
    except KeyError:
        return None
    plugin = obtener_patologia(patologia)
    columna_anio = plugin.columna_anio
    if datos.empty or columna_anio not in datos.columns or "semana" not in datos.columns:
        return None
    anio_maximo = int(datos[columna_anio].max())
    semana_maxima = int(datos.loc[datos[columna_anio] == anio_maximo, "semana"].max())
    return anio_maximo, semana_maxima


def _mostrar_estado_actual(patologia: str) -> None:
    version = modelos.version_activa(patologia)
    fin_consolidado = _fin_del_consolidado(patologia)

    if version is None:
        st.warning(
            "Todavía no hay ningún modelo entrenado: la pestaña Pronóstico no puede mostrar el "
            "pronóstico en vivo hasta que se entrene el primero.",
            icon=":material/warning:",
        )
        return

    manifest = modelos.leer_manifest(patologia, version) or {}
    rango = manifest.get("rango", {})
    texto_rango = describir_rango(rango) if rango else "rango desconocido"
    st.markdown(
        f":material/check_circle: Versión activa: entrenada el "
        f"{formatear_fecha_larga(manifest['fecha_entrenamiento'])} por {manifest.get('usuario', '-')}, "
        f"con datos de {texto_rango} ({manifest.get('semanas', '-')} semanas)."
    )
    if fin_consolidado is not None and rango:
        fin_modelo = (rango["anio_fin"], rango["semana_fin"])
        if fin_consolidado > fin_modelo:
            st.warning(
                f"El consolidado cargado llega hasta {fin_consolidado[0]} (sem. {fin_consolidado[1]}), "
                f"más reciente que los datos del modelo activo. Conviene reentrenar.",
                icon=":material/update:",
            )

    tabla = tabla_metricas(manifest)
    if not tabla.empty:
        with st.expander("Error por horizonte de la versión activa (validación walk-forward del sistema)"):
            st.dataframe(tabla, hide_index=True, width="stretch")


@st.dialog("Reentrenar el pronóstico")
def dialogo_confirmar_reentrenamiento(patologia: str, usuario) -> None:
    """Confirmacion explicita antes de encolar. Tambien la abre la pestana
    Pronostico cuando avisa que el modelo quedo desactualizado."""
    st.markdown(
        "Se entrenan los modelos con todo el histórico cargado, se calcula su error por "
        "horizonte y la versión nueva queda activa para todas las personas. La versión actual "
        "se conserva y se puede volver a ella desde Gestión."
    )
    st.caption("Tarda unos minutos y corre en segundo plano: puedes seguir usando el tablero.")
    columna_cancelar, columna_confirmar = st.columns(2)
    with columna_cancelar:
        if st.button("Cancelar", width="stretch", key=f"cancelar_reentrenar_{patologia}"):
            st.rerun()
    with columna_confirmar:
        if st.button(
            "Sí, reentrenar",
            type="primary",
            icon=":material/model_training:",
            width="stretch",
            key=f"confirmar_reentrenar_{patologia}",
        ):
            enviado = lanzar_reentrenamiento(patologia, usuario)
            if enviado:
                st.rerun()


def lanzar_reentrenamiento(patologia: str, usuario) -> bool:
    fecha_solicitud = datetime.now(timezone.utc).isoformat()
    try:
        encolar_entrenamiento(patologia, usuario.nombre_usuario, fecha_solicitud)
    except Exception as error:
        st.error(f"No se pudo enviar el reentrenamiento a la cola de trabajos: {error}")
        return False

    pendientes = st.session_state.setdefault(CLAVE_ENTRENAMIENTOS_PENDIENTES, [])
    pendientes.append({
        "patologia": patologia,
        "usuario": usuario.nombre_usuario,
        "fecha_solicitud": fecha_solicitud,
    })
    st.session_state.setdefault(CLAVE_AVISO_ENVIADO, {})[patologia] = True
    return True


def _mostrar_versiones(patologia: str, usuario) -> None:
    st.markdown("#### :material/history: Versiones")
    versiones = modelos.listar_versiones(patologia)
    if not versiones:
        st.caption("Sin versiones todavía.")
        return

    activa = modelos.version_activa(patologia)
    filas = []
    for version in versiones:
        manifest = modelos.leer_manifest(patologia, version) or {}
        rango = manifest.get("rango", {})
        filas.append({
            "Versión": version,
            "Activa": "Sí" if version == activa else "",
            "Entrenada el": formatear_fecha_larga(manifest["fecha_entrenamiento"]) if manifest.get("fecha_entrenamiento") else "-",
            "Por": manifest.get("usuario", "-"),
            "Datos": describir_rango(rango) if rango else "-",
            "Semanas": manifest.get("semanas"),
            "Código": manifest.get("version_codigo", "-"),
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")

    anteriores = [version for version in versiones if version != activa]
    if not anteriores:
        return
    columna_selector, columna_boton = st.columns([3, 1.4], vertical_alignment="bottom")
    with columna_selector:
        version_elegida = st.selectbox(
            "Volver a una versión anterior",
            anteriores,
            key=f"version_a_activar_{patologia}",
        )
    with columna_boton:
        if st.button("Usar esta versión", icon=":material/restore:", width="stretch", key=f"activar_version_{patologia}"):
            dialogo_confirmar_activacion(patologia, version_elegida, usuario)


@st.dialog("Cambiar la versión activa del pronóstico")
def dialogo_confirmar_activacion(patologia: str, version: str, usuario) -> None:
    manifest = modelos.leer_manifest(patologia, version) or {}
    rango = manifest.get("rango", {})
    st.markdown(
        f"La pestaña Pronóstico pasará a usar la versión {version}, entrenada con datos de "
        f"{describir_rango(rango) if rango else 'rango desconocido'}, para todas las personas."
    )
    columna_cancelar, columna_confirmar = st.columns(2)
    with columna_cancelar:
        if st.button("Cancelar", width="stretch", key=f"cancelar_activar_{patologia}"):
            st.rerun()
    with columna_confirmar:
        if st.button("Sí, usar esta versión", type="primary", width="stretch", key=f"confirmar_activar_{patologia}"):
            modelos.activar_version(patologia, version, usuario.nombre_usuario)
            registrar_activacion(
                patologia,
                version,
                usuario.nombre_usuario,
                datetime.now(timezone.utc).isoformat(),
                describir_rango(rango) if rango else None,
            )
            st.rerun()


def _mostrar_historial(patologia: str) -> None:
    st.markdown("#### :material/receipt_long: Historial de reentrenamientos")
    movimientos = listar_entrenamientos(patologia)
    if not movimientos:
        st.caption("Todavía no hay reentrenamientos registrados.")
        return
    filas = []
    for movimiento in movimientos:
        if movimiento["accion"] == "activar":
            accion = "Cambio de versión activa"
        else:
            accion = "Reentrenamiento"
        if movimiento["estado"] == "listo":
            estado = "Listo"
        else:
            estado = "Falló"
        duracion = movimiento.get("duracion_segundos")
        filas.append({
            "Fecha": formatear_fecha_larga(movimiento["fecha_fin"]),
            "Acción": accion,
            "Estado": estado,
            "Usuario": movimiento["usuario"],
            "Datos": movimiento.get("rango_datos") or "-",
            "Duración (s)": round(duracion, 1) if duracion else None,
            "Versión": movimiento.get("version") or "-",
            "Motivo del fallo": movimiento.get("motivo_fallo") or "",
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")


def verificar_entrenamientos_pendientes(usuario_nombre: str) -> None:
    """Igual que verificar_y_resolver_pendientes de las cargas: si el worker ya
    termino un reentrenamiento que lanzo esta persona, avisa con st.toast."""
    pendientes = st.session_state.get(CLAVE_ENTRENAMIENTOS_PENDIENTES, [])
    propios = [pendiente for pendiente in pendientes if pendiente["usuario"] == usuario_nombre]
    if not propios:
        return

    aun_pendientes = []
    for pendiente in propios:
        resultado = _buscar_resultado(pendiente)
        if resultado is None:
            aun_pendientes.append(pendiente)
            continue
        if resultado["estado"] == "listo":
            st.toast(
                f"Pronóstico reentrenado: versión {resultado['version']} activa.",
                icon=":material/check_circle:",
            )
        else:
            motivo = resultado.get("motivo_fallo") or "motivo desconocido"
            st.toast(f"El reentrenamiento falló. {motivo}", icon=":material/error:", duration="long")

    otros = [pendiente for pendiente in pendientes if pendiente["usuario"] != usuario_nombre]
    st.session_state[CLAVE_ENTRENAMIENTOS_PENDIENTES] = aun_pendientes + otros


def _buscar_resultado(pendiente: dict) -> dict | None:
    movimientos = listar_entrenamientos(patologia=pendiente["patologia"], usuario=pendiente["usuario"])
    for movimiento in movimientos:
        if movimiento["accion"] != "entrenar":
            continue
        if movimiento.get("fecha_solicitud") == pendiente["fecha_solicitud"]:
            return movimiento
    return None
