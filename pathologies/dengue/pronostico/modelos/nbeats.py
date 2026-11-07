"""N-BEATS (version generica) sobre una ventana de log1p(casos). Familia de
aprendizaje profundo.

Escrito en Keras (el mismo framework de la LSTM) para no sumar PyTorch y darts
a la imagen. Reproduce la arquitectura generica de darts.NBEATSModel que uso el
notebook 05: num_pilas pilas de bloques_por_pila bloques; cada bloque es una
pila de capas densas ReLU que produce coeficientes (dimension_expansion) para un
"backcast" (lo que el bloque explica de la ventana, que se resta antes del
bloque siguiente) y un aporte al pronostico (que se suma). Salida de una semana
y pronostico recursivo, igual que output_chunk_length=1 del notebook.

Valores por defecto: los que encontro la busqueda del notebook 05 sin clima
(ventana 12, 1 bloque, 2 capas, ancho 128) y los valores por defecto de darts
(30 pilas, dimension de expansion 5, Adam con tasa 0.001, perdida MSE, parada
temprana con paciencia 20) y dropout 0.0.

A diferencia de darts, la ventana se escala con el mismo min-max de la LSTM
(pronostico/redes.py): las dos redes se entrenan y evaluan de la misma forma.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico import redes
from pathologies.dengue.pronostico.configuracion import FAMILIA_APRENDIZAJE_PROFUNDO

_ARCHIVO_RED = "nbeats.keras"


class NBeats(ModeloPronostico):
    clave = "nbeats"
    nombre = "N-BEATS"
    familia = FAMILIA_APRENDIZAJE_PROFUNDO
    paquetes_requeridos = ("tensorflow", "keras")
    archivos_exportados = {
        _ARCHIVO_RED: "Red N-BEATS guardada con model.save de Keras 3 (.keras).",
        redes.ARCHIVO_ESCALADOR: "Mínimo y máximo de log1p(casos) con que se escala la ventana de entrada (JSON).",
    }
    hiperparametros_por_defecto = {
        "ventana_semanas": 12,
        "num_pilas": 30,
        "bloques_por_pila": 1,
        "capas_por_bloque": 2,
        "ancho_capa": 128,
        "dimension_expansion": 5,
        "dropout": 0.0,
        "tasa_aprendizaje": 0.001,
        "perdida": "mse",
        "batch_size": 16,
        "epocas_maximas": 200,
        "fraccion_validacion": 0.15,
        "paciencia": 20,
        "paciencia_tasa_aprendizaje": None,
        "semilla": 42,
    }

    def __init__(self, hiperparametros=None):
        super().__init__(hiperparametros)
        self.red = None
        self.escalador = None
        self._detalles = {}

    def _construir_red(self):
        import keras

        configuracion = self.hiperparametros
        ventana = configuracion["ventana_semanas"]
        cantidad_bloques = configuracion["num_pilas"] * configuracion["bloques_por_pila"]

        entrada = keras.Input(shape=(ventana,))
        residuo = entrada
        aportes_pronostico = []
        for _ in range(cantidad_bloques):
            oculta = residuo
            for _ in range(configuracion["capas_por_bloque"]):
                oculta = keras.layers.Dense(configuracion["ancho_capa"], activation="relu")(oculta)
                if configuracion["dropout"] > 0:
                    oculta = keras.layers.Dropout(configuracion["dropout"])(oculta)
            theta_backcast = keras.layers.Dense(configuracion["dimension_expansion"], use_bias=False)(oculta)
            theta_pronostico = keras.layers.Dense(configuracion["dimension_expansion"], use_bias=False)(oculta)
            backcast = keras.layers.Dense(ventana)(theta_backcast)
            aporte = keras.layers.Dense(1)(theta_pronostico)
            residuo = keras.layers.Subtract()([residuo, backcast])
            aportes_pronostico.append(aporte)

        if len(aportes_pronostico) == 1:
            salida = aportes_pronostico[0]
        else:
            salida = keras.layers.Add()(aportes_pronostico)

        red = keras.Model(entrada, salida)
        optimizador = keras.optimizers.Adam(learning_rate=configuracion["tasa_aprendizaje"])
        red.compile(optimizer=optimizador, loss=configuracion["perdida"])
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
