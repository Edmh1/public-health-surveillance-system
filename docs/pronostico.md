# Pronóstico de casos de dengue: documentación técnica

Este documento es la fuente central del sistema de pronóstico de SIVIDEM. La pestaña Pronóstico muestra estas mismas secciones en su diálogo de Fundamentación; donde aparece un comentario de la forma app:nombre, la aplicación inserta una gráfica o una tabla calculada con los datos del modelo activo. La metodología de experimentación con que se eligen los modelos está en METODOLOGIA_PRONOSTICO.md del repositorio dengue-surveillance-magdalena.

El código está en pathologies/dengue/pronostico (cálculo, sin interfaz), core/storage/modelos.py (versiones), core/ingestion/entrenamiento.py (trabajos del procesador), core/dashboard_base/gestion_entrenamiento.py (Gestión) y pathologies/dengue/views/pronostico.py (pestaña).

## 1. Resumen del sistema de pronóstico

El tablero pronostica los casos notificados de dengue y dengue grave (códigos 210 y 220, probables y confirmados) del departamento del Magdalena, semana a semana, de 1 a 6 semanas hacia adelante. La serie es departamental y no depende de los filtros de la barra lateral.

Hay un modelo activo por cada familia (estadística, aprendizaje automático y aprendizaje profundo). Cada modelo activo es una versión: un modelo definitivo entrenado con todas las semanas de su rango, acompañado de la evaluación que se hizo antes de entrenarlo. Las versiones se crean en Gestión, entrenándolas en el tablero o subiendo un paquete .zip entrenado en otro equipo con el mismo código.

La pestaña ofrece dos vistas que no se deben confundir:

- Pronóstico en vivo: las próximas 6 semanas, calculadas por el modelo definitivo a partir de los casos reales hasta la última semana cargada. Lo acompañan las métricas que tuvo el procedimiento en la prueba, como referencia del error esperado por horizonte.
- Pronóstico de una semana pasada: los pronósticos individuales que se hicieron durante la evaluación, en semanas que el modelo de evaluación no había visto, comparados con lo que pasó.

## 2. Familias de modelos

| Familia | Candidatos | Librería |
|---|---|---|
| Estadística | ARIMA, SARIMA, Prophet-AR | statsmodels, prophet |
| Aprendizaje automático | XGBoost, LightGBM | xgboost, lightgbm |
| Aprendizaje profundo | LSTM, N-BEATS | tensorflow y keras |

Ninguno usa variables climáticas (sección 14). ARIMA y SARIMA trabajan sobre log1p(casos). Prophet-AR combina la estacionalidad anual de Prophet con los casos de 1, 2, 4 y 8 semanas atrás en escala log1p. XGBoost y LightGBM usan esos mismos rezagos. LSTM y N-BEATS reciben las últimas 12 semanas de log1p(casos) escaladas entre 0 y 1.

Se muestra el mejor modelo de cada familia para comparar enfoques distintos sobre la misma serie: uno que modela la estructura temporal de forma explícita, uno que aprende relaciones no lineales entre rezagos y uno que aprende patrones de secuencias. Cuál ocupa cada familia se decide en la experimentación (sección 15) y lo activa el perfil de administración.

## 3. Ciclo de vida: entrenamiento, evaluación, exportación, importación e inferencia

<!-- app:diagrama_ciclo_de_vida -->

A. Entrenamiento. Desde Gestión se elige el modelo, el rango de semanas y los hiperparámetros, y el procesador ejecuta el trabajo. Fuera de la aplicación se hace lo mismo llamando al código del proyecto (sección 16).

B. Evaluación. Antes del modelo definitivo, se entrena un modelo de evaluación con el primer 85 % del rango y se pronostica desde cada semana de origen del 15 % final (sección 7). Los resultados individuales se guardan en pronosticos_prueba.csv y desde ellos se calculan las métricas.

C. Exportación. Se entrena el modelo definitivo con el 100 % del rango y se guarda en el formato nativo de su librería, junto con manifest.json y el CSV de la prueba. En la aplicación esto queda como una versión en data/dengue/modelos/modelo/version; fuera de ella se empaqueta en un .zip. Ambos caminos usan la misma función: paquete.entrenar_evaluar_y_guardar.

