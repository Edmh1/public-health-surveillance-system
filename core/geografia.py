"""Geometria de los municipios del Magdalena, leida del GeoJSON nacional del MGN
(Marco Geoestadistico Nacional, IGAC) en core/references/. Se filtra una sola vez al
departamento del Magdalena (cod_dpto 47), el alcance fijo del sistema (ver CLAUDE.md,
"Alcance geografico y regla de tasas"). Compartido entre patologias: la geometria de
los municipios no cambia segun la patologia, a diferencia del mapeo a subregion.
"""

import json
from pathlib import Path

import streamlit as st

RUTA_GEOJSON_NACIONAL = Path(__file__).parent / "references" / "MGN_ADM_MPIO_GRAFICO.geojson"
COD_DPTO_MAGDALENA = "47"


@st.cache_data
def obtener_geojson_municipios_magdalena() -> dict:
    """GeoJSON de los 30 municipios del Magdalena. La propiedad mpio_cdpmp trae el
    codigo DIVIPOLA completo (departamento+municipio), igual formato que cod_mun_completo.
    """
    with open(RUTA_GEOJSON_NACIONAL, encoding="utf-8") as archivo:
        geojson_nacional = json.load(archivo)

    features_magdalena = [
        feature
        for feature in geojson_nacional["features"]
        if feature["properties"]["dpto_ccdgo"] == COD_DPTO_MAGDALENA
    ]
    return {"type": "FeatureCollection", "features": features_magdalena}
