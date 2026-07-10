"""Pestana 4 Diagnostico: calidad y oportunidad de la notificacion.

KPIs: % confirmados, oportunidad diagnostica (dias inicio sintomas -> notificacion).
Graficas: metodo de confirmacion, clasificacion del caso, pulmonar vs extrapulmonar,
distribucion de tiempos de diagnostico.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL

COD_PULMONAR = 820
COD_EXTRAPULMONAR = 810
COD_RESISTENTE = 825


def _casos_total(datos: pd.DataFrame) -> pd.DataFrame:
    codigos = set(datos["cod_eve"].unique())
    if codigos == {COD_RESISTENTE}:
        return datos
    return datos[datos["cod_eve"].isin({COD_PULMONAR, COD_EXTRAPULMONAR})]

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0))

ETIQUETAS_CASO = {
    0: "No aplica", 3: "Conf. laboratorio", 4: "Conf. clínica",
    5: "Conf. nexo epidemiológico", 6: "Descartado", 7: "Otra actualización",
}


def mostrar_diagnostico(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    casos = _casos_total(datos)

    if casos.empty:
        st.info("No hay casos de tuberculosis para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(casos)

    st.space("small")

    col_conf, col_clasif = st.columns(2)
    with col_conf:
        with st.container(border=True):
            _mostrar_confirmacion(casos)
    with col_clasif:
        with st.container(border=True):
            _mostrar_clasificacion(casos)

    st.space("small")

    col_tipo, col_oportunidad = st.columns(2)
    with col_tipo:
        with st.container(border=True):
            _mostrar_tipo_tb(casos)
    with col_oportunidad:
        with st.container(border=True):
            _mostrar_oportunidad(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_ajustes(casos)


def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)

    oportunidad_mediana = None
    if "ini_sin" in casos.columns and "fec_not" in casos.columns:
        con_fechas = casos[casos["ini_sin"].notna() & casos["fec_not"].notna()]
        if not con_fechas.empty:
            dias = (con_fechas["fec_not"] - con_fechas["ini_sin"]).dt.days
            oportunidad_mediana = int(dias.median())

    cols = st.columns(2)
    cols[0].metric("Casos totales", f"{total:,}")
    cols[1].metric(
        "Mediana días inicio → notificación",
        f"{oportunidad_mediana}" if oportunidad_mediana is not None else "N/D",
    )


def _mostrar_confirmacion(casos: pd.DataFrame) -> None:
    if "estado_final_de_caso" not in casos.columns:
        st.info("Datos de confirmación no disponibles.", icon=":material/info:")
        return

    copia = casos.copy()
    copia["clasif"] = copia["estado_final_de_caso"].map(ETIQUETAS_CASO).fillna("Sin dato")

    por_tipo = copia.groupby("clasif").size().reset_index(name="casos")

    fig = px.pie(
        por_tipo, values="casos", names="clasif",
        title="Confirmación del caso",
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(**_LAYOUT_BASE)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_clasificacion(casos: pd.DataFrame) -> None:
    copia = casos.copy()

    copia["tipo_tb"] = "Pulmonar"
    copia.loc[copia["cod_eve"] == 810, "tipo_tb"] = "Extrapulmonar"

    por_anio = copia.groupby(["ano", "tipo_tb"]).size().reset_index(name="casos")
    por_anio["ano"] = por_anio["ano"].astype(int)

    fig = px.bar(
        por_anio, x="ano", y="casos", color="tipo_tb",
        title="Clasificación por tipo de TB (anual)",
        color_discrete_sequence=[AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL],
    )
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_tipo_tb(casos: pd.DataFrame) -> None:
    copia = casos.copy()
    copia["tipo"] = "Pulmonar"
    copia.loc[copia["cod_eve"] == 810, "tipo"] = "Extrapulmonar"

    por_tipo = copia.groupby("tipo").size().reset_index(name="casos")
    total = por_tipo["casos"].sum()
    por_tipo["pct"] = (por_tipo["casos"] / total * 100).round(1)

    colores_map = {"Pulmonar": AZUL_INSTITUCIONAL, "Extrapulmonar": NARANJA_INSTITUCIONAL}

    fig = px.pie(
        por_tipo, values="casos", names="tipo",
        title="TB pulmonar vs extrapulmonar",
        color="tipo", color_discrete_map=colores_map,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(**_LAYOUT_BASE)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_oportunidad(casos: pd.DataFrame) -> None:
    if "ini_sin" not in casos.columns or "fec_not" not in casos.columns:
        st.info("Datos de fechas insuficientes para análisis de oportunidad.", icon=":material/info:")
        return

    con_fechas = casos[casos["ini_sin"].notna() & casos["fec_not"].notna()].copy()
    if con_fechas.empty:
        st.info("Sin fechas completas para calcular oportunidad.", icon=":material/info:")
        return

    con_fechas["dias_diagnostico"] = (con_fechas["fec_not"] - con_fechas["ini_sin"]).dt.days
    con_fechas["dias_diagnostico"] = con_fechas["dias_diagnostico"].clip(lower=0, upper=365)

    mapeo_subregion = st.session_state.get("_mapeo_subregion_tb")
    if mapeo_subregion:
        con_fechas["subregion"] = con_fechas["cod_mun_completo"].map(mapeo_subregion)

    fig = px.box(
        con_fechas, y="dias_diagnostico",
        title="Días desde inicio de síntomas hasta notificación",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
    )
    fig.update_layout(**_LAYOUT_BASE, yaxis_title="Días")
    st.plotly_chart(fig, use_container_width=True)

    st.caption(f"Mediana: {int(con_fechas['dias_diagnostico'].median())} días  |  "
               f"P75: {int(con_fechas['dias_diagnostico'].quantile(0.75))} días  |  "
               f"P90: {int(con_fechas['dias_diagnostico'].quantile(0.90))} días  |  "
               f"Casos con fechas: {len(con_fechas):,}")


def _mostrar_ajustes(casos: pd.DataFrame) -> None:
    if "ajuste" not in casos.columns:
        return

    copia = casos.copy()
    copia["ajustado"] = copia["ajuste"].notna().map({True: "Con ajuste", False: "Sin ajuste"})

    por_ajuste = copia.groupby("ajustado").size().reset_index(name="casos")

    fig = px.bar(
        por_ajuste, x="ajustado", y="casos",
        title="Casos con ajuste en clasificación",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text="casos",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)
