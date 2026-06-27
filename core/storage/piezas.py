"""Lectura y escritura de piezas individuales: un Parquet por patologia+anio+codigo."""

from pathlib import Path

import pandas as pd

from core.storage.parquet_atomico import escribir_parquet_atomico


def ruta_pieza(directorio_piezas: Path, anio: int, codigo: int) -> Path:
    """Ruta del Parquet de una pieza dentro del directorio de piezas de la patologia."""
    return directorio_piezas / f"{anio}_{codigo}.parquet"


def guardar_pieza(directorio_piezas: Path, anio: int, codigo: int, dataframe: pd.DataFrame) -> Path:
    """Guarda el dataframe procesado de una pieza como Parquet, de forma atomica."""
    destino = ruta_pieza(directorio_piezas, anio, codigo)
    columnas_esperadas = set(dataframe.columns)
    filas_esperadas = len(dataframe)
    escribir_parquet_atomico(dataframe, destino, columnas_esperadas, filas_esperadas)
    return destino


def leer_pieza(directorio_piezas: Path, anio: int, codigo: int) -> pd.DataFrame:
    """Lee el Parquet de una pieza existente."""
    origen = ruta_pieza(directorio_piezas, anio, codigo)
    datos_pieza = pd.read_parquet(origen)
    return datos_pieza