D. Importación. Al subir un .zip, el procesador lo descomprime de forma segura y lo revisa (sección 5): formato del manifest, serie, modelo y familia, librerías y versiones, archivos, que las métricas del manifest se reconstruyan desde el CSV, y que el modelo cargue y produzca un pronóstico válido. No entrena, no optimiza ni vuelve a evaluar.

E. Inferencia. Para el pronóstico en vivo, la pestaña carga el modelo definitivo (una vez por versión) y le pide las próximas 6 semanas. No ejecuta fit, Optuna ni ningún entrenamiento. Todas las familias responden a la misma interfaz, ModeloPronostico.pronosticar_trayectorias, así que la pestaña no necesita saber si detrás hay Keras, Prophet, XGBoost, LightGBM o statsmodels.

Las únicas etapas que entrenan son A y B, y lo hacen una vez por versión: el modelo de evaluación (85 %) y el modelo definitivo (100 %).

## 4. Formatos de serialización e importación por modelo

Hay cuatro cosas distintas que no se deben confundir:

- El paquete .zip: un contenedor estandarizado con todos los archivos de una versión (sección 5).
- El archivo nativo del modelo entrenado: contiene lo que el modelo aprendió (pesos, árboles, coeficientes o parámetros ajustados), guardado con la función de su propia librería.
- Los archivos auxiliares: lo que hace falta para preparar los datos de entrada; por ejemplo, el escalador de las redes.
- Los hiperparámetros: la configuración elegida antes de entrenar (orden del ARIMA, rezagos, número de árboles, capas). Van en el manifest y sirven para reconstruir el modelo al cargarlo, pero no contienen lo aprendido.

| Modelo | Familia | Librería | Archivo del modelo entrenado | Qué contiene | Auxiliar | Se exporta con | Se carga con | Predice con |
|---|---|---|---|---|---|---|---|---|
| ARIMA | Estadística | statsmodels | parametros_estimados.json | Parámetros estimados por máxima verosimilitud: coeficientes AR y MA y varianza de las innovaciones sigma2 | ninguno | json.dump de los parámetros de ARIMA(...).fit() | json.load | ARIMA(...).filter(parámetros).forecast() |
| SARIMA | Estadística | statsmodels | parametros_estimados.json | Igual que ARIMA, más los coeficientes estacionales si el orden estacional no es cero | ninguno | igual que ARIMA | json.load | igual que ARIMA |
| Prophet-AR | Estadística | prophet | prophet.json | Modelo Prophet ajustado: tendencia, puntos de cambio, estacionalidad anual, coeficientes de los regresores e historia de ajuste | ninguno | prophet.serialize.model_to_json | prophet.serialize.model_from_json | Prophet.predict |
| XGBoost | Aprendizaje automático | xgboost | xgboost.json | Árboles de decisión aprendidos y su configuración | ninguno | XGBRegressor.save_model | XGBRegressor().load_model | XGBRegressor.predict |
| LightGBM | Aprendizaje automático | lightgbm | lightgbm.txt | Árboles de decisión aprendidos (texto) | ninguno | Booster.save_model | lightgbm.Booster(model_file=...) | Booster.predict |
| LSTM | Aprendizaje profundo | keras (tensorflow) | lstm.keras | Arquitectura de la red y pesos entrenados | escalador.json | Model.save | keras.models.load_model | Model.predict |
| N-BEATS | Aprendizaje profundo | keras (tensorflow) | nbeats.keras | Arquitectura de la red y pesos entrenados | escalador.json | Model.save | keras.models.load_model | Model.predict |

ARIMA y SARIMA no guardan el objeto de statsmodels: su estado aprendido son los parámetros estimados. Para pronosticar desde una semana, se arma el mismo ARIMA con la serie hasta esa semana y se le aplican esos parámetros fijos con el filtro de Kalman (filter); no se vuelven a estimar.

escalador.json guarda el mínimo y el máximo de log1p(casos) con que se escaló la ventana de entrada cuando se entrenó la red. Sin él no se pueden preparar las entradas ni volver a la escala de casos.

