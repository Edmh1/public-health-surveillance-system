"""Subida de una pieza (agregar o editar): formulario con autocompletado desde el
nombre de archivo Datos_ANIO_CODIGO, que el usuario debe confirmar antes de
encolar. El worker decide solo si es agregar o editar segun si ya hay una pieza
activa con ese anio+codigo; esta pantalla no necesita saberlo.

El aviso de exito/fallo es SOLO para quien subio (CLAUDE.md): se vigila con un
fragmento que consulta Procesamientos cada pocos segundos hasta que aparece el
resultado de esta subida especifica.
"""

from datetime import datetime, timezone

import streamlit as st

from core.audit.procesamientos import listar_procesamientos
from core.ingestion.cola import encolar_procesamiento
from core.ingestion.nombres_archivo import NombreArchivoInvalido, analizar_nombre_archivo
from core.storage import rutas

CLAVE_SUBIDAS_PENDIENTES = "subidas_pendientes_por_usuario"


def mostrar_formulario_subida(patologia: str, usuario) -> None:
    st.subheader("Subir archivo")

    archivo_subido = st.file_uploader(
        "Archivo SIVIGILA (.xls o .xlsx)", type=["xls", "xlsx"], key=f"subir_{patologia}"
    )
    if archivo_subido is None:
        return

    anio_sugerido = None
    codigo_sugerido = None
    try:
        anio_sugerido, codigo_sugerido = analizar_nombre_archivo(archivo_subido.name)
    except NombreArchivoInvalido:
        st.warning(
            "El nombre del archivo no sigue el patron Datos_ANIO_CODIGO. "
            "Completa anio y codigo manualmente antes de confirmar."
        )

    with st.form(f"confirmar_subida_{patologia}"):
        st.caption("Confirma anio y codigo antes de procesar (red de seguridad contra archivos mal nombrados).")
        anio = st.number_input("Anio", min_value=2000, max_value=2100, value=anio_sugerido or 2024, step=1)
        codigo = st.number_input("Codigo", min_value=0, value=codigo_sugerido or 0, step=1)
        confirmado = st.form_submit_button("Confirmar y procesar")

    if not confirmado:
        return

    _encolar_subida(patologia, int(anio), int(codigo), archivo_subido, usuario)


def _encolar_subida(patologia: str, anio: int, codigo: int, archivo_subido, usuario) -> None:
    directorio_subidas = rutas.directorio_subidas(patologia)
    directorio_subidas.mkdir(parents=True, exist_ok=True)
    ruta_archivo = directorio_subidas / f"{anio}_{codigo}_{archivo_subido.name}"
    ruta_archivo.write_bytes(archivo_subido.getvalue())

    momento_envio = datetime.now(timezone.utc).isoformat()
    encolar_procesamiento(
        patologia=patologia,
        anio=anio,
        codigo=codigo,
        ruta_archivo=ruta_archivo,
        archivo_original=archivo_subido.name,
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

    st.success(f"{archivo_subido.name} encolado. El resultado aparece abajo en unos segundos.")


@st.fragment(run_every="4s")
def fragmento_subidas_pendientes(usuario_nombre: str) -> None:
    """Avisa SOLO a quien subio el archivo, cuando el worker termine de procesarlo."""
    pendientes = st.session_state.get(CLAVE_SUBIDAS_PENDIENTES, [])
    pendientes_propias = [p for p in pendientes if p["usuario"] == usuario_nombre]
    if not pendientes_propias:
        return

    aun_pendientes = []
    for pendiente in pendientes_propias:
        resultado = _buscar_resultado(pendiente)
        if resultado is None:
            aun_pendientes.append(pendiente)
            continue
        _mostrar_resultado(pendiente, resultado)

    pendientes_de_otros = [p for p in pendientes if p["usuario"] != usuario_nombre]
    st.session_state[CLAVE_SUBIDAS_PENDIENTES] = aun_pendientes + pendientes_de_otros


def _buscar_resultado(pendiente: dict) -> dict | None:
    procesamientos = listar_procesamientos(patologia=pendiente["patologia"], usuario=pendiente["usuario"])
    for procesamiento in procesamientos:
        coincide_pieza = procesamiento["anio"] == pendiente["anio"] and procesamiento["codigo"] == pendiente["codigo"]
        es_posterior_al_envio = procesamiento["fecha"] >= pendiente["momento_envio"]
        if coincide_pieza and es_posterior_al_envio:
            return procesamiento
    return None


def _mostrar_resultado(pendiente: dict, resultado: dict) -> None:
    descripcion = f"Datos_{pendiente['anio']}_{pendiente['codigo']}"
    if resultado["estado"] == "listo":
        st.success(f"{descripcion}: procesado correctamente.")
    else:
        st.error(f"{descripcion}: fallo. Motivo: {resultado['motivo_fallo']}")
