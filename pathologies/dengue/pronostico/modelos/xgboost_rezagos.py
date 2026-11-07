"""XGBoost sobre rezagos de casos (notebook 05, seccion 7.5). Familia de
aprendizaje automatico.

Por defecto trabaja en escala original (como el notebook); el hiperparametro
transformacion permite probar log1p. Ojo: un modelo de arboles no predice por
encima del maximo que vio al entrenar, asi que un brote mas grande que todo el
historico queda subestimado.

El archivo no se llama xgboost.py para no tapar la libreria xgboost al importarla.
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

_ARCHIVO_MODELO = "xgboost.json"


class XGBoostRezagos(ModeloPronostico):
    clave = "xgboost"
    nombre = "XGBoost"
    familia = FAMILIA_APRENDIZAJE_AUTOMATICO
    paquetes_requeridos = ("xgboost",)
    archivos_exportados = {
        _ARCHIVO_MODELO: "Árboles de XGBoost guardados con save_model (JSON).",
    }
    hiperparametros_por_defecto = {
        "rezagos": [1, 2, 4, 8],
        "transformacion": TRANSFORMACION_NINGUNA,
        "learning_rate": 0.04,
        "max_depth": 2,
        "min_child_weight": 5,
        "n_estimators": 300,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_lambda": 3,
        "random_state": 42,
    }

    def __init__(self, hiperparametros=None):
        super().__init__(hiperparametros)
        self.estimador = None

    def _columnas_rezago(self) -> list[str]:
        return [nombre_columna_rezago(rezago) for rezago in self.hiperparametros["rezagos"]]

    def entrenar(self, serie: pd.DataFrame) -> None:
        from xgboost import XGBRegressor

        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos = serie_ordenada["casos"].to_numpy(dtype=float)
        valores = transformar(casos, self.hiperparametros["transformacion"])
        tabla = tabla_de_rezagos(valores, self.hiperparametros["rezagos"])

        modelo = XGBRegressor(
            learning_rate=self.hiperparametros["learning_rate"],
            max_depth=self.hiperparametros["max_depth"],
            min_child_weight=self.hiperparametros["min_child_weight"],
            n_estimators=self.hiperparametros["n_estimators"],
            subsample=self.hiperparametros["subsample"],
            colsample_bytree=self.hiperparametros["colsample_bytree"],
            reg_lambda=self.hiperparametros["reg_lambda"],
            random_state=self.hiperparametros["random_state"],
            n_jobs=1,
        )
        modelo.fit(tabla[self._columnas_rezago()], tabla["objetivo"])
        self.estimador = modelo

    def pronosticar_trayectorias(self, serie: pd.DataFrame, origenes: list[int], horizonte: int) -> np.ndarray:
        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos = serie_ordenada["casos"].to_numpy(dtype=float)
        transformacion = self.hiperparametros["transformacion"]
        valores = transformar(casos, transformacion)
        columnas = self._columnas_rezago()

        def predecir_paso(entrada: pd.DataFrame, paso: int) -> np.ndarray:
            prediccion = self.estimador.predict(entrada[columnas])
            return np.maximum(prediccion, 0.0)

        trayectorias = trayectorias_con_rezagos(
            valores, origenes, self.hiperparametros["rezagos"], horizonte, predecir_paso
        )
        return destransformar(trayectorias, transformacion)

    def guardar(self, carpeta: Path) -> list[str]:
        carpeta.mkdir(parents=True, exist_ok=True)
        self.estimador.save_model(carpeta / _ARCHIVO_MODELO)
        return [_ARCHIVO_MODELO]

    def cargar(self, carpeta: Path) -> None:
        from xgboost import XGBRegressor

        estimador = XGBRegressor()
        estimador.load_model(carpeta / _ARCHIVO_MODELO)
        self.estimador = estimador
