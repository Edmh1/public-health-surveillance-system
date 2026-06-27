"""Implementacion concreta del contrato PathologyPlugin para dengue."""

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from core.registry import PathologyPlugin
from pathologies.dengue.clean import limpiar as limpiar_dengue
from pathologies.dengue.views import obtener_vistas_dengue

RUTA_MANIFEST = Path(__file__).parent / "manifest.yaml"


class DenguePathologyPlugin(PathologyPlugin):
    """Plugin de dengue. Limpieza ya construida; indicadores, transformaciones y vistas
    quedan con TODO explicito hasta que se construyan (ver CLAUDE.md).
    """

    @property
    def nombre(self) -> str:
        return "dengue"

    @property
    def codigos_esperados(self) -> set[int]:
        return {210, 220, 580}

    @property
    def columna_anio(self) -> str:
        return "ano"

    @property
    def columna_codigo(self) -> str:
        return "cod_eve"

    @property
    def manifest(self) -> dict[str, Any]:
        with open(RUTA_MANIFEST, encoding="utf-8") as archivo_manifest:
            contenido_manifest = yaml.safe_load(archivo_manifest)
        return contenido_manifest or {}

    def limpiar(self, datos_crudos: pd.DataFrame) -> pd.DataFrame:
        return limpiar_dengue(datos_crudos)

    def calcular_canal_endemico(self, datos_procesados: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("calcular_canal_endemico todavia no esta construido")

    def calcular_indicadores(self, datos_consolidados: pd.DataFrame, filtros: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "calcular_indicadores (incidencia, mortalidad, letalidad, letalidad grave, "
            "% confirmados grave, % hospitalizados) todavia no esta construido"
        )

    def obtener_esquema(self) -> dict[str, Any]:
        raise NotImplementedError("obtener_esquema todavia no esta construido")

    def obtener_vistas(self) -> list[Any]:
        return obtener_vistas_dengue()
