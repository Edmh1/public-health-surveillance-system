"""Catalogo de modelos de pronostico de dengue.

Descubre solo los modelos: recorre los archivos de modelos/ y registra cada
subclase de core.registry.ModeloPronostico definida en ellos. Agregar un modelo
es agregar un archivo ahi; este modulo no se toca.

Importar los archivos es barato: cada modelo importa su libreria dentro de sus
metodos, asi que el catalogo lista tambien los modelos cuya libreria falta
(marcados como no disponibles con paquetes_faltantes()).
"""

import importlib
import inspect
import pkgutil

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico import modelos as paquete_modelos
from pathologies.dengue.pronostico.configuracion import FAMILIAS

_CATALOGO: dict[str, type[ModeloPronostico]] | None = None


def _es_modelo_del_modulo(objeto, nombre_modulo: str) -> bool:
    if not inspect.isclass(objeto):
        return False
    if not issubclass(objeto, ModeloPronostico):
        return False
    if inspect.isabstract(objeto):
        return False
    # Solo la clase DEFINIDA en ese archivo, no las que importa de otro (sarima
    # hereda de arima: sin este filtro ARIMA quedaria registrado dos veces).
    return objeto.__module__ == nombre_modulo


def _descubrir() -> dict[str, type[ModeloPronostico]]:
    encontrados = {}
    for informacion in pkgutil.iter_modules(paquete_modelos.__path__):
        nombre_modulo = f"{paquete_modelos.__name__}.{informacion.name}"
        modulo = importlib.import_module(nombre_modulo)
        for objeto in vars(modulo).values():
            if not _es_modelo_del_modulo(objeto, nombre_modulo):
                continue
            if not objeto.clave:
                raise ValueError(f"El modelo {objeto.__name__} de {nombre_modulo} no declara clave.")
            if objeto.familia not in FAMILIAS:
                raise ValueError(
                    f"El modelo {objeto.clave} declara la familia '{objeto.familia}', que no existe. "
                    f"Familias válidas: {', '.join(FAMILIAS)}."
                )
            if objeto.clave in encontrados:
                raise ValueError(f"Hay dos modelos con la clave {objeto.clave}.")
            encontrados[objeto.clave] = objeto
    return encontrados


def listar_modelos() -> dict[str, type[ModeloPronostico]]:
    """Todos los modelos del catalogo, por clave (disponibles o no)."""
    global _CATALOGO
    if _CATALOGO is None:
        _CATALOGO = _descubrir()
    return dict(_CATALOGO)


def obtener_modelo(clave: str) -> type[ModeloPronostico]:
    catalogo = listar_modelos()
    if clave not in catalogo:
        raise KeyError(f"No existe el modelo '{clave}' en el catálogo de pronóstico de dengue.")
    return catalogo[clave]


def modelos_por_familia() -> dict[str, list[type[ModeloPronostico]]]:
    """Candidatos de cada familia, en el orden de FAMILIAS y por nombre."""
    agrupados = {familia: [] for familia in FAMILIAS}
    for clase in listar_modelos().values():
        agrupados[clase.familia].append(clase)
    for familia in agrupados:
        agrupados[familia].sort(key=lambda clase: clase.nombre)
    return agrupados