Dependencias y versiones. El manifest registra la versión de cada librería con que se exportó el modelo (campo librerias). Al importar, se compara con la instalada en el servidor: si cambia la versión mayor (por ejemplo, Keras 2 contra Keras 3), el paquete se rechaza, porque los formatos nativos no garantizan compatibilidad entre versiones mayores; si cambia solo una versión menor, se acepta y queda registrado (campo compatibilidad).

Ejemplos de exportación y carga con la API nativa de cada librería (el proyecto los encapsula en el método guardar y cargar de cada modelo, en pathologies/dengue/pronostico/modelos):

```python
# ARIMA / SARIMA (statsmodels)
resultado = ARIMA(casos_log, order=(2, 1, 2), trend="n",
                  enforce_stationarity=False, enforce_invertibility=False).fit()
contenido = {"nombres": list(resultado.model.param_names), "valores": list(resultado.params)}
Path("parametros_estimados.json").write_text(json.dumps(contenido))
parametros = np.array(json.loads(Path("parametros_estimados.json").read_text())["valores"])
filtrado = ARIMA(casos_log_hasta_origen, order=(2, 1, 2), trend="n",
                 enforce_stationarity=False, enforce_invertibility=False).filter(parametros)
pronostico = np.expm1(filtrado.forecast(steps=6))

# Prophet-AR
Path("prophet.json").write_text(model_to_json(modelo_prophet))
modelo_prophet = model_from_json(Path("prophet.json").read_text())
yhat_log = modelo_prophet.predict(entrada)["yhat"]   # entrada: ds y casos_lag1_log, casos_lag2_log, ...

# XGBoost
modelo_xgb.save_model("xgboost.json")
modelo_xgb = XGBRegressor(); modelo_xgb.load_model("xgboost.json")
prediccion = modelo_xgb.predict(rezagos)            # columnas casos_lag1, casos_lag2, casos_lag4, casos_lag8

# LightGBM
booster.save_model("lightgbm.txt")
booster = lightgbm.Booster(model_file="lightgbm.txt")
prediccion = booster.predict(rezagos)

# LSTM y N-BEATS (Keras 3)
red.save("lstm.keras")
red = keras.models.load_model("lstm.keras")
prediccion_escalada = red.predict(ventana_escalada)  # forma (n, 12, 1) en LSTM, (n, 12) en N-BEATS
```

## 5. Estructura del paquete .zip

<!-- app:arbol_zip -->

Un paquete tiene 3 o 4 archivos, en la raíz del .zip o dentro de una sola carpeta (sin subcarpetas):

```
modelo.zip
├── manifest.json            metadatos, hiperparámetros, librerías y métricas de la prueba
├── pronosticos_prueba.csv   resultados individuales de la prueba
├── archivo del modelo       en su formato nativo (tabla de la sección 4)
└── escalador.json           solo en LSTM y N-BEATS
```

Campos de manifest.json:

| Campo | Contenido |
|---|---|
| formato | Versión del formato del manifest. |
| patologia, serie | Patología y definición de la serie con que se entrenó; la serie debe ser la del tablero. |
| modelo, nombre, familia | Clave del modelo en el catálogo, nombre legible y familia. |
| origen, usuario, fecha_entrenamiento | Si se entrenó en el tablero o se subió, quién y cuándo. |
| rango, semanas | Primera y última semana del modelo definitivo y cantidad de semanas. |
| hiperparametros | Configuración del modelo (no lo aprendido). |
| archivos_modelo | Archivos del modelo definitivo y sus auxiliares. |
| archivo_pronosticos_prueba | Nombre del CSV de la prueba. |
| horizonte_maximo_semanas | 6. |
| prueba | Descripción, semanas de entrenamiento del modelo de evaluación, semanas de prueba, inicio y fin, orígenes y registros. |
| metricas_prueba | Alcance, métricas globales y métricas por horizonte H1 a H6, del modelo y de la persistencia, cada una con n y n_mape. |
| detalles_entrenamiento | Datos del entrenamiento del modelo definitivo (por ejemplo, época en que se detuvo una red). |
| librerias | Versión de cada librería con que se exportó. |
| subido_por, fecha_subida, compatibilidad | Los agrega el tablero al importar. |

Columnas de pronosticos_prueba.csv (una fila por semana de origen y horizonte):

