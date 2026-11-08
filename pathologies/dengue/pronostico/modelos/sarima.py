"""SARIMA sobre log1p(casos), con estacionalidad anual de 52 semanas. Familia
estadistica.

Misma implementacion que ARIMA; solo cambia el orden estacional. Los ordenes
regular y estacional son hiperparametros que elige la experimentacion con Optuna
(notebook 06 del repositorio de experimentacion). El valor por defecto,
(2, 1, 2)(0, 0, 0, 52), es solo un punto de partida: con el orden estacional en
cero, SARIMA da lo mismo que ARIMA.
"""

from pathologies.dengue.pronostico.modelos.arima import Arima


class Sarima(Arima):
    clave = "sarima"
    nombre = "SARIMA"
    hiperparametros_por_defecto = {
        "orden": [2, 1, 2],
        "orden_estacional": [0, 0, 0, 52],
        "tendencia": "n",
    }
