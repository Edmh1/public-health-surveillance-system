"""SARIMA sobre log1p(casos), con estacionalidad anual de 52 semanas (notebook
05, seccion 7.3). Familia estadistica.

Misma implementacion que ARIMA; solo cambia el orden estacional. El valor por
defecto es lo que encontro auto_arima en el notebook 05 sin clima:
(2, 1, 2)(0, 0, 0, 52). Con ese orden el termino estacional queda en cero y
SARIMA da lo mismo que ARIMA (el notebook lo documenta: sin exogenas la
estacionalidad anual no aparece como estructura ARMA). Queda como candidato para
que la experimentacion pruebe otros ordenes estacionales.
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
