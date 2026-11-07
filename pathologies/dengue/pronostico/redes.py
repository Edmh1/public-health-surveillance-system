"""Partes comunes de las redes neuronales (LSTM, N-BEATS): escalado min-max de
log1p(casos), ventanas de entrada, entrenamiento con parada temprana y
pronostico recursivo deslizando la ventana.

Cada red solo define su arquitectura; el resto es igual para todas, asi que dos
redes del catalogo se entrenan y se evaluan exactamente de la misma forma.

El escalador se exporta como JSON (minimo y maximo), no como pickle de
scikit-learn: un modelo entrenado en otro equipo carga aunque cambie la version
de scikit-learn. Keras se importa dentro de las funciones (tarda del orden de
decenas de segundos).
"""

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from pathologies.dengue.pronostico.recursivo import historial_inicial

ARCHIVO_ESCALADOR = "escalador.json"
_TASA_APRENDIZAJE_MINIMA = 1e-5


class EscaladorMinMax:
    """Min-max sobre log1p(casos), ajustado solo con la parte de ajuste."""

    def __init__(self, minimo: float | None = None, maximo: float | None = None) -> None:
        self.minimo = minimo
        self.maximo = maximo

    def ajustar(self, valores: np.ndarray) -> None:
        self.minimo = float(np.min(valores))
        self.maximo = float(np.max(valores))

    def _amplitud(self) -> float:
        amplitud = self.maximo - self.minimo
        if amplitud == 0:
            return 1.0
        return amplitud

    def escalar(self, valores: np.ndarray) -> np.ndarray:
        return (valores - self.minimo) / self._amplitud()

    def desescalar(self, valores: np.ndarray) -> np.ndarray:
        return valores * self._amplitud() + self.minimo

    def guardar(self, carpeta: Path) -> str:
        contenido = {"minimo_log1p": self.minimo, "maximo_log1p": self.maximo}
        ruta = carpeta / ARCHIVO_ESCALADOR
        ruta.write_text(json.dumps(contenido, indent=2), encoding="utf-8")
        return ARCHIVO_ESCALADOR

    @classmethod
    def cargar(cls, carpeta: Path) -> "EscaladorMinMax":
        contenido = json.loads((carpeta / ARCHIVO_ESCALADOR).read_text(encoding="utf-8"))
        return cls(float(contenido["minimo_log1p"]), float(contenido["maximo_log1p"]))


def casos_log_ordenados(serie: pd.DataFrame) -> np.ndarray:
    serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
    return np.log1p(serie_ordenada["casos"].to_numpy(dtype=float))


def entrenar_red(
    construir_red: Callable[[], object],
    casos_log: np.ndarray,
    hiperparametros: dict,
) -> tuple[object, EscaladorMinMax, dict]:
    """Entrena una red que recibe ventana_semanas valores escalados y predice el
    siguiente. Usa de hiperparametros: ventana_semanas, batch_size,
    epocas_maximas, fraccion_validacion, paciencia, paciencia_tasa_aprendizaje
    (None = sin reducir la tasa) y semilla.

    El ultimo tramo de la serie (fraccion_validacion) solo decide cuando parar
    (parada temprana, restaurando los mejores pesos); con fraccion_validacion = 0
    se entrenan epocas_maximas epocas fijas. Devuelve la red, el escalador y los
    detalles del entrenamiento para el manifest.
    """
    import keras

    ventana = hiperparametros["ventana_semanas"]
    cantidad = len(casos_log)
    semanas_validacion = int(round(cantidad * hiperparametros["fraccion_validacion"]))
    fin_ajuste = cantidad - semanas_validacion

    escalador = EscaladorMinMax()
    escalador.ajustar(casos_log[:fin_ajuste])
    escalados = escalador.escalar(casos_log)

    secuencias = []
    objetivos = []
    for posicion in range(ventana, cantidad):
        secuencias.append(escalados[posicion - ventana:posicion])
        objetivos.append(escalados[posicion])
    entradas = np.array(secuencias)
    salidas = np.array(objetivos)
    posiciones_objetivo = np.arange(ventana, cantidad)
    es_validacion = posiciones_objetivo >= fin_ajuste

    keras.utils.set_random_seed(hiperparametros["semilla"])
    red = construir_red()
    # La LSTM recibe (ventana, 1) y N-BEATS (ventana,): se ajusta a la red.
    forma_entrada = (-1,) + tuple(red.input_shape[1:])
    entradas = entradas.reshape(forma_entrada)

    if semanas_validacion == 0:
        historia = red.fit(
            entradas,
            salidas,
            epochs=hiperparametros["epocas_maximas"],
            batch_size=hiperparametros["batch_size"],
            verbose=0,
        )
        detalles = {"epocas_ejecutadas": len(historia.history["loss"])}
        return red, escalador, detalles

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=hiperparametros["paciencia"],
            restore_best_weights=True,
        )
    ]
    if hiperparametros.get("paciencia_tasa_aprendizaje") is not None:
        callbacks.append(keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=hiperparametros["paciencia_tasa_aprendizaje"],
            min_lr=_TASA_APRENDIZAJE_MINIMA,
        ))

    historia = red.fit(
        entradas[~es_validacion],
        salidas[~es_validacion],
        validation_data=(entradas[es_validacion], salidas[es_validacion]),
        epochs=hiperparametros["epocas_maximas"],
        batch_size=hiperparametros["batch_size"],
        callbacks=callbacks,
        verbose=0,
    )
    perdidas_validacion = historia.history["val_loss"]
    detalles = {
        "epocas_ejecutadas": len(perdidas_validacion),
        "mejor_epoca": int(np.argmin(perdidas_validacion)) + 1,
        "perdida_validacion_mejor": round(float(min(perdidas_validacion)), 5),
    }
    return red, escalador, detalles


def trayectorias_red(
    red,
    escalador: EscaladorMinMax,
    casos_log: np.ndarray,
    origenes: list[int],
    ventana: int,
    horizonte: int,
) -> np.ndarray:
    """Pronostico recursivo deslizando la ventana: cada prediccion entra a la
    ventana del paso siguiente. Devuelve la matriz (origenes x horizonte) en casos."""
    historial = historial_inicial(casos_log, origenes, ventana - 1, horizonte)
    trayectorias = np.zeros((len(origenes), horizonte))
    forma_entrada = (len(origenes),) + tuple(red.input_shape[1:])

    for paso in range(1, horizonte + 1):
        inicio = paso - 1
        columna_objetivo = inicio + ventana
        ventana_log = historial[:, inicio:columna_objetivo]
        ventana_escalada = escalador.escalar(ventana_log).reshape(forma_entrada)

        prediccion_escalada = red.predict(ventana_escalada, verbose=0).flatten()
        prediccion_log = np.maximum(escalador.desescalar(prediccion_escalada), 0.0)

        historial[:, columna_objetivo] = prediccion_log
        trayectorias[:, paso - 1] = np.expm1(prediccion_log)
    return trayectorias