| Columna | Contenido |
|---|---|
| fecha_origen | Última semana con dato real que vio el pronóstico (inicio de semana). |
| horizonte_semanas | Semanas adelante, de 1 a 6. |
| fecha_objetivo | Semana pronosticada; siempre pertenece a la prueba. |
| casos_reales | Casos notificados en la semana objetivo. |
| pronostico_modelo | Pronóstico del modelo de evaluación, sin redondear. |
| error_absoluto | Valor absoluto de casos_reales menos pronostico_modelo. |
| error_porcentual | Error absoluto sobre casos reales por 100; vacío si los casos reales son 0. |
| pronostico_persistencia | Casos reales de la semana de origen. |
| error_absoluto_persistencia, error_porcentual_persistencia | Los mismos errores para la persistencia. |

Reglas de la revisión al importar: formato del manifest vigente, serie igual a la del tablero, modelo existente en el catálogo con la misma familia, librería instalada y misma versión mayor, solo archivos .json, .csv, .txt y .keras (nunca pickle ni joblib, que pueden ejecutar código al abrirse), archivos del modelo presentes, CSV con todas sus columnas, métricas del manifest iguales a las reconstruidas desde el CSV, y un pronóstico de prueba con valores finitos y no negativos. Si algo falla no se guarda nada y el motivo queda en el historial.

<!-- app:ejemplos_archivos -->

## 6. División temporal de los datos

Cada versión se entrena con un rango de semanas consecutivas (en Gestión se elige el desde y el hasta). Ese rango se divide sin barajar:

- Entrenamiento del modelo de evaluación: el primer 85 % de las semanas.
- Prueba: el 15 % final. El modelo de evaluación nunca ve esas semanas al entrenar.
- Modelo definitivo: el 100 % del rango, después de la evaluación.

Las redes (LSTM y N-BEATS) además separan, dentro de los datos con que entrenan, un tramo final de validación (el 15 % de esos datos) que solo sirve para decidir cuándo detener el entrenamiento (parada temprana, restaurando los mejores pesos). Esa validación es parte del entrenamiento; la prueba es otra cosa.

<!-- app:linea_de_tiempo -->

## 7. Evaluación con orígenes móviles

El modelo de evaluación se entrena una vez y sus parámetros quedan fijos. Luego, desde cada semana de origen, recibe los casos reales hasta esa semana y pronostica las 6 siguientes. Dentro de esas 6 semanas el pronóstico es recursivo: los valores de entrada que caen dentro del horizonte se completan con la propia predicción del modelo, y por eso el error crece con el horizonte. En la semana de origen siguiente se descarta lo pronosticado y se vuelve a partir de los casos reales: el error no se arrastra de un origen a otro.

<!-- app:origenes_moviles -->

Solo se guardan los pronósticos cuya semana objetivo pertenece a la prueba. Para que cada horizonte tenga exactamente un registro por semana de prueba, los orígenes empiezan 6 semanas antes de la prueba: desde esas semanas, los horizontes que caen todavía en el entrenamiento se descartan. Con una prueba de 149 semanas, cada horizonte tiene 149 registros y el CSV tiene 149 × 6 = 894.

## 8. Resultados individuales de la prueba y modo de semana pasada

Cada fila del CSV es un resultado individual: un pronóstico concreto, desde una semana de origen, a un horizonte, comparado con los casos reales de la semana objetivo. Es la fuente de verdad de la evaluación: las métricas se calculan desde estas filas.

Error absoluto de un registro:

$$E_{abs} = |y - \hat{y}|$$

Error porcentual absoluto de un registro:

$$APE = \frac{|y - \hat{y}|}{|y|} \times 100$$

donde $y$ son los casos reales y $\hat{y}$ el pronóstico. Por ejemplo, con 10 casos reales y un pronóstico de 16.151:

$$E_{abs} = |10 - 16.151| = 6.151 \qquad APE = \frac{6.151}{10} \times 100 = 61.51\ \%$$

Los cálculos usan siempre los valores sin redondear. La aplicación muestra un decimal (16.2, 6.2 y 61.5 %). Si los casos reales son 0, el error porcentual no está definido (no se puede dividir por cero): se deja vacío y se muestra como no definido; el error absoluto sí se calcula.

