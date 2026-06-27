"""Registro de patologias: sistema de plugins que descubre e indexa cada patologia disponible."""

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class PathologyPlugin(ABC):
    """Contrato que debe implementar cada patologia para integrarse al sistema sin modificar core/."""

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Nombre de la patologia, tal como aparece en el selector del dashboard."""

    @property
    @abstractmethod
    def codigos_esperados(self) -> set[int]:
        """Codigos que la patologia espera encontrar en las piezas que se le suben."""

    @property
    @abstractmethod
    def columna_anio(self) -> str:
        """Nombre de la columna del dato procesado que identifica el anio de la pieza."""

    @property
    @abstractmethod
    def columna_codigo(self) -> str:
        """Nombre de la columna del dato procesado que identifica el codigo de la pieza."""

    @property
    @abstractmethod
    def manifest(self) -> dict[str, Any]:
        """Contenido del manifest.yaml: nombre, codigos esperados, rutas y columnas esperadas."""

    @abstractmethod
    def limpiar(self, datos_crudos: pd.DataFrame) -> pd.DataFrame:
        """Limpia una pieza recien leida del Excel y devuelve el dataframe procesado."""

    @abstractmethod
    def transformar(self, datos_procesados: pd.DataFrame) -> pd.DataFrame:
        """Calcula transformaciones derivadas de la pieza procesada, como canal endemico e incidencia."""

    @abstractmethod
    def calcular_indicadores(self, datos_consolidados: pd.DataFrame, filtros: dict[str, Any]) -> dict[str, Any]:
        """Calcula los KPIs de la patologia sobre el consolidado filtrado.

        Si falta una pieza necesaria para un indicador, ese indicador debe quedar marcado
        como no disponible, nunca en cero.
        """

    @abstractmethod
    def obtener_esquema(self) -> dict[str, Any]:
        """Devuelve el esquema estable y documentado de los datos procesados de la patologia."""

    @abstractmethod
    def obtener_vistas(self) -> list[Any]:
        """Devuelve las pestanas y graficos que la patologia expone al dashboard."""


_PATOLOGIAS_REGISTRADAS: dict[str, PathologyPlugin] = {}


def registrar_patologia(plugin: PathologyPlugin) -> None:
    """Registra un plugin de patologia bajo su nombre, para que el resto del sistema lo use por nombre."""
    _PATOLOGIAS_REGISTRADAS[plugin.nombre] = plugin


def obtener_patologia(nombre: str) -> PathologyPlugin:
    """Devuelve el plugin registrado para una patologia, o lanza KeyError si no esta registrada."""
    if nombre not in _PATOLOGIAS_REGISTRADAS:
        raise KeyError(f"Patologia no registrada: {nombre}")
    return _PATOLOGIAS_REGISTRADAS[nombre]


def listar_patologias() -> list[str]:
    """Lista los nombres de las patologias registradas."""
    return sorted(_PATOLOGIAS_REGISTRADAS.keys())
