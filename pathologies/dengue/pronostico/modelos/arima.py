"""ARIMA sobre log1p(casos) (notebook 05, seccion 7.2). Familia estadistica.

El orden por defecto es el que encontro auto_arima en el notebook 05 sin clima:
(2, 1, 2). La app no corre auto_arima (no depende de pmdarima): el orden es un
hiperparametro que se fija en la experimentacion.

El modelo entrenado son sus parametros estimados por maxima verosimilitud
(coeficientes AR y MA y la varianza de las innovaciones sigma2), que se exportan
en parametros_estimados.json; el orden (p, d, q) es un hiperparametro y va en el
manifest. Para pronosticar desde un origen se arma el mismo ARIMA con la serie
hasta ese origen y se aplica el filtro de Kalman con esos parametros fijos
(filter): no se vuelve a estimar nada. Es lo mismo que
results.apply(endog, refit=False) del notebook 05, y un JSON no se rompe entre
versiones de statsmodels como un pickle.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico.configuracion import FAMILIA_ESTADISTICO

_ARCHIVO_PARAMETROS = "parametros_estimados.json"


class Arima(ModeloPronostico):
    clave = "arima"
    nombre = "ARIMA"
    familia = FAMILIA_ESTADISTICO
    paquetes_requeridos = ("statsmodels",)
    archivos_exportados = {
        _ARCHIVO_PARAMETROS: (
            "Modelo entrenado: parámetros estimados por máxima verosimilitud (coeficientes AR y "
            "MA y varianza de las innovaciones sigma2), con sus nombres (JSON). El orden (p, d, q) "
            "es un hiperparámetro y va en el manifest."
        ),
    }
    hiperparametros_por_defecto = {
        "orden": [2, 1, 2],
        "orden_estacional": [0, 0, 0, 0],
        "tendencia": "n",
    }

    def __init__(self, hiperparametros=None):
        super().__init__(hiperparametros)
        self.parametros = None
        self.nombres_parametros = None

    def _especificacion(self, valores_log: np.ndarray):
        from statsmodels.tsa.arima.model import ARIMA

        return ARIMA(
            valores_log,
            order=tuple(self.hiperparametros["orden"]),
            seasonal_order=tuple(self.hiperparametros["orden_estacional"]),
            trend=self.hiperparametros["tendencia"],
            enforce_stationarity=False,
            enforce_invertibility=False,
        )

    def entrenar(self, serie: pd.DataFrame) -> None:
        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos_log = np.log1p(serie_ordenada["casos"].to_numpy(dtype=float))
        resultado = self._especificacion(casos_log).fit()
        self.parametros = np.asarray(resultado.params, dtype=float)
        self.nombres_parametros = list(resultado.model.param_names)

    def pronosticar_trayectorias(self, serie: pd.DataFrame, origenes: list[int], horizonte: int) -> np.ndarray:
        serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
        casos_log = np.log1p(serie_ordenada["casos"].to_numpy(dtype=float))
        trayectorias = np.zeros((len(origenes), horizonte))
        for fila, origen in enumerate(origenes):
            historia = casos_log[:origen + 1]
            filtrado = self._especificacion(historia).filter(self.parametros)
            pronostico_log = np.asarray(filtrado.forecast(steps=horizonte), dtype=float)
            trayectorias[fila, :] = np.maximum(np.expm1(pronostico_log), 0.0)
        return trayectorias

    def guardar(self, carpeta: Path) -> list[str]:
        carpeta.mkdir(parents=True, exist_ok=True)
        contenido = {
            "nombres": self.nombres_parametros,
            "valores": [float(valor) for valor in self.parametros],
        }
        ruta = carpeta / _ARCHIVO_PARAMETROS
        ruta.write_text(json.dumps(contenido, indent=2), encoding="utf-8")
        return [_ARCHIVO_PARAMETROS]

    def cargar(self, carpeta: Path) -> None:
        contenido = json.loads((carpeta / _ARCHIVO_PARAMETROS).read_text(encoding="utf-8"))
        self.nombres_parametros = contenido["nombres"]
        self.parametros = np.asarray(contenido["valores"], dtype=float)
