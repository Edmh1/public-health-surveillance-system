"""Registro de patologias: sistema de plugins que descubre e indexa cada patologia disponible."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd


class ModuloPronostico(ABC):
    """Contrato del pronostico de una patologia que lo tenga. El nucleo lo usa
    para el reentrenamiento que lanza el perfil de administracion desde Gestion
    (core/ingestion/entrenamiento.py) sin saber que modelos hay detras.

    entrenar_y_exportar entrena con el consolidado completo, valida y escribe
    los modelos en carpeta, junto con un manifest.json. El nucleo lee del
    manifest estos campos, que toda implementacion debe incluir:
      - fecha_entrenamiento (ISO 8601, UTC) y usuario
      - rango: {"anio_inicio", "semana_inicio", "anio_fin", "semana_fin",
        "fecha_ultima_semana"} de los datos usados
      - semanas: cantidad de semanas de la serie de entrenamiento
      - modelos: {clave: rotulo legible}
      - metricas: {clave_modelo: {"1": {"RMSE", "MAE", "MAPE", "R2"}, ...}}
    Puede agregar los campos propios que necesite (hiperparametros, etc.).
    Si no se puede entrenar (ej. historico insuficiente), lanza una excepcion
    con un mensaje legible: el nucleo lo registra como fallo y no toca la
    version activa.
    """

    @abstractmethod
    def entrenar_y_exportar(self, datos: pd.DataFrame, carpeta: Path, usuario: str) -> dict[str, Any]:
        """Entrena, valida y exporta los modelos en carpeta. Devuelve el manifest."""


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
    def calcular_canal_endemico(
        self,
        datos_procesados: pd.DataFrame,
        metodo: str,
        anio_vigilancia: int,
        anios_base: list[int],
    ) -> dict[str, Any]:
        """Calcula el canal endemico: percentiles historicos de casos por semana
        epidemiologica (metodo Bortman o cuartiles), para comparar el anio de
        vigilancia contra el historial. Tiene logica propia (no es un cociente simple
        como los KPIs de calcular_indicadores) y no depende de poblacion en riesgo.

        datos_procesados ya viene acotado a un solo territorio (una subregion o un
        municipio): la escala geografica es decision de quien llama, no de este
        calculo. anios_base es la lista explicita de anios que entran a la linea
        base historica, elegida por quien llama (tipicamente un selector en la
        vista, con todos los anios disponibles preseleccionados); este metodo
        nunca decide por su cuenta que anio incluir o excluir, salvo una garantia
        de correccion: la implementacion descarta cualquier anio de anios_base
        que no sea estrictamente anterior a anio_vigilancia (el canal compara el
        presente contra el pasado, nunca contra el futuro).

        Devuelve un diccionario con las bandas por semana (inferior, central,
        superior), la serie del anio de vigilancia ya clasificada por zona, los
        anios que quedaron en la linea base y el metodo usado.
        """

    @abstractmethod
    def calcular_indicadores(self, datos_filtrados: pd.DataFrame, filtros: dict[str, Any]) -> dict[str, Any]:
        """Calcula los KPIs de la patologia: cocientes simples como incidencia,
        mortalidad, letalidad, letalidad grave, % de casos confirmados graves o %
        de hospitalizados.

        datos_filtrados ya paso por aplicar_filtros() (mismo dato que reciben las
        vistas). filtros es el dict de filtros_globales vigente (session_state),
        usado para resolver el alcance geografico y temporal de los indicadores
        con denominador poblacional (ej. que anios y que subregiones/municipios
        entran a sumar poblacion en riesgo).

        Si falta una pieza necesaria para un indicador, ese indicador debe quedar
        marcado como no disponible (None), nunca en cero.
        """

    @abstractmethod
    def obtener_esquema(self) -> dict[str, Any]:
        """Devuelve el esquema estable y documentado de los datos procesados de la patologia."""

    @abstractmethod
    def obtener_vistas(self) -> list[Any]:
        """Devuelve las pestanas y graficos que la patologia expone al dashboard."""

    @abstractmethod
    def obtener_mapeo_subregion(self) -> dict[int, str]:
        """Mapeo de codigo DIVIPOLA de municipio (cod_mun_completo) a nombre de subregion,
        leido del archivo de configuracion intercambiable de la patologia (config/subregiones.csv).
        No es una columna del dato procesado: se deriva en memoria al filtrar, asi que
        cambiar ese archivo reagrupa todo sin reprocesar ninguna pieza.
        """

    def obtener_mapeo_estratificacion_riesgo(self, datos: pd.DataFrame) -> dict[int, str]:
        """Mapeo de codigo DIVIPOLA de municipio (cod_mun_completo) a nivel de riesgo
        (ej. "Alta transmision", "Sin riesgo"). Cada patologia decide como lo obtiene
        (leerlo de un archivo externo, calcularlo, etc.); dengue lo calcula en
        pathologies/dengue/estratificacion.py. Alimenta el filtro global
        "Estratificacion de riesgo" (ver core/dashboard_base/filtros.py). No es una
        columna del dato procesado: se deriva en memoria al filtrar, igual que
        obtener_mapeo_subregion.

        datos: el consolidado COMPLETO de la patologia (layout.py lo pasa antes de
        aplicar ningun filtro global). Asi la estratificacion nunca depende de lo que
        el usuario filtre en pantalla, solo del dato cargado en la sesion.

        No es abstracto (metodo concreto, no @abstractmethod): no toda patologia tiene
        una nocion de estratificacion de riesgo (ej. tuberculosis no es transmitida por
        vector). El default devuelve un mapeo vacio, con lo que el filtro simplemente
        no ofrece opciones para esa patologia.
        """
        return {}

    def obtener_pronostico(self) -> ModuloPronostico | None:
        """Modulo de pronostico de la patologia, o None si no tiene. Habilita el
        apartado de reentrenamiento en Gestion (solo perfil de administracion) y
        el trabajo de entrenamiento del worker.

        No es abstracto: el default None deja a las patologias sin pronostico
        (ej. tuberculosis) funcionando sin cambios. El nucleo nunca pregunta por
        el nombre de la patologia, solo por lo que este metodo declara.
        """
        return None


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
