"""Prophet-AR: estacionalidad anual de Prophet + rezagos de log1p(casos) como
regresores. Familia estadistica.

Trabaja en escala log1p. En el pronostico multipaso los rezagos que caen dentro
del horizonte se completan con la propia prediccion. El conjunto de rezagos y los
parametros de Prophet son hiperparametros que elige la experimentacion con Optuna
(notebook 06 del repositorio de experimentacion); los valores por defecto solo son
el punto de partida.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico.configuracion import FAMILIA_ESTADISTICO
from pathologies.dengue.pronostico.recursivo import (
    nombre_columna_rezago,
    tabla_de_rezagos,
    trayectorias_con_rezagos,
)

_ARCHIVO_MODELO = "prophet.json"


class ProphetAR(ModeloPronostico):
    clave = "prophet_ar"
    nombre = "Prophet-AR"
    familia = FAMILIA_ESTADISTICO
    paquetes_requeridos = ("prophet",)
    archivos_exportados = {
        _ARCHIVO_MODELO: "Modelo Prophet serializado con prophet.serialize.model_to_json (JSON).",
    }
    hiperparametros_por_defecto = {
        "rezagos": [1, 2, 4, 8],
        "estacionalidad_anual": True,
        "modo_estacionalidad": "additive",
        "changepoint_prior_scale": 0.05,
        "seasonality_prior_scale": 10.0,
    }

    def __init__(self, hiperparametros=None):
        super().__init__(hiperparametros)
        self.estimador = None

    def _nombres_regresores(self) -> dict[str, str]:
        """Columna de rezago -> nombre del regresor en Prophet. Los regresores
        llevan el sufijo _log (estan en escala log1p). Las versiones guardadas
        dependen de estos nombres: cambiarlos impide cargarlas."""
        nombres = {}
        for rezago in self.hiperparametros["rezagos"]:
            columna = nombre_columna_rezago(rezago)
            nombres[columna] = f"{columna}_log"
        return nombres

    def entrenar(self, serie: pd.DataFrame) -> None:
        from prophet import Prophet

        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos_log = np.log1p(serie_ordenada["casos"].to_numpy(dtype=float))
        rezagos = self.hiperparametros["rezagos"]
        tabla = tabla_de_rezagos(casos_log, rezagos)

        # tabla_de_rezagos descarta las primeras max(rezagos) filas; las fechas
        # se alinean descartando las mismas.
        fechas = serie_ordenada["fecha_semana"].iloc[max(rezagos):].reset_index(drop=True)
        datos_entrenamiento = tabla.rename(columns={"objetivo": "y"})
        datos_entrenamiento = datos_entrenamiento.rename(columns=self._nombres_regresores())
        datos_entrenamiento["ds"] = fechas

        modelo = Prophet(
            yearly_seasonality=self.hiperparametros["estacionalidad_anual"],
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode=self.hiperparametros["modo_estacionalidad"],
            changepoint_prior_scale=self.hiperparametros["changepoint_prior_scale"],
            seasonality_prior_scale=self.hiperparametros["seasonality_prior_scale"],
        )
        for regresor in self._nombres_regresores().values():
            modelo.add_regressor(regresor)
        modelo.fit(datos_entrenamiento)
        self.estimador = modelo

    def pronosticar_trayectorias(self, serie: pd.DataFrame, origenes: list[int], horizonte: int) -> np.ndarray:
        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos_log = np.log1p(serie_ordenada["casos"].to_numpy(dtype=float))
        fechas = pd.to_datetime(serie_ordenada["fecha_semana"]).tolist()

        def predecir_paso(entrada: pd.DataFrame, paso: int) -> np.ndarray:
            fechas_objetivo = [fechas[origen] + pd.Timedelta(weeks=paso) for origen in origenes]
            entrada_prophet = entrada.rename(columns=self._nombres_regresores())
            entrada_prophet["ds"] = fechas_objetivo
            # Prophet reordena por ds al predecir; se vuelve a alinear por fecha
            # (las fechas objetivo de un mismo paso son unicas, una por origen).
            prediccion = self.estimador.predict(entrada_prophet)
            yhat_por_fecha = prediccion.set_index("ds")["yhat"]
            yhat_log = yhat_por_fecha.reindex(pd.DatetimeIndex(fechas_objetivo)).to_numpy()
            return np.maximum(yhat_log, 0.0)

        trayectorias_log = trayectorias_con_rezagos(
            casos_log, origenes, self.hiperparametros["rezagos"], horizonte, predecir_paso
        )
        return np.expm1(trayectorias_log)

    def guardar(self, carpeta: Path) -> list[str]:
        from prophet.serialize import model_to_json

        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / _ARCHIVO_MODELO
        ruta.write_text(model_to_json(self.estimador), encoding="utf-8")
        return [_ARCHIVO_MODELO]

    def cargar(self, carpeta: Path) -> None:
        from prophet.serialize import model_from_json

        contenido = (carpeta / _ARCHIVO_MODELO).read_text(encoding="utf-8")
        self.estimador = model_from_json(contenido)
