"""Estratificacion de riesgo de arbovirosis para los 30 municipios del Magdalena,
segun el Lineamiento metodologico para la estratificacion y estimacion de la
poblacion en riesgo para arbovirosis en Colombia 2020-2023 (MSPS/INS). PDF de
referencia: pathologies/dengue/config/referencias/
lineamiento-metodologico-estimacion-poblacion-arbovirosis-colombia-2020-2023.pdf

Calculo puro (sin Streamlit, igual que canal_endemico.py): 4 variables por
municipio (A altura, B presencia del vector, C magnitud de casos, D
persistencia de la transmision), suma 0-12 y clasificacion final (Tabla 4 del
lineamiento). poblacion.py llama a calcular_estratificacion() en vez de leer
el Excel estatico que traia la clasificacion ya publicada en los anexos.

Diferencia real con la metodologia oficial (documentarla, no esconderla): las
variables C y D dependen de percentiles/proporciones sobre el universo de
analisis. El lineamiento los calcula sobre los ~1.122 municipios de Colombia
con las bases nacionales de SIVIGILA (6 anios). Aca solo se tiene el
consolidado de dengue del Magdalena (30 municipios), asi que C y D se calculan
sobre ese universo mas chico. El resultado puede no coincidir exactamente con
la clasificacion oficial publicada en los anexos del lineamiento (Anexos 10 a
17), que fue la fuente del Excel que este modulo reemplaza.

Ademas de las 4 variables, calcula la asignacion de poblacion por area
geografica (Tabla 5 del lineamiento: Cabecera Municipal, Centros Poblados y
Rural Disperso, o Total). El lineamiento la decide por presencia del vector
POR AREA (cabecera / centro poblado / rural disperso), dato que no se tiene
desagregado (solo se tiene presencia del vector a nivel municipio completo,
ver MUNICIPIOS_SIN_VECTOR). En su lugar se usa como proxy la transmision real
de casos por area (columna "area" del dato SIVIGILA, que si se tiene): si un
municipio tiene casos en cabecera Y en zona rural, se le asigna poblacion
Total; si solo en una de las dos, se le asigna solo esa poblacion. Es una
aproximacion razonable (donde hay casos confirmados, hay vector), no lo mismo
que la vigilancia entomologica por area que pide el lineamiento.
"""

import pandas as pd

COD_DENGUE = 210
COD_DENGUE_GRAVE = 220
CODIGOS_CASOS = {COD_DENGUE, COD_DENGUE_GRAVE}

COD_DPTO_MAGDALENA = 47

# ---------------------------------------------------------------------------
# Variable A: altura sobre el nivel del mar (m s.n.m.)
# ---------------------------------------------------------------------------

# Valores de referencia general (fichas municipales de dominio publico), no
# verificados pieza por pieza contra el dato oficial IGAC. No cambia el
# resultado de la variable: los 30 municipios del Magdalena estan muy por
# debajo del umbral de 2.200 m s.n.m. del lineamiento (el punto alto del
# departamento, la Sierra Nevada, no es territorio de ninguna cabecera
# municipal), asi que la categoria "con riesgo por altura" (A=1) es la misma
# para los 30 sin importar el margen de error en el metro exacto.
ALTURA_MUNICIPIO_MSNM: dict[int, int] = {
    47001: 2,     # Santa Marta
    47030: 15,    # Algarrobo
    47053: 32,    # Aracataca
    47058: 42,    # Ariguani
    47161: 20,    # Cerro San Antonio
    47170: 30,    # Chibolo
    47189: 2,     # Cienaga
    47205: 30,    # Concordia
    47245: 20,    # El Banco
    47258: 20,    # El Pinon
    47268: 15,    # El Reten
    47288: 14,    # Fundacion
    47318: 25,    # Guamal
    47460: 40,    # Nueva Granada
    47541: 40,    # Pedraza
    47545: 30,    # Pijino del Carmen
    47551: 30,    # Pivijay
    47555: 40,    # Plato
    47570: 1,     # Puebloviejo
    47605: 10,    # Remolino
    47660: 120,   # Sabanas de San Angel
    47675: 10,    # Salamina
    47692: 30,    # San Sebastian de Buenavista
    47703: 30,    # San Zenon
    47707: 30,    # Santa Ana
    47720: 30,    # Santa Barbara de Pinto
    47745: 5,     # Sitionuevo
    47798: 20,    # Tenerife
    47960: 50,    # Zapayan
    47980: 4,     # Zona Bananera
}

UMBRAL_ALTURA_MSNM = 2200


def _puntaje_altura(cod_municipio: int) -> int:
    altura = ALTURA_MUNICIPIO_MSNM.get(cod_municipio)
    if altura is None:
        return 0
    return 1 if altura <= UMBRAL_ALTURA_MSNM else 0


# ---------------------------------------------------------------------------
# Variable B: presencia del vector (Aedes aegypti)
# ---------------------------------------------------------------------------

