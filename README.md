<p align="center">
  <img src="assets/logo_sividem.svg" alt="SIVIDEM" width="300">
</p>

<p align="center">
  Sistema de Vigilancia Departamental del Magdalena<br>
  CITES - Centro de Innovación y Transferencia en Salud, Universidad del Magdalena
</p>

# SIVIDEM

SIVIDEM es un dashboard web de vigilancia epidemiológica para el departamento del Magdalena (Colombia). Convierte los microdatos que publica el INS en el portal SIVIGILA en indicadores, mapas, canales endémicos y pronósticos de corto plazo, listos para apoyar decisiones de salud pública a nivel departamental, subregional y municipal.

La primera patología implementada es dengue. El sistema está construido como plataforma modular: cada patología es un plugin que cumple un contrato común, de modo que se pueden agregar nuevas (por ejemplo tuberculosis) sin modificar el núcleo.

La investigación que sustenta el sistema (análisis exploratorio, variables climáticas y comparación de modelos de pronóstico) está en el repositorio [dengue-surveillance-magdalena](https://github.com/Edmh1/dengue-surveillance-magdalena). Ver [Investigación y modelado](#investigación-y-modelado).

## Qué ofrece

- Situación actual: incidencia, mortalidad y letalidad del año (con alerta si la letalidad supera la meta nacional del INS), mapa del estado epidemiológico de cada subregión y canal endémico por los métodos de cuartiles y Bortman, lado a lado, como recomienda el INS.
- Pronóstico: casos esperados en las próximas 1 a 4 semanas con un modelo Prophet autorregresivo, banda de incertidumbre y modo de validación con ejemplos históricos reales en el que el modelo solo ve datos hasta una fecha pasada y se compara con lo que ocurrió después. El modelo se eligió en el [estudio de modelado](https://github.com/Edmh1/dengue-surveillance-magdalena).
- Tendencia: casos por año, comparación semanal contra el año anterior, variación porcentual, mapa interactivo de incidencia en tres niveles (subregión, municipio y zona) y evolución por territorio.
- Sociodemográfica: pirámide por sexo y edad, grupos vulnerables, área, estrato, etnia, pueblos indígenas, régimen de salud, EPS y UPGD notificadoras.
- Morbilidad: gravedad, hospitalización, flujo de clasificación inicial a final (diagrama de Sankey), fuente de notificación y tasas por subregión y municipio.
- Mortalidad: muertes, letalidad y letalidad grave por subregión con referencia departamental, distribución por sexo, edad, semana, régimen y EPS, tabla por territorio y causas CIE-10.
- Gestión de datos desde la interfaz: subida de archivos SIVIGILA, reemplazo de archivos corregidos, papelera con restauración, historial de procesamientos y bitácora de auditoría.
- Multiusuario con roles (Visor, Editor, Admin) y autenticación centralizada en Keycloak.

La descripción completa de cada pestaña, con sus gráficas, selectores y reglas de cálculo, está en la [guía de módulos](docs/modulos.md).


## Arquitectura

SIVIDEM se despliega como cuatro contenedores orquestados con Docker Compose: la aplicación web (Streamlit), un worker de procesamiento (RQ), la cola (Redis) y el proveedor de identidad (Keycloak). Los datos de casos se guardan en Parquet y el estado operativo (procesamientos, bitácora, registro de archivos) en SQLite.

### Vista de contenedores

![Diagrama de contenedores de SIVIDEM](docs/img/arquitectura-contenedores.png)

### Vista de despliegue

![Diagrama de despliegue con Docker Compose](docs/img/arquitectura-despliegue.png)

### Vista de componentes

El núcleo (core/) no conoce ninguna patología en particular; cada patología vive en pathologies/ e implementa el contrato PathologyPlugin.

![Diagrama de componentes del núcleo y los módulos de patología](docs/img/arquitectura-componentes.png)

### Flujo de una carga de datos

```mermaid
flowchart LR
    A["Editor sube el Excel<br/>y confirma año y código"] --> B["El archivo queda<br/>en la cola"]
    B --> C["El worker lo lee<br/>y lo limpia"]
    C --> D{"¿Resultado<br/>válido?"}
    D -->|"Sí"| E["Se actualizan los datos<br/>del dashboard"]
    E --> F["Todos los conectados<br/>ven el aviso de datos nuevos"]
    D -->|"No"| G["Los datos anteriores<br/>quedan intactos"]
    G --> H["Quien subió el archivo<br/>ve el motivo del error"]
```

1. La persona sube el archivo desde la pestaña Gestión. El sistema propone año y código a partir del nombre y ella los confirma.
2. La interfaz no procesa el archivo: lo deja en una cola y la persona puede seguir trabajando. Si dos personas suben al mismo tiempo, los archivos se procesan en orden, uno a la vez.
3. Un proceso aparte (el worker) lee el Excel y lo limpia.
4. Antes de publicar, el sistema comprueba que el resultado esté completo. Si lo está, reemplaza los datos del dashboard de una sola vez, sin que nadie llegue a ver datos a medias, y todas las personas conectadas reciben un aviso para actualizar.
5. Si algo falla (archivo ilegible, falta una columna, resultado incompleto), los datos anteriores no se tocan y quien subió el archivo ve el motivo. El fallo queda registrado en el historial de Procesamientos.

#### Secuencia técnica

El mismo flujo, visto por componente:

```mermaid
sequenceDiagram
    autonumber
    actor E as Editor
    participant D as Dashboard<br/>(Streamlit)
    participant R as Cola<br/>(Redis)
    participant W as Worker<br/>(RQ)
    participant A as Almacenamiento<br/>(Parquet + SQLite)

    E->>D: Sube el Excel y confirma año y código
    D->>R: Encola el trabajo
    D-->>E: "Enviado a procesar"
    R->>W: Entrega el trabajo
    W->>W: Lee y limpia el Excel
    alt Resultado válido
        W->>A: Publica el consolidado nuevo y registra el éxito
    else Falla la lectura, la limpieza o la verificación
        W->>A: Registra el error con su motivo
    end
    Note over D,A: El dashboard consulta el estado en SQLite cada 4 segundos
    D->>A: ¿Terminó el procesamiento?
    A-->>D: Éxito o error
    D-->>E: Notificación con el resultado
```

- El dashboard y el worker no se hablan directamente: se comunican por la cola (para entregar el trabajo) y por SQLite (para saber cómo terminó).
- El consolidado nuevo se escribe aparte y se verifica antes de reemplazar al oficial con un cambio de nombre atómico. Por eso, si algo falla, el consolidado anterior sigue intacto.
- Las demás sesiones abiertas también revisan cada 4 segundos si cambió la fecha de modificación del consolidado. Cuando cambia, muestran el aviso de datos nuevos; los datos solo se recargan cuando cada persona pulsa Actualizar.

## Tecnologías

| Área | Herramienta |
|---|---|
| Interfaz y visualización | Streamlit, Plotly |
| Identidad y acceso | Keycloak (python-keycloak) |
| Procesamiento asíncrono | Redis, RQ |
| Datos de casos | Parquet (pandas, pyarrow) |
| Estado, bitácora y registro | SQLite |
| Lectura de Excel grandes (.xls y .xlsx) | calamine |
| Limpieza de datos | pandas, scikit-learn |
| Pronóstico | Prophet (cmdstanpy), epiweeks |
| Despliegue | Docker, Docker Compose |

## Estructura del repositorio

```
.
├── app.py                      # Entrada del dashboard: registra las patologías y arranca la interfaz
├── worker.py                   # Entrada del worker: atiende la cola, un archivo a la vez
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── assets/                     # Logo e íconos institucionales
├── core/                       # Núcleo, independiente de cualquier patología
│   ├── auth/                   # Contrato AuthProvider, implementación Keycloak y permisos por rol
│   ├── audit/                  # SQLite: procesamientos, bitácora y registro de piezas
│   ├── dashboard_base/         # Layout, login, filtros globales, avisos y pestaña de Gestión
│   ├── ingestion/              # Cola, procesador de piezas y papelera
│   ├── storage/                # Piezas, consolidado y escritura atómica de Parquet
│   ├── references/             # GeoJSON de municipios
│   ├── geografia.py
│   └── registry.py             # Contrato PathologyPlugin y registro de patologías
├── pathologies/
│   └── dengue/                 # Plugin de dengue
│       ├── manifest.yaml       # Nombre, códigos esperados, rutas y columnas
│       ├── plugin.py           # Implementación del contrato
│       ├── clean.py            # Limpieza de los archivos SIVIGILA
│       ├── indicators.py       # Incidencia, mortalidad, letalidad
│       ├── canal_endemico.py   # Cuartiles y Bortman
│       ├── estratificacion.py  # Estratificación de riesgo MSPS/INS
│       ├── poblacion.py        # Población DANE y población en riesgo
│       ├── prediccion.py       # Modelo Prophet-AR
│       ├── schema.py           # Esquema estable de los datos procesados
│       ├── config/             # Subregiones y tablas de referencia
│       └── views/              # Las seis pestañas de análisis
├── docs/                       # Guía de módulos y diagramas
└── data/                       # Piezas, consolidado, papelera y sistema.db (generados en ejecución)
```

## Puesta en marcha

### Requisitos

- Docker y Docker Compose.
- Para desarrollo sin Docker: Python 3.12 y un servidor Redis. El worker de RQ requiere un sistema tipo Unix (Linux, macOS o WSL); en Windows, usar Docker para el worker.

### 1. Variables de entorno

```bash
cp .env.example .env
```

Completar .env. Dentro de Docker Compose el dashboard llega a Keycloak por el nombre del servicio:

```env
KEYCLOAK_SERVER_URL=http://keycloak:8080/
KEYCLOAK_REALM=cites
KEYCLOAK_CLIENT_ID=dashboard
KEYCLOAK_CLIENT_SECRET=<secreto del cliente en Keycloak>
```

### 2. Levantar los servicios

```bash
docker compose up --build
```

- Dashboard: http://localhost:8501
- Consola de Keycloak: http://localhost:8080 (credenciales iniciales admin / admin definidas en docker-compose.yml; cambiarlas fuera de un entorno local)

La primera construcción tarda varios minutos porque Prophet compila cmdstan durante la instalación.

### 3. Configurar Keycloak

1. Crear el realm cites.
2. Crear el cliente dashboard con autenticación de cliente activada y el flujo Direct access grants habilitado (el login usa usuario y contraseña). Copiar su secreto en KEYCLOAK_CLIENT_SECRET y reiniciar el dashboard.
3. Crear los realm roles Visor, Editor y Admin.
4. Crear las cuentas y asignar a cada una uno de esos roles. Una cuenta sin ninguno de los tres roles no puede ingresar.

| Rol | Permisos |
|---|---|
| Visor | Ver todas las pestañas de análisis. |
| Editor | Todo lo del Visor, más subir, reemplazar y enviar a papelera archivos, restaurar desde la papelera y consultar procesamientos y bitácora. |
| Admin | Todo lo del Editor, más eliminar archivos para siempre desde la papelera. |

Los permisos de cada rol se definen en la aplicación (core/auth/permisos.py); Keycloak solo entrega la identidad y el rol.

### Desarrollo sin Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# con Redis y Keycloak disponibles y .env apuntando a ellos (por ejemplo KEYCLOAK_SERVER_URL=http://localhost:8080/)
python worker.py
streamlit run app.py
```

## Carga de datos

1. Descargar del portal de microdatos de SIVIGILA (INS) los archivos de dengue por año: código 210 (dengue), 220 (dengue grave) y 580 (mortalidad por dengue). El portal los nombra Datos_AÑO_CÓDIGO, por ejemplo Datos_2024_580.xls.
2. Ingresar con una cuenta Editor o Admin, abrir la pestaña Gestión y subir cada archivo. El sistema propone año y código a partir del nombre y pide confirmarlos.
3. La matriz de Piezas activas muestra qué combinaciones de año y código faltan.

Algunos análisis necesitan historia acumulada: el canal endémico pide al menos 5 años anteriores al año de vigilancia, la estratificación de riesgo (y con ella las tasas con población en riesgo) pide 6 años y el pronóstico necesita alrededor de 120 semanas continuas.

El procesamiento recorta automáticamente los casos al Magdalena por departamento de ocurrencia, valida los municipios contra DIVIPOLA y enriquece el dato con las tablas de referencia de pathologies/dengue/config/referencias (DIVIPOLA, países, ocupaciones, aseguradoras, CIE-10, grupos étnicos y proyecciones de población DANE).

## Agregar una nueva patología

1. Crear la carpeta pathologies/nombre_patologia/ con su manifest.yaml (nombre, códigos esperados, rutas y columnas).
2. Implementar una clase que herede de PathologyPlugin (core/registry.py): limpieza, indicadores, canal endémico, esquema, mapeo de subregiones y la lista de pestañas que expone. La estratificación de riesgo es opcional.
3. Registrar el plugin en app.py y en worker.py con registrar_patologia(...).

El selector de patología, los filtros globales, la subida de archivos, la papelera, el historial, los avisos y la escritura atómica funcionan sin cambios para la nueva patología.

## Investigación y modelado

El análisis y la experimentación previos al sistema viven en un repositorio aparte: [dengue-surveillance-magdalena](https://github.com/Edmh1/dengue-surveillance-magdalena). Usa la serie histórica de SIVIGILA 2007-2024 del Magdalena y deja trazados los experimentos con MLflow. Este repositorio lleva a producción lo que allí se validó.

| Notebook | Qué contiene | Qué aportó a SIVIDEM |
|---|---|---|
| [01 Análisis exploratorio](https://github.com/Edmh1/dengue-surveillance-magdalena/blob/main/notebooks/01_dengue_eda.ipynb) | Limpieza y consolidación de los microdatos SIVIGILA | Las reglas de limpieza que aplica el worker (pathologies/dengue/clean.py) y la evidencia de subnotificación que llevó a calcular tasas por subregión |
| [02 Variables climáticas](https://github.com/Edmh1/dengue-surveillance-magdalena/blob/main/notebooks/02_dengue_climate_feature.ipynb) | Temperatura, precipitación y humedad de NASA POWER, ERA5 y CHIRPS, validadas contra estaciones del IDEAM | Las covariables climáticas que se evaluaron en el modelado |
| [03 Modelado](https://github.com/Edmh1/dengue-surveillance-magdalena/blob/main/notebooks/03_dengue_modeling.ipynb) | Comparación de SARIMAX, Prophet, XGBoost, LightGBM, LSTM y N-BEATS con evaluación walk-forward | La elección de Prophet con rezagos de 1, 2, 4 y 8 semanas |
| [04 Agrupamiento](https://github.com/Edmh1/dengue-surveillance-magdalena/blob/main/notebooks/04_dengue_clustering.ipynb) | Agrupación de los municipios del Magdalena según su clima | Trabajo exploratorio, no integrado al sistema |
| [05 Ablación clima vs. rezagos](https://github.com/Edmh1/dengue-surveillance-magdalena/blob/main/notebooks/05_dengue_ablacion_clima_vs_lags.ipynb) | Aporte del clima frente al de los casos de semanas anteriores, por horizonte | Pronóstico sin variables climáticas y horizonte máximo de 4 semanas |

Las métricas de validación del modelo (R2 y RMSE por horizonte) se resumen dentro del propio dashboard, en el diálogo de Fundamentación de la pestaña Pronóstico.

## Metodología y referencias

- Protocolo de vigilancia en salud pública de dengue, Instituto Nacional de Salud (INS).
- Bortman M. Elaboración de corredores o canales endémicos mediante planillas de cálculo. Rev Panam Salud Pública. 1999;5(1).
- Lineamiento metodológico para la estratificación y estimación de la población en riesgo para arbovirosis en Colombia 2020-2023, Ministerio de Salud y Protección Social e INS.
- Proyecciones de población municipal DANE, Censo Nacional de Población y Vivienda 2018.
- Taylor SJ, Letham B. Forecasting at scale. The American Statistician. 2018;72(1).

## Créditos

Desarrollado para el CITES (Centro de Innovación y Transferencia en Salud) de la Universidad del Magdalena, Santa Marta, Colombia.
