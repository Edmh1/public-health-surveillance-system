"""Pronostico semanal de casos de dengue a nivel departamental (Magdalena).

Reproduce el modelo elegido en el documento tecnico de modelado (repo de
modelado, notebooks 03_dengue_modeling y 05_dengue_ablacion_clima_vs_lags):
Prophet-AR sin variables climaticas, es decir estacionalidad anual mas
regresores autorregresivos de los rezagos 1, 2, 4 y 8 semanas de log1p(casos).
Es el modelo con menor dependencia del clima de las 6 familias evaluadas
(SARIMAX, Prophet, XGBoost, LightGBM, LSTM, N-BEATS) y el de mejor desempeño
sin clima a partir de 2 semanas de horizonte. Horizonte operativo: hasta 4
semanas (mas alla de eso la exactitud absoluta cae por debajo de un umbral
util y el documento no lo recomienda).

Serie DEPARTAMENTAL unica (Magdalena completo): el modelo se valido a esa
escala, sin desagregacion por subregion, asi que este modulo (y la pestaña
Pronostico que lo consume) no depende de los filtros geograficos globales.

Casos = cod_eve en {210, 220}, igual que canal_endemico.py.

Modulo de calculo puro: sin Streamlit. El cache (entrenar es lo caro, unos
segundos) vive en la vista, ver views/pronostico.py.

Pronostico recursivo multi-paso: para la semana o+k, los rezagos que ya
ocurrieron usan el caso real; los rezagos que caen DENTRO del horizonte
pronosticado se realimentan con la propia prediccion del modelo (misma logica
que path_prophet_ms en el notebook 05, seccion 9, la evaluacion honesta
walk-forward que valida el documento tecnico). Por eso la banda de
incertidumbre de cada semana solo refleja la incertidumbre de ESE paso: no
acumula el error de los pasos anteriores que se usaron como insumo.
"""

from datetime import timedelta

import numpy as np
import pandas as pd
from epiweeks import Week
from prophet import Prophet

CODIGOS_CASOS = {210, 220}

# Mismos rezagos (en semanas) que el Prophet-AR validado en el documento tecnico.
LAGS_TARGET = [1, 2, 4, 8]

# Horizonte operativo recomendado por el documento tecnico (seccion 8): mas alla
# de 4 semanas la exactitud absoluta cae de forma notoria (MAPE ~35%) y varias
# familias alternativas fallan frente a la persistencia, asi que no se ofrece.
HORIZONTE_MAXIMO_SEMANAS = 4

# Prophet necesita historia suficiente para estimar una estacionalidad ANUAL
# confiable; menos de ~2 anios no alcanza a cubrir ni dos ciclos completos.
# Cuenta doble margen: el span real de entrenamiento es MENOR que esta
# cantidad de semanas, porque entrenar_modelo descarta las primeras
# max(LAGS_TARGET)=8 filas (dropna de las columnas de rezago) antes de
# entrenar, y el span temporal de N puntos semanales es (N-1)*7 dias, no N*7.
# Prophet mismo advierte por debajo de 730 dias; 120 semanas deja margen
# comodo despues de ambos descuentos.
SEMANAS_MINIMAS_ENTRENAMIENTO = 120


def construir_serie_semanal_departamental(datos: pd.DataFrame) -> pd.DataFrame:
    """Serie semanal CONTINUA de casos de dengue (210+220) a nivel Magdalena
    completo, por semana epidemiologica (convencion CDC, inicio domingo, igual
    que el resto del sistema). Reindexa sobre TODAS las semanas del rango (de la
    primera a la ultima con datos), rellenando con 0 las semanas sin casos
    notificados: Prophet necesita una serie sin huecos para estimar
    correctamente la estacionalidad anual, y una semana sin casos es un dato
    real (no informacion faltante), igual que en canal_endemico._tabla_anio_semana.

    Devuelve columnas: fecha_semana (datetime, inicio domingo CDC), ano, semana, casos.
    Vacio si no hay casos en datos.
    """
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]
    if casos.empty:
        return pd.DataFrame(columns=["fecha_semana", "ano", "semana", "casos"])

    conteo = casos.groupby(["ano", "semana"]).size().reset_index(name="casos")
    conteo["ano"] = conteo["ano"].astype(int)
    conteo["semana"] = conteo["semana"].astype(int)
    conteo["fecha_semana"] = conteo.apply(
        lambda fila: pd.Timestamp(Week(fila["ano"], fila["semana"], system="CDC").startdate()),
        axis=1,
    )
    conteo = conteo.sort_values("fecha_semana").reset_index(drop=True)

    rango_completo = pd.date_range(conteo["fecha_semana"].min(), conteo["fecha_semana"].max(), freq="7D")
    serie = pd.DataFrame({"fecha_semana": rango_completo})
    serie = serie.merge(conteo[["fecha_semana", "casos"]], on="fecha_semana", how="left")
    serie["casos"] = serie["casos"].fillna(0).astype(int)
    serie["ano"] = serie["fecha_semana"].apply(lambda f: Week.fromdate(f.date(), system="CDC").year)
    serie["semana"] = serie["fecha_semana"].apply(lambda f: Week.fromdate(f.date(), system="CDC").week)
    return serie[["fecha_semana", "ano", "semana", "casos"]]


