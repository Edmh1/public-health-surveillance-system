"""Poblacion DANE por municipio y anio: denominador de incidencia y mortalidad
en indicators.py. Poblacion en riesgo = poblacion total (area geografica
"Total", cabecera + centros poblados y rural disperso) de los municipios del
Magdalena clasificados con algun nivel de transmision de dengue segun el
lineamiento MSPS/INS (archivo de estratificacion de arbovirosis).

Los archivos de poblacion son intercambiables: viven en config/referencias/
nombrados poblacionDane-{anio_inicio}-{anio_fin}.xlsx (convencion de nombre de
las publicaciones del DANE). Cuando el DANE publique una proyeccion nueva, se
agrega el archivo con ese nombre y el sistema lo toma solo, sin tocar codigo.
La hoja y la fila de encabezado varian entre publicaciones del DANE, por eso
se detectan buscando la columna "DP" en vez de asumir una posicion fija.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

RUTA_REFERENCIAS = Path(__file__).parent / "config" / "referencias"
RUTA_ESTRATIFICACION = RUTA_REFERENCIAS / "estratificacion_arbovirosis_colombia_2020_2023.xlsx"

COD_DPTO_MAGDALENA = 47

# Niveles del lineamiento MSPS/INS que significan que el municipio NO aporta
# a la poblacion en riesgo de dengue (no hay transmision o no hay vector).
_NIVELES_SIN_TRANSMISION = {
    "Sin riesgo",
    "Sin transmisión sin vector",
    "Sin transmisión con vector",
}


def _leer_archivo_poblacion(ruta: Path) -> pd.DataFrame:
    """Lee un archivo poblacionDane-*.xlsx: busca la hoja y fila de encabezado
    por la columna "DP" (varian entre publicaciones del DANE) y normaliza
    columnas a cod_dpto, cod_mun_completo, ano, area_geografica, poblacion.

    engine="calamine": el lector por defecto de pandas (openpyxl) tarda ~4-6s en
    este archivo porque trae poblacion de TODO el pais (80k+ filas) antes de
    filtrar a Magdalena; calamine (el mismo lector rapido que ya usa
    core/ingestion/procesador.py para las cargas SIVIGILA) lo baja a ~1-2s.
    """
    libro = pd.ExcelFile(ruta, engine="calamine")
    for nombre_hoja in libro.sheet_names:
        vista_previa = pd.read_excel(libro, sheet_name=nombre_hoja, header=None, nrows=30)
        coincidencias = vista_previa[vista_previa.iloc[:, 0].astype(str).str.strip() == "DP"]
        if coincidencias.empty:
            continue
        datos = pd.read_excel(libro, sheet_name=nombre_hoja, header=coincidencias.index[0])
        datos.columns = [str(columna).strip() for columna in datos.columns]
        columna_poblacion = "TOTAL" if "TOTAL" in datos.columns else "Población"
        datos = datos.rename(columns={
            "DP": "cod_dpto",
            "MPIO": "cod_mun_completo",
            "AÑO": "ano",
            "ÁREA GEOGRÁFICA": "area_geografica",
            columna_poblacion: "poblacion",
        })
        return datos[["cod_dpto", "cod_mun_completo", "ano", "area_geografica", "poblacion"]]
    raise ValueError(f"No se encontro la fila de encabezado (columna DP) en {ruta.name}")


def _leer_estratificacion_magdalena() -> pd.DataFrame:
    """Estratificacion de arbovirosis (nivel_riesgo por municipio, lineamiento
    MSPS/INS), acotada al Magdalena. Fuente unica para poblacion en riesgo
    (indicators.py, via _obtener_municipios_con_transmision) y para el filtro
    global "Estratificacion de riesgo" (filtros.py, via
    obtener_mapeo_estratificacion_riesgo).
    """
    estratificacion = pd.read_excel(RUTA_ESTRATIFICACION, engine="calamine")
    return estratificacion[estratificacion["cod_departamento"] == COD_DPTO_MAGDALENA]


def _obtener_municipios_con_transmision() -> set[int]:
    """Municipios del Magdalena con algun nivel de transmision de dengue,
    segun el lineamiento MSPS/INS. Poblacion en riesgo solo cuenta estos
    municipios: los marcados sin riesgo o sin transmision no aportan al
    denominador aunque tengan poblacion.
    """
    magdalena = _leer_estratificacion_magdalena()
    con_transmision = magdalena[~magdalena["nivel_riesgo"].isin(_NIVELES_SIN_TRANSMISION)]
    return set(con_transmision["cod_municipio"].astype(int))


@st.cache_data
def obtener_mapeo_estratificacion_riesgo() -> dict[int, str]:
    """Mapeo de cod_municipio (DIVIPOLA, coincide con cod_mun_completo) a
    nivel_riesgo, para el filtro global "Estratificacion de riesgo"
    (core/dashboard_base/filtros.py). A diferencia de poblacion en riesgo, aqui
    se devuelven TODOS los niveles (incluidos "sin riesgo"/"sin transmision"):
    es un filtro, la persona debe poder ver y elegir cualquier categoria.
    """
    magdalena = _leer_estratificacion_magdalena()
    return magdalena.set_index("cod_municipio")["nivel_riesgo"].to_dict()


@st.cache_data
def _leer_poblacion_magdalena_todas_areas() -> pd.DataFrame:
    """Consolida los archivos poblacionDane-*.xlsx, acotados al Magdalena y a
    los municipios con transmision de dengue, SIN colapsar por area geografica
    (deja Cabecera Municipal, Centros Poblados y Rural Disperso, y Total tal
    como los publica el DANE). Base comun de
    obtener_poblacion_por_municipio_anio (usa solo Total) y
    obtener_poblacion_por_zona_municipio_anio (usa cabecera vs resto).
    """
    archivos = sorted(RUTA_REFERENCIAS.glob("poblacionDane-*.xlsx"))
    if not archivos:
        raise FileNotFoundError(
            "No se encontro ningun archivo poblacionDane-*.xlsx en "
            f"{RUTA_REFERENCIAS}. La poblacion DANE es necesaria para "
            "incidencia y mortalidad."
        )

    piezas = [_leer_archivo_poblacion(archivo) for archivo in archivos]
    poblacion = pd.concat(piezas, ignore_index=True)

    poblacion = poblacion[poblacion["cod_dpto"].astype(str).str.strip() == str(COD_DPTO_MAGDALENA)]
    poblacion = poblacion.dropna(subset=["cod_mun_completo", "ano", "poblacion", "area_geografica"])
    poblacion["cod_mun_completo"] = poblacion["cod_mun_completo"].astype(int)
    poblacion["ano"] = poblacion["ano"].astype(int)
    poblacion["poblacion"] = poblacion["poblacion"].astype(int)
    poblacion["area_geografica"] = poblacion["area_geografica"].astype(str).str.strip()

    # Si dos archivos se solapan en el mismo anio+municipio+area, se prioriza el
    # ultimo leido: sorted() ya ordena los archivos por nombre, y el nombre
    # poblacionDane-inicio-fin hace que el rango mas reciente quede al final.
    poblacion = poblacion.drop_duplicates(subset=["cod_mun_completo", "ano", "area_geografica"], keep="last")

    municipios_con_transmision = _obtener_municipios_con_transmision()
    poblacion = poblacion[poblacion["cod_mun_completo"].isin(municipios_con_transmision)]

    return poblacion.reset_index(drop=True)


@st.cache_data
def obtener_poblacion_por_municipio_anio() -> pd.DataFrame:
    """Poblacion en riesgo del Magdalena por municipio y anio: poblacion
    total DANE, solo de municipios con transmision de dengue.

    Devuelve columnas: cod_mun_completo, ano, poblacion.
    """
    poblacion = _leer_poblacion_magdalena_todas_areas()
    poblacion = poblacion[poblacion["area_geografica"] == "Total"]
    return poblacion[["cod_mun_completo", "ano", "poblacion"]].reset_index(drop=True)


_AREA_DANE_CABECERA = "Cabecera Municipal"
_AREA_DANE_RESTO = "Centros Poblados y Rural Disperso"

# El dato SIVIGILA distingue 3 zonas de ocurrencia (cabecera municipal, centro
# poblado, rural disperso: ver _ZONA_AREA_MAP en tendencia.py) pero el DANE
# solo publica 2 categorias no-Total (cabecera vs el resto combinado); centro
# poblado y rural disperso comparten esa misma poblacion.
ZONA_A_AREA_DANE = {
    "Cabecera municipal": _AREA_DANE_CABECERA,
    "Centro poblado": _AREA_DANE_RESTO,
    "Rural disperso": _AREA_DANE_RESTO,
}


@st.cache_data
def obtener_poblacion_por_zona_municipio_anio() -> pd.DataFrame:
    """Poblacion DANE por municipio, anio y zona (Cabecera Municipal vs
    Centros Poblados y Rural Disperso), sin colapsar a Total. Denominador de
    calcular_tasa_por_zona_municipio (mapa, 3er nivel: zonas dentro de un
    municipio).

    Devuelve columnas: cod_mun_completo, ano, area_geografica, poblacion.
    """
    poblacion = _leer_poblacion_magdalena_todas_areas()
    poblacion = poblacion[poblacion["area_geografica"] != "Total"]
    return poblacion[["cod_mun_completo", "ano", "area_geografica", "poblacion"]].reset_index(drop=True)


def obtener_poblacion_departamental(anios_en_alcance: list[int]) -> float | None:
    """Poblacion en riesgo del Magdalena completo (suma de los 30 municipios) para
    los anios dados. Util para la linea de referencia departamental en graficas
    por subregion (ej. 5.7 en mortalidad.py). None si falta poblacion para alguno
    de esos anios, nunca un numero incompleto.
    """
    if not anios_en_alcance:
        return None
    poblacion_municipio = obtener_poblacion_por_municipio_anio()
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]
    anios_con_poblacion = set(poblacion_periodo["ano"].unique())
    if not set(anios_en_alcance).issubset(anios_con_poblacion):
        return None
    return float(poblacion_periodo["poblacion"].sum())


def obtener_poblacion_por_subregion_anio(mapeo_subregion: dict[int, str]) -> pd.DataFrame:
    """Poblacion en riesgo agregada a nivel subregion (suma de sus municipios) por
    anio. Reutiliza obtener_poblacion_por_municipio_anio(); es la base de las tasas
    por subregion en las vistas (tendencia, morbilidad, mortalidad).

    Devuelve columnas: subregion, ano, poblacion.
    """
    poblacion_municipio = obtener_poblacion_por_municipio_anio().copy()
    poblacion_municipio["subregion"] = poblacion_municipio["cod_mun_completo"].map(mapeo_subregion)
    poblacion_municipio = poblacion_municipio.dropna(subset=["subregion"])
    return poblacion_municipio.groupby(["subregion", "ano"], as_index=False)["poblacion"].sum()


def calcular_tasa_por_subregion(
    eventos: pd.DataFrame,
    anios_en_alcance: list[int],
    mapeo_subregion: dict[int, str],
) -> dict[str, float | None]:
    """Tasa por 100.000 hab. de cada subregion del Magdalena para el conjunto de
    eventos dado (casos o muertes, ya filtrados, con columna "subregion").

    anios_en_alcance son los anios cuya poblacion se suma como denominador
    (persona-anios si son varios, misma logica que indicators.py._poblacion_en_
    riesgo: no se usa un solo anio de referencia si el filtro cubre un rango).
    Si falta poblacion para alguno de los anios pedidos en una subregion, esa
    subregion queda en None (no disponible), nunca en cero: el sistema no
    publica numeros falsos.

    Devuelve un dict {subregion: tasa_o_None}, con TODAS las subregiones del
    mapeo (incluidas las que no tuvieron ningun evento: tasa 0.0, no None).
    """
    poblacion_subregion = obtener_poblacion_por_subregion_anio(mapeo_subregion)
    poblacion_periodo = poblacion_subregion[poblacion_subregion["ano"].isin(anios_en_alcance)]

    resultado: dict[str, float | None] = {}
    for subregion in sorted(set(mapeo_subregion.values())):
        if not anios_en_alcance:
            resultado[subregion] = None
            continue
        poblacion_sub = poblacion_periodo[poblacion_periodo["subregion"] == subregion]
        anios_con_poblacion = set(poblacion_sub["ano"].unique())
        if not set(anios_en_alcance).issubset(anios_con_poblacion):
            resultado[subregion] = None
            continue
        poblacion_total = poblacion_sub["poblacion"].sum()
        n_eventos = int((eventos["subregion"] == subregion).sum())
        resultado[subregion] = n_eventos / poblacion_total * 100_000

    return resultado


def calcular_tasa_por_municipio(
    eventos: pd.DataFrame,
    anios_en_alcance: list[int],
    municipios: list[int],
) -> dict[int, float | None]:
    """Tasa por 100.000 hab. de cada municipio dado, para el conjunto de eventos
    (casos o muertes, ya filtrados, con columna cod_mun_completo). Misma logica
    de persona-anios y "None si falta poblacion" que calcular_tasa_por_subregion,
    pero a escala municipio.

    Devuelve un dict {cod_mun_completo: tasa_o_None}.
    """
    poblacion_municipio = obtener_poblacion_por_municipio_anio()
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]

    resultado: dict[int, float | None] = {}
    for municipio in municipios:
        if not anios_en_alcance:
            resultado[municipio] = None
            continue
        poblacion_mun = poblacion_periodo[poblacion_periodo["cod_mun_completo"] == municipio]
        anios_con_poblacion = set(poblacion_mun["ano"].unique())
        if not set(anios_en_alcance).issubset(anios_con_poblacion):
            resultado[municipio] = None
            continue
        poblacion_total = poblacion_mun["poblacion"].sum()
        n_eventos = int((eventos["cod_mun_completo"] == municipio).sum())
        resultado[municipio] = n_eventos / poblacion_total * 100_000

    return resultado


def calcular_tasa_por_zona_municipio(
    casos_por_zona: dict[str, int],
    codigo_municipio: int,
    anios_en_alcance: list[int],
) -> dict[str, float | None]:
    """Tasa por 100.000 hab. de cada zona (cabecera municipal, centro poblado,
    rural disperso) DENTRO de un solo municipio (mapa, 3er nivel de detalle).

    Centro poblado y rural disperso comparten denominador porque el DANE no
    los separa (ver ZONA_A_AREA_DANE / obtener_poblacion_por_zona_municipio_
    anio); cabecera usa su propio denominador. None si falta poblacion DANE del
    municipio para alguno de los anios pedidos, nunca en cero.
    """
    if not anios_en_alcance:
        return {zona: None for zona in ZONA_A_AREA_DANE}

    poblacion = obtener_poblacion_por_zona_municipio_anio()
    poblacion_municipio = poblacion[poblacion["cod_mun_completo"] == codigo_municipio]
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]

    resultado: dict[str, float | None] = {}
    for zona, area_dane in ZONA_A_AREA_DANE.items():
        poblacion_area = poblacion_periodo[poblacion_periodo["area_geografica"] == area_dane]
        anios_con_poblacion = set(poblacion_area["ano"].unique())
        if not set(anios_en_alcance).issubset(anios_con_poblacion):
            resultado[zona] = None
            continue
        poblacion_total = poblacion_area["poblacion"].sum()
        n_casos = casos_por_zona.get(zona, 0)
        resultado[zona] = n_casos / poblacion_total * 100_000

    return resultado
