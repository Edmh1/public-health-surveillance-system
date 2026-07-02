"""Geometria de los municipios del Magdalena. Compartido entre patologias: la
geometria de los municipios no cambia segun la patologia, a diferencia del mapeo
a subregion.

municipios_magdalena.geojson es una version PRE-FILTRADA Y SIMPLIFICADA del
GeoJSON nacional del MGN (Marco Geoestadistico Nacional, IGAC): el nacional pesa
273 MB (1122 municipios de todo el pais, ~7700 vertices en promedio por poligono,
precision catastral que un mapa web no necesita). Se genero una sola vez con
shapely (geom.simplify(0.0005, preserve_topology=True), tolerancia ~55m, imper-
ceptible al nivel de zoom de este dashboard) y filtrando a cod_dpto 47 (Magdalena,
el alcance fijo del sistema, ver CLAUDE.md "Alcance geografico y regla de tasas").
Quedo en 480 KB, 30 municipios. Si el geojson nacional se actualiza, regenerar con
el mismo procedimiento (no hace falta shapely en produccion, solo para regenerar).
"""

import json
from pathlib import Path

import streamlit as st

RUTA_GEOJSON_MAGDALENA = Path(__file__).parent / "references" / "municipios_magdalena.geojson"


@st.cache_data
def obtener_geojson_municipios_magdalena() -> dict:
    """GeoJSON de los 30 municipios del Magdalena. La propiedad mpio_cdpmp trae el
    codigo DIVIPOLA completo (departamento+municipio), igual formato que cod_mun_completo.
    """
    with open(RUTA_GEOJSON_MAGDALENA, encoding="utf-8") as archivo:
        return json.load(archivo)