El modo de semana pasada lee estas filas: se elige una semana de origen y se muestran sus horizontes disponibles. Solo aparecen los horizontes cuya semana objetivo pertenece a la prueba; por eso las semanas de origen del principio (anteriores a la prueba) y del final (cerca del fin de la prueba) tienen menos de 6 horizontes. La última semana de origen evaluable es la anterior al fin de la prueba y solo tiene el horizonte 1. Nada de esto se reconstruye con el modelo definitivo: son los pronósticos que hizo el modelo de evaluación sin haber visto esas semanas.

<!-- app:tabla_csv_ejemplo -->

## 9. Pronóstico en vivo

El modelo definitivo (entrenado con el 100 % del rango) recibe los casos reales hasta la última semana cargada en el tablero y pronostica las 6 semanas siguientes con el mismo procedimiento recursivo. Estos pronósticos se calculan al abrir la pestaña (se guardan en la memoria del servidor por versión y por datos cargados) y no se escriben en ningún archivo: no forman parte del CSV de la prueba ni del manifest.

Junto a cada semana futura se muestran las métricas de la prueba del mismo horizonte: la primera semana futura con las de H1, la sexta con las de H6. Son la referencia del error que tuvo el procedimiento en la prueba, no el error de estas predicciones (el futuro todavía no pasó) ni una evaluación del modelo definitivo.

## 10. Métricas

Hay tres niveles, todos calculados desde el CSV de la prueba y con valores sin redondear:

- Resultados individuales: el error de cada registro (sección 8).
- Métricas por horizonte: se toman los registros de un horizonte (por ejemplo, todos los pronósticos a 1 semana para H1) y se aplica cada fórmula.
- Métricas globales: se aplica cada fórmula a todos los registros de todos los horizontes a la vez. No son el promedio de las seis métricas por horizonte.

Todas describen el rendimiento histórico del modelo de evaluación en la prueba (15 %), antes de entrenar el modelo definitivo. No son las métricas de la última semana de origen ni una evaluación del modelo definitivo. El manifest guarda cada métrica con n (registros usados) y n_mape (registros usados en el MAPE).

MAE, error absoluto medio, en casos:

$$MAE = \frac{1}{n} \sum_{i=1}^{n} |y_i - \hat{y}_i|$$

RMSE, raíz del error cuadrático medio, en casos. Al elevar al cuadrado, un error grande pesa más que varios pequeños; por eso RMSE es mayor o igual que MAE, y la diferencia crece cuando hay errores grandes, como al subestimar un brote:

$$RMSE = \sqrt{\frac{1}{n} \sum_{i=1}^{n} (y_i - \hat{y}_i)^2}$$

MAPE, error porcentual absoluto medio. Se calcula solo con los registros que tienen casos reales distintos de 0 ($n_{mape}$); los registros con 0 casos reales sí entran en MAE, RMSE y R²:

$$MAPE = \frac{100}{n_{mape}} \sum_{y_i \neq 0} \left| \frac{y_i - \hat{y}_i}{y_i} \right|$$

R², coeficiente de determinación: compara el error del modelo con el de pronosticar siempre el promedio de los casos reales ($\bar{y}$). Vale 1 si el pronóstico es perfecto, 0 si no mejora al promedio y es negativo si es peor que el promedio. No es un porcentaje de exactitud:

$$R^2 = 1 - \frac{\sum_{i=1}^{n} (y_i - \hat{y}_i)^2}{\sum_{i=1}^{n} (y_i - \bar{y})^2}$$

## 11. Banda ±RMSE y sus limitaciones

En el pronóstico en vivo, a cada semana futura se le suma y resta el RMSE de la prueba de su horizonte:

$$\text{Límite inferior} = \hat{y} - RMSE_h \qquad \text{Límite superior} = \hat{y} + RMSE_h$$

Por ejemplo, con un pronóstico de 195 casos y un RMSE de H1 de 17.438: 195 − 17.438 = 177.562 y 195 + 17.438 = 212.438, que se muestra como 177.6 a 212.4. El límite inferior nunca baja de 0 casos.

La aplicación lo llama rango orientativo (±RMSE). No es un intervalo de confianza ni un intervalo de predicción: no se construyó con un modelo probabilístico ni tiene una probabilidad asociada. Es la magnitud típica del error que tuvo el procedimiento a ese horizonte en la prueba. En un brote mayor que los de la prueba, el error real puede ser bastante mayor.

