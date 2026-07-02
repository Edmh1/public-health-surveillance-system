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
def obtener_poblacion_por_municipio_anio() -> pd.DataFrame:
    """Poblacion en riesgo del Magdalena por municipio y anio: poblacion
    total DANE, solo de municipios con transmision de dengue. Consolida todos
    los archivos poblacionDane-*.xlsx disponibles en config/referencias/.

    Devuelve columnas: cod_mun_completo, ano, poblacion.
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
    poblacion = poblacion[poblacion["area_geografica"].astype(str).str.strip() == "Total"]
    poblacion = poblacion.dropna(subset=["cod_mun_completo", "ano", "poblacion"])
    poblacion["cod_mun_completo"] = poblacion["cod_mun_completo"].astype(int)
    poblacion["ano"] = poblacion["ano"].astype(int)
    poblacion["poblacion"] = poblacion["poblacion"].astype(int)

    # Si dos archivos se solapan en el mismo anio+municipio, se prioriza el
    # ultimo leido: sorted() ya ordena los archivos por nombre, y el nombre
    # poblacionDane-inicio-fin hace que el rango mas reciente quede al final.
    poblacion = poblacion.drop_duplicates(subset=["cod_mun_completo", "ano"], keep="last")

    municipios_con_transmision = _obtener_municipios_con_transmision()
    poblacion = poblacion[poblacion["cod_mun_completo"].isin(municipios_con_transmision)]

    return poblacion[["cod_mun_completo", "ano", "poblacion"]].reset_index(drop=True)
