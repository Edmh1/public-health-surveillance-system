"""Subida de una pieza (agregar o editar): formulario con autocompletado desde el
nombre de archivo Datos_ANIO_CODIGO, que el usuario debe confirmar antes de
encolar. El worker decide solo si es agregar o editar segun si ya hay una pieza
activa con ese anio+codigo; esta pantalla no necesita saberlo.

El aviso de exito/fallo llega via fragmento_avisos_subida (ver layout.py), que
vive en el nivel raiz de la pagina (fuera de cualquier tab) con posicion estable.
Usa st.toast() para no necesitar renderizar widgets en el contenido del tab,
evitando el problema de fragment_id inestable que causaba pantalla en blanco.
"""

from datetime import datetime, timezone

import streamlit as st

from core.audit.procesamientos import listar_procesamientos
from core.audit.registro_piezas import obtener_pieza_activa
from core.ingestion.cola import encolar_procesamiento
from core.ingestion.nombres_archivo import NombreArchivoInvalido, analizar_nombre_archivo
from core.storage import rutas

CLAVE_SUBIDAS_PENDIENTES = "subidas_pendientes_por_usuario"
CLAVE_CONTADOR_UPLOADER = "subida_contador_widget_uploader"
CLAVE_BANNER_CONFIRMACION = "subida_banner_confirmacion"


def _key_uploader(patologia: str) -> str:
    """Streamlit no tiene un "clear" directo para file_uploader; cambiar su key fuerza
    un widget nuevo y vacio. El contador se sube cada vez que una subida se confirma,
    para que la zona de carga no se quede mostrando el archivo ya enviado.
    """
    contador = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER, {}).get(patologia, 0)
    return f"subir_{patologia}_{contador}"


def _limpiar_zona_subida(patologia: str) -> None:
    contadores = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER, {})
    contadores[patologia] = contadores.get(patologia, 0) + 1


def mostrar_banner_confirmacion(patologia: str) -> None:
    """Banner persistente de "archivo enviado a procesar". Se queda visible hasta
    que el usuario lo cierra con la X. Se llama desde _mostrar_seccion_gestion.
    """
    banners = st.session_state.setdefault(CLAVE_BANNER_CONFIRMACION, {})
    nombre_archivo = banners.get(patologia)
    if not nombre_archivo:
        return

    columna_mensaje, columna_cerrar = st.columns([10, 1])
    with columna_mensaje:
        st.info(f":material/check_circle: {nombre_archivo} se envio a procesar correctamente.")
    with columna_cerrar:
        if st.button("", icon=":material/close:", help="Cerrar este aviso", key=f"cerrar_banner_subida_{patologia}"):
            banners.pop(patologia, None)
            st.rerun()


def mostrar_formulario_subida(patologia: str, usuario) -> None:
    st.subheader(":material/upload_file: Subir archivo")

    archivo_subido = st.file_uploader(
        "Archivo SIVIGILA (.xls o .xlsx)", type=["xls", "xlsx"], key=_key_uploader(patologia)
    )
    if archivo_subido is None:
        return

    anio_sugerido = None
    codigo_sugerido = None
    try:
        anio_sugerido, codigo_sugerido = analizar_nombre_archivo(archivo_subido.name)
    except NombreArchivoInvalido:
        st.warning(
            "El nombre del archivo no sigue el patrón Datos_ANIO_CODIGO. "
            "Completa año y código manualmente antes de confirmar."
        )

    with st.form(f"confirmar_subida_{patologia}"):
        st.caption("Confirma año y código antes de procesar (red de seguridad contra archivos mal nombrados).")
        anio = st.number_input("Año", min_value=2000, max_value=2100, value=anio_sugerido or 2024, step=1)
        codigo = st.number_input("Código", min_value=0, value=codigo_sugerido or 0, step=1)
        confirmado = st.form_submit_button("Confirmar y procesar", type="primary", icon=":material/check_circle:")

    if not confirmado:
        return

    pieza_existente = obtener_pieza_activa(patologia, int(anio), int(codigo))
    if pieza_existente is not None:
        _dialogo_confirmar_reemplazo(
            patologia,
            int(anio),
            int(codigo),
            archivo_subido.name,
            archivo_subido.getvalue(),
            pieza_existente["archivo_original"],
            usuario,
        )
        return

    encolar_subida(patologia, int(anio), int(codigo), archivo_subido.name, archivo_subido.getvalue(), usuario)
    _limpiar_zona_subida(patologia)
    st.rerun()


