"""Evaluacion de un modelo en el conjunto de prueba con origenes moviles.

Es la MISMA evaluacion que usan el worker al entrenar en la app y los notebooks
del repositorio de experimentacion al exportar un modelo: las metricas de un
modelo subido y las de uno entrenado aqui se calculan igual.

Tres niveles de resultados, todos del conjunto de prueba (el ultimo 15 % del
rango), producidos por el modelo de evaluacion (entrenado con el primer 85 %),
ANTES de entrenar el modelo definitivo con el 100 % de los datos:

1. Resultados individuales (registros_prueba): un registro por cada semana de
   origen y horizonte cuya semana objetivo pertenece a la prueba. Es la fuente
   de verdad: se guarda en el CSV de la version.
2. Metricas por horizonte: se calculan agrupando esos registros por horizonte
   (H1 con todas las predicciones a 1 semana, H2 con todas las de 2 semanas...).
3. Metricas globales: se calculan sobre todos los registros, de todos los
   horizontes a la vez (no promediando las seis metricas por horizonte).

Ninguna de ellas evalua al modelo definitivo; describen el rendimiento historico
del procedimiento en la prueba. Los calculos usan valores sin redondear.
"""

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico.configuracion import (
    FRACCION_PRUEBA,
    HORIZONTE_MAXIMO_SEMANAS,
    SEMANAS_MINIMAS_ENTRENAMIENTO,
)

DESCRIPCION_PRUEBA = (
    "Evaluación con orígenes móviles en el conjunto de prueba: el último 15 % del rango de "
    "entrenamiento se reserva como prueba y el modelo de evaluación se entrena con el 85 % "
    "anterior. Desde cada semana de origen recibe los casos reales hasta esa semana y pronostica "
    "las 6 siguientes realimentando su propia predicción. Se guardan todos los pronósticos cuya "
    "semana objetivo pertenece a la prueba, junto con la persistencia (repetir el último valor "
    "real) en los mismos orígenes y horizontes."
)

ALCANCE_METRICAS = (
    "Rendimiento histórico en el conjunto de prueba (15 %) del modelo de evaluación, entrenado "
    "con el 85 % anterior, antes de entrenar el modelo definitivo con el 100 % de los datos. No "
    "es una evaluación del modelo definitivo ni el error de los pronósticos futuros."
)

# Columnas del CSV de pronosticos de la prueba, en orden.
COLUMNAS_REGISTROS = [
    "fecha_origen",
    "horizonte_semanas",
    "fecha_objetivo",
    "casos_reales",
    "pronostico_modelo",
    "error_absoluto",
    "error_porcentual",
    "pronostico_persistencia",
    "error_absoluto_persistencia",
    "error_porcentual_persistencia",
]

PRONOSTICADOR_MODELO = "modelo"
PRONOSTICADOR_PERSISTENCIA = "persistencia"

_COLUMNAS_POR_PRONOSTICADOR = {
    PRONOSTICADOR_MODELO: "pronostico_modelo",
    PRONOSTICADOR_PERSISTENCIA: "pronostico_persistencia",
}


def calcular_metricas(valores_reales, valores_pronosticados) -> dict[str, float | int | None]:
    """RMSE, MAE, MAPE (%) y R2 de un conjunto de registros, con valores sin
    redondear. Los registros con 0 casos reales participan en RMSE, MAE y R2,
    pero no en MAPE (no se puede dividir por cero): n cuenta todos los registros
    y n_mape solo los que entran al MAPE. MAPE None si todos los reales son 0; R2
    None con menos de 2 registros (no esta definido)."""
    reales = np.asarray(valores_reales, dtype=float)
    pronosticados = np.asarray(valores_pronosticados, dtype=float)
    cantidad = len(reales)

    rmse = float(np.sqrt(mean_squared_error(reales, pronosticados)))
    mae = float(mean_absolute_error(reales, pronosticados))

    con_casos = reales != 0
    cantidad_mape = int(con_casos.sum())
    if cantidad_mape > 0:
        diferencias = np.abs(reales[con_casos] - pronosticados[con_casos])
        errores_relativos = diferencias / np.abs(reales[con_casos])
        mape = float(np.mean(errores_relativos) * 100)
    else:
        mape = None

    if cantidad >= 2:
        r2 = float(r2_score(reales, pronosticados))
    else:
        r2 = None

    return {
        "RMSE": rmse,
        "MAE": mae,
        "MAPE": mape,
        "R2": r2,
        "n": cantidad,
        "n_mape": cantidad_mape,
    }


def _error_porcentual(reales: np.ndarray, pronosticados: np.ndarray) -> np.ndarray:
    """Error porcentual absoluto de cada registro. NaN (no definido) cuando los
    casos reales son 0."""
    resultado = np.full(len(reales), np.nan)
    con_casos = reales != 0
    diferencias = np.abs(reales[con_casos] - pronosticados[con_casos])
    resultado[con_casos] = diferencias / np.abs(reales[con_casos]) * 100
    return resultado


