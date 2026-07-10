"""Poblacion DANE por municipio y anio: denominador de incidencia y mortalidad
en indicators.py. Poblacion en riesgo = poblacion total (area geografica "Total",
cabecera + centros poblados y rural disperso) de TODOS los municipios del Magdalena.

A diferencia de dengue, tuberculosis usa toda la poblacion del departamento, no
filtra por nivel de transmision de vector (TB no es transmitida por vector). No
hay estratificacion de riesgo para TB.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

RUTA_REFERENCIAS = Path(__file__).parent / "config" / "referencias"

COD_DPTO_MAGDALENA = 47


def _leer_archivo_poblacion(ruta: Path) -> pd.DataFrame:
    """Lee un archivo poblacionDane-*.xlsx: busca la hoja y fila de encabezado
    por la columna "DP" y normaliza columnas a cod_dpto, cod_mun_completo, ano,
    area_geografica, poblacion.
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


@st.cache_data
def obtener_poblacion_por_municipio_anio() -> pd.DataFrame:
    """Poblacion del Magdalena por municipio y anio: poblacion total DANE de
    TODOS los 30 municipios. Consolida los archivos poblacionDane-*.xlsx
    disponibles en config/referencias/.

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

    poblacion = poblacion.drop_duplicates(subset=["cod_mun_completo", "ano"], keep="last")

    return poblacion[["cod_mun_completo", "ano", "poblacion"]].reset_index(drop=True)


def obtener_poblacion_departamental(anios_en_alcance: list[int]) -> float | None:
    """Poblacion del Magdalena completo (suma de los 30 municipios) para los anios dados."""
    if not anios_en_alcance:
        return None
    poblacion_municipio = obtener_poblacion_por_municipio_anio()
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]
    anios_con_poblacion = set(poblacion_periodo["ano"].unique())
    if not set(anios_en_alcance).issubset(anios_con_poblacion):
        return None
    return float(poblacion_periodo["poblacion"].sum())


def obtener_poblacion_por_subregion_anio(mapeo_subregion: dict[int, str]) -> pd.DataFrame:
    """Poblacion agregada a nivel subregion (suma de sus municipios) por anio."""
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
