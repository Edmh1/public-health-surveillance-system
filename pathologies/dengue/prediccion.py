"""Pronostico semanal de casos de dengue a nivel departamental (Magdalena).

Tres modelos, uno por familia, sin variables climaticas. De cada familia va el
que mejor desempeno tuvo A MULTIPASO Y SIN CLIMA en el notebook 05 del
repositorio de modelado (05_dengue_ablacion_clima_vs_lags, evaluacion
walk-forward), que es el escenario operativo real del tablero:

- Estadistico de series de tiempo: Prophet-AR (estacionalidad anual + rezagos
  1, 2, 4 y 8 semanas de log1p(casos)). Descartado SARIMAX.
- Aprendizaje automatico: XGBoost sobre los rezagos 1, 2, 4 y 8 en escala
  original. Descartado LightGBM.
- Aprendizaje profundo: LSTM sobre una ventana de 12 semanas de log1p(casos).
  Descartado N-BEATS.

Prophet es el modelo por defecto: es el unico que se sostiene en todo el rango
de horizontes y el mejor a 4 semanas, el horizonte operativo.

Horizonte: hasta 6 semanas. El documento tecnico recomienda hasta 4; a partir de
la quinta el error crece de forma notoria (en la sexta, MAPE del 35 % y R2 de
0.62 contra 0.87 en la primera) y la vista lo avisa. La quinta semana no se
evaluo en el notebook, pero el pronostico recursivo la produce igual y su error
sale de la validacion que corre el propio sistema al entrenar
(evaluar_walk_forward).

Pronostico recursivo multipaso (misma logica que path_prophet_ms, _path_arbol y
path_lstm_ms del notebook 05): para la semana o+k, los rezagos que ya
ocurrieron usan el caso real y los que caen DENTRO del horizonte se realimentan
con la propia prediccion del modelo. Las trayectorias se calculan vectorizadas
por origen (todas las semanas de origen a la vez en cada paso), lo que da el
mismo resultado que recorrer origen por origen y vuelve barata la validacion.

Serie DEPARTAMENTAL unica (Magdalena completo): los modelos se validaron a esa
escala, sin desagregacion territorial, asi que la pestana Pronostico no depende
de los filtros geograficos globales. Casos = cod_eve en {210, 220}.

Modulo de calculo puro: sin Streamlit. TensorFlow/Keras se importa DENTRO de las
funciones de la LSTM y no al inicio del archivo, a proposito: importarlo tarda
del orden de decenas de segundos y la vista importa este modulo al arrancar el
dashboard; solo se paga ese costo cuando de verdad se usa la LSTM.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from epiweeks import Week
from prophet import Prophet
from prophet.serialize import model_from_json, model_to_json
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBRegressor

CODIGOS_CASOS = {210, 220}

MODELO_PROPHET = "prophet"
MODELO_XGBOOST = "xgboost"
MODELO_LSTM = "lstm"
MODELOS_DISPONIBLES = [MODELO_PROPHET, MODELO_XGBOOST, MODELO_LSTM]
MODELO_POR_DEFECTO = MODELO_PROPHET

# Rotulo de cada modelo con su familia, tal como se muestra en la pestana.
NOMBRES_MODELOS = {
    MODELO_PROPHET: "Prophet (estadístico)",
    MODELO_XGBOOST: "XGBoost (aprendizaje automático)",
    MODELO_LSTM: "LSTM (aprendizaje profundo)",
}

# Linea base de la validacion: pronosticar que todas las semanas siguientes
# repiten el ultimo valor observado.
PERSISTENCIA = "persistencia"

# Mismos rezagos (en semanas) que el notebook 05 para Prophet y XGBoost.
LAGS_TARGET = [1, 2, 4, 8]

# Ventana de entrada de la LSTM, en semanas.
VENTANA_LSTM = 12

HORIZONTE_MAXIMO_SEMANAS = 6
HORIZONTE_RECOMENDADO_SEMANAS = 4

# Prophet necesita historia suficiente para estimar una estacionalidad ANUAL
# confiable. El span real de entrenamiento es MENOR que esta cantidad de
# semanas, porque se descartan las primeras max(LAGS_TARGET)=8 filas (sin
# rezagos) y el span de N puntos semanales es (N-1)*7 dias, no N*7. Prophet
# advierte por debajo de 730 dias; 120 semanas deja margen comodo despues de
# ambos descuentos (104 y hasta 110 seguian disparando la advertencia).
SEMANAS_MINIMAS_ENTRENAMIENTO = 120

# Fraccion final de la serie que la validacion walk-forward reserva como prueba
# (los modelos de validacion nunca la ven al entrenar). Mismo 15 % de prueba del
# notebook 05.
FRACCION_PRUEBA_VALIDACION = 0.15

# Hiperparametros exactos de cada modelo, sin clima. Quedan en el manifest de
# cada entrenamiento exportado.
HIPERPARAMETROS = {
    MODELO_PROPHET: {
        "yearly_seasonality": True,
        "weekly_seasonality": False,
        "daily_seasonality": False,
        "regresores": [f"casos_lag{rezago}_log" for rezago in LAGS_TARGET],
        "escala_objetivo": "log1p(casos)",
    },
    MODELO_XGBOOST: {
        "learning_rate": 0.04,
        "max_depth": 2,
        "min_child_weight": 5,
        "n_estimators": 300,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_lambda": 3,
        "random_state": 42,
        "variables_entrada": [f"casos_lag{rezago}" for rezago in LAGS_TARGET],
        "escala_objetivo": "casos (escala original)",
    },
    MODELO_LSTM: {
        "ventana_semanas": VENTANA_LSTM,
        "unidades": [64, 16],
        "activacion": "tanh",
        "dropout": 0.2,
        "capa_salida": "Dense(1)",
        "optimizador": "rmsprop",
        "perdida": "mean_absolute_error",
        "batch_size": 16,
        "epocas": 40,
        "semilla": 42,
        "escalador": "MinMaxScaler sobre log1p(casos)",
    },
}

_COLUMNAS_XGBOOST = [f"casos_lag{rezago}" for rezago in LAGS_TARGET]
_COLUMNAS_PROPHET = [f"casos_lag{rezago}_log" for rezago in LAGS_TARGET]

_ARCHIVO_PROPHET = "prophet.json"
_ARCHIVO_XGBOOST = "xgboost.json"
_ARCHIVO_LSTM = "lstm.keras"
_ARCHIVO_ESCALADOR_LSTM = "lstm_escalador.joblib"


@dataclass
class ModeloEntrenado:
    """Un modelo listo para pronosticar. escalador solo lo usa la LSTM: sin el
    MinMaxScaler con el que se entreno, el modelo no sirve."""

    tipo: str
    estimador: Any
    escalador: Any = None


# ---------------------------------------------------------------------------
# Serie
# ---------------------------------------------------------------------------

def construir_serie_semanal_departamental(datos: pd.DataFrame) -> pd.DataFrame:
    """Serie semanal CONTINUA de casos de dengue (210+220) a nivel Magdalena
    completo, por semana epidemiologica (convencion CDC, inicio domingo, igual
    que el resto del sistema). Reindexa sobre TODAS las semanas del rango (de la
    primera a la ultima con datos), rellenando con 0 las semanas sin casos
    notificados: los modelos necesitan una serie sin huecos, y una semana sin
    casos es un dato real (no informacion faltante), igual que en
    canal_endemico._tabla_anio_semana.

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


