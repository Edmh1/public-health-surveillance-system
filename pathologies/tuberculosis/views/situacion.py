"""Pestana 2 Situacion: KPIs, canal endemico, mapa de situacion y tabla de priorizacion.

Incluye 4 KPIs: incidencia, mortalidad, letalidad y % TB resistente.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.geografia import obtener_geojson_municipios_magdalena
from pathologies.tuberculosis.canal_endemico import (
    METODOS_DISPONIBLES,
    ZONA_EXITO,
    ZONA_SEGURIDAD,
    ZONA_ALERTA,
    ZONA_EPIDEMIA,
    calcular_canal_endemico,
)
from pathologies.tuberculosis.indicators import calcular_indicadores

COD_PULMONAR = 820
COD_EXTRAPULMONAR = 810
COD_RESISTENTE = 825


def _casos_total(datos: pd.DataFrame) -> pd.DataFrame:
    codigos = set(datos["cod_eve"].unique())
    if codigos == {COD_RESISTENTE}:
        return datos
    return datos[datos["cod_eve"].isin({COD_PULMONAR, COD_EXTRAPULMONAR})]

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

    casos = _casos_total(datos)

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

    cols = st.columns(4)
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
    ultimas_8_semanas = sorted(casos["semana"].dropna().unique())[-8:] if "semana" in casos.columns else []
    casos_recientes = casos[casos["semana"].isin(ultimas_8_semanas)] if ultimas_8_semanas else casos

    por_municipio = casos.groupby("cod_mun_completo").agg(
        casos=("cod_eve", "count"),
        muertes=("fec_def", lambda x: x.notna().sum()),
    ).reset_index()

    recientes_por_mun = casos_recientes.groupby("cod_mun_completo").size().reset_index(name="casos_recientes")
    por_municipio = por_municipio.merge(recientes_por_mun, on="cod_mun_completo", how="left")
    por_municipio["casos_recientes"] = por_municipio["casos_recientes"].fillna(0).astype(int)

    if "nom_mun_o" in casos.columns:
        nombres = casos[["cod_mun_completo", "nom_mun_o"]].drop_duplicates("cod_mun_completo")
        por_municipio = por_municipio.merge(nombres, on="cod_mun_completo", how="left")

    por_municipio = por_municipio.sort_values("casos", ascending=False)

    columnas_mostrar = {
        "cod_mun_completo": "Cód. municipio",
        "casos": "Casos totales",
        "muertes": "Muertes",
        "casos_recientes": "Últimas 8 sem.",
    }
    if "nom_mun_o" in por_municipio.columns:
        columnas_mostrar["nom_mun_o"] = "Municipio"
        columnas_mostrar.pop("cod_mun_completo")

    st.dataframe(
        por_municipio[list(columnas_mostrar.keys())].rename(columns=columnas_mostrar),
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

    try:
        resultado = calcular_canal_endemico(casos, metodo, anio_vigilancia, anios_base)
    except Exception as e:
        st.warning(f"No se pudo calcular el canal endémico: {e}", icon=":material/error:")
        return

    bandas = resultado["bandas"]
    serie_actual = resultado["serie_actual"]
    semanas = bandas["semana"].tolist()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=semanas + semanas[::-1],
        y=bandas["superior"].tolist() + bandas["central"].tolist()[::-1],
        fill="toself",
        fillcolor="rgba(232, 133, 44, 0.20)",
        line=dict(color="rgba(0,0,0,0)"),
        name=ZONA_ALERTA,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=semanas + semanas[::-1],
        y=bandas["central"].tolist() + bandas["inferior"].tolist()[::-1],
        fill="toself",
        fillcolor="rgba(27, 58, 107, 0.38)",
        line=dict(color="rgba(0,0,0,0)"),
        name=ZONA_SEGURIDAD,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=semanas + semanas[::-1],
        y=bandas["inferior"].tolist() + [0] * len(semanas),
        fill="toself",
        fillcolor="rgba(40, 167, 69, 0.10)",
        line=dict(color="rgba(0,0,0,0)"),
        name=ZONA_EXITO,
        hoverinfo="skip",
    ))

    fig.add_trace(go.Scatter(
        x=semanas, y=bandas["inferior"],
        mode="lines", line=dict(color=COLORES_ZONA[ZONA_EXITO], width=1.5, dash="dot"),
        name="Límite inferior",
    ))
    fig.add_trace(go.Scatter(
        x=semanas, y=bandas["central"],
        mode="lines", line=dict(color=COLORES_ZONA[ZONA_SEGURIDAD], width=2),
        name="Mediana histórica",
    ))
    fig.add_trace(go.Scatter(
        x=semanas, y=bandas["superior"],
        mode="lines", line=dict(color=COLORES_ZONA[ZONA_EPIDEMIA], width=1.5, dash="dash"),
        name="Límite superior",
    ))

    if not serie_actual.empty:
        colores_puntos = [COLORES_ZONA.get(z, "#666") for z in serie_actual["zona"]]
        fig.add_trace(go.Scatter(
            x=serie_actual["semana"], y=serie_actual["casos"],
            mode="markers",
            marker=dict(color=colores_puntos, size=7, line=dict(width=1, color="#fff")),
            name=f"Año {anio_vigilancia}",
        ))

    fig.update_layout(
        title=f"Canal endémico — {anio_vigilancia} ({metodo})",
        xaxis=dict(title="Semana epidemiológica", tickmode="linear", tick0=1, dtick=4),
        yaxis=dict(title="Casos"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Metodología del canal endémico"):
        st.markdown(f"""
        **Método**: {'Bortman (paramétrico, IC 95%)' if metodo == 'bortman' else 'Cuartiles (INS Colombia)'}

        **Leyenda de zonas**:
        - {ZONA_EXITO}: por debajo del límite inferior
        - {ZONA_SEGURIDAD}: entre límite inferior y umbral central
        - {ZONA_ALERTA}: entre umbral central y límite superior
        - {ZONA_EPIDEMIA}: por encima del límite superior

        **Años de línea base**: {', '.join(str(a) for a in sorted(anios_base))}
        """)
