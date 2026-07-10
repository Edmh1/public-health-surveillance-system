"""Implementacion concreta del contrato PathologyPlugin para tuberculosis."""

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from core.registry import PathologyPlugin
from pathologies.tuberculosis.canal_endemico import calcular_canal_endemico as calcular_canal_endemico_tb
from pathologies.tuberculosis.clean import limpiar as limpiar_tb
from pathologies.tuberculosis.geografia import obtener_mapeo_subregion as obtener_mapeo_subregion_tb
from pathologies.tuberculosis.indicators import calcular_indicadores as calcular_indicadores_tb
from pathologies.tuberculosis.views import obtener_vistas_tb

RUTA_MANIFEST = Path(__file__).parent / "manifest.yaml"


class TuberculosisPathologyPlugin(PathologyPlugin):
    """Plugin de tuberculosis. Tres codigos SIVIGILA: 810 (extrapulmonar),
    820 (pulmonar) y 825 (farmacoresistente).
    """

    @property
    def nombre(self) -> str:
        return "tuberculosis"

    @property
    def codigos_esperados(self) -> set[int]:
        return {810, 820, 825}

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
        return limpiar_tb(datos_crudos)

    def calcular_canal_endemico(
        self,
        datos_procesados: pd.DataFrame,
        metodo: str,
        anio_vigilancia: int,
        anios_base: list[int],
    ) -> dict[str, Any]:
        return calcular_canal_endemico_tb(datos_procesados, metodo, anio_vigilancia, anios_base)

    def calcular_indicadores(self, datos_filtrados: pd.DataFrame, filtros: dict[str, Any]) -> dict[str, Any]:
        return calcular_indicadores_tb(datos_filtrados, filtros)

    def obtener_esquema(self) -> dict[str, Any]:
        raise NotImplementedError("obtener_esquema todavia no esta construido")

    def obtener_vistas(self) -> list[Any]:
        return obtener_vistas_tb()

    def obtener_mapeo_subregion(self) -> dict[int, str]:
        return obtener_mapeo_subregion_tb()