# Municipios reportados sin presencia confirmada del vector; informacion
# provista por el equipo (el lineamiento define COMO se construye la
# variable, no trae el dato entomologico en si). El resto del Magdalena
# queda con presencia = si.
MUNICIPIOS_SIN_VECTOR: set[int] = {
    47001,  # Santa Marta
    47745,  # Sitionuevo
    47030,  # Algarrobo
    47161,  # Cerro San Antonio
    47798,  # Tenerife
}


def _puntaje_vector(cod_municipio: int) -> int:
    return 0 if cod_municipio in MUNICIPIOS_SIN_VECTOR else 1


# ---------------------------------------------------------------------------
# Variable C: magnitud de casos (percentiles 25/50/75/90)
# ---------------------------------------------------------------------------

def _calcular_magnitud(casos: pd.DataFrame, municipios: list[int]) -> dict[int, int]:
    """Frecuencia absoluta de casos de dengue por municipio en el periodo de
    analisis disponible, puntuada 0-5: 0 casos -> 0; <P25 -> 1; P25-P50 -> 2;
    P50-P75 -> 3; P75-P90 -> 4; >=P90 -> 5. Percentiles calculados sobre los
    municipios del Magdalena que SI tuvieron casos (los de 0 casos no entran
    en el calculo del percentil, van directo a puntaje 0).
    """
    conteo = casos["cod_mun_completo"].value_counts()
    valores = {municipio: int(conteo.get(municipio, 0)) for municipio in municipios}

    con_casos = pd.Series({m: v for m, v in valores.items() if v > 0})
    if con_casos.empty:
        return {municipio: 0 for municipio in municipios}

    p25, p50, p75, p90 = con_casos.quantile([0.25, 0.5, 0.75, 0.9])

    def puntaje(valor: int) -> int:
        if valor == 0:
            return 0
        if valor < p25:
            return 1
        if valor < p50:
            return 2
        if valor < p75:
            return 3
        if valor < p90:
            return 4
        return 5

    return {municipio: puntaje(valor) for municipio, valor in valores.items()}


# ---------------------------------------------------------------------------
# Variable D: persistencia de la transmision en el tiempo
# ---------------------------------------------------------------------------

def _calcular_persistencia(
    casos: pd.DataFrame, municipios: list[int], anios_periodo: list[int]
) -> dict[int, int]:
    """Indice de persistencia = (semanas con casos / semanas totales del
    periodo) x (anios con casos), puntuado 0-5 dividiendo el rango teorico
    [0, numero de anios del periodo] en 5 categorias iguales (mismo criterio
    del ejemplo del lineamiento en su Tabla 2: ahi el periodo es de 6 anios y
    el rango 0-6 se divide en pasos de 1.2).
    """
    n_anios = len(anios_periodo)
    if n_anios == 0:
        return {municipio: 0 for municipio in municipios}

    semanas_totales = n_anios * 52
    paso = n_anios / 5

    def puntaje(indice: float) -> int:
        if indice <= 0:
            return 0
        if indice <= paso:
            return 1
        if indice <= paso * 2:
            return 2
        if indice <= paso * 3:
            return 3
        if indice <= paso * 4:
            return 4
        return 5

    resultado = {}
    for municipio in municipios:
        casos_municipio = casos[casos["cod_mun_completo"] == municipio]
        if casos_municipio.empty:
            resultado[municipio] = 0
            continue
        semanas_con_casos = casos_municipio.drop_duplicates(subset=["ano", "semana"]).shape[0]
        anios_con_casos = casos_municipio["ano"].nunique()
        indice_persistencia = (semanas_con_casos / semanas_totales) * anios_con_casos
        resultado[municipio] = puntaje(indice_persistencia)

    return resultado


# ---------------------------------------------------------------------------
# Asignacion de poblacion por area geografica (Tabla 5 del lineamiento)
# ---------------------------------------------------------------------------

# Codigos de "area" del dato SIVIGILA (area de ocurrencia del caso).
_AREA_SIVIGILA_CABECERA = 1
_AREA_SIVIGILA_CENTRO_POBLADO = 2
_AREA_SIVIGILA_RURAL_DISPERSO = 3

# Mismos nombres que usa el DANE en area_geografica (ver poblacion.py:
# _AREA_DANE_CABECERA / _AREA_DANE_RESTO); se repiten aca como literales
# (no se importa poblacion.py, que ya importa este modulo) para que
# poblacion.py pueda filtrar directo con el valor que devuelve esta funcion.
POBLACION_CABECERA = "Cabecera Municipal"
POBLACION_RESTO = "Centros Poblados y Rural Disperso"
POBLACION_TOTAL = "Total"


