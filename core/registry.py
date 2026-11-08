"""Registro de patologias: sistema de plugins que descubre e indexa cada patologia disponible."""

import copy
import importlib.util
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class ModeloPronostico(ABC):
    """Contrato de UN modelo de pronostico (Prophet, XGBoost, LSTM...).

    El contrato es comun; las implementaciones viven en cada patologia
    (pathologies/<patologia>/pronostico/modelos/, un archivo por modelo), porque
    la forma de preparar la serie y de evaluar puede cambiar entre patologias.
    Agregar un modelo es agregar un archivo con una subclase de este contrato e
    instalar su libreria; no se toca nada mas.

    Atributos de clase que toda implementacion declara:
      - clave: identificador unico y estable (tambien es el nombre de su carpeta
        de versiones en data/<patologia>/modelos/<clave>/).
      - nombre: rotulo legible.
      - familia: clave de la familia a la que pertenece (las familias las
        declara la patologia).
      - paquetes_requeridos: nombres de importacion de las librerias que usa. Si
        falta alguna, el modelo se muestra como no disponible y el resto del
        sistema sigue funcionando.
      - hiperparametros_por_defecto: los que se usan si no se indican otros.
      - archivos_exportados: {nombre de archivo: que contiene}, los archivos que
        escribe guardar(). Gestion los muestra a quien arma un paquete .zip.

    Las implementaciones importan su libreria DENTRO de los metodos, nunca al
    inicio del archivo: asi la ausencia de una libreria solo afecta a su modelo,
    y librerias lentas de importar (TensorFlow) no frenan el arranque.

    La serie que reciben es la que construye la patologia; el contrato solo
    exige que el modelo sepa entrenar con ella, pronosticar trayectorias
    multipaso desde posiciones de origen, guardarse y cargarse.
    """

    clave: str = ""
    nombre: str = ""
    familia: str = ""
    paquetes_requeridos: tuple[str, ...] = ()
    hiperparametros_por_defecto: dict[str, Any] = {}
    archivos_exportados: dict[str, str] = {}

    def __init__(self, hiperparametros: dict[str, Any] | None = None) -> None:
        combinados = copy.deepcopy(self.hiperparametros_por_defecto)
        if hiperparametros is not None:
            combinados.update(hiperparametros)
        self.hiperparametros = combinados

    @classmethod
    def paquetes_faltantes(cls) -> list[str]:
        """Librerias requeridas que no estan instaladas (sin importarlas)."""
        faltantes = []
        for paquete in cls.paquetes_requeridos:
            if importlib.util.find_spec(paquete) is None:
                faltantes.append(paquete)
        return faltantes

    @classmethod
    def versiones_paquetes(cls) -> dict[str, str]:
        """Version instalada de cada libreria requerida, para el manifest. Importa
        las librerias: llamarlo solo cuando ya se van a usar."""
        versiones = {}
        for paquete in cls.paquetes_requeridos:
            modulo = importlib.import_module(paquete)
            versiones[paquete] = str(getattr(modulo, "__version__", "desconocida"))
        return versiones

    @abstractmethod
    def entrenar(self, serie: pd.DataFrame) -> None:
        """Ajusta el modelo con toda la serie recibida."""

    @abstractmethod
    def pronosticar_trayectorias(self, serie: pd.DataFrame, origenes: list[int], horizonte: int) -> np.ndarray:
        """Pronostico multipaso desde cada posicion de origen de la serie (el
        origen es la ultima semana con dato real que el modelo ve). Devuelve una
        matriz (len(origenes) x horizonte) en la escala original de la serie."""

    @abstractmethod
    def guardar(self, carpeta: Path) -> list[str]:
        """Exporta el modelo entrenado en carpeta. Devuelve los archivos escritos."""

    @abstractmethod
    def cargar(self, carpeta: Path) -> None:
        """Carga un modelo exportado por guardar. Los hiperparametros llegan por
        el constructor (salen del manifest de la version)."""

    def detalles_entrenamiento(self) -> dict[str, Any]:
        """Datos del ultimo entrenamiento que vale la pena dejar en el manifest
        (por ejemplo, en que epoca se detuvo una red). Opcional."""
        return {}


