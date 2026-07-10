"""Pestana 2 Situacion: KPIs, canal endemico, mapa de situacion y tabla de priorizacion.

Incluye los 5 KPIs principales: incidencia, mortalidad, letalidad,
% confirmacion bacteriologica y % TB resistente.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.geografia import obtener_geojson_municipios_magdalena
from pathologies.tuberculosis.canal_endemico import (
    SEMANA_MAX,
    METODOS_DISPONIBLES,
    ZONA_EXITO,
    ZONA_SEGURIDAD,
    ZONA_ALERTA,
    ZONA_EPIDEMIA,
    ZONAS_ORDEN,
    calcular_canal_endemico,
)
from pathologies.tuberculosis.geografia import obtener_mapeo_subregion
from pathologies.tuberculosis.indicators import calcular_indicadores
from pathologies.tuberculosis.views.utils import aplicar_filtro_tipo_tb

CODIGOS_TB = {810, 820, 825}

COLORES_ZONA = {
    ZONA_EXITO: "#28a745",
    ZONA_SEGURIDAD: "#1b3a6b",
    ZONA_ALERTA: NARANJA_INSTITUCIONAL,
    ZONA_EPIDEMIA: "#c0392b",
}

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0))


def mostrar_situacion(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    datos = aplicar_filtro_tipo_tb(datos)
    casos = datos[datos["cod_eve"].isin(CODIGOS_TB)]

    if casos.empty:
        st.info("No hay casos de tuberculosis para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(datos)

    st.space("small")

    col_mapa, col_priorizacion = st.columns([1, 1])
    with col_mapa:
        with st.container(border=True):
            _mostrar_mapa_situacion(casos)
    with col_priorizacion:
        with st.container(border=True):
            _mostrar_tabla_priorizacion(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_canal_endemico(casos)


def _mostrar_kpis(datos: pd.DataFrame) -> None:
    indicadores = calcular_indicadores(datos, st.session_state.get("filtros_globales", {}))

    cols = st.columns(5)
    cols[0].metric(
        "Incidencia TB",
        f"{indicadores['incidencia']:.2f}" if indicadores.get("incidencia") is not None else "N/D",
        help="Casos × 100.000 hab."
    )
    cols[1].metric(
        "Mortalidad TB",
        f"{indicadores['mortalidad']:.2f}" if indicadores.get("mortalidad") is not None else "N/D",
        help="Muertes × 100.000 hab."
    )
    cols[2].metric(
        "Letalidad",
        f"{indicadores['letalidad']:.2f}%" if indicadores.get("letalidad") is not None else "N/D",
    )
    cols[3].metric(
        "% Conf. bacteriológica",
        f"{indicadores['pct_confirmados']:.1f}%" if indicadores.get("pct_confirmados") is not None else "N/D",
    )
    cols[4].metric(
        "% TB resistente",
        f"{indicadores['pct_resistentes']:.2f}%" if indicadores.get("pct_resistentes") is not None else "N/D",
    )


def _mostrar_mapa_situacion(casos: pd.DataFrame) -> None:
    anios_disponibles = sorted(int(a) for a in casos["ano"].dropna().unique())
    if len(anios_disponibles) < 1:
        return

    anio_vigilancia = st.selectbox(
        "Año de vigilancia",
        options=anios_disponibles,
        index=len(anios_disponibles) - 1,
        key="situacion_mapa_anio",
    )

    casos_anio = casos[casos["ano"] == anio_vigilancia]

    por_municipio = casos_anio.groupby("cod_mun_completo").size().reset_index(name="casos")
    por_municipio["cod_mun_str"] = por_municipio["cod_mun_completo"].astype(str)

    geojson = obtener_geojson_municipios_magdalena()

    fig = px.choropleth_mapbox(
        por_municipio,
        geojson=geojson,
        locations="cod_mun_str",
        featureidkey="properties.mpio_cdpmp",
        color="casos",
        color_continuous_scale=["#9ecae1", "#5ba3d0", "#2a6db0", "#1b3a6b"],
        mapbox_style="carto-positron",
        center={"lat": 10.4, "lon": -74.2},
        zoom=7.5,
        title=f"Casos por municipio — {anio_vigilancia}",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_tabla_priorizacion(casos: pd.DataFrame) -> None:
    mapeo_subregion = obtener_mapeo_subregion()
    casos_copia = casos.copy()
    casos_copia["subregion"] = casos_copia["cod_mun_completo"].map(mapeo_subregion)
    casos_copia = casos_copia.dropna(subset=["subregion"])

    ultimas_8_semanas = sorted(casos_copia["semana"].dropna().unique())[-8:] if "semana" in casos_copia.columns else []
    casos_recientes = casos_copia[casos_copia["semana"].isin(ultimas_8_semanas)] if ultimas_8_semanas else casos_copia

    por_subregion = casos_copia.groupby("subregion").agg(
        casos=("cod_eve", "count"),
        muertes=("fec_def", lambda x: x.notna().sum()),
    ).reset_index()

    recientes_por_sub = casos_recientes.groupby("subregion").size().reset_index(name="casos_recientes")
    por_subregion = por_subregion.merge(recientes_por_sub, on="subregion", how="left")
    por_subregion["casos_recientes"] = por_subregion["casos_recientes"].fillna(0).astype(int)

    por_subregion["tendencia"] = "Estable"
    por_subregion = por_subregion.sort_values("casos", ascending=False)

    st.dataframe(
        por_subregion.rename(columns={
            "subregion": "Subregión",
            "casos": "Casos totales",
            "muertes": "Muertes",
            "casos_recientes": "Últimas 8 sem.",
            "tendencia": "Tendencia reciente",
        }),
        use_container_width=True,
        hide_index=True,
    )


def _mostrar_canal_endemico(casos: pd.DataFrame) -> None:
    anios_disponibles = sorted(int(a) for a in casos["ano"].dropna().unique())

    if len(anios_disponibles) < 2:
        st.info("Se necesitan al menos 2 años de datos para el canal endémico.", icon=":material/info:")
        return

    col_sel1, col_sel2, col_sel3 = st.columns(3)
    with col_sel1:
        anio_vigilancia = st.selectbox(
            "Año de vigilancia",
            options=anios_disponibles,
            index=len(anios_disponibles) - 1,
            key="canal_anio_vigilancia",
        )
    with col_sel2:
        anios_disponibles_base = [a for a in anios_disponibles if a < anio_vigilancia]
        anios_base = st.multiselect(
            "Años de línea base",
            options=anios_disponibles_base,
            default=anios_disponibles_base[-5:] if len(anios_disponibles_base) >= 5 else anios_disponibles_base,
            key="canal_anios_base",
        )
    with col_sel3:
        metodo = st.selectbox(
            "Método",
            options=sorted(METODOS_DISPONIBLES),
            format_func=lambda m: "Bortman (paramétrico)" if m == "bortman" else "Cuartiles (INS Colombia)",
            key="canal_metodo",
        )

    if not anios_base:
        st.info("Selecciona al menos un año para la línea base.", icon=":material/info:")
        return

    canal = calcular_canal_endemico(casos, metodo, anio_vigilancia, anios_base)

    semanas = range(1, SEMANA_MAX + 1)
    inferior = canal.get("inferior", [])
    central = canal.get("central", [])
    superior = canal.get("superior", [])
    observado = canal.get("observado", [])
    zonas = canal.get("zonas", [])

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=list(semanas), y=superior,
        fill=None, mode="lines", line=dict(width=0), showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=list(semanas), y=inferior,
        fill="tonexty", mode="lines", line=dict(width=0),
        fillcolor="rgba(27, 58, 107, 0.15)", name="Banda esperada",
    ))
    fig.add_trace(go.Scatter(
        x=list(semanas), y=central,
        mode="lines", line=dict(color=AZUL_INSTITUCIONAL, dash="dash"),
        name="Mediana histórica",
    ))

    colores_observado = [COLORES_ZONA.get(z, "#666") for z in zonas] if len(zonas) == len(observado) else AZUL_INSTITUCIONAL
    fig.add_trace(go.Scatter(
        x=list(semanas), y=observado,
        mode="lines+markers", line=dict(color=NARANJA_INSTITUCIONAL, width=2.5),
        marker=dict(color=colores_observado, size=6),
        name=f"Observado {anio_vigilancia}",
    ))

    fig.update_layout(
        title=f"Canal endémico — {anio_vigilancia} (método {metodo})",
        xaxis_title="Semana epidemiológica",
        yaxis_title="Casos",
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Metodología del canal endémico"):
        st.markdown(f"""
        **Método seleccionado**: {'Bortman (paramétrico, IC 95%)' if metodo == 'bortman' else 'Cuartiles (INS Colombia)'}

        **Leyenda de zonas**:
        - {ZONA_EXITO}: por debajo del límite inferior
        - {ZONA_SEGURIDAD}: entre límite inferior y umbral central
        - {ZONA_ALERTA}: entre umbral central y límite superior
        - {ZONA_EPIDEMIA}: por encima del límite superior

        **Años de línea base**: {', '.join(str(a) for a in sorted(anios_base))}
        """)
