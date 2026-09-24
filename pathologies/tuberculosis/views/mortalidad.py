"""Pestana de Mortalidad: defunciones por TB.

KPIs: total muertes, tasa de mortalidad, letalidad, muertes < 15 anios.
Graficas: muertes por anio, distribucion por sexo y edad, muertes
por municipio, letalidad en el tiempo.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.geografia import obtener_geojson_municipios_magdalena

COD_PULMONAR = 820
COD_EXTRAPULMONAR = 810
COD_RESISTENTE = 825
CODIGOS_BASE = {COD_PULMONAR, COD_EXTRAPULMONAR}

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0))

GRUPOS_ETARIOS = [
    (0, 4, "0-4"), (5, 14, "5-14"), (15, 24, "15-24"),
    (25, 44, "25-44"), (45, 64, "45-64"), (65, 200, "65+"),
]


def _clasificar_grupo_etario(edad):
    for minimo, maximo, etiqueta in GRUPOS_ETARIOS:
        if pd.notna(edad) and minimo <= edad <= maximo:
            return etiqueta
    return "Sin dato"


def _casos_total(datos: pd.DataFrame) -> pd.DataFrame:
    codigos = set(datos["cod_eve"].unique())
    if codigos == {COD_RESISTENTE}:
        return datos
    return datos[datos["cod_eve"].isin({COD_PULMONAR, COD_EXTRAPULMONAR})]


def mostrar_mortalidad(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    casos = _casos_total(datos)
    muertes = casos[casos["fec_def"].notna()] if "fec_def" in casos.columns else pd.DataFrame()

    if casos.empty:
        st.info("No hay casos de tuberculosis para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(casos, muertes)

    st.space("small")

    col_anual, col_sexo = st.columns(2)
    with col_anual:
        with st.container(border=True):
            _mostrar_muertes_por_anio(muertes, casos)
    with col_sexo:
        with st.container(border=True):
            _mostrar_muertes_sexo_edad(muertes)

    st.space("small")

    with st.container(border=True):
        _mostrar_mapa_muertes(casos, muertes)

    st.space("small")

    with st.container(border=True):
        _mostrar_letalidad_temporal(casos, muertes)


def _mostrar_kpis(casos: pd.DataFrame, muertes: pd.DataFrame) -> None:
    total_casos = len(casos)
    total_muertes = len(muertes)
    letalidad = total_muertes / total_casos * 100 if total_casos else None

    if "edad_anios" in muertes.columns:
        muertes_menores_15 = int((muertes["edad_anios"] < 15).sum())
    else:
        muertes_menores_15 = 0

    cols = st.columns(4)
    cols[0].metric("Total muertes", f"{total_muertes:,}")
    cols[1].metric("Letalidad", f"{letalidad:.2f}%" if letalidad is not None else "N/D")
    cols[2].metric("Muertes < 15 años", f"{muertes_menores_15:,}")
    cols[3].metric("Total casos", f"{total_casos:,}")


def _mostrar_muertes_por_anio(muertes: pd.DataFrame, casos: pd.DataFrame) -> None:
    por_anio_m = muertes.groupby("ano").size().reset_index(name="muertes")
    por_anio_c = casos.groupby("ano").size().reset_index(name="casos")
    por_anio = por_anio_c.merge(por_anio_m, on="ano", how="left")
    por_anio["muertes"] = por_anio["muertes"].fillna(0).astype(int)
    por_anio["ano"] = por_anio["ano"].astype(int)
    por_anio = por_anio.sort_values("ano")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=por_anio["ano"], y=por_anio["casos"],
        name="Casos", marker_color=AZUL_INSTITUCIONAL, opacity=0.6,
    ))
    fig.add_trace(go.Bar(
        x=por_anio["ano"], y=por_anio["muertes"],
        name="Muertes", marker_color="#c0392b",
    ))
    fig.update_layout(
        title="Casos y muertes por TB (anual)",
        barmode="overlay",
        **_LAYOUT_BASE, xaxis_title=None, yaxis_title=None,
    )
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_muertes_sexo_edad(muertes: pd.DataFrame) -> None:
    if muertes.empty:
        st.info("No hay muertes registradas en el periodo.", icon=":material/info:")
        return

    if "edad_anios" not in muertes.columns:
        st.info("Datos de edad no disponibles.", icon=":material/info:")
        return

    copia = muertes.copy()
    copia["grupo_etario"] = copia["edad_anios"].apply(_clasificar_grupo_etario)

    masc = copia[copia["sexo"].isin(["m", "masculino"])]
    fem = copia[copia["sexo"].isin(["f", "femenino"])]

    etiquetas = [g[2] for g in GRUPOS_ETARIOS]
    por_edad_masc = masc.groupby("grupo_etario").size()
    por_edad_fem = fem.groupby("grupo_etario").size()

    valores_masc = [-por_edad_masc.get(e, 0) for e in etiquetas]
    valores_fem = [por_edad_fem.get(e, 0) for e in etiquetas]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=etiquetas, x=valores_masc, orientation="h",
        name="Masculino", marker_color=AZUL_INSTITUCIONAL,
    ))
    fig.add_trace(go.Bar(
        y=etiquetas, x=valores_fem, orientation="h",
        name="Femenino", marker_color=NARANJA_INSTITUCIONAL,
    ))
    fig.update_layout(
        title="Muertes por grupo etario y sexo",
        barmode="relative",
        xaxis_title="Muertes",
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_mapa_muertes(casos: pd.DataFrame, muertes: pd.DataFrame) -> None:
    por_mun = casos.groupby("cod_mun_completo").size().reset_index(name="casos")
    muertes_por_mun = muertes.groupby("cod_mun_completo").size().reset_index(name="muertes")
    por_mun = por_mun.merge(muertes_por_mun, on="cod_mun_completo", how="left")
    por_mun["muertes"] = por_mun["muertes"].fillna(0).astype(int)
    por_mun["cod_mun_str"] = por_mun["cod_mun_completo"].astype(str)

    geojson = obtener_geojson_municipios_magdalena()

    fig = px.choropleth_mapbox(
        por_mun,
        geojson=geojson,
        locations="cod_mun_str",
        featureidkey="properties.mpio_cdpmp",
        color="muertes",
        color_continuous_scale=["#f7f7f7", "#fdd49e", "#fdbb84", "#fc8d59", "#e34a33", "#b30000"],
        mapbox_style="carto-positron",
        center={"lat": 10.4, "lon": -74.2},
        zoom=7.5,
        title="Muertes por TB — municipio",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_letalidad_temporal(casos: pd.DataFrame, muertes: pd.DataFrame) -> None:
    por_anio_c = casos.groupby("ano").size().reset_index(name="casos")
    por_anio_m = muertes.groupby("ano").size().reset_index(name="muertes")
    por_anio = por_anio_c.merge(por_anio_m, on="ano", how="left")
    por_anio["muertes"] = por_anio["muertes"].fillna(0).astype(int)
    por_anio["ano"] = por_anio["ano"].astype(int)
    por_anio["letalidad"] = (por_anio["muertes"] / por_anio["casos"] * 100).round(2)

    fig = px.line(
        por_anio, x="ano", y="letalidad",
        title="Letalidad por TB en el tiempo",
        markers=True,
        color_discrete_sequence=[NARANJA_INSTITUCIONAL],
    )
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title="%")
    st.plotly_chart(fig, use_container_width=True)
