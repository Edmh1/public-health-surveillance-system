"""Implementacion concreta del contrato PathologyPlugin para dengue."""

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from core.registry import PathologyPlugin
from pathologies.dengue.canal_endemico import calcular_canal_endemico as calcular_canal_endemico_dengue
from pathologies.dengue.clean import limpiar as limpiar_dengue
from pathologies.dengue.geografia import obtener_mapeo_subregion as obtener_mapeo_subregion_dengue
from pathologies.dengue.indicators import calcular_indicadores as calcular_indicadores_dengue
from pathologies.dengue.poblacion import obtener_mapeo_estratificacion_riesgo as obtener_mapeo_estratificacion_riesgo_dengue
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

    def calcular_canal_endemico(
        self,
        datos_procesados: pd.DataFrame,
        metodo: str,
        anio_vigilancia: int,
        anios_base: list[int],
    ) -> dict[str, Any]:
        return calcular_canal_endemico_dengue(datos_procesados, metodo, anio_vigilancia, anios_base)

    def calcular_indicadores(self, datos_filtrados: pd.DataFrame, filtros: dict[str, Any]) -> dict[str, Any]:
        return calcular_indicadores_dengue(datos_filtrados, filtros)

    def obtener_esquema(self) -> dict[str, Any]:
        raise NotImplementedError("obtener_esquema todavia no esta construido")

    def obtener_vistas(self) -> list[Any]:
        return obtener_vistas_dengue()

    def obtener_mapeo_subregion(self) -> dict[int, str]:
        return obtener_mapeo_subregion_dengue()

    def obtener_mapeo_estratificacion_riesgo(self) -> dict[int, str]:
        return obtener_mapeo_estratificacion_riesgo_dengue()