@st.dialog("Ya existe una pieza para ese año y código")
def _dialogo_confirmar_reemplazo(
    patologia: str,
    anio: int,
    codigo: int,
    nombre_archivo: str,
    contenido: bytes,
    archivo_anterior: str,
    usuario,
) -> None:
    st.warning(
        f":material/warning: Ya hay una pieza activa para año {anio}, código {codigo} "
        f"(archivo {archivo_anterior}). Si confirmas, el sistema reemplaza esa pieza por "
        f"{nombre_archivo}, igual que si hubieras usado Editar en piezas activas."
    )
    st.caption("Si te equivocaste de año o código, cancela y corrige antes de subir de nuevo.")

    columna_cancelar, columna_confirmar = st.columns(2)
    with columna_cancelar:
        if st.button("Cancelar", width="stretch", key=f"cancelar_reemplazo_{patologia}"):
            st.rerun()
    with columna_confirmar:
        if st.button(
            "Si, reemplazar",
            type="primary",
            icon=":material/check_circle:",
            width="stretch",
            key=f"confirmar_reemplazo_{patologia}",
        ):
            encolar_subida(patologia, anio, codigo, nombre_archivo, contenido, usuario)
            _limpiar_zona_subida(patologia)
            st.rerun()


def encolar_subida(patologia: str, anio: int, codigo: int, nombre_archivo: str, contenido: bytes, usuario) -> None:
    """Encola un archivo para procesar. La usan el formulario de subida y el flujo de
    editar desde piezas activas (ver gestion_piezas.py).
    """
    directorio_subidas = rutas.directorio_subidas(patologia)
    directorio_subidas.mkdir(parents=True, exist_ok=True)
    ruta_archivo = directorio_subidas / f"{anio}_{codigo}_{nombre_archivo}"
    ruta_archivo.write_bytes(contenido)

    momento_envio = datetime.now(timezone.utc).isoformat()
    encolar_procesamiento(
        patologia=patologia,
        anio=anio,
        codigo=codigo,
        ruta_archivo=ruta_archivo,
        archivo_original=nombre_archivo,
        usuario=usuario.nombre_usuario,
    )

    pendientes = st.session_state.setdefault(CLAVE_SUBIDAS_PENDIENTES, [])
    pendientes.append(
        {
            "patologia": patologia,
            "anio": anio,
            "codigo": codigo,
            "usuario": usuario.nombre_usuario,
            "momento_envio": momento_envio,
        }
    )

    st.session_state.setdefault(CLAVE_BANNER_CONFIRMACION, {})[patologia] = nombre_archivo


def _buscar_resultado(pendiente: dict) -> dict | None:
    procesamientos = listar_procesamientos(patologia=pendiente["patologia"], usuario=pendiente["usuario"])
    for procesamiento in procesamientos:
        coincide_pieza = (
            procesamiento["anio"] == pendiente["anio"]
            and procesamiento["codigo"] == pendiente["codigo"]
        )
        es_posterior_al_envio = procesamiento["fecha"] >= pendiente["momento_envio"]
        if coincide_pieza and es_posterior_al_envio:
            return procesamiento
    return None


def _notificar_resultado(pendiente: dict, resultado: dict) -> None:
    """Notifica el resultado via st.toast(), visible desde cualquier tab."""
    descripcion = f"Datos_{pendiente['anio']}_{pendiente['codigo']}"
    if resultado["estado"] == "listo":
        st.toast(f"{descripcion}: procesado correctamente.", icon=":material/check_circle:")
    else:
        motivo = resultado.get("motivo_fallo") or "motivo desconocido"
        st.toast(f"{descripcion}: fallo. {motivo}", icon=":material/error:", duration="long")


def verificar_y_resolver_pendientes(usuario_nombre: str) -> None:
    """Comprueba si el worker termino con alguna subida pendiente de este usuario.
    Emite st.toast() con el resultado y elimina la entrada de la lista.
    No es un fragmento: se invoca desde fragmento_avisos_subida (nivel raiz, posicion
    estable), que es quien tiene el run_every.
    """
    pendientes = st.session_state.get(CLAVE_SUBIDAS_PENDIENTES, [])
    propias = [p for p in pendientes if p["usuario"] == usuario_nombre]
    if not propias:
        return

    aun_pendientes = []
    for pendiente in propias:
        resultado = _buscar_resultado(pendiente)
        if resultado is None:
            aun_pendientes.append(pendiente)
            continue
        _notificar_resultado(pendiente, resultado)

    otros = [p for p in pendientes if p["usuario"] != usuario_nombre]
    st.session_state[CLAVE_SUBIDAS_PENDIENTES] = aun_pendientes + otros


@st.fragment(run_every="4s")
def fragmento_avisos_subida(usuario_nombre: str) -> None:
    """Fragmento de polling en posicion estable al nivel de pagina (fuera de tabs).
    Su fragment_id nunca cambia porque no hay widgets condicionales antes de el
    en el flujo principal de ejecutar_dashboard(). Cuando el worker termina,
    notifica al usuario via st.toast() sin renderizar nada en el arbol de la pagina.
    """
    verificar_y_resolver_pendientes(usuario_nombre)
