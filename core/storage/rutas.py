"""Convencion de rutas de datos por patologia: data/<patologia>/{piezas,consolidado,papelera}."""

from pathlib import Path

DIR_DATA = Path(__file__).resolve().parents[2] / "data"


def directorio_piezas(patologia: str) -> Path:
    return DIR_DATA / patologia / "piezas"


def directorio_papelera(patologia: str) -> Path:
    return DIR_DATA / patologia / "papelera"


def ruta_consolidado(patologia: str) -> Path:
    return DIR_DATA / patologia / "consolidado" / f"{patologia}_consolidado.parquet"
