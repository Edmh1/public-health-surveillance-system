"""Analisis del nombre de archivo del portal SIVIGILA: Datos_ANIO_CODIGO.xls/.xlsx.

Solo sugiere anio y codigo para autocompletar el formulario de subida; el usuario
debe confirmarlos antes de que el archivo se encole, como red de seguridad contra
archivos mal nombrados.
"""

import re
from pathlib import Path

PATRON_NOMBRE_ARCHIVO = re.compile(r"^Datos_(\d{4})_(\d+)\.(xls|xlsx)$", re.IGNORECASE)


class NombreArchivoInvalido(Exception):
    """El nombre del archivo no sigue el patron Datos_ANIO_CODIGO del portal SIVIGILA."""


def analizar_nombre_archivo(nombre_archivo: str) -> tuple[int, int]:
    """Extrae (anio, codigo) del nombre de archivo, ej. Datos_2024_580.xls -> (2024, 580)."""
    coincidencia = PATRON_NOMBRE_ARCHIVO.match(Path(nombre_archivo).name)
    if coincidencia is None:
        mensaje = f"El nombre '{nombre_archivo}' no sigue el patron Datos_ANIO_CODIGO esperado"
        raise NombreArchivoInvalido(mensaje)

    anio = int(coincidencia.group(1))
    codigo = int(coincidencia.group(2))
    return anio, codigo
