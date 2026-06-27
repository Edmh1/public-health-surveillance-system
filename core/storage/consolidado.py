"""Operaciones quirurgicas sobre el Parquet consolidado: agregar, editar y eliminar por anio+codigo.

La consolidada no tiene soft delete; siempre refleja solo lo activo. Cada operacion
reescribe el consolidado completo de forma atomica (ver core/storage/parquet_atomico.py).
"""

from pathlib import Path

import pandas as pd

from core.storage.parquet_atomico import escribir_parquet_atomico


def cargar_consolidado(ruta_consolidado: Path) -> pd.DataFrame | None:
    """Carga el consolidado oficial, o None si todavia no existe (primera pieza de la patologia)."""
    if not ruta_consolidado.exists():
        return None
    consolidado = pd.read_parquet(ruta_consolidado)
    return consolidado


def _quitar_pieza(
    consolidado: pd.DataFrame, columna_anio: str, columna_codigo: str, anio: int, codigo: int
) -> pd.DataFrame:
    es_la_pieza = (consolidado[columna_anio] == anio) & (consolidado[columna_codigo] == codigo)
    consolidado_sin_pieza = consolidado.loc[~es_la_pieza]
    return consolidado_sin_pieza


def actualizar_consolidado(
    ruta_consolidado: Path,
    columna_anio: str,
    columna_codigo: str,
    anio: int,
    codigo: int,
    pieza_nueva: pd.DataFrame | None,
) -> Path:
    """Reemplaza quirurgicamente una pieza (anio+codigo) en el consolidado y lo reescribe de forma atomica.

    Si pieza_nueva tiene datos, se usa para agregar (pieza nueva) o editar (pieza reemplazada).
    Si pieza_nueva es None, la pieza solo se elimina del consolidado.
    """
    consolidado_actual = cargar_consolidado(ruta_consolidado)

    if consolidado_actual is None:
        if pieza_nueva is None:
            raise ValueError("No existe un consolidado todavia y se pidio eliminar una pieza de el")
        consolidado_sin_pieza = pieza_nueva.iloc[0:0]
    else:
        consolidado_sin_pieza = _quitar_pieza(consolidado_actual, columna_anio, columna_codigo, anio, codigo)

    if pieza_nueva is None:
        consolidado_nuevo = consolidado_sin_pieza
    else:
        consolidado_nuevo = pd.concat([consolidado_sin_pieza, pieza_nueva], ignore_index=True)

    columnas_esperadas = set(consolidado_nuevo.columns)
    filas_esperadas = len(consolidado_nuevo)
    escribir_parquet_atomico(consolidado_nuevo, ruta_consolidado, columnas_esperadas, filas_esperadas)
    return ruta_consolidado


def agregar_pieza(
    ruta_consolidado: Path, columna_anio: str, columna_codigo: str, anio: int, codigo: int, pieza_nueva: pd.DataFrame
) -> Path:
    """Agrega una pieza nueva (anio+codigo que todavia no existia) al consolidado."""
    return actualizar_consolidado(ruta_consolidado, columna_anio, columna_codigo, anio, codigo, pieza_nueva)


def editar_pieza(
    ruta_consolidado: Path, columna_anio: str, columna_codigo: str, anio: int, codigo: int, pieza_corregida: pd.DataFrame
) -> Path:
    """Reemplaza una pieza existente (anio+codigo) por su version corregida en el consolidado."""
    return actualizar_consolidado(ruta_consolidado, columna_anio, columna_codigo, anio, codigo, pieza_corregida)


def eliminar_pieza(ruta_consolidado: Path, columna_anio: str, columna_codigo: str, anio: int, codigo: int) -> Path:
    """Quita del consolidado las filas de una pieza (anio+codigo), sin agregar nada en su lugar."""
    return actualizar_consolidado(ruta_consolidado, columna_anio, columna_codigo, anio, codigo, None)