def _calcular_poblacion_asignada(casos: pd.DataFrame, municipios: list[int]) -> dict[int, str]:
    """Que poblacion DANE usar como denominador de cada municipio, segun en
    que area geografica tuvo casos en el periodo (ver docstring del modulo).
    """
    resultado = {}
    for municipio in municipios:
        casos_municipio = casos[casos["cod_mun_completo"] == municipio]
        areas = (
            set(casos_municipio["area"].dropna().astype(int).unique())
            if "area" in casos_municipio.columns
            else set()
        )
        tiene_cabecera = _AREA_SIVIGILA_CABECERA in areas
        tiene_resto = _AREA_SIVIGILA_CENTRO_POBLADO in areas or _AREA_SIVIGILA_RURAL_DISPERSO in areas

        if tiene_cabecera and tiene_resto:
            resultado[municipio] = POBLACION_TOTAL
        elif tiene_cabecera:
            resultado[municipio] = POBLACION_CABECERA
        elif tiene_resto:
            resultado[municipio] = POBLACION_RESTO
        else:
            # Sin ningun caso con area valida en el periodo: se usa Total por
            # defecto (la opcion mas conservadora) para no dejar el
            # denominador en cero por un dato de area faltante.
            resultado[municipio] = POBLACION_TOTAL

    return resultado


# ---------------------------------------------------------------------------
# Suma y clasificacion final (Tabla 4 del lineamiento)
# ---------------------------------------------------------------------------

def _clasificar_nivel_riesgo(puntaje_total: int) -> str:
    if puntaje_total == 0:
        return "Sin riesgo"
    if puntaje_total == 1:
        return "Sin transmisión sin vector"
    if puntaje_total == 2:
        return "Sin transmisión con vector"
    if 3 <= puntaje_total <= 6:
        return "Baja transmisión"
    if 7 <= puntaje_total <= 9:
        return "Mediana transmisión"
    if 10 <= puntaje_total <= 11:
        return "Alta transmisión"
    return "Muy alta transmisión"


# El lineamiento pide "por lo menos seis anios" de historico para magnitud y
# persistencia (Tabla 1 y variable D). Con menos de eso la clasificacion sale
# armada con muy poca informacion, asi que en vez de calcularla "a medias" se
# devuelve vacio (ver calcular_estratificacion): mejor "no disponible" que un
# nivel de riesgo poco confiable.
ANIOS_REQUERIDOS = 6


def calcular_estratificacion(datos: pd.DataFrame) -> pd.DataFrame:
    """Calcula la estratificacion de riesgo (variables A-D, puntaje total y
    nivel de transmision) para los 30 municipios del Magdalena, usando los
    ultimos ANIOS_REQUERIDOS (6) anios de casos disponibles en el consolidado
    (igual que el lineamiento, que trabaja con una ventana fija de 6 anios, no
    con todo el historico acumulado).

    datos: consolidado de dengue con cualquier cod_eve (se filtra aca a
    210+220, el "evento trazador de arbovirosis" segun el lineamiento).

    Devuelve un DataFrame con columnas: cod_municipio, puntaje_altura,
    puntaje_vector, puntaje_magnitud, puntaje_persistencia, puntaje_total,
    nivel_riesgo, poblacion_asignada (una fila por cada uno de los 30
    municipios), o un DataFrame VACIO si el consolidado todavia no tiene los
    6 anios que pide el lineamiento: la estratificacion completa queda "no
    disponible" en vez de calcularse con menos datos de los que la
    metodologia requiere.
    """
    municipios = sorted(ALTURA_MUNICIPIO_MSNM.keys())
    columnas_vacio = [
        "cod_municipio", "puntaje_altura", "puntaje_vector", "puntaje_magnitud",
        "puntaje_persistencia", "puntaje_total", "nivel_riesgo", "poblacion_asignada",
    ]

    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]
    if "cod_dpto_o" in casos.columns:
        casos = casos[casos["cod_dpto_o"] == COD_DPTO_MAGDALENA]

    anios_disponibles = sorted(int(a) for a in casos["ano"].dropna().unique()) if "ano" in casos.columns else []
    if len(anios_disponibles) < ANIOS_REQUERIDOS:
        return pd.DataFrame(columns=columnas_vacio)

    anios_periodo = anios_disponibles[-ANIOS_REQUERIDOS:]
    casos = casos[casos["ano"].isin(anios_periodo)]

    puntajes_magnitud = _calcular_magnitud(casos, municipios)
    puntajes_persistencia = _calcular_persistencia(casos, municipios, anios_periodo)
    poblacion_asignada = _calcular_poblacion_asignada(casos, municipios)

    filas = []
    for municipio in municipios:
        puntaje_altura = _puntaje_altura(municipio)
        puntaje_vector = _puntaje_vector(municipio)
        puntaje_magnitud = puntajes_magnitud[municipio]
        puntaje_persistencia = puntajes_persistencia[municipio]
        puntaje_total = puntaje_altura + puntaje_vector + puntaje_magnitud + puntaje_persistencia
        filas.append({
            "cod_municipio": municipio,
            "puntaje_altura": puntaje_altura,
            "puntaje_vector": puntaje_vector,
            "puntaje_magnitud": puntaje_magnitud,
            "puntaje_persistencia": puntaje_persistencia,
            "puntaje_total": puntaje_total,
            "nivel_riesgo": _clasificar_nivel_riesgo(puntaje_total),
            "poblacion_asignada": poblacion_asignada[municipio],
        })

    return pd.DataFrame(filas)
