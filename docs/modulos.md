# Guía de módulos de SIVIDEM

Descripción detallada de lo que la persona usuaria ve y puede hacer en cada pestaña del dashboard: componentes en el orden en que aparecen, selectores, parámetros, mensajes informativos y reglas de cálculo. Para la visión general del proyecto, la arquitectura y la instalación, ver el [README principal](../README.md).

Contenido:

- [Contexto común a todos los módulos](#contexto-común-a-todos-los-módulos)
- [Situación](#situación)
- [Pronóstico](#pronóstico)
- [Tendencia](#tendencia)
- [Sociodemográfica](#sociodemográfica)
- [Morbilidad](#morbilidad)
- [Mortalidad](#mortalidad)
- [Gestión](#gestión)

## Contexto común a todos los módulos

### Qué es SIVIDEM

Dashboard web de vigilancia epidemiológica del departamento del Magdalena (Colombia), desarrollado para el CITES (Centro de Innovación y Transferencia en Salud) de la Universidad del Magdalena. La primera patología implementada es dengue. El sistema está diseñado como plataforma modular: cada patología es un complemento (plugin) que cumple un contrato común, de modo que agregar una nueva patología (por ejemplo tuberculosis) no requiere modificar el núcleo.

Fuente de datos: archivos Excel de microdatos del portal SIVIGILA del INS (Instituto Nacional de Salud), uno por año y código de evento. Para dengue los códigos son 210 (dengue), 220 (dengue grave) y 580 (mortalidad por dengue).

Alcance geográfico: exclusivamente el departamento del Magdalena (código DANE 47, 30 municipios), por territorio de ocurrencia del caso. No hay vista nacional ni comparación con otros departamentos (para eso existe el propio SIVIGILA).

Tecnologías: Streamlit y Plotly (interfaz y gráficos), Keycloak (identidad), Redis y RQ (cola de procesamiento), SQLite (estado, bitácora, registro de archivos), Parquet (datos de casos), Prophet, XGBoost y TensorFlow/Keras (pronóstico), orquestación con docker-compose.

### Pantalla de inicio de sesión

Pantalla dividida en dos paneles:

- Panel izquierdo (institucional, fondo azul): escudo de la Universidad del Magdalena, nombre SIVIDEM y su significado, acento tricolor institucional (azul, naranja, verde), un párrafo que describe la herramienta ("Herramienta de análisis epidemiológico departamental para la toma de decisiones en salud pública...") y una lista de capacidades: análisis de tendencias y ciclos epidémicos; situación epidemiológica actual por subregión; perfil sociodemográfico de la población afectada; indicadores de morbilidad, mortalidad y letalidad; canal endémico y pronóstico de corto plazo. Al pie, el logo de SIVIDEM y la leyenda "CITES - Centro de Innovación y Transferencia en Salud, Universidad del Magdalena, Santa Marta, Colombia".
- Panel derecho (formulario): rótulo "Acceso restringido", título "Bienvenido", campos de correo electrónico institucional y contraseña, botón "Ingresar al sistema" y una nota de acceso seguro vinculado a la cuenta institucional.

Comportamiento: la verificación de credenciales contra Keycloak se hace en dos fases (primero se envía el formulario, luego aparece un indicador "Verificando credenciales..." en el mismo panel) para evitar parpadeos. Mensajes de error posibles: credenciales inválidas o usuario sin rol asignado; servidor de autenticación no disponible.

### Roles y permisos

Keycloak solo entrega la identidad y la etiqueta del rol; qué puede hacer cada rol lo decide la aplicación.

| Rol | Público previsto | Qué puede hacer |
|---|---|---|
| Visor | Estudiantes | Ver las seis pestañas de análisis. No ve la pestaña Gestión. |
| Editor | Personal CITES | Todo lo del Visor, más subir, reemplazar (editar) y enviar a papelera archivos; restaurar desde la papelera; ver Procesamientos y Bitácora. Alcance global: gestiona cualquier patología. |
| Admin | Administración | Todo lo del Editor, más eliminar para siempre desde la papelera y gestionar los modelos de pronóstico: entrenar, subir, activar y eliminar versiones (apartado Pronóstico de Gestión). |

### Barra superior y encabezado

Fija en la parte superior al desplazarse. Contiene:

- Título "Vigilancia de Dengue" y un contador: "N registros tras los filtros, de M en el consolidado". Permite ver en todo momento cuánto del universo de datos se está analizando.
- A la izquierda, marca SIVIDEM con el texto "CITES - Universidad del Magdalena".
- Al centro, selector de patología (hoy solo dengue; muestra las patologías habilitadas).
- A la derecha, nombre de la persona usuaria, su rol y botón de cerrar sesión.

### Barra lateral: filtros globales

Todos los filtros operan sobre los datos ya cargados en memoria de la sesión; moverlos nunca relee el archivo del disco, por eso la respuesta es inmediata.

- Botón "Actualizar datos" (principal): recarga el consolidado desde disco. Es uno de los tres únicos momentos en que los datos cambian (los otros dos son refrescar la página e iniciar sesión).
- Encabezado "Filtros" con una insignia que indica cuántos filtros están activos (por ejemplo "3 activos").
- Botón "Limpiar filtros": restablece todos.
- Territorio:
  - Subregión: botones tipo píldora, selección múltiple, con las 5 subregiones oficiales: Santa Marta, Centro, Norte, Río y Sur.
  - Municipio: lista desplegable de selección múltiple, subordinada a la subregión (si se eligió una subregión, solo ofrece sus municipios).
- Periodo:
  - Años: deslizador de rango (por ejemplo 2019 a 2024).
  - Semana epidemiológica: deslizador de rango, rotulado "Sem. 1" a "Sem. 53" (convención CDC, semana que inicia en domingo).
- Estratificación de riesgo: píldoras de selección múltiple con el nivel de transmisión calculado para cada municipio según el lineamiento MSPS/INS 2020-2023 (niveles posibles: Sin riesgo, Sin transmisión sin vector, Sin transmisión con vector, Baja, Mediana, Alta y Muy alta transmisión). Solo aparece si la estratificación se pudo calcular (requiere 6 años de histórico).
- Clasificación del caso: píldoras de selección múltiple sobre la clasificación final del caso (Sospechoso, Probable, Confirmado por laboratorio, Confirmado por clínica, Confirmado por nexo epidemiológico, Descartado, No aplica, Otro, Error de digitación; solo aparecen las presentes en los datos).

No existe filtro de departamento: el Magdalena es el techo fijo del sistema.

Título y contexto de cada gráfica: el criterio es el de la epidemiología descriptiva, un título está bien cuando permite identificar tiempo, lugar y persona. Se reparte en dos piezas:

- Título fijo, encima de la tarjeta: la métrica y la persona o dimensión ("Muertes por régimen de afiliación (SGSSS)", "Casos hospitalizados por semana epidemiológica").
- Dentro de la propia figura se repite el título en negrita y debajo va el contexto: patología, lugar y período, por ejemplo "Dengue · Magdalena · 2007-2025" o "Dengue · Subregión Río · 2022-2024 · Sem. 1-20". Nunca queda vacío: sin filtros, el lugar es el Magdalena y el período es el rango completo de años cargados. Va dentro de la figura para que se vea en pantalla completa y en la imagen descargada con el botón de cámara.

Las gráficas que analizan un año concreto (las semanales) declaran ese año, y las comparativas los dos años que comparan ("2025 frente a 2024").

Presentación común: letra de 15 en las gráficas, con la misma tipografía del tablero (ninguna etiqueta por debajo de 12), mapas sin fondo blanco, ejes de conteos que no bajan de cero, barra de herramientas de Plotly solo al pasar el cursor y solo con descargar imagen, zoom, mover y restablecer, leyenda arriba a la izquierda para que la barra de herramientas no la tape, y una gráfica por fila salvo los pares complementarios.

Sin filtros propios dentro de las gráficas: manda la barra lateral. Se conservan solo los selectores de representación (eligen qué variable se dibuja, no recortan los casos) y los parámetros de método del canal endémico.

Datos insuficientes: si con los filtros actuales una gráfica quedaría con una sola barra (o una serie con menos de 4 puntos, o una comparación entre años con menos de 2 años), no se dibuja. En su lugar aparece un mensaje que dice cuántos registros hay y qué ampliar, por ejemplo "Con los filtros actuales hay 2 muertes en una sola semana epidemiológica. Amplía el período para ver la distribución temporal".

Filtro cruzado en los pares: en tres pares de gráficas (Tendencia, Sociodemográfica y Mortalidad) seleccionar en una gráfica filtra la otra. En la gráfica donde se hizo clic, lo elegido queda a color pleno y lo demás atenuado. Sobre el par aparece "Mostrando solo: ..." con un botón "Quitar selección", y la selección se borra sola al cambiar cualquier filtro de la barra lateral.

### Avisos y notificaciones

- Banner de datos nuevos: cuando alguien procesa un archivo y el consolidado oficial cambia, a todas las personas conectadas (cualquier rol) les aparece, en unos 4 segundos, un banner delgado "Hay datos nuevos disponibles para esta patología" con botón "Actualizar" y una x para cerrarlo. Cerrarlo no pierde información: el procesamiento queda registrado en Procesamientos.
- Notificación del resultado de una subida: solo a quien subió el archivo, como notificación emergente (toast): "Datos_2024_210: procesado correctamente" o "Datos_2024_210: falló. [motivo]".

### Reglas de cálculo transversales

- Casos = códigos 210 + 220. Muertes = código 580.
- Incidencia = casos (210+220) / población en riesgo x 100.000.
- Mortalidad = muertes (580) / población en riesgo x 100.000.
- Letalidad = muertes (580) / casos (210+220) x 100. Meta nacional INS: menor a 0,10 %.
- Letalidad de dengue grave = muertes (580) / casos de dengue grave (220) x 100.
- Población en riesgo: proyecciones DANE (Censo 2018) de los municipios clasificados con transmisión según la estratificación de riesgo MSPS/INS, calculada por el propio sistema con 4 variables (altura, presencia del vector, magnitud de casos y persistencia de la transmisión, puntaje 0 a 12). Cuando el periodo abarca varios años, la población se suma año a año (persona-años).
- Regla de "no disponible": si falta un insumo necesario (por ejemplo población DANE de algún año, o los 6 años de histórico que exige la estratificación), el indicador se muestra como "No disponible", nunca como cero. El sistema no publica números falsos.
- Las tasas se calculan solo para el Magdalena, a nivel de subregión como regla general; el mapa, la hospitalización por territorio y los KPI de incidencia y mortalidad también las muestran a nivel municipio.
- Subregiones: mapeo por código DIVIPOLA en un único archivo de configuración, fácil de modificar.

## Situación

### Propósito

Resumen ejecutivo de "cómo estamos ahora": los tres indicadores clave del año, el estado epidemiológico de cada subregión en su última semana reportada y el canal endémico, que compara la semana actual contra el comportamiento histórico de esa misma semana.

### Datos y filtros

- Usa los casos 210+220 para el mapa y el canal endémico, y además el 580 para los KPI de mortalidad y letalidad.
- Responde a los filtros globales. El filtro de años de la barra lateral limita la historia disponible para la línea base; si se acota demasiado, el sistema avisa que no hay años suficientes.

### Componentes (en orden de aparición)

#### Selector "Año de los indicadores"

Deslizador de un solo año que por defecto se ubica en el año más reciente. Afecta solo a los tres KPI de arriba (no al mapa ni al canal). Texto de ayuda: los indicadores son anuales porque la letalidad se compara con la meta anual del INS. Debajo, la leyenda "Indicadores del año N".

#### KPI principales (3 tarjetas)

- Incidencia: casos (210+220) / población en riesgo x 100.000.
- Mortalidad: muertes (580) / población en riesgo x 100.000.
- Letalidad: muertes / casos x 100, con 4 decimales. Si supera la meta INS de 0,10 %, la tarjeta muestra la etiqueta "Supera la meta INS" en color de alerta; el texto de ayuda indica si el año cumple o supera la meta.
- Si incidencia o mortalidad no se pueden calcular, muestran "No disponible" con un texto de ayuda que explica el motivo (falta población DANE o faltan los 6 años de histórico que pide el lineamiento).

#### Situación actual por subregión (mapa)

- Mapa coroplético del Magdalena con las 5 subregiones como polígonos (al pasar el cursor se resalta la subregión completa). Cada subregión se colorea según la zona del canal endémico en que está su última semana reportada: Éxito, Seguridad, Alerta, Epidemia o "Sin datos suficientes" (gris). Los colores son los institucionales reservados para estados epidemiológicos.
- A la derecha del mapa, una tarjeta por subregión con su nombre, su zona y la semana y año de referencia ("Seguridad - semana 20 de 2024").
- Encima del mapa, una leyenda con la semana de referencia: si todas las subregiones comparten la misma semana se indica una sola; si alguna reporta con más rezago, se avisa que el detalle está en cada tarjeta.
- Panel desplegable "Ajustar año de vigilancia y línea base histórica" con los mismos controles del canal endémico (ver abajo), aplicados a las 5 subregiones a la vez.
- Panel desplegable "¿Cómo se lee este mapa?": explica que cada subregión se compara contra su propia última semana con casos (no una semana fija del calendario), que no se inventan semanas futuras, que la comparación es siempre contra la misma semana calendario de los años base (no contra el promedio anual), y remite al botón Metodología.
- La situación del mapa se calcula con el método de cuartiles.

#### Canal endémico

- Título con botón "Metodología" a la derecha.
- Obedece el filtro territorial de la barra lateral: sin filtro es el canal de todo el Magdalena; con una subregión o un municipio filtrado, el de ese territorio. No tiene selectores propios de escala ni de territorio.
- Control segmentado "Metodología": Cuartiles (por defecto) o Bortman (media geométrica). Se dibuja una sola gráfica a ancho completo; con los dos métodos en paralelo cada canal quedaba a media pantalla y no se leía.
  - Cuartiles: líneas Cuartil inferior (P25), Mediana (P50), Cuartil superior (P75).
  - Bortman: líneas Límite inferior IC 95 %, Umbral estacional, Límite superior IC 95 %.
  - El área bajo la curva se divide en zonas sombreadas (Éxito, Seguridad, Alerta; lo que queda por encima del límite superior es Epidemia). Los casos semanales del año de vigilancia se dibujan como puntos, cada uno coloreado según la zona en que cae. Si no hay datos del año de vigilancia, aparece la anotación "Sin datos notificados para N".
- Parámetros del canal, debajo de la gráfica, en el panel desplegable "Ajustar año de vigilancia y línea base histórica" (colapsado por defecto). El panel aclara que son parámetros del método, no filtros de la vista:
  - Año de vigilancia: lista desplegable.
  - Años hacia atrás en la línea base: deslizador de 5 a 7 años (recomendación INS: menos de 5 no es confiable; más de 7 diluye el comportamiento reciente). Si solo hay 5 años disponibles se usan todos y se informa.
  - Excluir años de la línea base: selección múltiple para retirar años atípicos. Al excluir un año, la ventana se extiende automáticamente con el siguiente año más antiguo disponible. La exclusión es manual a propósito: un brote real y un año con datos incompletos se ven parecidos en las cifras.
  - Leyenda final: "Línea base: N años (lista de años)".
  - Si no hay al menos 5 años anteriores al año de vigilancia (o quedan menos de 5 tras las exclusiones), se muestra una advertencia que explica la recomendación del INS y cómo resolverlo.

#### Diálogo "Metodología del canal endémico"

Ventana emergente amplia con:

- Descripción general y 4 tarjetas de colores con la definición de cada zona (Éxito, Seguridad, Alerta, Epidemia).
- Pestaña "Cuartiles / medianas": fórmulas de P25, P50 y P75, ejemplo numérico (semana 14 con 5 años de línea base) y tabla de clasificación de casos en zonas.
- Pestaña "Bortman": fórmulas con corrección de Kirkwood (ln(v+1)), media y desviación en escala logarítmica, margen del IC 95 % con t de Student, ejemplo numérico paso a paso con los mismos datos, y tabla de clasificación.
- Pestaña "Comparativa": tabla que contrasta ambos métodos (tipo, sensibilidad a extremos, manejo de semanas en cero, base de los límites, años mínimos).
- Pestaña "Recursos": enlaces al protocolo de vigilancia de dengue del INS, manual SIVIGILA, portal de microdatos, documento del INS sobre comportamientos inusuales y el artículo original de Bortman (1999).

## Pronóstico

### Propósito

Estimar cuántos casos de dengue se esperan en las próximas 1 a 6 semanas en el Magdalena, como apoyo a la alerta temprana. Es "qué se espera" a continuación de "cómo estamos ahora".

### Datos y filtros

- Serie semanal departamental única (todo el Magdalena) de casos notificados de dengue y dengue grave (210+220, probables y confirmados, la misma definición que el resto del tablero), construida con todas las semanas del rango (las semanas sin casos se registran como cero, porque son un dato real).
- No depende de ningún filtro global. Los modelos se entrenan y evalúan a escala departamental. Si la persona tiene activo un filtro de subregión o municipio, aparece el aviso "Tienes un filtro de subregión o municipio activo: no afecta a esta pestaña, el pronóstico siempre es departamental".

### Modelos

El mejor modelo de cada familia, sin variables climáticas:

| Familia | Candidatos | Color en la gráfica |
|---|---|---|
| Estadístico | ARIMA, SARIMA, Prophet-AR | azul |
| Aprendizaje automático | XGBoost, LightGBM | naranja |
| Aprendizaje profundo | LSTM, N-BEATS | verde azulado |

- Cuál ocupa cada familia lo decide la experimentación, con la metodología de [METODOLOGIA_PRONOSTICO.md](https://github.com/Edmh1/dengue-surveillance-magdalena/blob/main/METODOLOGIA_PRONOSTICO.md), y lo activa el perfil de administración desde Gestión. La pestaña muestra la versión activa de cada familia.
- Pronóstico recursivo: para semanas más allá de la primera, los valores que caen dentro del horizonte se completan con la propia predicción del modelo. Desde cada semana se pronostican como máximo 6 semanas.
- Requisito mínimo: 120 semanas de histórico (aproximadamente 2,3 años).

### La pestaña solo muestra

No entrena, no sube ni cambia modelos y no tiene botones para hacerlo; todo eso se hace desde Gestión, subpestaña Pronóstico, y solo el perfil de administración. La metodología completa (ciclo de vida, formatos, evaluación, métricas y fórmulas) está en la [documentación técnica del pronóstico](pronostico.md).

### Componentes (en orden de aparición)

#### Encabezado

Título "Pronóstico de casos de dengue" con el botón "Fundamentación" a la derecha, y la leyenda "Pronóstico de casos notificados (probables y confirmados, los mismos que el resto del tablero) a nivel departamental...".

#### Selector "Modo"

- Pronóstico en vivo (próximas semanas): el modelo definitivo de cada familia pronostica desde la última semana con datos.
- Pronóstico de una semana pasada (prueba): los resultados individuales de la prueba, leídos del CSV de la versión.

#### Selectores de modelo, horizonte y métrica

- Modelo: el modelo activo de cada familia, rotulado con su familia (por ejemplo "Prophet-AR (estadístico)"; el estadístico es el valor por defecto), o "Comparar", que superpone todos sobre la misma serie real.
- Horizonte (semanas): de 1 a 6, por defecto 4. Más allá del horizonte recomendado aparece un aviso de que el error crece.
- Métrica: "Casos" (por defecto) o "Tasa semanal (x100.000 hab.)". La tasa usa la población total del Magdalena (30 municipios), no la población en riesgo.

#### Procedencia de los modelos y aviso de datos nuevos

- En modo en vivo, en texto visible, por cada modelo mostrado: "Prophet-AR: modelo definitivo entrenado el 6 de noviembre de 2026 con 2007 (sem. 1) a 2025 (sem. 53)".
- Si el consolidado tiene datos más recientes que los que vio un modelo, un aviso lo dice y explica que el perfil de administración puede reentrenarlo desde Gestión. No hay botón.
- Si todavía no hay modelos activos, la pestaña lo explica y dice quién puede generarlos.

#### Modo en vivo: pronóstico de las próximas semanas

- Gráfica: línea negra continua con los casos reales; pronóstico punteado con marcadores, un color fijo por familia (estadístico azul, aprendizaje automático naranja, aprendizaje profundo verde azulado); línea vertical "Última semana cargada"; barra de desplazamiento con la vista inicial de los últimos dos años. Con un solo modelo, banda sombreada del rango orientativo: pronóstico ± el RMSE de la prueba de cada horizonte, sin bajar de 0. No es un intervalo de confianza.
- Tabla con un modelo: Semana, Horizonte (H1 a H6), Pronóstico, ±RMSE y Rango orientativo (±RMSE). Al comparar: una columna por modelo con el pronóstico y su rango.

#### Modo en vivo: desempeño histórico en la prueba

Bloque aparte, con el alcance escrito: son las métricas del modelo de evaluación en la prueba (15 %), antes de entrenar el modelo definitivo; no son el error de los pronósticos de arriba. Tabla por modelo con una fila por horizonte hasta el elegido y una fila global (todos los registros de H1 a H6): n, RMSE, MAE, MAPE, R², RMSE de la persistencia y razón entre ambos RMSE.

#### Modo de semana pasada

- Selector "Pronosticar desde la semana (semana de origen)": todas las semanas de origen del CSV, cada una con sus horizontes evaluables (solo los que caen dentro de la prueba; al principio y al final hay menos de 6, y la última semana de origen solo tiene H1). Por defecto, la última semana de origen con los 6 horizontes.
- Aviso: "Estás viendo resultados individuales de la PRUEBA, no el pronóstico de hoy. Los hizo el modelo de evaluación, entrenado solo con el 85 % de los datos (...), que no había visto estas semanas. No es el modelo definitivo".
- Gráfica con los casos reales antes y después de la semana de origen y los pronósticos guardados.
- Tabla, una fila por registro del CSV: semana objetivo, horizonte, casos reales, pronóstico, error absoluto, error porcentual ("no definido (0 casos reales)" cuando corresponde), persistencia y su error absoluto.

Todas las tablas y la gráfica muestran 1 decimal (R² con 2); los cálculos usan los valores sin redondear.

#### Diálogo "Fundamentación del pronóstico"

Muestra las secciones de la [documentación técnica del pronóstico](pronostico.md), con un selector del modelo activo para las partes que usan sus datos reales. Seis pestañas:

- Resumen: resumen del sistema y familias de modelos.
- Ciclo de vida y formatos: diagrama del ciclo de vida, formatos de serialización por modelo, estructura del paquete con el árbol y el contenido real de cada archivo.
- División y evaluación: división temporal (línea de tiempo de la versión), evaluación con orígenes móviles (gráfica de seis pronósticos desde tres semanas de origen consecutivas) y resultados individuales con filas reales del CSV.
- Pronóstico en vivo: cómo se calcula y el rango orientativo ±RMSE con sus limitaciones.
- Métricas y persistencia: fórmulas, ejemplo numérico verificable, cálculo con los registros reales del modelo activo comparado contra su manifest, y tabla contra la persistencia.
- Clima y estudio de modelado: por qué no se usan variables climáticas y criterios de selección de los modelos.

## Tendencia

### Propósito

Describir la evolución de los casos en el tiempo y en el territorio: cuántos casos por año, cómo se comporta el año semana a semana frente al anterior, dónde se concentra la incidencia y cómo evoluciona cada subregión o municipio.

### Datos y filtros

- Casos 210+220 (la mortalidad vive en su propia pestaña).
- Responde a todos los filtros globales. La sección semanal analiza el último año del filtro de años; el año de comparación es el inmediatamente anterior en los datos, esté o no dentro del filtro.

### Componentes (en orden de aparición)

#### KPI (3 tarjetas)

Leyenda previa: los casos totales cubren todo el periodo filtrado; semana pico y municipio más afectado corresponden al año más reciente.

- Casos totales.
- Semana pico del año más reciente.
- Municipio más afectado del año más reciente.

El alza frente al año anterior no es una tarjeta: va anotada sobre la gráfica comparativa semanal.

#### Par: Casos por año + Incidencia por subregión en el Magdalena

Las dos gráficas van juntas porque el mapa filtra la serie: al entrar a una subregión, a un municipio o a una zona, "Casos por año" muestra solo ese territorio y sobre el par aparece "Mostrando solo: Subregión Río" con el botón "Quitar selección".

- Casos por año: barras por año con el número de casos. La línea punteada del promedio anual solo se dibuja con dos años o más.
- Incidencia por subregión en el Magdalena, en tres niveles, todos en incidencia (x100.000 hab.) y con la misma escala de color:
  - Nivel 1, subregiones. Clic en una subregión para ver sus municipios.
  - Nivel 2, municipios de la subregión, con botón "Volver". Clic en un municipio para ver sus zonas.
  - Nivel 3, zonas: el municipio en sus dos zonas con dato, cabecera municipal y resto rural (centros poblados y rural disperso unidos en una sola figura), como coropleto con la incidencia de cada una. Son las dos únicas tasas válidas: el DANE publica una sola población para centros poblados y rural disperso juntos, y así agrupa también la población en riesgo el lineamiento MSPS/INS. Los centros poblados no se dibujan por separado porque no hay datos a ese nivel (SIVIGILA no registra en cuál ocurrió el caso). Al lado, las barras con las dos tasas y debajo el número de casos en cabecera, centros poblados y rural disperso. Una zona sin población de referencia se pinta en gris. Clic en una zona para filtrar la serie anual a la cabecera o al resto rural.
  - Al pie del tercer nivel, la fuente de la capa (DANE, Marco Geoestadístico Nacional 2020 y Censo Nacional de Población y Vivienda 2018; nombres de DIVIPOLA) y un panel con sus límites: los centros poblados son la unión de manzanas censales de 2018, no un perímetro normativo; las tres clases suman entre el 100 % y el 101,2 % del área municipal por la diferencia de años entre capas; dos centros poblados no tienen nombre en la DIVIPOLA (47570008 y 47660015).

#### Casos por semana epidemiológica

Par complementario con el año resuelto por el filtro global ("Semana a semana, 2025 frente a 2024"):

- Casos de cada semana del año de análisis, con la línea del promedio semanal.
- Comparación con el año anterior: barras naranjas del año anterior y línea azul del año de análisis, con la anotación del alza o baja del año frente a las mismas semanas del anterior.
- Si los datos no tienen un año anterior, se dibuja solo el año de análisis y se dice por qué.

#### Variación porcentual semanal frente al año anterior

Sola, a ancho completo: barras azules para aumentos y naranjas para disminuciones, con línea de referencia en cero.

#### Evolución de la incidencia por territorio

- Control segmentado "Agrupar por": Subregión o Municipio (selector de representación).
- Líneas con la incidencia por año (x100.000 hab.), una por territorio. Necesita al menos dos años.

## Sociodemográfica

### Propósito

Caracterizar a la población afectada: quiénes enferman (sexo, edad, grupos vulnerables), dónde viven (área, estrato), su pertenencia étnica, su aseguramiento y qué instituciones notifican.

### Datos y filtros

- Casos 210+220. Son distribuciones en conteos y porcentajes, no tasas.
- Responde a todos los filtros globales (por ejemplo, el filtro de subregión recorta todas las distribuciones).

### Componentes (en orden de aparición)

#### KPI de vulnerabilidad (4 tarjetas)

- Casos totales.
- Gestantes: número y porcentaje del total.
- Menores de 5 años: número y porcentaje del total.
- Mayores de 65 años: número y porcentaje del total.

Los porcentajes usan una precisión adaptativa para que nunca aparezca "0 %" cuando hay casos reales.

#### Par: Pirámide de casos por sexo y edad + Distribución demográfica de casos

- Pirámide de casos por sexo y edad: masculino a la izquierda (azul) y femenino a la derecha (naranja), en grupos quinquenales de 0-4 hasta 65 y más (la agrupación de los boletines del INS). Al hacer clic en una barra (un grupo de edad y sexo), esa barra queda resaltada y la distribución de al lado se recalcula solo con esos casos ("Mostrando solo: Femenino de 20-24 años", con "Quitar selección").
- Distribución demográfica de casos: control segmentado "Ver distribución por" (selector de representación) con Área, Estrato, Etnia y Régimen, todas en barras horizontales. Al hacer clic en una categoría, la pirámide muestra solo esos casos (filtro en ambos sentidos).

#### Pueblos indígenas afectados (condicional)

Solo aparece si en los datos filtrados hay casos con pertenencia étnica indígena. Barras horizontales con los 10 pueblos indígenas con más casos (excluye registros sin información).

#### Casos por EPS de afiliación

Barras horizontales con las 10 EPS con más casos de sus afiliados en el período filtrado. El título dice "de afiliación" y no "notificados" a propósito: la EPS no notifica, notifica la UPGD.

#### Casos notificados por UPGD

Debajo de la anterior, a ancho completo: las 10 unidades con más casos notificados en el período filtrado.

## Morbilidad

### Propósito

Analizar el comportamiento clínico y de notificación de los casos: gravedad, hospitalización, cómo se clasificaron al inicio y cómo terminaron, por qué fuente se captaron y dónde la incidencia y la hospitalización son más altas.

### Datos y filtros

- Casos 210+220.
- Responde a los filtros globales. Las gráficas semanales muestran el último año del filtro de años, declarado en su contexto.
- A diferencia de Situación (un solo año), aquí la incidencia sigue el filtro global de años y permite ver tasas de un rango de años.
- Las etiquetas dicen "Dengue" y "Dengue grave", sin el código numérico; los códigos quedan en las notas metodológicas.

### Componentes (en orden de aparición)

#### KPI (5 tarjetas)

- Casos totales.
- Incidencia (o "No disponible", con explicación).
- Hospitalizados: número y porcentaje del total.
- Dengue grave: número y porcentaje del total (es donde vive la proporción de graves).
- Hospitalizados graves: número y porcentaje sobre los casos graves.

#### Par: Casos por tipo + Casos por clasificación final

Composición inicial y final del mismo universo, lado a lado: anillo de dengue frente a dengue grave y anillo de la clasificación final.

#### Gráfico de Sankey de flujo de clasificación de casos

A ancho completo, justo debajo del par: Total, Clasificación inicial y Clasificación final. Solo se dibujan los cambios de clasificación. Se lee la composición al notificar, la composición después del ajuste y luego el flujo que conecta las dos.

#### Casos por semana epidemiológica y tipo

Barras apiladas por semana: dengue y dengue grave. No lleva la serie de porcentaje de graves ni eje secundario.

#### Clasificación final de los casos por semana epidemiológica

Barras apiladas por semana según la clasificación final.

#### Casos hospitalizados por semana epidemiológica

Barras apiladas por semana con los casos hospitalizados, por tipo.

#### Tasa de hospitalización por territorio

- Control segmentado "Tipo de caso": Ambos, Dengue o Dengue grave (selector de representación).
- Tasa de hospitalizados por subregión y los 15 municipios de mayor tasa (x100.000 hab.).

#### Incidencia de dengue por subregión

Barras horizontales con la incidencia de cada subregión dentro del alcance del filtro.

#### Casos por fuente de notificación

Barras horizontales por fuente, con casos y porcentaje.

## Mortalidad

### Propósito

Analizar las muertes por dengue: cuántas, cuándo, quiénes, dónde y si la letalidad supera la meta nacional. El diseño es sobrio: no alarma visualmente, pero tampoco suaviza la realidad. Es el único lugar del dashboard (junto al KPI de letalidad de Situación) donde se usa color de alerta en un indicador, porque existe un umbral epidemiológico definido.

### Datos y filtros

- Muertes (580), cruzadas con casos 210+220 y graves 220 para las letalidades.
- Responde a los filtros globales. La gráfica de muertes por semana cubre todo el período filtrado.
- Si no hay muertes para los filtros actuales, la pestaña muestra solo el mensaje "No hay muertes por dengue registradas para los filtros actuales".

### Componentes (en orden de aparición)

#### KPI (5 tarjetas)

- Muertes por dengue.
- Mortalidad: muertes / población en riesgo x 100.000 (o "No disponible").
- Menores de 15 años: número y porcentaje del total de muertes.
- Letalidad: con 4 decimales; si supera la meta INS de 0,10 % aparece "Supera la meta INS" en color de alerta.
- Letalidad grave: muertes / casos graves x 100.

#### Par: Muertes por semana epidemiológica + Muertes por régimen de afiliación (SGSSS)

Se filtran en ambos sentidos: hacer clic en semanas filtra el régimen, y hacer clic en un régimen filtra la serie semanal. Sobre el par aparece lo que está seleccionado, con "Quitar selección".

- Muertes por semana epidemiológica: muertes de cada semana del año epidemiológico (1 a 53), sumadas sobre todos los años del filtro; muestra en qué parte del año se concentran.
- Muertes por régimen de afiliación (SGSSS): barras horizontales con número y porcentaje.

#### Indicadores de mortalidad por subregión

- Control segmentado "Indicador": Muertes (conteo), Letalidad (%), Letalidad grave (%) y Tasa de mortalidad (x100.000). Por defecto, Letalidad.
- Barras por subregión con una línea punteada naranja con el valor del Magdalena. Con una sola subregión en el filtro, se pide ampliarlo para poder comparar.

#### Muertes por sexo y edad

Barras horizontales agrupadas por grupo quinquenal de edad, masculino y femenino.

#### Indicadores de mortalidad por territorio

- Control segmentado "Nivel de agregación": Magdalena, Subregión o Municipio.
- Tabla con Territorio, Muertes, Casos (210+220), Casos graves (220), Letalidad (%) y Letalidad grave (%), con fila TOTAL. Se queda en conteos y letalidad (no dependen de población), no en tasas.

#### Muertes por EPS de afiliación

Barras horizontales con las 10 EPS con más muertes de sus afiliados.

#### Diagnóstico que ocasionó la muerte relacionado con el evento

Barras horizontales con los 10 diagnósticos más frecuentes (codificación CIE-10), con número y porcentaje y el nombre junto a cada barra.

## Gestión

### Propósito

Administrar los datos del sistema desde la propia interfaz, sin tocar archivos ni servidores: subir archivos SIVIGILA, reemplazarlos si traen errores, enviarlos a la papelera, restaurarlos y consultar el historial de todo lo ocurrido. Es la pestaña que convierte al dashboard en un sistema mantenible por el propio equipo del CITES.

### Visibilidad

- Solo aparece para Editor y Admin. El Visor no la ve.
- Encabezado: nota "Piezas, papelera e historial no se actualizan automáticamente" y botón "Actualizar".
- Subpestañas: Subir, Piezas activas, Papelera e Historial; para el perfil de administración, además, Pronóstico (solo en las patologías que tienen pronóstico).

### Concepto de pieza

La unidad mínima de datos es la pieza: patología + año + código (por ejemplo dengue 2024 código 210). Es lo que se sube, se reemplaza o se elimina. Los archivos del portal SIVIGILA se llaman Datos_AÑO_CÓDIGO (por ejemplo Datos_2024_580.xls). Se aceptan .xls (formato antiguo, años 2007-2009) y .xlsx.

### Subpestaña Subir

- Zona de carga de archivo (.xls o .xlsx).
- Al cargar, el sistema lee el nombre y autocompleta año y código. Si el nombre no sigue el patrón, avisa y pide completarlos a mano.
- Formulario de confirmación con año y código editables y botón "Confirmar y procesar". La confirmación es una red de seguridad contra archivos mal nombrados.
- Si ya existe una pieza activa con ese año y código, se abre un diálogo "Ya existe una pieza para ese año y código" que advierte que la nueva reemplazará a la anterior (indicando el archivo actual), con opciones Cancelar o "Sí, reemplazar".
- Tras confirmar, aparece un aviso persistente "[archivo] se envió a procesar correctamente" (se cierra con x), la zona de carga se limpia y el archivo entra a la cola. La persona puede seguir trabajando: el procesamiento no bloquea la interfaz.

### Procesamiento en segundo plano (lo que ocurre tras subir)

Un proceso trabajador independiente atiende la cola de a un archivo a la vez (si dos personas suben al mismo tiempo, los archivos se procesan en orden). Por cada archivo:

1. Lee el Excel con un lector rápido (calamine), preparado para archivos de más de 500.000 filas.
2. Lo limpia con el proceso específico de dengue: descarte de unas 29 columnas sin valor analítico, estandarización de nombres y textos, conversión de tipos, construcción de la edad en años, validación geográfica contra DIVIPOLA, recorte a casos ocurridos en el Magdalena, enriquecimiento con tablas de referencia (DIVIPOLA, países, ocupaciones, aseguradoras, CIE-10, grupos étnicos). Resultado: unas 56 columnas.
3. Actualiza el consolidado (la tabla que lee el dashboard) con una operación quirúrgica: agrega las filas de la pieza o, si es un reemplazo, quita las filas de ese año y código y agrega las nuevas. Nunca reprocesa el histórico.
4. Guarda la pieza como archivo Parquet individual; si es un reemplazo, la versión anterior pasa a la papelera.
5. Registra el resultado (listo o fallo, con motivo) y deja traza en la bitácora.

Escritura atómica: el consolidado nuevo se escribe con un nombre temporal, se verifica (que abra, que tenga las columnas y el número de filas esperados) y solo entonces reemplaza al oficial en un cambio instantáneo de nombre. El dashboard nunca puede leer un consolidado a medio escribir. La consolidación se hace antes de guardar la pieza a propósito: si la verificación falla, todavía no se ha tocado ningún archivo de piezas ni de la papelera.

Ante un fallo (archivo ilegible, falta una columna, el consolidado nuevo no pasa la verificación, etc.) no se guarda el Excel, no se tocan los datos previos y el motivo queda registrado como error en el historial de Procesamientos. Al terminar, quien subió recibe la notificación emergente de éxito o fallo, y todas las personas conectadas ven el banner de datos nuevos.

### Ciclo de vida de una pieza

```mermaid
flowchart LR
    N([Archivo nuevo]) -->|Subir| A[Activa]
    A -->|Eliminar o editar| P[Papelera]
    P -->|Restaurar| A
    P -->|Eliminar para siempre| X([Borrada])
```

- Subir: el archivo se procesa y la pieza queda activa, es decir, forma parte de los datos que muestra el dashboard.
- Eliminar: la pieza sale del dashboard y pasa a la papelera, de donde se puede recuperar.
- Editar: se sube una versión corregida que queda activa en su lugar, y la versión anterior pasa a la papelera.
- Restaurar: la pieza vuelve a estar activa. Si ya hay una activa del mismo año y código, el sistema pide confirmar el reemplazo.
- Eliminar para siempre: solo Admin, con confirmación explícita. El archivo se destruye y no se puede recuperar.

La papelera guarda una versión por año y código: si una pieza se edita dos veces sin restaurar la versión intermedia, la más antigua se reemplaza. Todos los movimientos quedan en la bitácora con usuario y fecha.

### Subpestaña Piezas activas

- Matriz "Años con pendientes": filas = códigos esperados (210, 220, 580), columnas = años que tienen algún código faltante. Cada celda es un botón: azul con marca de verificación si la pieza está cargada, gris con símbolo de error si falta. Al pie de cada columna, "2/3" (códigos completos del año). Si todos los años están completos, se muestra "Todos los años tienen los códigos completos".
  - Al pasar el cursor sobre una celda azul: nombre del archivo y fecha de carga. Al hacer clic: detalle y botones Editar (subir versión corregida) y Eliminar (enviar a papelera).
  - Al hacer clic en una celda gris: carga directa del archivo faltante para ese año y código.
  - Esta matriz responde en segundos a la pregunta "¿qué me falta subir?", que es la que determina si un indicador aparece como "No disponible".
- Panel desplegable "Ver todas las piezas (búsqueda y detalle)": lista de tarjetas con buscador (por archivo, año o código) y paginación de 10 en 10. Cada tarjeta muestra archivo, año, código y fecha, con botones Editar y Eliminar.
- Editar = reemplazar la pieza por una versión corregida (no se editan celdas). Se reprocesa solo esa pieza; la versión anterior pasa a la papelera y es recuperable.
- Eliminar = eliminación lógica: la pieza sale del consolidado y pasa a la papelera.

### Subpestaña Papelera

- Tarjetas con buscador y paginación. Cada tarjeta: archivo, año, código y fecha de eliminación.
- Restaurar (Editor y Admin): pide confirmación. Si ya existe una pieza activa con el mismo año y código, avisa "Ya existe una pieza activa con el mismo año y código. Restaurar la reemplazará" y pide confirmar o cancelar; nunca sobrescribe a ciegas.
- Eliminar para siempre (solo Admin): advertencia de acción irreversible y confirmación explícita "Sí, eliminar para siempre". La traza en la bitácora se conserva aunque el archivo desaparezca.
- La papelera es permanente: nada se borra solo por tiempo.

### Subpestaña Historial

- Procesamientos: tres métricas (Exitosos, Con error, Total), buscador por archivo, año, código o usuario, y tarjetas paginadas con archivo, año, código, fecha, usuario y una insignia "Procesado" (azul) o "Error" (roja). Los fallidos tienen un panel desplegable "Ver motivo del error". Es el registro permanente: sirve para consultar un fallo cuya notificación se cerró sin leer, o para que un colega revise desde otro equipo un error que quien subió no entiende.
- Bitácora de movimientos: filtros por tipo de acción (píldoras: Agregar, Editar, Eliminar, Restaurar, Eliminar para siempre) y por usuario (lista desplegable), contador "N de M movimientos" y tabla con Fecha, Acción, Año, Código y Usuario. Responde a "quién hizo qué, sobre qué pieza y cuándo".

### Subpestaña Pronóstico (solo Admin)

Es el único lugar donde se gestionan los modelos de pronóstico. Cambiar un modelo cambia lo que el tablero pronostica para todo el mundo, por eso es un nivel más restrictivo que el resto de Gestión: el Editor no la ve. Solo aparece en las patologías cuyo plugin declara un pronóstico (hoy dengue).

- Modelos activos: una tarjeta por familia con el nombre de la familia en negrita, el modelo activo, su rango de datos, su origen (entrenado en la app o subido), cuándo entró al sistema en hora de Colombia, el código de versión y un aviso si el consolidado ya tiene datos más recientes.
- Entrenar: familia, modelo (los que no tienen su librería instalada aparecen como no disponibles), rango de entrenamiento (deslizador de semanas, desde y hasta) e hiperparámetros en JSON, que parten de los de la versión activa de ese modelo. Opción "Dejarla como activa de su familia al terminar". Con confirmación; el trabajo va a la misma cola que las cargas de archivos y al terminar llega una notificación emergente. El trabajo evalúa el modelo en la prueba (último 15 % del rango), guarda los resultados individuales y las métricas, y después entrena el modelo definitivo con todo el rango.
- Subir modelo: un .zip entrenado en otro equipo con el código del tablero. El procesador lo descomprime de forma segura y lo revisa sin entrenar: formato del manifest, serie, modelo y familia, librería instalada con la misma versión mayor, solo archivos .json, .csv, .txt y .keras, archivos presentes, métricas del manifest iguales a las reconstruidas desde el CSV, carga y pronóstico de prueba. Si algo falla no se guarda nada y el motivo queda en el historial. El botón "Ver estructura del paquete" muestra la estructura, los campos, las columnas del CSV, las reglas, el script para generarlo y, por cada modelo activo, el árbol de su paquete y el contenido real de cada archivo.
- Versiones: filtro por familia y tabla de las versiones vigentes con origen, rango, fecha, usuario, RMSE global (todos los registros de H1 a H6) y razón contra la persistencia. Las versiones del esquema anterior van aparte, en un desplegable de histórico, y no se pueden activar. El selector "Elegir versión" las nombra de forma legible, por ejemplo "XGBoost · 6 nov 2026, 5:09 p. m. · datos 2007-2025 · entrenado en la app · ACTIVA". Sobre la versión elegida: "Activar en su familia" y "Eliminar" (definitivo, con confirmación); la versión activa no se puede eliminar. Un desplegable muestra la serie, la prueba, las métricas globales y por horizonte con su n, las librerías con su compatibilidad y los hiperparámetros.
- Historial: entrenar, subir, activar y eliminar, con fecha, estado, modelo, familia, versión, usuario, rango de datos, duración, archivo subido y motivo del fallo. Un desplegable muestra el detalle de cada movimiento: lo pedido al entrenar, el nombre del .zip al subir y una copia del manifest de cada versión eliminada (hiperparámetros, métricas y rango), que sobrevive aunque la versión ya no exista.