## 12. Ejemplo numérico completo

Cuatro registros, uno de ellos con 0 casos reales:

| Registro | Casos reales $y$ | Pronóstico $\hat{y}$ | $|y - \hat{y}|$ | $(y - \hat{y})^2$ | APE |
|---|---|---|---|---|---|
| 1 | 10 | 12 | 2 | 4 | 20.0 % |
| 2 | 20 | 17 | 3 | 9 | 15.0 % |
| 3 | 30 | 36 | 6 | 36 | 20.0 % |
| 4 | 0 | 2 | 2 | 4 | no definido |

$$MAE = \frac{2 + 3 + 6 + 2}{4} = 3.25 \qquad RMSE = \sqrt{\frac{4 + 9 + 36 + 4}{4}} = \sqrt{13.25} = 3.640$$

$$MAPE = \frac{20 + 15 + 20}{3} = 18.33\ \% \quad (n = 4,\ n_{mape} = 3)$$

Con $\bar{y} = 15$, la suma de cuadrados respecto del promedio es $25 + 25 + 225 + 225 = 500$, así que:

$$R^2 = 1 - \frac{53}{500} = 0.894$$

Si en cambio se pronostica con la persistencia y el valor en el origen es 20 (pronóstico de 20 en los cuatro registros), los errores absolutos son 10, 0, 10 y 20: MAE = 10, RMSE = √150 = 12.247, MAPE = 44.44 % y R² = 1 − 600/500 = −0.2 (peor que el promedio).

<!-- app:ejemplo_metricas -->

## 13. Comparación con la persistencia

La persistencia es la línea base más simple: desde cada semana de origen, pronostica que las 6 semanas siguientes repiten los casos reales de esa semana. Si en el origen hubo 20 casos, pronostica 20 en H1, H2, H3, H4, H5 y H6.

Se calcula en los mismos orígenes y horizontes que el modelo (las mismas filas del CSV, columnas de persistencia) y con las mismas fórmulas. La razón entre el RMSE del modelo y el de la persistencia resume la comparación: menos de 1 significa que el modelo se equivoca menos que repetir la última semana. Sirve para saber si la complejidad del modelo está justificada; no es el criterio para elegir el modelo de cada familia (sección 15).

<!-- app:tabla_persistencia -->

## 14. Por qué no se usan variables climáticas

En el estudio de modelado se entrenó cada modelo con y sin variables climáticas (humedad, precipitación y temperatura), con los mismos hiperparámetros. Diferencia de R² (sin clima menos con clima; más negativo significa que el clima ayuda más):

| Modelo | H1 | H3 | H4 | H6 |
|---|---|---|---|---|
| Prophet | -0.006 | -0.012 | -0.016 | -0.026 |
| ARIMA / SARIMA | -0.003 | -0.035 | -0.053 | -0.120 |
| XGBoost | -0.010 | -0.056 | -0.080 | -0.154 |
| LightGBM | -0.017 | -0.050 | -0.081 | -0.093 |
| LSTM | -0.022 | -0.064 | -0.081 | -0.119 |
| N-BEATS | -0.026 | -0.218 | -0.481 | -1.555 |

El tablero no usa covariables climáticas: adquirir, actualizar y validar series climáticas cada semana recae sobre la operación del sistema, y para el pronóstico de corto plazo la mayor parte de la señal está en los casos recientes.

## 15. Estudio de modelado y criterios de selección

Qué modelo ocupa cada familia se decide en el repositorio de experimentación (METODOLOGIA_PRONOSTICO.md), con la serie del tablero y el mismo código de este sistema:

- Periodos iguales para las tres familias: entrenamiento de 2007 a abril de 2022 (85 % de 2007-2024), prueba de abril de 2022 a diciembre de 2024 (15 %) y prueba final en 2025, que solo se reporta.
- Hiperparámetros con Optuna dentro del entrenamiento: validación cruzada temporal en los modelos estadísticos y de aprendizaje automático; bloque de validación (70/15/15) en las redes, con 5 semillas, eligiendo la configuración más estable.
- Ganador de cada familia en la prueba por RMSE en los horizontes 1 a 4 (MAE como desempate; en las redes cuenta también la estabilidad). La persistencia se usa para comprobar si el ganador la supera, no para elegir.
- El ganador se exporta con el procedimiento de la sección 3 sobre 2007-2025 y se sube en Gestión.

