"""Procesamiento de piezas: wrapper sincrono que llama a procesar_pieza
directamente, sin cola Redis ni worker. El procesamiento ocurre en el mismo
hilo del dashboard con un spinner/st.toast.
"""

from pathlib import Path

from core.ingestion.procesador import procesar_pieza


def procesar_archivo_subido(
    patologia: str,
    anio: int,
    codigo: int,
    ruta_archivo: Path,
    archivo_original: str,
    usuario: str,
) -> None:
    """Procesa una pieza de forma sincrona, directamente en el dashboard."""
    procesar_pieza(
        patologia=patologia,
        anio=anio,
        codigo=codigo,
        ruta_archivo=ruta_archivo,
        archivo_original=archivo_original,
        usuario=usuario,
    )
