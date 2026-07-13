"""Subida de una pieza (agregar o editar): formulario con autocompletado desde el
nombre de archivo Datos_ANIO_CODIGO. El procesamiento es sincrono: se ejecuta
directamente en el dashboard con st.spinner, sin cola ni worker.
"""

from pathlib import Path

import streamlit as st

from core.ingestion.cola import procesar_archivo_subido
from core.ingestion.nombres_archivo import NombreArchivoInvalido, analizar_nombre_archivo
from core.audit.registro_piezas import obtener_pieza_activa
from core.storage import rutas

CLAVE_CONTADOR_UPLOADER = "subida_contador_widget_uploader"


def _key_uploader(patologia: str) -> str:
    contador = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER, {}).get(patologia, 0)
    return f"subir_{patologia}_{contador}"


def _limpiar_zona_subida(patologia: str) -> None:
    contadores = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER, {})
    contadores[patologia] = contadores.get(patologia, 0) + 1


def _procesar_archivo(patologia: str, anio: int, codigo: int, nombre_archivo: str, contenido: bytes, usuario) -> str:
    directorio_subidas = rutas.directorio_subidas(patologia)
    directorio_subidas.mkdir(parents=True, exist_ok=True)
    ruta_archivo = directorio_subidas / f"{anio}_{codigo}_{nombre_archivo}"
    ruta_archivo.write_bytes(contenido)

    try:
        procesar_archivo_subido(
            patologia=patologia,
            anio=anio,
            codigo=codigo,
            ruta_archivo=ruta_archivo,
            archivo_original=nombre_archivo,
            usuario=usuario.nombre_usuario,
        )
        ruta_archivo.unlink(missing_ok=True)
        return "ok"
    except Exception as e:
        ruta_archivo.unlink(missing_ok=True)
        return str(e)


def mostrar_banner_confirmacion(patologia: str) -> None:
    pass


def mostrar_formulario_subida(patologia: str, usuario) -> None:
    st.subheader(":material/upload_file: Subir archivo")

    archivos_subidos = st.file_uploader(
        "Archivos SIVIGILA (.xls o .xlsx)",
        type=["xls", "xlsx"],
        key=_key_uploader(patologia),
        accept_multiple_files=True,
    )
    if not archivos_subidos:
        return

    archivos = _analizar_archivos(archivos_subidos)

    if not archivos:
        st.warning("Ninguno de los archivos seleccionados sigue el patrón Datos_ANIO_CODIGO.")
        return

    _mostrar_previa_lote(archivos)

    if st.button("Confirmar y procesar todos", type="primary", icon=":material/check_circle:", key=f"confirmar_lote_{patologia}"):
        with st.spinner("Procesando archivos..."):
            for archivo in archivos:
                anio = archivo["anio"]
                codigo = archivo["codigo"]
                nombre = archivo["nombre"]
                contenido = archivo["contenido"]

                pieza_existente = obtener_pieza_activa(patologia, anio, codigo)
                if pieza_existente is not None:
                    st.toast(f"{nombre}: reemplazando pieza existente {anio}_{codigo}", icon=":material/warning:")

                resultado = _procesar_archivo(patologia, anio, codigo, nombre, contenido, usuario)
                if resultado == "ok":
                    st.toast(f"{nombre}: procesado correctamente.", icon=":material/check_circle:")
                else:
                    st.toast(f"{nombre}: falló — {resultado}", icon=":material/error:")

            st.toast("Procesamiento completado.", icon=":material/done_all:")

        _limpiar_zona_subida(patologia)
        st.rerun()


def _analizar_archivos(archivos_subidos: list) -> list[dict]:
    archivos = []
    for archivo in archivos_subidos:
        try:
            anio, codigo = analizar_nombre_archivo(archivo.name)
        except NombreArchivoInvalido:
            continue
        archivos.append({
            "archivo": archivo,
            "nombre": archivo.name,
            "anio": anio,
            "codigo": codigo,
            "contenido": archivo.getvalue(),
        })
    return archivos


def _mostrar_previa_lote(archivos: list[dict]) -> None:
    st.caption(f"{len(archivos)} archivos detectados:")
    for a in archivos:
        st.text(f"  Datos_{a['anio']}_{a['codigo']}  ←  {a['nombre']}")


def encolar_subida(patologia: str, anio: int, codigo: int, nombre_archivo: str, contenido: bytes, usuario) -> None:
    """Wrapper que procesa sincronamente. Mantiene la firma para compatibilidad
    con gestion_piezas.py (flujo de editar).
    """
    with st.spinner(f"Procesando {nombre_archivo}..."):
        resultado = _procesar_archivo(patologia, anio, codigo, nombre_archivo, contenido, usuario)
        if resultado == "ok":
            st.toast(f"{nombre_archivo}: procesado correctamente.", icon=":material/check_circle:")
        else:
            st.toast(f"{nombre_archivo}: falló — {resultado}", icon=":material/error:")