def _agregar_semana_epidemiologica(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ano"] = df["fecha_semana"].apply(lambda f: Week.fromdate(f.date(), system="CDC").year)
    df["semana"] = df["fecha_semana"].apply(lambda f: Week.fromdate(f.date(), system="CDC").week)
    return df


# ---------------------------------------------------------------------------
# Entrenamiento
# ---------------------------------------------------------------------------

def entrenar_modelo(serie: pd.DataFrame, tipo: str = MODELO_POR_DEFECTO) -> ModeloEntrenado | None:
    """Entrena uno de los tres modelos sobre TODA la serie recibida (sin clima).

    None si no hay suficiente historia (ver SEMANAS_MINIMAS_ENTRENAMIENTO):
    nunca se fuerza un ajuste con menos historia de la que el modelo necesita.
    """
    if len(serie) < SEMANAS_MINIMAS_ENTRENAMIENTO:
        return None
    if tipo == MODELO_PROPHET:
        return _entrenar_prophet(serie)
    if tipo == MODELO_XGBOOST:
        return _entrenar_xgboost(serie)
    if tipo == MODELO_LSTM:
        return _entrenar_lstm(serie)
    raise ValueError(f"Modelo desconocido: {tipo}")


def _entrenar_prophet(serie: pd.DataFrame) -> ModeloEntrenado:
    base = serie.set_index("fecha_semana").sort_index().copy()
    base["casos_log"] = np.log1p(base["casos"].astype(float))
    for rezago in LAGS_TARGET:
        base[f"casos_lag{rezago}_log"] = base["casos_log"].shift(rezago)
    entrenamiento = base.dropna(subset=_COLUMNAS_PROPHET).reset_index()
    datos_entrenamiento = entrenamiento[["fecha_semana", "casos_log"] + _COLUMNAS_PROPHET].rename(
        columns={"fecha_semana": "ds", "casos_log": "y"}
    )

    configuracion = HIPERPARAMETROS[MODELO_PROPHET]
    modelo = Prophet(
        yearly_seasonality=configuracion["yearly_seasonality"],
        weekly_seasonality=configuracion["weekly_seasonality"],
        daily_seasonality=configuracion["daily_seasonality"],
    )
    for columna in _COLUMNAS_PROPHET:
        modelo.add_regressor(columna)
    modelo.fit(datos_entrenamiento)
    return ModeloEntrenado(tipo=MODELO_PROPHET, estimador=modelo)


def _entrenar_xgboost(serie: pd.DataFrame) -> ModeloEntrenado:
    """Misma construccion de variables que build_features del notebook 05:
    rezagos de casos en escala original (los arboles no usan log1p)."""
    base = serie.sort_values("fecha_semana").reset_index(drop=True)[["casos"]].astype(float)
    for rezago in LAGS_TARGET:
        base[f"casos_lag{rezago}"] = base["casos"].shift(rezago)
    entrenamiento = base.dropna().reset_index(drop=True)

    configuracion = HIPERPARAMETROS[MODELO_XGBOOST]
    modelo = XGBRegressor(
        learning_rate=configuracion["learning_rate"],
        max_depth=configuracion["max_depth"],
        min_child_weight=configuracion["min_child_weight"],
        n_estimators=configuracion["n_estimators"],
        subsample=configuracion["subsample"],
        colsample_bytree=configuracion["colsample_bytree"],
        reg_lambda=configuracion["reg_lambda"],
        random_state=configuracion["random_state"],
        n_jobs=1,
    )
    modelo.fit(entrenamiento[_COLUMNAS_XGBOOST], entrenamiento["casos"])
    return ModeloEntrenado(tipo=MODELO_XGBOOST, estimador=modelo)


def _construir_red_lstm():
    import keras

    configuracion = HIPERPARAMETROS[MODELO_LSTM]
    keras.utils.set_random_seed(configuracion["semilla"])
    unidades_primera, unidades_segunda = configuracion["unidades"]
    red = keras.Sequential([
        keras.Input(shape=(configuracion["ventana_semanas"], 1)),
        keras.layers.LSTM(unidades_primera, activation=configuracion["activacion"], return_sequences=True),
        keras.layers.Dropout(configuracion["dropout"]),
        keras.layers.LSTM(unidades_segunda, activation=configuracion["activacion"]),
        keras.layers.Dropout(configuracion["dropout"]),
        keras.layers.Dense(1),
    ])
    red.compile(optimizer=configuracion["optimizador"], loss=configuracion["perdida"])
    return red


def _entrenar_lstm(serie: pd.DataFrame) -> ModeloEntrenado:
    """Misma preparacion que preparar_lstm del notebook 05: log1p(casos),
    MinMaxScaler ajustado sobre la serie de entrenamiento, secuencias de 12
    semanas que predicen la semana siguiente."""
    configuracion = HIPERPARAMETROS[MODELO_LSTM]
    ventana = configuracion["ventana_semanas"]

    casos_log = np.log1p(serie.sort_values("fecha_semana")["casos"].to_numpy(dtype=float)).reshape(-1, 1)
    escalador = MinMaxScaler().fit(casos_log)
    escalados = escalador.transform(casos_log).flatten()

    secuencias = []
    objetivos = []
    for posicion in range(ventana, len(escalados)):
        secuencias.append(escalados[posicion - ventana:posicion])
        objetivos.append(escalados[posicion])
    entradas = np.array(secuencias).reshape(-1, ventana, 1)
    salidas = np.array(objetivos)

    red = _construir_red_lstm()
    red.fit(
        entradas,
        salidas,
        epochs=configuracion["epocas"],
        batch_size=configuracion["batch_size"],
        verbose=0,
    )
    return ModeloEntrenado(tipo=MODELO_LSTM, estimador=red, escalador=escalador)


# ---------------------------------------------------------------------------
# Trayectorias recursivas multipaso
# ---------------------------------------------------------------------------

def _historial_inicial(valores: np.ndarray, origenes: list[int], largo: int, horizonte: int) -> np.ndarray:
    """Matriz de trabajo de la recursion: una fila por origen. La columna j
    corresponde a la posicion (origen - largo + j) de la serie; las primeras
    largo+1 columnas son datos reales y las ultimas horizonte se van llenando
    con las predicciones (la realimentacion del pronostico recursivo)."""
    historial = np.full((len(origenes), largo + 1 + horizonte), np.nan)
    for fila, origen in enumerate(origenes):
        historial[fila, :largo + 1] = valores[origen - largo:origen + 1]
    return historial


def _trayectorias_prophet(modelo: ModeloEntrenado, casos, fechas, origenes, horizonte) -> np.ndarray:
    rezago_maximo = max(LAGS_TARGET)
    historial = _historial_inicial(np.log1p(casos), origenes, rezago_maximo, horizonte)
    trayectorias = np.zeros((len(origenes), horizonte))

    for paso in range(1, horizonte + 1):
        columna_objetivo = rezago_maximo + paso
        fechas_objetivo = [fechas[origen] + pd.Timedelta(weeks=paso) for origen in origenes]
        entrada = pd.DataFrame({"ds": fechas_objetivo})
        for rezago in LAGS_TARGET:
            entrada[f"casos_lag{rezago}_log"] = historial[:, columna_objetivo - rezago]

        # Prophet reordena por ds al predecir; se vuelve a alinear por fecha
        # (las fechas objetivo de un mismo paso son unicas, una por origen).
        prediccion = modelo.estimador.predict(entrada)
        yhat_por_fecha = prediccion.set_index("ds")["yhat"]
        yhat_log = yhat_por_fecha.reindex(pd.DatetimeIndex(fechas_objetivo)).to_numpy()

        historial[:, columna_objetivo] = yhat_log
        trayectorias[:, paso - 1] = np.maximum(np.expm1(yhat_log), 0.0)
    return trayectorias


def _trayectorias_xgboost(modelo: ModeloEntrenado, casos, origenes, horizonte) -> np.ndarray:
    rezago_maximo = max(LAGS_TARGET)
    historial = _historial_inicial(casos, origenes, rezago_maximo, horizonte)
    trayectorias = np.zeros((len(origenes), horizonte))

    for paso in range(1, horizonte + 1):
        columna_objetivo = rezago_maximo + paso
        entrada = pd.DataFrame({
            f"casos_lag{rezago}": historial[:, columna_objetivo - rezago] for rezago in LAGS_TARGET
        })
        prediccion = np.maximum(modelo.estimador.predict(entrada[_COLUMNAS_XGBOOST]), 0.0)
        historial[:, columna_objetivo] = prediccion
        trayectorias[:, paso - 1] = prediccion
    return trayectorias


def _trayectorias_lstm(modelo: ModeloEntrenado, casos, origenes, horizonte) -> np.ndarray:
    ventana = HIPERPARAMETROS[MODELO_LSTM]["ventana_semanas"]
    historial = _historial_inicial(np.log1p(casos), origenes, ventana - 1, horizonte)
    trayectorias = np.zeros((len(origenes), horizonte))
    cantidad_origenes = len(origenes)

    for paso in range(1, horizonte + 1):
        inicio = paso - 1
        columna_objetivo = inicio + ventana
        ventana_log = historial[:, inicio:columna_objetivo]
        ventana_escalada = modelo.escalador.transform(ventana_log.reshape(-1, 1))
        ventana_escalada = ventana_escalada.reshape(cantidad_origenes, ventana, 1)

        prediccion_escalada = modelo.estimador.predict(ventana_escalada, verbose=0).reshape(-1, 1)
        prediccion_log = modelo.escalador.inverse_transform(prediccion_escalada).flatten()

        historial[:, columna_objetivo] = prediccion_log
        trayectorias[:, paso - 1] = np.maximum(np.expm1(prediccion_log), 0.0)
    return trayectorias


def calcular_trayectorias(
    modelo: ModeloEntrenado, serie: pd.DataFrame, origenes: list[int], horizonte: int
) -> np.ndarray:
    """Pronostico recursivo de horizonte semanas desde cada posicion de origen
    de la serie (el origen es la ultima semana con dato real que el modelo ve).
    Devuelve una matriz (origenes x horizonte) en casos."""
    serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
    casos = serie_ordenada["casos"].to_numpy(dtype=float)
    fechas = pd.to_datetime(serie_ordenada["fecha_semana"]).tolist()
    if modelo.tipo == MODELO_PROPHET:
        return _trayectorias_prophet(modelo, casos, fechas, origenes, horizonte)
    if modelo.tipo == MODELO_XGBOOST:
        return _trayectorias_xgboost(modelo, casos, origenes, horizonte)
    if modelo.tipo == MODELO_LSTM:
        return _trayectorias_lstm(modelo, casos, origenes, horizonte)
    raise ValueError(f"Modelo desconocido: {modelo.tipo}")


def pronosticar(
    modelo: ModeloEntrenado, serie: pd.DataFrame, horizonte_semanas: int = HORIZONTE_RECOMENDADO_SEMANAS
) -> pd.DataFrame:
    """Interfaz comun de los tres modelos: pronostico de las proximas
    horizonte_semanas semanas desde la ultima semana de la serie. Devuelve
    columnas: fecha_semana, ano, semana, horizonte_semanas, casos_pronosticados.

    Sin banda de incertidumbre: solo Prophet la produce de forma nativa y
    mostrarla en uno de los tres modelos los haria ver de distinta calidad. La
    incertidumbre se expresa como el error esperado por horizonte, medido en la
    validacion walk-forward (igual de valida para los tres).
    """
    horizonte = int(min(max(horizonte_semanas, 1), HORIZONTE_MAXIMO_SEMANAS))
    serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
    origen = len(serie_ordenada) - 1
    trayectoria = calcular_trayectorias(modelo, serie_ordenada, [origen], horizonte)[0]

    ultima_fecha = pd.Timestamp(serie_ordenada["fecha_semana"].iloc[-1])
    pasos = list(range(1, horizonte + 1))
    pronostico = pd.DataFrame({
        "fecha_semana": [ultima_fecha + pd.Timedelta(weeks=paso) for paso in pasos],
        "horizonte_semanas": pasos,
        "casos_pronosticados": trayectoria,
    })
    pronostico = _agregar_semana_epidemiologica(pronostico)
    return pronostico[["fecha_semana", "ano", "semana", "horizonte_semanas", "casos_pronosticados"]]


# ---------------------------------------------------------------------------
# Metricas y validacion walk-forward
# ---------------------------------------------------------------------------

def calcular_metricas(valores_reales, valores_pronosticados) -> dict[str, float | None]:
    """RMSE, MAE, MAPE (%) y R2, igual que compute_metrics del notebook 05. El
    MAPE excluye las semanas con 0 casos reales (division por cero); None si
    todas son cero. R2 None con menos de 2 puntos (no esta definido)."""
    reales = np.asarray(valores_reales, dtype=float)
    pronosticados = np.asarray(valores_pronosticados, dtype=float)

    rmse = float(np.sqrt(mean_squared_error(reales, pronosticados)))
    mae = float(mean_absolute_error(reales, pronosticados))

    semanas_con_casos = reales != 0
    if semanas_con_casos.any():
        errores_relativos = np.abs((reales[semanas_con_casos] - pronosticados[semanas_con_casos]) / reales[semanas_con_casos])
        mape = float(np.mean(errores_relativos) * 100)
    else:
        mape = None

    r2 = float(r2_score(reales, pronosticados)) if len(reales) >= 2 else None

    return {
        "RMSE": round(rmse, 3),
        "MAE": round(mae, 3),
        "MAPE": round(mape, 2) if mape is not None else None,
        "R2": round(r2, 4) if r2 is not None else None,
    }


def evaluar_walk_forward(
    serie: pd.DataFrame,
    modelos: list[str] = MODELOS_DISPONIBLES,
    horizonte_maximo: int = HORIZONTE_MAXIMO_SEMANAS,
) -> dict[str, Any]:
    """Validacion walk-forward multipaso, mismo procedimiento que
    evaluar_multistep del notebook 05: se reserva el ultimo 15 % de la serie como
    prueba, se entrena cada modelo con el resto, y desde cada semana de origen se
    pronostican las horizonte_maximo semanas siguientes realimentando la propia
    prediccion (el modelo ve los casos reales hasta el origen, nunca los de las
    semanas que pronostica). Cada pronostico se compara con lo que paso.

    Incluye la persistencia como linea base. Devuelve:
    {"metricas": {modelo: {"1": {RMSE, MAE, MAPE, R2}, ..., "6": {...}}},
     "semanas_entrenamiento": n, "semanas_prueba": n, "origenes": n,
     "inicio_prueba": "AAAA-MM-DD", "fin_prueba": "AAAA-MM-DD"}

    Lanza ValueError si la parte de entrenamiento no alcanza el minimo.
    """
    serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
    cantidad_semanas = len(serie_ordenada)
    semanas_prueba = int(round(cantidad_semanas * FRACCION_PRUEBA_VALIDACION))
    primera_prueba = cantidad_semanas - semanas_prueba
    ultima_prueba = cantidad_semanas - 1

    if primera_prueba < SEMANAS_MINIMAS_ENTRENAMIENTO:
        raise ValueError(
            f"Histórico insuficiente para validar: hacen falta al menos "
            f"{SEMANAS_MINIMAS_ENTRENAMIENTO} semanas de entrenamiento antes del 15 % de "
            f"prueba, y hay {primera_prueba}."
        )

    rezago_necesario = max(max(LAGS_TARGET), VENTANA_LSTM - 1)
    origen_minimo = max(primera_prueba - horizonte_maximo, rezago_necesario)
    origenes = list(range(origen_minimo, ultima_prueba))
    casos_reales = serie_ordenada["casos"].to_numpy(dtype=float)
    serie_entrenamiento = serie_ordenada.iloc[:primera_prueba].reset_index(drop=True)

    trayectorias_por_modelo = {}
    trayectorias_por_modelo[PERSISTENCIA] = np.repeat(
        casos_reales[origenes].reshape(-1, 1), horizonte_maximo, axis=1
    )
    for tipo in modelos:
        modelo_validacion = entrenar_modelo(serie_entrenamiento, tipo)
        trayectorias_por_modelo[tipo] = calcular_trayectorias(
            modelo_validacion, serie_ordenada, origenes, horizonte_maximo
        )

    metricas = {}
    for nombre, trayectorias in trayectorias_por_modelo.items():
        metricas_modelo = {}
        for horizonte in range(1, horizonte_maximo + 1):
            reales = []
            pronosticados = []
            for fila, origen in enumerate(origenes):
                posicion_objetivo = origen + horizonte
                if posicion_objetivo < primera_prueba or posicion_objetivo > ultima_prueba:
                    continue
                reales.append(casos_reales[posicion_objetivo])
                pronosticados.append(trayectorias[fila, horizonte - 1])
            metricas_modelo[str(horizonte)] = calcular_metricas(reales, pronosticados)
        metricas[nombre] = metricas_modelo

    return {
        "metricas": metricas,
        "semanas_entrenamiento": int(primera_prueba),
        "semanas_prueba": int(semanas_prueba),
        "origenes": len(origenes),
        "inicio_prueba": serie_ordenada["fecha_semana"].iloc[primera_prueba].strftime("%Y-%m-%d"),
        "fin_prueba": serie_ordenada["fecha_semana"].iloc[ultima_prueba].strftime("%Y-%m-%d"),
    }


# ---------------------------------------------------------------------------
# Exportar y cargar
# ---------------------------------------------------------------------------

def guardar_modelo(modelo: ModeloEntrenado, carpeta: Path) -> list[str]:
    """Exporta un modelo entrenado. Prophet con su propio model_to_json (no
    pickle), XGBoost con save_model en JSON y la LSTM en formato .keras con su
    MinMaxScaler aparte (joblib). Devuelve los nombres de archivo escritos."""
    carpeta.mkdir(parents=True, exist_ok=True)
    if modelo.tipo == MODELO_PROPHET:
        ruta = carpeta / _ARCHIVO_PROPHET
        ruta.write_text(model_to_json(modelo.estimador), encoding="utf-8")
        return [_ARCHIVO_PROPHET]
    if modelo.tipo == MODELO_XGBOOST:
        modelo.estimador.save_model(carpeta / _ARCHIVO_XGBOOST)
        return [_ARCHIVO_XGBOOST]
    if modelo.tipo == MODELO_LSTM:
        modelo.estimador.save(carpeta / _ARCHIVO_LSTM)
        joblib.dump(modelo.escalador, carpeta / _ARCHIVO_ESCALADOR_LSTM)
        return [_ARCHIVO_LSTM, _ARCHIVO_ESCALADOR_LSTM]
    raise ValueError(f"Modelo desconocido: {modelo.tipo}")


def cargar_modelo(tipo: str, carpeta: Path) -> ModeloEntrenado:
    """Carga un modelo exportado por guardar_modelo. La LSTM importa Keras aqui
    (ver docstring del modulo)."""
    if tipo == MODELO_PROPHET:
        contenido = (carpeta / _ARCHIVO_PROPHET).read_text(encoding="utf-8")
        return ModeloEntrenado(tipo=MODELO_PROPHET, estimador=model_from_json(contenido))
    if tipo == MODELO_XGBOOST:
        estimador = XGBRegressor()
        estimador.load_model(carpeta / _ARCHIVO_XGBOOST)
        return ModeloEntrenado(tipo=MODELO_XGBOOST, estimador=estimador)
    if tipo == MODELO_LSTM:
        import keras

        red = keras.models.load_model(carpeta / _ARCHIVO_LSTM)
        escalador = joblib.load(carpeta / _ARCHIVO_ESCALADOR_LSTM)
        return ModeloEntrenado(tipo=MODELO_LSTM, estimador=red, escalador=escalador)
    raise ValueError(f"Modelo desconocido: {tipo}")


def leer_manifest(carpeta: Path) -> dict | None:
    ruta = carpeta / "manifest.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))
