"""LightGBM sobre rezagos de casos. Familia de aprendizaje automatico. Mismas
entradas que XGBoost. Los rezagos y los demas hiperparametros los elige la
experimentacion con Optuna (notebook 06 del repositorio de experimentacion); los
valores por defecto solo son el punto de partida.

El archivo no se llama lightgbm.py para no tapar la libreria lightgbm al importarla.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico.configuracion import FAMILIA_APRENDIZAJE_AUTOMATICO
from pathologies.dengue.pronostico.recursivo import (
    TRANSFORMACION_NINGUNA,
    destransformar,
    nombre_columna_rezago,
    tabla_de_rezagos,
    trayectorias_con_rezagos,
    transformar,
)

_ARCHIVO_MODELO = "lightgbm.txt"


class LightGBMRezagos(ModeloPronostico):
    clave = "lightgbm"
    nombre = "LightGBM"
    familia = FAMILIA_APRENDIZAJE_AUTOMATICO
    paquetes_requeridos = ("lightgbm",)
    archivos_exportados = {
        _ARCHIVO_MODELO: "Árboles de LightGBM guardados con Booster.save_model (texto).",
    }
    hiperparametros_por_defecto = {
        "rezagos": [1, 2, 4, 8],
        "transformacion": TRANSFORMACION_NINGUNA,
        "num_leaves": 7,
        "learning_rate": 0.03,
        "n_estimators": 200,
        "min_child_samples": 10,
        "subsample": 0.8,
        "subsample_freq": 1,
        "colsample_bytree": 0.8,
        "reg_lambda": 3,
        "random_state": 42,
    }

    def __init__(self, hiperparametros=None):
        super().__init__(hiperparametros)
        # Se guarda el Booster (no el LGBMRegressor): es lo que se exporta y
        # se vuelve a cargar, asi entrenado y cargado predicen por el mismo camino.
        self.booster = None

    def _columnas_rezago(self) -> list[str]:
        return [nombre_columna_rezago(rezago) for rezago in self.hiperparametros["rezagos"]]

    def entrenar(self, serie: pd.DataFrame) -> None:
        from lightgbm import LGBMRegressor

        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos = serie_ordenada["casos"].to_numpy(dtype=float)
        valores = transformar(casos, self.hiperparametros["transformacion"])
        tabla = tabla_de_rezagos(valores, self.hiperparametros["rezagos"])

        modelo = LGBMRegressor(
            num_leaves=self.hiperparametros["num_leaves"],
            learning_rate=self.hiperparametros["learning_rate"],
            n_estimators=self.hiperparametros["n_estimators"],
            min_child_samples=self.hiperparametros["min_child_samples"],
            subsample=self.hiperparametros["subsample"],
            subsample_freq=self.hiperparametros["subsample_freq"],
            colsample_bytree=self.hiperparametros["colsample_bytree"],
            reg_lambda=self.hiperparametros["reg_lambda"],
            random_state=self.hiperparametros["random_state"],
            n_jobs=1,
            verbose=-1,
        )
        modelo.fit(tabla[self._columnas_rezago()], tabla["objetivo"])
        self.booster = modelo.booster_

    def pronosticar_trayectorias(self, serie: pd.DataFrame, origenes: list[int], horizonte: int) -> np.ndarray:
        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos = serie_ordenada["casos"].to_numpy(dtype=float)
        transformacion = self.hiperparametros["transformacion"]
        valores = transformar(casos, transformacion)
        columnas = self._columnas_rezago()

        def predecir_paso(entrada: pd.DataFrame, paso: int) -> np.ndarray:
            prediccion = self.booster.predict(entrada[columnas])
            return np.maximum(prediccion, 0.0)

        trayectorias = trayectorias_con_rezagos(
            valores, origenes, self.hiperparametros["rezagos"], horizonte, predecir_paso
        )
        return destransformar(trayectorias, transformacion)

    def guardar(self, carpeta: Path) -> list[str]:
        carpeta.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(carpeta / _ARCHIVO_MODELO))
        return [_ARCHIVO_MODELO]

    def cargar(self, carpeta: Path) -> None:
        from lightgbm import Booster

        self.booster = Booster(model_file=str(carpeta / _ARCHIVO_MODELO))
