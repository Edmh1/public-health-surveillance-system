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

urbano_rural_magdalena.geojson es la capa que parte cada municipio en sus tres
clases de area (cabecera, centros poblados y rural disperso): 340 poligonos (30
cabeceras, 280 centros poblados, 30 rurales dispersos). Sale del archivo
original magdalena_urbano_rural.geojson (12,6 MB, WGS84 / EPSG:4326, fuente DANE
MGN 2020 para el perimetro urbano y CNPV 2018 para manzanas y secciones rurales;
nombres de DIVIPOLA), con una CORRECCION de la cabecera: en el original, el
poligono de clase "cabecera" es todo el sector urbano MGN 2020 del municipio, que
incluye tambien el casco urbano de cada centro poblado (en 29 de los 30
municipios, 279 de los 280 centros poblados quedaban dentro de esa "cabecera").
Se separo asi: las piezas del sector urbano que no tocan ningun centro poblado
quedan como cabecera; cada pieza que cae sobre un centro poblado se une a ese
centro poblado (al de mayor solape si toca dos). En El Reten y San Sebastian de
Buenavista quedan 2 y 3 piezas sin centro poblado encima: se dejan como cabecera
porque no hay como saber de quien son. Despues se simplifico igual que el de
municipios: shapely geom.simplify(0.0005, preserve_topology=True), coordenadas a 5
decimales (~1 m) y solo las propiedades que usa el dashboard (divipola, clase,
codigo, nombre, area_ha). Quedo en 0,5 MB. El campo clase coincide con el area
de ocurrencia de SIVIGILA (1 cabecera, 2 centro poblado, 3 rural disperso). El
script de la correccion es corregir_urbano_rural.py (fuera del repositorio).

Limites de uso de esa capa (vienen del LEEME del archivo original y se declaran
en la interfaz, debajo del mapa):
- El poligono de un centro poblado es la union de las manzanas censales de 2018,
  no un perimetro normativo: marca donde hay manzanas, no el borde legal.
- Las clases vienen de dos anios distintos (perimetro urbano 2020, manzanas y
  secciones 2018) y se solapan un poco: area_ha no se suma entre clases sin
  descontar ese solape.
- Dos centros poblados no tienen nombre en la DIVIPOLA consultada: 47570008
  (Puebloviejo) y 47660015 (Sabanas de San Angel).
"""

import json
from pathlib import Path

import streamlit as st
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

RUTA_GEOJSON_MAGDALENA = Path(__file__).parent / "references" / "municipios_magdalena.geojson"
RUTA_GEOJSON_URBANO_RURAL = Path(__file__).parent / "references" / "urbano_rural_magdalena.geojson"

# Clase de la capa urbano-rural que corresponde a la cabecera municipal (area 1
# de ocurrencia de SIVIGILA). Las otras dos clases de la capa (centro_poblado y
# rural_disperso) se dibujan juntas como resto rural.
CLASE_CABECERA = "cabecera"

ATRIBUCION_CAPA_URBANO_RURAL = (
    "Fuente: DANE, Marco Geoestadístico Nacional 2020 (perímetro urbano) y Censo Nacional "
    "de Población y Vivienda 2018 (manzanas y secciones rurales); nombres de DIVIPOLA."
)


@st.cache_data(show_spinner=False)
def _leer_geojson_urbano_rural() -> dict:
    with open(RUTA_GEOJSON_URBANO_RURAL, encoding="utf-8") as archivo:
        return json.load(archivo)


@st.cache_data(show_spinner=False)
def obtener_geojson_zonas_municipio(codigo_municipio: int) -> dict:
    """Poligonos de cabecera, centros poblados y rural disperso de UN municipio.
    Se filtra antes de dibujar: nunca se pintan los 340 poligonos a la vez.
    La propiedad codigo identifica cada poligono (8 digitos para cabecera y
    centro poblado, el del municipio para rural disperso).
    """
    capa = _leer_geojson_urbano_rural()
    codigo_texto = f"{int(codigo_municipio):05d}"
    features = [
        feature for feature in capa["features"]
        if feature["properties"]["divipola"] == codigo_texto
    ]
    return {"type": "FeatureCollection", "features": features}


ZONA_GEOMETRIA_CABECERA = "cabecera"
ZONA_GEOMETRIA_RESTO_RURAL = "resto_rural"


@st.cache_data(show_spinner=False)
def obtener_geojson_dos_zonas_municipio(codigo_municipio: int) -> dict:
    """Las dos zonas de UN municipio que tienen dato: la cabecera y el resto
    rural, que es la union de los centros poblados y el rural disperso en una
    sola figura. Los centros poblados no se dibujan por separado: no hay casos ni
    poblacion a ese nivel de desagregacion (SIVIGILA no registra en cual centro
    poblado ocurrio el caso y el DANE no publica poblacion por centro poblado),
    asi que pintarlos sugeriria un dato que no existe.

    La propiedad zona identifica cada feature: ZONA_GEOMETRIA_CABECERA o
    ZONA_GEOMETRIA_RESTO_RURAL.
    """
    geojson = obtener_geojson_zonas_municipio(codigo_municipio)
    cabecera = []
    resto_rural = []
    for feature in geojson["features"]:
        geometria = shape(feature["geometry"]).buffer(0)
        if feature["properties"]["clase"] == CLASE_CABECERA:
            cabecera.append(geometria)
        else:
            resto_rural.append(geometria)

    cabecera_unida = unary_union(cabecera)

    # El resto rural es todo el municipio menos la cabecera. Se toma el contorno
    # exterior de la union (sin huecos) y se le resta la cabecera: al unir
    # centros poblados de 2018 y 2020 con el rural disperso quedaban huecos
    # diminutos donde los bordes no encajan, y se veian como puntos blancos.
    todo_el_municipio = unary_union(cabecera + resto_rural)
    if todo_el_municipio.geom_type == "MultiPolygon":
        partes = list(todo_el_municipio.geoms)
    else:
        partes = [todo_el_municipio]
    contorno_sin_huecos = unary_union([Polygon(parte.exterior) for parte in partes])
    resto_rural_unido = contorno_sin_huecos.difference(cabecera_unida)

    features = []
    for zona, geometria in ((ZONA_GEOMETRIA_CABECERA, cabecera_unida), (ZONA_GEOMETRIA_RESTO_RURAL, resto_rural_unido)):
        if geometria.is_empty:
            continue
        features.append({
            "type": "Feature",
            "properties": {"zona": zona},
            "geometry": mapping(geometria),
        })
    return {"type": "FeatureCollection", "features": features}


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
