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
Quedo en 480 KB, 30 municipios.

El GeoJSON de subregiones se deriva en tiempo de ejecucion (fusionando los
municipios por subregion con shapely), no como archivo aparte: el mapeo
municipio->subregion es intercambiable (vive en la config de cada patologia,
ver CLAUDE.md), asi que fusionar en memoria y cachear mantiene ese unico archivo
como fuente de verdad; cambiarlo reagrupa el mapa sin regenerar nada.
"""

import json
from pathlib import Path

import streamlit as st
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

RUTA_GEOJSON_MAGDALENA = Path(__file__).parent / "references" / "municipios_magdalena.geojson"


@st.cache_data
def obtener_geojson_municipios_magdalena() -> dict:
    """GeoJSON de los 30 municipios del Magdalena. La propiedad mpio_cdpmp trae el
    codigo DIVIPOLA completo (departamento+municipio), igual formato que cod_mun_completo.
    """
    with open(RUTA_GEOJSON_MAGDALENA, encoding="utf-8") as archivo:
        return json.load(archivo)


@st.cache_data
def obtener_geojson_subregiones(mapeo_subregion: dict[int, str]) -> dict:
    """GeoJSON de las 5 subregiones del Magdalena: cada feature es la union de los
    poligonos de los municipios de esa subregion (shapely unary_union). Sirve para
    mapas donde hover/click debe resaltar la subregion completa, no un municipio
    suelto. La propiedad de cada feature es "subregion" (nombre).

    mapeo_subregion (cod_mun_completo -> nombre de subregion) es el mismo mapeo
    intercambiable de la patologia; al pasarlo como argumento, el cache se
    invalida solo si cambia el mapeo.
    """
    municipios = obtener_geojson_municipios_magdalena()

    geometrias_por_subregion: dict[str, list] = {}
    for feature in municipios["features"]:
        cod_municipio = int(feature["properties"]["mpio_cdpmp"])
        subregion = mapeo_subregion.get(cod_municipio)
        if subregion is None:
            continue
        geometrias_por_subregion.setdefault(subregion, []).append(shape(feature["geometry"]))

    features = []
    for subregion, geometrias in sorted(geometrias_por_subregion.items()):
        geometria_unida = unary_union(geometrias)
        features.append({
            "type": "Feature",
            "properties": {"subregion": subregion},
            "geometry": mapping(geometria_unida),
        })

    return {"type": "FeatureCollection", "features": features}