def evaluar_en_prueba(
    clase_modelo: type[ModeloPronostico],
    hiperparametros: dict[str, Any] | None,
    serie: pd.DataFrame,
    horizonte_maximo: int = HORIZONTE_MAXIMO_SEMANAS,
) -> dict[str, Any]:
    """Entrena el modelo de evaluacion con el primer 85 % de la serie (ya
    recortada al rango elegido) y produce los resultados individuales del 15 %
    final. Desde cada semana de origen el modelo recibe los casos reales hasta
    ella y pronostica horizonte_maximo semanas; solo se conservan los registros
    cuya semana objetivo cae dentro de la prueba (para que cada horizonte tenga
    un registro por cada semana de prueba, los origenes empiezan horizonte_maximo
    semanas antes de la prueba).

    Devuelve {"registros": DataFrame con COLUMNAS_REGISTROS, "semanas_entrenamiento",
    "semanas_prueba", "inicio_prueba", "fin_prueba", "cantidad_origenes"}.
    Lanza ValueError si la parte de entrenamiento no alcanza el minimo.
    """
    serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
    cantidad_semanas = len(serie_ordenada)
    semanas_prueba = int(round(cantidad_semanas * FRACCION_PRUEBA))
    primera_prueba = cantidad_semanas - semanas_prueba
    ultima_prueba = cantidad_semanas - 1

    if primera_prueba < SEMANAS_MINIMAS_ENTRENAMIENTO:
        raise ValueError(
            f"Histórico insuficiente para evaluar: hacen falta al menos "
            f"{SEMANAS_MINIMAS_ENTRENAMIENTO} semanas de entrenamiento antes del 15 % de "
            f"prueba, y hay {primera_prueba}."
        )

    origenes = list(range(primera_prueba - horizonte_maximo, ultima_prueba))
    casos_reales = serie_ordenada["casos"].to_numpy(dtype=float)
    fechas = pd.to_datetime(serie_ordenada["fecha_semana"]).tolist()
    serie_entrenamiento = serie_ordenada.iloc[:primera_prueba].reset_index(drop=True)

    modelo_evaluacion = clase_modelo(hiperparametros)
    modelo_evaluacion.entrenar(serie_entrenamiento)
    trayectorias = modelo_evaluacion.pronosticar_trayectorias(serie_ordenada, origenes, horizonte_maximo)

    filas = []
    for fila, origen in enumerate(origenes):
        valor_en_origen = casos_reales[origen]
        for horizonte in range(1, horizonte_maximo + 1):
            posicion_objetivo = origen + horizonte
            if posicion_objetivo < primera_prueba or posicion_objetivo > ultima_prueba:
                continue
            filas.append({
                "fecha_origen": fechas[origen],
                "horizonte_semanas": horizonte,
                "fecha_objetivo": fechas[posicion_objetivo],
                "casos_reales": casos_reales[posicion_objetivo],
                "pronostico_modelo": float(trayectorias[fila, horizonte - 1]),
                "pronostico_persistencia": float(valor_en_origen),
            })
    registros = pd.DataFrame(filas)

    reales = registros["casos_reales"].to_numpy(dtype=float)
    for pronosticador, columna in _COLUMNAS_POR_PRONOSTICADOR.items():
        pronosticados = registros[columna].to_numpy(dtype=float)
        if pronosticador == PRONOSTICADOR_MODELO:
            sufijo = ""
        else:
            sufijo = "_persistencia"
        registros[f"error_absoluto{sufijo}"] = np.abs(reales - pronosticados)
        registros[f"error_porcentual{sufijo}"] = _error_porcentual(reales, pronosticados)

    return {
        "registros": registros[COLUMNAS_REGISTROS],
        "semanas_entrenamiento": int(primera_prueba),
        "semanas_prueba": int(semanas_prueba),
        "inicio_prueba": fechas[primera_prueba].strftime("%Y-%m-%d"),
        "fin_prueba": fechas[ultima_prueba].strftime("%Y-%m-%d"),
        "cantidad_origenes": int(registros["fecha_origen"].nunique()),
    }


def metricas_desde_registros(registros: pd.DataFrame, horizonte_maximo: int = HORIZONTE_MAXIMO_SEMANAS) -> dict[str, Any]:
    """Metricas acumuladas a partir de los resultados individuales de la prueba
    (el CSV): globales sobre todos los registros y por horizonte agrupando por
    horizonte_semanas, para el modelo y para la persistencia. Es la unica forma
    en que el sistema calcula metricas, asi que el manifest siempre coincide con
    lo que se reconstruye desde el CSV.

    {"global": {"modelo": {...}, "persistencia": {...}},
     "por_horizonte": {"1": {"modelo": {...}, "persistencia": {...}}, ...}}
    """
    resultado = {"global": {}, "por_horizonte": {}}
    reales = registros["casos_reales"]
    for pronosticador, columna in _COLUMNAS_POR_PRONOSTICADOR.items():
        resultado["global"][pronosticador] = calcular_metricas(reales, registros[columna])

    for horizonte in range(1, horizonte_maximo + 1):
        del_horizonte = registros[registros["horizonte_semanas"] == horizonte]
        metricas_horizonte = {}
        for pronosticador, columna in _COLUMNAS_POR_PRONOSTICADOR.items():
            metricas_horizonte[pronosticador] = calcular_metricas(
                del_horizonte["casos_reales"], del_horizonte[columna]
            )
        resultado["por_horizonte"][str(horizonte)] = metricas_horizonte
    return resultado
