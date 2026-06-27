"""Escritura atomica de Parquet con verificacion previa a la promocion.

El archivo nuevo se escribe aparte con nombre temporal, se verifica que se puede
abrir y que tiene las columnas y el numero de filas esperados, y solo entonces
se promueve mediante un cambio de nombre atomico. Si la verificacion falla, el
archivo oficial anterior no se toca.
"""

from pathlib import Path

import pandas as pd


class ParquetVerificationError(Exception):
    """Se lanza cuando el Parquet recien escrito no pasa la verificacion antes de promoverlo."""


def escribir_parquet_atomico(
    dataframe: pd.DataFrame,
    ruta_destino: Path,
    columnas_esperadas: set[str],
    filas_esperadas: int,
) -> Path:
    """Escribe dataframe en ruta_destino de forma atomica, verificando antes de promover."""
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    ruta_temporal = ruta_destino.with_name(ruta_destino.name + ".tmp")

    dataframe.to_parquet(ruta_temporal, index=False)

    try:
        datos_verificacion = pd.read_parquet(ruta_temporal)
    except Exception as error:
        ruta_temporal.unlink()
        raise ParquetVerificationError(f"El Parquet temporal de {ruta_destino.name} no se pudo abrir") from error

    columnas_temporal = set(datos_verificacion.columns)
    if columnas_temporal != columnas_esperadas:
        ruta_temporal.unlink()
        mensaje = (
            f"Columnas inesperadas en {ruta_destino.name}: "
            f"esperaba {sorted(columnas_esperadas)}, obtuvo {sorted(columnas_temporal)}"
        )
        raise ParquetVerificationError(mensaje)

    filas_temporal = len(datos_verificacion)
    if filas_temporal != filas_esperadas:
        ruta_temporal.unlink()
        mensaje = (
            f"Numero de filas inesperado en {ruta_destino.name}: "
            f"esperaba {filas_esperadas}, obtuvo {filas_temporal}"
        )
        raise ParquetVerificationError(mensaje)

    ruta_temporal.replace(ruta_destino)
    return ruta_destino
