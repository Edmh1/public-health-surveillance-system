"""Pestana 1 Tendencia: casos por anio, casos semanales, comparacion entre anios,
variacion porcentual, evolucion temporal por subregion o municipio, y mapa del
Magdalena. Ver CLAUDE.md, seccion "Las 5 pestanas del dashboard".

Casos = cod_eve en {210, 220} (dengue y dengue grave). La mortalidad (580) se
muestra en la pestana 5, no aqui.

El mapa colorea por CONTEO de casos, no por incidencia: la incidencia necesita
poblacion en riesgo (proyecciones DANE), que se construye junto a los KPIs al
final por su complejidad (ver CLAUDE.md, "Reglas de calculo de indicadores").
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from core.geografia import obtener_geojson_municipios_magdalena

CODIGOS_CASOS = {210, 220}

OPCIONES_NIVEL_GEOGRAFICO = ["Subregion", "Municipio"]
ETIQUETAS_NIVEL_GEOGRAFICO = {
    "Subregion": ":material/map: Subregion",
    "Municipio": ":material/location_city: Municipio",
}


def mostrar_tendencia(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.")
        return

    columna_anio, columna_variacion = st.columns([3, 1])
    with columna_anio:
        with st.container(border=True, height="stretch"):
            _mostrar_casos_por_anio(casos)
    with columna_variacion:
        with st.container(border=True, height="stretch"):
            _mostrar_variacion_porcentual(casos)

    with st.container(border=True):
        _mostrar_casos_semanales(casos)

    with st.container(border=True):
        _mostrar_evolucion_temporal(casos)

    with st.container(border=True):
        _mostrar_mapa(casos)


def _mostrar_casos_por_anio(casos: pd.DataFrame) -> None:
    st.subheader(":material/bar_chart: Casos por anio")
    casos_por_anio = casos.groupby("ano").size().reset_index(name="casos")

    figura = px.bar(casos_por_anio, x="ano", y="casos", text="casos")
    figura.update_xaxes(type="category", title="Anio")
    figura.update_yaxes(title="Casos")
    st.plotly_chart(figura, width="stretch")


def _mostrar_variacion_porcentual(casos: pd.DataFrame) -> None:
    casos_por_anio = casos.groupby("ano").size().sort_index()

    if len(casos_por_anio) < 2:
        st.metric("Variacion vs anio anterior", "no disponible")
        return

    anio_actual = casos_por_anio.index[-1]
    anio_anterior = casos_por_anio.index[-2]
    casos_actual = casos_por_anio.iloc[-1]
    casos_anterior = casos_por_anio.iloc[-2]
    variacion_porcentual = (casos_actual - casos_anterior) / casos_anterior * 100

    st.metric(
        f"Casos {anio_actual} (vs {anio_anterior})",
        f"{casos_actual:,}",
        delta=f"{variacion_porcentual:+.1f}%",
    )


def _mostrar_casos_semanales(casos: pd.DataFrame) -> None:
    st.subheader(":material/show_chart: Casos semanales por anio")
    casos_semanales = casos.groupby(["ano", "semana"]).size().reset_index(name="casos")
    casos_semanales["ano"] = casos_semanales["ano"].astype(str)

    figura = px.line(
        casos_semanales,
        x="semana",
        y="casos",
        color="ano",
        markers=True,
        labels={"semana": "Semana epidemiologica", "casos": "Casos", "ano": "Anio"},
    )
    st.plotly_chart(figura, width="stretch")


def _mostrar_evolucion_temporal(casos: pd.DataFrame) -> None:
    st.subheader(":material/timeline: Evolucion temporal")
    nivel = st.segmented_control(
        "Agrupar por",
        OPCIONES_NIVEL_GEOGRAFICO,
        default="Subregion",
        required=True,
        format_func=lambda opcion: ETIQUETAS_NIVEL_GEOGRAFICO[opcion],
        key="tendencia_evolucion_nivel",
    )
    columna_nivel = "subregion" if nivel == "Subregion" else "nom_mun_o"

    casos_con_nivel = casos.dropna(subset=[columna_nivel])
    if casos_con_nivel.empty:
        st.info("No hay casos con geografia valida para los filtros actuales.")
        return

    evolucion = casos_con_nivel.groupby(["ano", columna_nivel]).size().reset_index(name="casos")
    evolucion["ano"] = evolucion["ano"].astype(str)

    figura = px.line(
        evolucion,
        x="ano",
        y="casos",
        color=columna_nivel,
        markers=True,
        labels={"ano": "Anio", "casos": "Casos", columna_nivel: nivel},
    )
    st.plotly_chart(figura, width="stretch")


def _mostrar_mapa(casos: pd.DataFrame) -> None:
    st.subheader(":material/map: Mapa del Magdalena")
    nivel = st.segmented_control(
        "Ver por",
        OPCIONES_NIVEL_GEOGRAFICO,
        default="Subregion",
        required=True,
        format_func=lambda opcion: ETIQUETAS_NIVEL_GEOGRAFICO[opcion],
        key="tendencia_mapa_nivel",
    )

    casos_con_geografia = casos[casos["mun_valido"]].dropna(subset=["cod_mun_completo", "subregion"])
    if casos_con_geografia.empty:
        st.info("No hay casos con geografia valida para los filtros actuales.")
        return

    casos_con_geografia = casos_con_geografia.copy()
    casos_con_geografia["cod_mun_completo"] = casos_con_geografia["cod_mun_completo"].astype(int)

    conteo_por_municipio = casos_con_geografia.groupby(["cod_mun_completo", "subregion"]).size()
    conteo_por_municipio = conteo_por_municipio.reset_index(name="casos_municipio")

    if nivel == "Subregion":
        conteo_por_municipio["casos"] = conteo_por_municipio.groupby("subregion")["casos_municipio"].transform("sum")
        etiqueta_color = "Casos (subregion)"
    else:
        conteo_por_municipio["casos"] = conteo_por_municipio["casos_municipio"]
        etiqueta_color = "Casos (municipio)"

    conteo_por_municipio["cod_mun_completo_str"] = conteo_por_municipio["cod_mun_completo"].apply(lambda x: f"{x:05d}")

    geojson_municipios = obtener_geojson_municipios_magdalena()

    figura = px.choropleth(
        conteo_por_municipio,
        geojson=geojson_municipios,
        locations="cod_mun_completo_str",
        featureidkey="properties.mpio_cdpmp",
        color="casos",
        labels={"casos": etiqueta_color},
    )
    figura.update_geos(fitbounds="locations", visible=False)
    figura.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(figura, width="stretch")
    st.caption(
        "Mapa por conteo de casos. La incidencia (tasa por poblacion en riesgo) se "
        "incorpora cuando se construya poblacion en riesgo, junto a los KPIs."
    )