Resultados del estudio de modelado previo (notebook 05, serie de investigación 2007-2024 con prueba 2022-2024, sin clima), que dieron origen al enfoque de un modelo por familia:

| Modelo | H | RMSE | MAE | MAPE | R² |
|---|---|---|---|---|---|
| Prophet | 1 | 12.335 | 8.909 | 23.07 % | 0.8672 |
| Prophet | 4 | 17.468 | 12.415 | 30.75 % | 0.7337 |
| Prophet | 6 | 20.761 | 14.152 | 35.37 % | 0.6239 |
| XGBoost | 1 | 12.912 | 9.528 | 24.65 % | 0.8545 |
| XGBoost | 4 | 17.804 | 13.361 | 35.29 % | 0.7234 |
| XGBoost | 6 | 23.585 | 16.665 | 40.74 % | 0.5146 |
| LSTM | 1 | 12.968 | 9.025 | 22.40 % | 0.8533 |
| LSTM | 4 | 19.815 | 13.479 | 31.10 % | 0.6574 |
| LSTM | 6 | 24.317 | 16.267 | 35.89 % | 0.4840 |
| Persistencia | 1 | 13.211 | 9.950 | 26.11 % | 0.8477 |
| Persistencia | 4 | 19.942 | 14.929 | 36.52 % | 0.6530 |
| Persistencia | 6 | 24.926 | 17.702 | 44.25 % | 0.4579 |

Estas cifras son de otra serie y otro periodo de prueba que las de los modelos del tablero, así que no se comparan con ellas.

## 16. Generar un paquete fuera de la aplicación

Requiere una copia del repositorio del tablero (para importar su código) y el consolidado de dengue. Script completo:

```python
import sys
from pathlib import Path

import pandas as pd

RUTA_TABLERO = Path("/ruta/a/public-health-surveillance-system")
sys.path.insert(0, str(RUTA_TABLERO))

from pathologies.dengue.pronostico import paquete
from pathologies.dengue.pronostico.manifest import ORIGEN_SUBIDO
from pathologies.dengue.pronostico.serie import construir_serie_semanal_departamental

consolidado = pd.read_parquet(RUTA_TABLERO / "data/dengue/consolidado/dengue_consolidado.parquet")
serie = construir_serie_semanal_departamental(consolidado)

hiperparametros = {"unidades": [64, 16], "dropout": 0.2}   # None para los valores por defecto
carpeta = Path("salida/lstm")                              # carpeta de trabajo: se crea sola

# Evalúa (85 % / 15 %), guarda el CSV y las métricas, entrena el modelo definitivo (100 %)
# y escribe manifest.json, todo dentro de la carpeta.
paquete.entrenar_evaluar_y_guardar("lstm", hiperparametros, serie, carpeta, "tu_usuario", ORIGEN_SUBIDO)

# Empaqueta los archivos de la carpeta en un .zip con los archivos en la raíz.
paquete.exportar_zip(carpeta, Path("salida/lstm.zip"))
```

Resultado en disco (salida es una carpeta; lstm.zip es el archivo que se sube en Gestión):

```
salida/
├── lstm/                       carpeta de trabajo
│   ├── manifest.json
│   ├── pronosticos_prueba.csv
│   ├── lstm.keras
│   └── escalador.json
└── lstm.zip                    contiene esos 4 archivos, sin la carpeta
```

## 17. Verificación

El módulo pathologies/dengue/pronostico/verificacion.py comprueba sobre las versiones activas que:

- las métricas globales y por horizonte del manifest se reconstruyen exactamente desde el CSV de la prueba;
- cada horizonte tiene un registro por semana de prueba y la última semana de origen se recupera del CSV;
- los errores del CSV se calculan con los valores sin redondear;
- cada modelo se exporta, se importa y pronostica las 6 semanas futuras sin ejecutar ningún entrenamiento.

Se ejecuta desde la raíz del repositorio con: python -m pathologies.dengue.pronostico.verificacion
