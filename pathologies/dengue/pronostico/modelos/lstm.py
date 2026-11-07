"""LSTM sobre una ventana de log1p(casos) (notebook 05, seccion 7.7). Familia de
aprendizaje profundo.

Mismo entrenamiento que el notebook 05: escalado min-max ajustado solo con la
parte de ajuste, ventanas de ventana_semanas semanas que predicen la siguiente,
parada temprana sobre el ultimo tramo restaurando los mejores pesos, y tasa de
aprendizaje a la mitad cuando se estanca. El escalado, el entrenamiento y la
recursion son comunes a todas las redes (pronostico/redes.py); aqui solo va la
arquitectura.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico import redes
from pathologies.dengue.pronostico.configuracion import FAMILIA_APRENDIZAJE_PROFUNDO

_ARCHIVO_RED = "lstm.keras"


class Lstm(ModeloPronostico):
    clave = "lstm"
    nombre = "LSTM"
    familia = FAMILIA_APRENDIZAJE_PROFUNDO
    paquetes_requeridos = ("tensorflow", "keras")
    archivos_exportados = {
        _ARCHIVO_RED: "Red LSTM guardada con model.save de Keras 3 (.keras).",
        redes.ARCHIVO_ESCALADOR: "Mínimo y máximo de log1p(casos) con que se escala la ventana de entrada (JSON).",
    }
    hiperparametros_por_defecto = {
        "ventana_semanas": 12,
        "unidades": [64, 16],
        "activacion": "tanh",
        "dropout": 0.2,
        "optimizador": "rmsprop",
        "perdida": "mean_absolute_error",
        "batch_size": 16,
        "epocas_maximas": 200,
        "fraccion_validacion": 0.15,
        "paciencia": 20,
        "paciencia_tasa_aprendizaje": 10,
        "semilla": 42,
    }

    def __init__(self, hiperparametros=None):
        super().__init__(hiperparametros)
        self.red = None
        self.escalador = None
        self._detalles = {}

    def _construir_red(self):
        import keras

        ventana = self.hiperparametros["ventana_semanas"]
        unidades = self.hiperparametros["unidades"]
        capas = [keras.Input(shape=(ventana, 1))]
        for posicion, cantidad_unidades in enumerate(unidades):
            es_ultima = posicion == len(unidades) - 1
            capas.append(keras.layers.LSTM(
                cantidad_unidades,
                activation=self.hiperparametros["activacion"],
                return_sequences=not es_ultima,
            ))
            if self.hiperparametros["dropout"] > 0:
                capas.append(keras.layers.Dropout(self.hiperparametros["dropout"]))
        capas.append(keras.layers.Dense(1))
        red = keras.Sequential(capas)
        red.compile(optimizer=self.hiperparametros["optimizador"], loss=self.hiperparametros["perdida"])
        return red

    def entrenar(self, serie: pd.DataFrame) -> None:
        casos_log = redes.casos_log_ordenados(serie)
        red, escalador, detalles = redes.entrenar_red(self._construir_red, casos_log, self.hiperparametros)
        self.red = red
        self.escalador = escalador
        self._detalles = detalles

    def detalles_entrenamiento(self) -> dict:
        return dict(self._detalles)

    def pronosticar_trayectorias(self, serie: pd.DataFrame, origenes: list[int], horizonte: int) -> np.ndarray:
        casos_log = redes.casos_log_ordenados(serie)
        ventana = self.hiperparametros["ventana_semanas"]
        return redes.trayectorias_red(self.red, self.escalador, casos_log, origenes, ventana, horizonte)

    def guardar(self, carpeta: Path) -> list[str]:
        carpeta.mkdir(parents=True, exist_ok=True)
        self.red.save(carpeta / _ARCHIVO_RED)
        archivo_escalador = self.escalador.guardar(carpeta)
        return [_ARCHIVO_RED, archivo_escalador]

    def cargar(self, carpeta: Path) -> None:
        import keras

        self.red = keras.models.load_model(carpeta / _ARCHIVO_RED)
        self.escalador = redes.EscaladorMinMax.cargar(carpeta)
