"""Utilidades del pronostico recursivo multipaso.

Para la semana origen+k, los valores que ya ocurrieron son reales y los que caen
DENTRO del horizonte se realimentan con la propia prediccion del modelo. Las
trayectorias se calculan vectorizadas por origen (todas las semanas de origen a
la vez en cada paso), lo que da el mismo resultado que recorrer origen por
origen y vuelve barata la validacion.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

TRANSFORMACION_NINGUNA = "ninguna"
TRANSFORMACION_LOG1P = "log1p"
TRANSFORMACIONES = [TRANSFORMACION_NINGUNA, TRANSFORMACION_LOG1P]


def transformar(valores: np.ndarray, transformacion: str) -> np.ndarray:
    if transformacion == TRANSFORMACION_LOG1P:
        return np.log1p(valores)
    if transformacion == TRANSFORMACION_NINGUNA:
        return valores
    raise ValueError(f"Transformación desconocida: {transformacion}")


def destransformar(valores: np.ndarray, transformacion: str) -> np.ndarray:
    if transformacion == TRANSFORMACION_LOG1P:
        return np.expm1(valores)
    if transformacion == TRANSFORMACION_NINGUNA:
        return valores
    raise ValueError(f"Transformación desconocida: {transformacion}")


def historial_inicial(valores: np.ndarray, origenes: list[int], largo: int, horizonte: int) -> np.ndarray:
    """Matriz de trabajo de la recursion: una fila por origen. La columna j
    corresponde a la posicion (origen - largo + j) de la serie; las primeras
    largo+1 columnas son datos reales y las ultimas horizonte se van llenando
    con las predicciones (la realimentacion del pronostico recursivo)."""
    historial = np.full((len(origenes), largo + 1 + horizonte), np.nan)
    for fila, origen in enumerate(origenes):
        historial[fila, :largo + 1] = valores[origen - largo:origen + 1]
    return historial


def nombre_columna_rezago(rezago: int) -> str:
    return f"casos_lag{rezago}"


def tabla_de_rezagos(valores: np.ndarray, rezagos: list[int]) -> pd.DataFrame:
    """Tabla de entrenamiento: objetivo y una columna por rezago, sin las
    primeras filas que no tienen todos los rezagos."""
    tabla = pd.DataFrame({"objetivo": valores})
    for rezago in rezagos:
        tabla[nombre_columna_rezago(rezago)] = tabla["objetivo"].shift(rezago)
    tabla = tabla.dropna().reset_index(drop=True)
    return tabla


def trayectorias_con_rezagos(
    valores: np.ndarray,
    origenes: list[int],
    rezagos: list[int],
    horizonte: int,
    predecir_paso: Callable[[pd.DataFrame, int], np.ndarray],
) -> np.ndarray:
    """Recursion comun a los modelos que predicen la semana siguiente a partir
    de rezagos. valores esta en la escala en que trabaja el modelo (por ejemplo
    log1p). predecir_paso(entrada, paso) recibe una fila por origen con las
    columnas casos_lag<r> y devuelve la prediccion en esa misma escala. Devuelve
    la matriz (origenes x horizonte) en esa misma escala."""
    rezago_maximo = max(rezagos)
    historial = historial_inicial(valores, origenes, rezago_maximo, horizonte)
    trayectorias = np.zeros((len(origenes), horizonte))

    for paso in range(1, horizonte + 1):
        columna_objetivo = rezago_maximo + paso
        entrada = pd.DataFrame()
        for rezago in rezagos:
            entrada[nombre_columna_rezago(rezago)] = historial[:, columna_objetivo - rezago]
        prediccion = np.asarray(predecir_paso(entrada, paso), dtype=float)
        historial[:, columna_objetivo] = prediccion
        trayectorias[:, paso - 1] = prediccion
    return trayectorias
