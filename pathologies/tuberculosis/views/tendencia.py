"""Pestana 1 Tendencia: evolucion temporal de casos de TB.

Casos = cod_eve en {810, 820, 825}. El analisis semanal usa un selector de anio
propio que ignora el filtro temporal global.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.geografia import obtener_geojson_municipios_magdalena, obtener_geojson_subregiones
from pathologies.tuberculosis.geografia import obtener_mapeo_subregion
from pathologies.tuberculosis.poblacion import calcular_tasa_por_subregion
from pathologies.tuberculosis.views.utils import aplicar_filtro_tipo_tb

CODIGOS_TB = {810, 820, 825}

ESCALA_INCIDENCIA = ["#9ecae1", "#5ba3d0", "#2a6db0", "#1b3a6b"]

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0))


def mostrar_tendencia(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    datos = aplicar_filtro_tipo_tb(datos)
    casos = datos[datos["cod_eve"].isin(CODIGOS_TB)]

    if casos.empty:
        st.info("No hay casos de tuberculosis para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(casos)

    st.space("small")

    col_serie, col_mapa = st.columns([1, 1.2])
    with col_serie:
        with st.container(border=True):
            _mostrar_casos_por_anio(casos)
    with col_mapa:
        with st.container(border=True):
            _mostrar_mapa(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_seccion_semanal(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_incidencia_por_territorio(casos)


def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)
    pulmonar = int((casos["cod_eve"] == 820).sum())
    extrapulmonar = int((casos["cod_eve"] == 810).sum())
    resistente = int((casos["cod_eve"] == 825).sum())

    por_anio = casos.groupby("ano").size()
    anios_ordenados = sorted(por_anio.index)
    anio_actual = anios_ordenados[-1] if anios_ordenados else None
    anio_anterior = anios_ordenados[-2] if len(anios_ordenados) >= 2 else None

    casos_actual = int(por_anio[anio_actual]) if anio_actual else 0
    casos_anterior = int(por_anio[anio_anterior]) if anio_anterior else 0
    variacion = ((casos_actual - casos_anterior) / casos_anterior * 100) if casos_anterior else None

    cols = st.columns(6)
    cols[0].metric("Casos totales", f"{total:,}")
    cols[1].metric("Pulmonar", f"{pulmonar:,}", f"{pulmonar / total * 100:.1f}%" if total else None)
    cols[2].metric("Extrapulmonar", f"{extrapulmonar:,}", f"{extrapulmonar / total * 100:.1f}%" if total else None)
    cols[3].metric("Resistente", f"{resistente:,}", f"{resistente / total * 100:.1f}%" if total else None)
    cols[4].metric(f"Casos {anio_actual}", f"{casos_actual:,}")
    if variacion is not None and anio_anterior:
        cols[5].metric(f"vs {anio_anterior}", f"{variacion:+.1f}%")


def _mostrar_casos_por_anio(casos: pd.DataFrame) -> None:
    por_anio = casos.groupby("ano").size().reset_index(name="casos")
    por_anio["ano"] = por_anio["ano"].astype(int)
    por_anio = por_anio.sort_values("ano")

    fig = px.bar(
        por_anio, x="ano", y="casos",
        title="Casos de tuberculosis por año",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
    )
    fig.update_traces(texttemplate="%{y:,}", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_mapa(casos: pd.DataFrame) -> None:
    geojson = obtener_geojson_municipios_magdalena()

    por_zona = casos.groupby("cod_mun_completo").size().reset_index(name="casos")
    por_zona["cod_mun_str"] = por_zona["cod_mun_completo"].astype(str)

    fig = px.choropleth_mapbox(
        por_zona,
        geojson=geojson,
        locations="cod_mun_str",
        featureidkey="properties.mpio_cdpmp",
        color="casos",
        color_continuous_scale=ESCALA_INCIDENCIA,
        mapbox_style="carto-positron",
        center={"lat": 10.4, "lon": -74.2},
        zoom=7.5,
        title="Distribución geográfica por municipio",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_seccion_semanal(casos: pd.DataFrame) -> None:
    anios_disponibles = sorted(int(a) for a in casos["ano"].dropna().unique())
    if not anios_disponibles:
        return

    anio_seleccionado = st.selectbox(
        "Año de análisis semanal",
        options=anios_disponibles,
        index=len(anios_disponibles) - 1,
        key="tendencia_semanal_anio",
    )

    casos_anio = casos[casos["ano"] == anio_seleccionado]
    casos_anterior = casos[casos["ano"] == (anio_seleccionado - 1)]

    semanal = casos_anio.groupby("semana").size().reindex(range(1, 54), fill_value=0).reset_index(name="casos")
    semanal.columns = ["semana", "casos"]

    col_barras, col_variacion = st.columns(2)

    with col_barras:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=semanal["semana"], y=semanal["casos"],
            name=str(anio_seleccionado),
            marker_color=AZUL_INSTITUCIONAL,
        ))

        if not casos_anterior.empty:
            semanal_ant = casos_anterior.groupby("semana").size().reindex(range(1, 54), fill_value=0).reset_index(name="casos")
            semanal_ant.columns = ["semana", "casos"]
            fig.add_trace(go.Scatter(
                x=semanal_ant["semana"], y=semanal_ant["casos"],
                name=str(anio_seleccionado - 1), mode="lines+markers",
                line=dict(color=NARANJA_INSTITUCIONAL),
            ))

        fig.update_layout(title=f"Casos semanales — {anio_seleccionado} vs {anio_seleccionado - 1}", **_LAYOUT_BASE)
        st.plotly_chart(fig, use_container_width=True)

    with col_variacion:
        if not casos_anterior.empty:
            variacion = []
            for sem in range(1, 54):
                c_act = semanal[semanal["semana"] == sem]["casos"].values
                c_ant = semanal_ant[semanal_ant["semana"] == sem]["casos"].values
                v_act = c_act[0] if len(c_act) > 0 else 0
                v_ant = c_ant[0] if len(c_ant) > 0 else 0
                denom = max(v_ant, 1)
                vp = ((v_act - v_ant) / denom) * 100
                variacion.append({"semana": sem, "variacion": vp})

            df_var = pd.DataFrame(variacion)
            colores = [NARANJA_INSTITUCIONAL if v >= 0 else "#c0392b" for v in df_var["variacion"]]
            fig = px.bar(
                df_var, x="semana", y="variacion",
                title=f"Variación % semanal vs {anio_seleccionado - 1}",
            )
            fig.update_traces(marker_color=colores)
            fig.update_layout(**_LAYOUT_BASE, yaxis_title="%")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"Sin datos para {anio_seleccionado - 1}", icon=":material/info:")


def _mostrar_incidencia_por_territorio(casos: pd.DataFrame) -> None:
    mapeo_subregion = obtener_mapeo_subregion()

    anios_en_alcance = sorted(int(a) for a in casos["ano"].dropna().unique())
    if not anios_en_alcance:
        return

    casos_copia = casos.copy()
    casos_copia["subregion"] = casos_copia["cod_mun_completo"].map(mapeo_subregion)
    casos_copia = casos_copia.dropna(subset=["subregion"])

    tasas = calcular_tasa_por_subregion(casos_copia, anios_en_alcance, mapeo_subregion)

    df_tasas = pd.DataFrame([
        {"subregion": sub, "tasa": tasa}
        for sub, tasa in tasas.items()
        if tasa is not None
    ]).sort_values("tasa", ascending=True)

    if df_tasas.empty:
        st.info("No hay datos de población para calcular tasas de incidencia.", icon=":material/info:")
        return

    fig = px.bar(
        df_tasas, x="tasa", y="subregion", orientation="h",
        title="Tasa de incidencia por subregión (×100.000 hab.)",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text=df_tasas["tasa"].round(1),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title="Tasa × 100.000", yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)
