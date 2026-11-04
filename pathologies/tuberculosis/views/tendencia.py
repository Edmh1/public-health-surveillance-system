"""Pestana 1 Tendencia: evolucion temporal de casos de TB.

Casos = cod_eve en {810, 820, 825}. El analisis semanal usa un selector de anio
propio que ignora el filtro temporal global.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    LEYENDA_SUPERIOR,
    NARANJA_INSTITUCIONAL,
)
from core.dashboard_base.filtros import CLAVE_FILTRO_EVENTO, seleccionar_municipio
from core.geografia import obtener_geojson_municipios_magdalena, obtener_geojson_subregiones
from pathologies.tuberculosis.etiquetas import ETIQUETAS_POR_CODIGO, etiqueta_tipos_tb
from pathologies.tuberculosis.geografia import obtener_mapeo_subregion
from pathologies.tuberculosis.mapas import (
    COLORES_SEMAFORO,
    ORDEN_SEMAFORO,
    boton_volver_municipio,
    clave_mapa,
    datos_mapa_casos,
    municipio_desde_seleccion,
    resumen_semaforo,
)
from pathologies.tuberculosis.poblacion import calcular_tasa_por_subregion
from pathologies.tuberculosis.views.ejes import mostrar_grafica_tb
from pathologies.tuberculosis.views.titulos import TAMANO_TITULO

COD_PULMONAR = 820
COD_EXTRAPULMONAR = 810
COD_RESISTENTE = 825


def _casos_total(datos: pd.DataFrame) -> pd.DataFrame:
    if st.session_state.get(CLAVE_FILTRO_EVENTO):
        return datos
    codigos = set(datos["cod_eve"].unique())
    if codigos == {COD_RESISTENTE}:
        return datos
    return datos[datos["cod_eve"].isin({COD_PULMONAR, COD_EXTRAPULMONAR})]

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0), title_font_size=TAMANO_TITULO)


def mostrar_tendencia(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    casos = _casos_total(datos)

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

    por_anio = casos.groupby("ano").size()
    anios_ordenados = sorted(por_anio.index)
    anio_actual = anios_ordenados[-1] if anios_ordenados else None
    casos_actual = int(por_anio[anio_actual]) if anio_actual else 0

    cols = st.columns(4)
    cols[0].metric("Casos totales", f"{total:,}")
    cols[1].metric("Pulmonar", f"{pulmonar:,}")
    cols[2].metric("Extrapulmonar", f"{extrapulmonar:,}")
    cols[3].metric(f"Casos {anio_actual}", f"{casos_actual:,}")


def _mostrar_casos_por_anio(casos: pd.DataFrame) -> None:
    por_anio_tipo = (
        casos.assign(tipo=casos["cod_eve"].map(ETIQUETAS_POR_CODIGO))
        .dropna(subset=["tipo"])
        .groupby(["ano", "tipo"])
        .size()
        .reset_index(name="casos")
    )
    por_anio_tipo["ano"] = por_anio_tipo["ano"].astype(int)
    por_anio_tipo = por_anio_tipo.sort_values(["ano", "tipo"])

    orden_tipos = ["Pulmonar", "Extrapulmonar", "Farmacorresistente"]
    colores_tipo = {
        "Pulmonar": AZUL_INSTITUCIONAL,
        "Extrapulmonar": NARANJA_INSTITUCIONAL,
        "Farmacorresistente": "#7c3aed",
    }

    fig = px.bar(
        por_anio_tipo,
        x="ano",
        y="casos",
        color="tipo",
        barmode="stack",
        category_orders={"tipo": orden_tipos},
        color_discrete_map=colores_tipo,
        labels={"ano": "Año", "casos": "Casos", "tipo": "Tipo"},
        title=f"Casos de {etiqueta_tipos_tb(casos)} por año",
    )
    fig.update_traces(texttemplate="%{y:,}", textposition="inside")
    fig.update_layout(
        **_LAYOUT_BASE,
        xaxis_title=None,
        yaxis_title="Casos",
        legend=LEYENDA_SUPERIOR,
    )
    mostrar_grafica_tb(fig, use_container_width=True)


def _mostrar_mapa(casos: pd.DataFrame) -> None:
    clave_base = "tb_mapa_tendencia"
    boton_volver_municipio(clave_base)
    seleccion_unica = len(st.session_state.get("filtro_municipio", [])) == 1

    geojson = obtener_geojson_municipios_magdalena()
    mapa = datos_mapa_casos(casos)

    fig = px.choropleth(
        mapa,
        geojson=geojson,
        locations="cod_mun_str",
        featureidkey="properties.mpio_cdpmp",
        color="semaforo",
        color_discrete_map=COLORES_SEMAFORO,
        category_orders={"semaforo": ORDEN_SEMAFORO},
        hover_name="municipio",
        hover_data={
            "cod_mun_str": False,
            "municipio": False,
            "municipio_normalizado": False,
            "subregion": False,
            "casos": True,
            "incidencia": ":.1f",
            "poblacion": ":,",
            "semaforo": False,
        },
        labels={
            "casos": "Casos",
            "incidencia": "Incidencia por 100.000 hab.",
            "poblacion": "Población",
        },
        title=f"Incidencia de {etiqueta_tipos_tb(casos)} por municipio de ocurrencia",
    )
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=1)
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        title_font_size=TAMANO_TITULO,
        showlegend=not seleccion_unica,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    resultado = mostrar_grafica_tb(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key=clave_mapa(clave_base),
    )
    nombre_municipio = municipio_desde_seleccion(resultado, mapa)
    if nombre_municipio and st.session_state.get("filtro_municipio") != [nombre_municipio]:
        if seleccionar_municipio(nombre_municipio):
            st.rerun()

    if seleccion_unica:
        fila = mapa.iloc[0]
        incidencia = fila["incidencia"]
        incidencia_txt = f"{incidencia:.1f}" if pd.notna(incidencia) else "sin dato"
        st.caption(
            f"{fila['municipio']} · Casos: {int(fila['casos']):,} · "
            f"Incidencia: {incidencia_txt} por 100.000 habitantes. "
            "Usa Volver para quitar el filtro."
        )
    else:
        st.caption(
            f"{resumen_semaforo(mapa, 'incidencia', 'casos por 100.000 habitantes')} "
            "Haz clic en un municipio para filtrar el dashboard."
        )


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

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=semanal["semana"], y=semanal["casos"],
        name=str(anio_seleccionado),
        marker_color=NARANJA_INSTITUCIONAL,
    ))

    if not casos_anterior.empty:
        semanal_ant = casos_anterior.groupby("semana").size().reindex(range(1, 54), fill_value=0).reset_index(name="casos")
        semanal_ant.columns = ["semana", "casos"]
        fig.add_trace(go.Scatter(
            x=semanal_ant["semana"], y=semanal_ant["casos"],
            name=str(anio_seleccionado - 1), mode="lines+markers",
            line=dict(color=AZUL_INSTITUCIONAL),
        ))

    fig.update_layout(
        title=f"Casos semanales de {etiqueta_tipos_tb(casos)} — {anio_seleccionado} vs {anio_seleccionado - 1}",
        **_LAYOUT_BASE,
    )
    mostrar_grafica_tb(fig, use_container_width=True)

    st.space("small")

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
            title=(
                f"Variación porcentual semanal de casos de {etiqueta_tipos_tb(casos)} — "
                f"{anio_seleccionado} vs {anio_seleccionado - 1}"
            ),
        )
        fig.update_traces(marker_color=colores)
        fig.update_layout(**_LAYOUT_BASE, yaxis_title="%")
        mostrar_grafica_tb(fig, use_container_width=True)
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
        title=f"Tasa de incidencia de {etiqueta_tipos_tb(casos)} por subregión (casos por 100.000 habitantes)",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text=df_tasas["tasa"].round(1),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title="Tasa × 100.000", yaxis_title=None)
    mostrar_grafica_tb(fig, use_container_width=True)