class ModuloPronostico(ABC):
    """Contrato del pronostico de una patologia que lo tenga. El nucleo lo usa
    para el apartado de modelos de Gestion (solo perfil de administracion) y los
    trabajos del worker (core/ingestion/entrenamiento.py), sin saber que modelos
    hay detras ni como se arma la serie.

    Cada modelo tiene sus propias versiones (core/storage/modelos.py) y cada
    familia una version activa. Una version llega por uno de dos caminos:
    entrenada en la app (entrenar_y_exportar) o subida en un .zip entrenado en
    otro equipo (importar).

    El nucleo lee del manifest.json de cada version estos campos, que toda
    implementacion debe escribir:
      - modelo (clave del catalogo), nombre, familia, origen
      - fecha_entrenamiento (ISO 8601, UTC) y usuario
      - rango: {"anio_inicio", "semana_inicio", "anio_fin", "semana_fin",
        "fecha_primera_semana", "fecha_ultima_semana"} del modelo definitivo
      - semanas: cantidad de semanas del rango
      - hiperparametros
      - prueba: {"inicio_prueba", "fin_prueba", ...}
      - metricas_prueba: {"alcance": texto, "global": {"modelo": m, "persistencia": m},
        "por_horizonte": {"1": {"modelo": m, "persistencia": m}, ...}}, con
        m = {"RMSE", "MAE", "MAPE", "R2", "n", "n_mape"}: rendimiento historico en
        la prueba, no del modelo definitivo
    Puede agregar los campos propios que necesite. Las versiones que no cumplen
    el formato vigente (es_version_vigente) se muestran como historico y no se
    pueden activar.

    Si algo no se puede hacer (historico insuficiente, paquete invalido), los
    metodos lanzan una excepcion con un mensaje legible: el nucleo lo registra
    como fallo y no toca ninguna version.
    """

    @abstractmethod
    def familias(self) -> dict[str, str]:
        """Familias de modelos, en el orden en que se muestran: {clave: rotulo}."""

    @abstractmethod
    def catalogo(self) -> dict[str, type[ModeloPronostico]]:
        """Modelos disponibles, por clave (incluidos los que no tienen su
        libreria instalada; ver ModeloPronostico.paquetes_faltantes)."""

    @abstractmethod
    def semanas_disponibles(self, datos: pd.DataFrame) -> pd.DataFrame:
        """Semanas de la serie que se puede armar con datos, para elegir el
        rango de entrenamiento. Columnas: fecha_semana, ano, semana."""

    @abstractmethod
    def entrenar_y_exportar(
        self,
        datos: pd.DataFrame,
        modelo: str,
        desde: pd.Timestamp | None,
        hasta: pd.Timestamp | None,
        hiperparametros: dict[str, Any] | None,
        carpeta: Path,
        usuario: str,
    ) -> dict[str, Any]:
        """Valida y entrena el modelo con las semanas entre desde y hasta (None
        = sin limite) y escribe en carpeta sus archivos y el manifest.json.
        Devuelve el manifest."""

    @abstractmethod
    def importar(self, carpeta: Path, datos: pd.DataFrame, usuario: str) -> dict[str, Any]:
        """Revisa un paquete ya descomprimido en carpeta (manifest, archivos,
        que cargue y pronostique). Devuelve el manifest completado con quien lo
        subio; lanza ValueError si el paquete no sirve."""

    def es_version_vigente(self, manifest: dict) -> bool:
        """True si la version es del formato vigente. Las demas se conservan
        como historico pero no se activan."""
        return True

    def describir_paquete(self) -> dict[str, Any] | None:
        """Descripcion del paquete .zip que acepta importar, para quien entrena
        un modelo en otro equipo. Gestion la muestra en "Ver estructura del
        paquete":
          - secciones: [{"titulo", "markdown"}] con la estructura del paquete y
            como generarlo
          - ejemplos_por_modelo: {nombre: {"arbol": texto, "archivos":
            [{"titulo", "lenguaje", "contenido"}]}} con muestras reales
        None si la patologia no la declara."""
        return None


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
        apartado de modelos de pronostico en Gestion (solo perfil de administracion) y
        los trabajos de entrenar e importar modelos del worker.

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
