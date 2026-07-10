"""Pestana 5 Resistencia: farmacorresistencia en TB.

La resistencia se aproxima por el codigo de evento SIVIGILA 825
(Tuberculosis Farmacoresistente). No hay datos de sensibilidad
individual ni perfiles RR/MDR/XDR en la fuente actual.

KPIs: % resistente, tendencia temporal, distribucion geografica.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.geografia import obtener_geojson_municipios_magdalena

COD_TB_PULMONAR = 820
COD_TB_EXTRAPULMONAR = 810
COD_TB_RESISTENTE = 825


def _casos_base(datos: pd.DataFrame) -> pd.DataFrame:
    codigos = set(datos["cod_eve"].unique())
    if codigos == {COD_TB_RESISTENTE}:
        return datos
    return datos[datos["cod_eve"].isin({COD_TB_PULMONAR, COD_TB_EXTRAPULMONAR})]

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0))


def mostrar_resistencia(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    casos = _casos_base(datos)
    resistentes = datos[datos["cod_eve"] == COD_TB_RESISTENTE]

    if casos.empty:
        st.info("No hay casos de tuberculosis para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(casos, resistentes)

    st.space("small")

    col_tendencia, col_tipo = st.columns(2)
    with col_tendencia:
        with st.container(border=True):
            _mostrar_tendencia_resistencia(datos)
    with col_tipo:
        with st.container(border=True):
            _mostrar_composicion_resistencia(casos, resistentes)

    st.space("small")

    with st.container(border=True):
        _mostrar_mapa_resistencia(datos)


def _mostrar_kpis(casos: pd.DataFrame, resistentes: pd.DataFrame) -> None:
    total = len(casos)
    n_resistentes = len(resistentes)
    pct = n_resistentes / total * 100 if total else None

    pulmonar = int((casos["cod_eve"] == COD_TB_PULMONAR).sum())
    extrapulmonar = int((casos["cod_eve"] == COD_TB_EXTRAPULMONAR).sum())

    cols = st.columns(4)
    cols[0].metric("Casos TB resistente", f"{n_resistentes:,}")
    cols[1].metric(
        "% del total",
        f"{pct:.2f}%" if pct is not None else "N/D",
    )
    cols[2].metric("TB Pulmonar", f"{pulmonar:,}")
    cols[3].metric("TB Extrapulmonar", f"{extrapulmonar:,}")


def _mostrar_tendencia_resistencia(datos: pd.DataFrame) -> None:
    copia = datos.copy()
    copia["es_resistente"] = copia["cod_eve"] == COD_TB_RESISTENTE

    por_anio = copia.groupby("ano").agg(
        total=("cod_eve", "count"),
        resistentes=("es_resistente", "sum"),
    ).reset_index()

    por_anio["ano"] = por_anio["ano"].astype(int)
    por_anio["pct"] = (por_anio["resistentes"] / por_anio["total"] * 100).round(2)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=por_anio["ano"], y=por_anio["resistentes"],
        name="Casos resistentes",
        marker_color="#c0392b",
    ))
    fig.add_trace(go.Scatter(
        x=por_anio["ano"], y=por_anio["pct"],
        name="% del total", mode="lines+markers",
        yaxis="y2",
        line=dict(color=NARANJA_INSTITUCIONAL, width=2),
    ))

    fig.update_layout(
        title="Evolución de TB farmacorresistente",
        yaxis=dict(title="Casos"),
        yaxis2=dict(title="%", overlaying="y", side="right"),
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_composicion_resistencia(casos: pd.DataFrame, resistentes: pd.DataFrame) -> None:
    if resistentes.empty:
        st.info("No hay casos de TB resistente en el periodo.", icon=":material/info:")
        return

    copia = casos.copy()
    copia["tipo"] = "Pulmonar"
    copia.loc[copia["cod_eve"] == COD_TB_EXTRAPULMONAR, "tipo"] = "Extrapulmonar"

    por_tipo = copia.groupby("tipo").size().reset_index(name="casos")
    colores = {"Pulmonar": AZUL_INSTITUCIONAL, "Extrapulmonar": NARANJA_INSTITUCIONAL}

    fig = px.bar(
        por_tipo, x="tipo", y="casos", color="tipo",
        title="Distribución por tipo de TB",
        color_discrete_map=colores,
        text="casos",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, showlegend=False, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    if "sexo" in resistentes.columns:
        por_sexo = resistentes.groupby("sexo").size().reset_index(name="casos")
        st.caption(f"Resistentes por sexo: "
                   f"M: {por_sexo[por_sexo['sexo'].isin(['m', 'M'])]['casos'].sum()}  |  "
                   f"F: {por_sexo[por_sexo['sexo'].isin(['f', 'F'])]['casos'].sum()}")


def _mostrar_mapa_resistencia(datos: pd.DataFrame) -> None:
    copia = datos.copy()
    copia["es_resistente"] = copia["cod_eve"] == COD_TB_RESISTENTE

    por_mun = copia.groupby("cod_mun_completo").agg(
        total=("cod_eve", "count"),
        resistentes=("es_resistente", "sum"),
    ).reset_index()

    por_mun["pct"] = (por_mun["resistentes"] / por_mun["total"] * 100).round(2)
    por_mun["cod_mun_str"] = por_mun["cod_mun_completo"].astype(str)

    geojson = obtener_geojson_municipios_magdalena()

    fig = px.choropleth_mapbox(
        por_mun,
        geojson=geojson,
        locations="cod_mun_str",
        featureidkey="properties.mpio_cdpmp",
        color="pct",
        color_continuous_scale=["#f7f7f7", "#fdd49e", "#fdbb84", "#fc8d59", "#e34a33", "#b30000"],
        mapbox_style="carto-positron",
        center={"lat": 10.4, "lon": -74.2},
        zoom=7.5,
        title="% TB resistente por municipio",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)