def _construir_columnas_ar(serie: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    base = serie.set_index("fecha_semana").sort_index().copy()
    base["casos_log"] = np.log1p(base["casos"])
    columnas_ar = []
    for rezago in LAGS_TARGET:
        columna = f"casos_lag{rezago}_log"
        base[columna] = base["casos_log"].shift(rezago)
        columnas_ar.append(columna)
    return base, columnas_ar


def entrenar_modelo(serie: pd.DataFrame) -> Prophet | None:
    """Entrena Prophet-AR (estacionalidad anual + regresores de rezago 1, 2, 4 y
    8 semanas de log1p(casos), sin clima) sobre TODA la serie disponible.

    A diferencia de la validacion del documento tecnico (que reservo 15% de
    prueba para medir desempeno honesto sobre datos nunca vistos), el modelo en
    produccion se entrena con el 100% del historico disponible: el objetivo aca
    es maximizar la exactitud del pronostico real, no medir desempeno. Los
    R2/RMSE/MAE que se citan en el dialogo de fundamentacion de la pestana son
    los de esa evaluacion honesta del documento, no se recalculan en produccion.

    None si no hay suficiente historia (ver SEMANAS_MINIMAS_ENTRENAMIENTO):
    nunca se fuerza un ajuste con menos historia de la que Prophet necesita
    para estimar una estacionalidad anual real.
    """
    if len(serie) < SEMANAS_MINIMAS_ENTRENAMIENTO:
        return None

    base, columnas_ar = _construir_columnas_ar(serie)
    entrenamiento = base.dropna(subset=columnas_ar).reset_index()
    datos_entrenamiento = entrenamiento[["fecha_semana", "casos_log"] + columnas_ar].rename(
        columns={"fecha_semana": "ds", "casos_log": "y"}
    )

    modelo = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
    for columna in columnas_ar:
        modelo.add_regressor(columna)
    modelo.fit(datos_entrenamiento)
    return modelo


def pronosticar(
    modelo: Prophet, serie: pd.DataFrame, horizonte_semanas: int = HORIZONTE_MAXIMO_SEMANAS
) -> pd.DataFrame:
    """Pronostico recursivo de las proximas horizonte_semanas semanas (ver
    docstring del modulo). Devuelve columnas: fecha_semana, ano, semana,
    horizonte_semanas (1..horizonte_semanas), casos_pronosticados, casos_min,
    casos_max (banda de incertidumbre del propio Prophet, intervalo 80% por
    defecto de esa unica semana, no acumulada).
    """
    base, _ = _construir_columnas_ar(serie)
    casos_log = base["casos_log"].to_numpy()
    ultima_fecha = base.index.max()
    rezago_maximo = max(LAGS_TARGET)
    n = len(casos_log)
    origen = n - 1

    historial_log = {posicion: casos_log[posicion] for posicion in range(origen - rezago_maximo, origen + 1)}

    filas = []
    for paso in range(1, horizonte_semanas + 1):
        posicion_objetivo = origen + paso
        fecha_objetivo = ultima_fecha + timedelta(weeks=paso)
        fila_entrada = {"ds": fecha_objetivo}
        for rezago in LAGS_TARGET:
            fila_entrada[f"casos_lag{rezago}_log"] = historial_log[posicion_objetivo - rezago]

        prediccion = modelo.predict(pd.DataFrame([fila_entrada]))
        yhat_log = float(prediccion["yhat"].iloc[0])
        yhat_inferior_log = float(prediccion["yhat_lower"].iloc[0])
        yhat_superior_log = float(prediccion["yhat_upper"].iloc[0])

        # Realimentacion: la propia prediccion pasa a ser el "rezago conocido"
        # para pasos siguientes que la necesiten (ver docstring del modulo).
        historial_log[posicion_objetivo] = yhat_log

        filas.append({
            "fecha_semana": fecha_objetivo,
            "horizonte_semanas": paso,
            "casos_pronosticados": max(float(np.expm1(yhat_log)), 0.0),
            "casos_min": max(float(np.expm1(yhat_inferior_log)), 0.0),
            "casos_max": max(float(np.expm1(yhat_superior_log)), 0.0),
        })

    pronostico = pd.DataFrame(filas)
    pronostico["ano"] = pronostico["fecha_semana"].apply(lambda f: Week.fromdate(f.date(), system="CDC").year)
    pronostico["semana"] = pronostico["fecha_semana"].apply(lambda f: Week.fromdate(f.date(), system="CDC").week)
    return pronostico[
        ["fecha_semana", "ano", "semana", "horizonte_semanas", "casos_pronosticados", "casos_min", "casos_max"]
    ]
