"""Manifest de una version de un modelo de pronostico de dengue.

Un solo formato para las dos formas de crear una version: entrenada en la app
(worker) o subida en un .zip (entrenada en otro equipo con el codigo de
pronostico del tablero). Describe el modelo definitivo (entrenado con el 100 %
del rango) y resume su evaluacion en la prueba. La documentacion completa de
cada campo esta en docs/pronostico.md y en DESCRIPCION_CAMPOS.

Las metricas del manifest (metricas_prueba) se calculan SIEMPRE desde los
registros del CSV de la prueba (evaluacion.metricas_desde_registros); al subir un
paquete se vuelven a calcular desde su CSV y deben coincidir.

Las versiones con un formato distinto de FORMATO_MANIFEST son del esquema
anterior: se conservan como historico, pero no se pueden activar.
"""

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico.configuracion import DEFINICION_SERIE, HORIZONTE_MAXIMO_SEMANAS
from pathologies.dengue.pronostico.evaluacion import ALCANCE_METRICAS, DESCRIPCION_PRUEBA
from pathologies.dengue.pronostico.serie import describir_rango

FORMATO_MANIFEST = 2

ORIGEN_SISTEMA = "sistema"
ORIGEN_SUBIDO = "subido"
ORIGENES = [ORIGEN_SISTEMA, ORIGEN_SUBIDO]

ARCHIVO_MANIFEST = "manifest.json"
ARCHIVO_PRONOSTICOS_PRUEBA = "pronosticos_prueba.csv"

CAMPOS_OBLIGATORIOS = [
    "formato",
    "patologia",
    "serie",
    "modelo",
    "familia",
    "origen",
    "usuario",
    "fecha_entrenamiento",
    "rango",
    "semanas",
    "hiperparametros",
    "archivos_modelo",
    "archivo_pronosticos_prueba",
    "horizonte_maximo_semanas",
    "prueba",
    "metricas_prueba",
    "librerias",
]

# Lo que contiene cada campo del manifest (Gestion, "Ver estructura del paquete",
# y docs/pronostico.md).
DESCRIPCION_CAMPOS = {
    "formato": f"Versión del formato del manifest ({FORMATO_MANIFEST}).",
    "patologia": "Siempre \"dengue\".",
    "serie": "Definición de la serie con que se entrenó. Debe ser igual a la del tablero.",
    "modelo": "Clave del modelo en el catálogo: arima, sarima, prophet_ar, xgboost, lightgbm, lstm o nbeats.",
    "nombre": "Nombre legible del modelo.",
    "familia": "estadistico, aprendizaje_automatico o aprendizaje_profundo. Debe coincidir con la del catálogo.",
    "origen": "Lo completa el tablero: sistema (entrenado en la app) o subido.",
    "usuario": "Quién entrenó el modelo.",
    "fecha_entrenamiento": "Fecha y hora del entrenamiento (ISO 8601, UTC).",
    "rango": "Primera y última semana de datos del modelo definitivo (año, semana y fecha).",
    "semanas": "Cantidad de semanas del rango (las del modelo definitivo).",
    "hiperparametros": "Configuración con que se entrenó (no el estado aprendido); el tablero la usa para reconstruir el modelo al cargarlo.",
    "archivos_modelo": "Archivos del modelo definitivo entrenado (y sus auxiliares) dentro del paquete.",
    "archivo_pronosticos_prueba": f"Nombre del CSV con los resultados individuales de la prueba ({ARCHIVO_PRONOSTICOS_PRUEBA}).",
    "horizonte_maximo_semanas": f"Horizonte máximo evaluado y pronosticado ({HORIZONTE_MAXIMO_SEMANAS}).",
    "prueba": "Cómo se evaluó: descripción, semanas de entrenamiento del modelo de evaluación, semanas de prueba, inicio y fin de la prueba, orígenes y registros.",
    "metricas_prueba": "Métricas acumuladas de la prueba calculadas desde el CSV: alcance, globales (todos los registros) y por horizonte H1 a H6, del modelo y de la persistencia, cada una con su n.",
    "detalles_entrenamiento": "Datos del entrenamiento del modelo definitivo, por ejemplo en qué época se detuvo una red.",
    "librerias": "Versión de cada librería con que se exportó; al importar se compara con la instalada.",
    "subido_por": "Lo agrega el tablero al importar: quién subió el paquete.",
    "fecha_subida": "Lo agrega el tablero al importar: cuándo se subió.",
    "compatibilidad": "Lo agrega el tablero al importar: versión exportada e instalada de cada librería.",
}


def es_formato_vigente(manifest: dict) -> bool:
    return manifest.get("formato") == FORMATO_MANIFEST


def construir_manifest(
    modelo: ModeloPronostico,
    serie_entrenamiento: pd.DataFrame,
    evaluacion: dict[str, Any],
    metricas: dict[str, Any],
    archivos_modelo: list[str],
    usuario: str,
    origen: str,
) -> dict[str, Any]:
    """Manifest del modelo definitivo recien entrenado con serie_entrenamiento.
    evaluacion es lo que devolvio evaluacion.evaluar_en_prueba y metricas lo que
    devolvio evaluacion.metricas_desde_registros sobre sus registros."""
    return {
        "formato": FORMATO_MANIFEST,
        "patologia": "dengue",
        "serie": DEFINICION_SERIE,
        "modelo": modelo.clave,
        "nombre": modelo.nombre,
        "familia": modelo.familia,
        "origen": origen,
        "usuario": usuario,
        "fecha_entrenamiento": datetime.now(timezone.utc).isoformat(),
        "rango": describir_rango(serie_entrenamiento),
        "semanas": int(len(serie_entrenamiento)),
        "hiperparametros": modelo.hiperparametros,
        "archivos_modelo": archivos_modelo,
        "archivo_pronosticos_prueba": ARCHIVO_PRONOSTICOS_PRUEBA,
        "horizonte_maximo_semanas": HORIZONTE_MAXIMO_SEMANAS,
        "prueba": {
            "descripcion": DESCRIPCION_PRUEBA,
            "semanas_entrenamiento": evaluacion["semanas_entrenamiento"],
            "semanas_prueba": evaluacion["semanas_prueba"],
            "inicio_prueba": evaluacion["inicio_prueba"],
            "fin_prueba": evaluacion["fin_prueba"],
            "cantidad_origenes": evaluacion["cantidad_origenes"],
            "registros": int(len(evaluacion["registros"])),
        },
        "metricas_prueba": {
            "alcance": ALCANCE_METRICAS,
            "global": metricas["global"],
            "por_horizonte": metricas["por_horizonte"],
        },
        "detalles_entrenamiento": modelo.detalles_entrenamiento(),
        "librerias": modelo.versiones_paquetes(),
    }


def campos_faltantes(manifest: dict) -> list[str]:
    faltantes = []
    for campo in CAMPOS_OBLIGATORIOS:
        if campo not in manifest:
            faltantes.append(campo)
    return faltantes
