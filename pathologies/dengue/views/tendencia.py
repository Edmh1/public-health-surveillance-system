"""Pestana 1 Tendencia: seis graficas del PDF (1.1 a 1.6).

Casos = cod_eve en {210, 220}. La mortalidad (580) va en Mortalidad.
El analisis semanal (1.2, 1.3, 1.4) usa un selector de anio propio que
ignora el filtro temporal global; responde al filtro geografico y de
clasificacion (ver PDF, 'Filtros que no aplican').
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.geografia import obtener_geojson_municipios_magdalena

CODIGOS_CASOS = {210, 220}

_NIVEL_OPCIONES = ["Subregion", "Municipio"]
_NIVEL_ETIQUETAS = {
    "Subregion": ":material/map: Subregion",
    "Municipio": ":material/location_city: Municipio",
}

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=40, b=0))


def mostrar_tendencia(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    # --- KPIs ---
    _mostrar_kpis(casos)

    st.space("small")

    # --- Fila principal: serie anual + mapa ---
    col_serie, col_mapa = st.columns([1, 1.2])
    with col_serie:
        with st.container(border=True, height="stretch"):
            _mostrar_casos_por_anio(casos)
    with col_mapa:
        with st.container(border=True, height="stretch"):
            _mostrar_mapa(casos)

    st.space("small")

    # --- Analisis semanal (selector local de anio: 1.2, 1.3, 1.4) ---
    with st.container(border=True):
        _mostrar_seccion_semanal(casos)

    st.space("small")

    # --- Evolucion temporal por subregion o municipio (1.6) ---
    with st.container(border=True):
        _mostrar_evolucion_temporal(casos)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)

    # Variacion vs anio anterior
    por_anio = casos.groupby("ano").size().sort_index()
    if len(por_anio) >= 2:
        anio_actual   = int(por_anio.index[-1])
        anio_anterior = int(por_anio.index[-2])
        n_actual   = int(por_anio.iloc[-1])
        n_anterior = int(por_anio.iloc[-2])
        pct = (n_actual - n_anterior) / n_anterior * 100 if n_anterior else 0
        # "Casos 2024" deja claro de que año es el número y el delta explica la variacion
        label_anio = f"Casos {anio_actual}"
        valor_anio = f"{n_actual:,}"
        delta_anio = f"{pct:+.1f}% vs {anio_anterior}"
    elif len(por_anio) == 1:
        label_anio = f"Casos {int(por_anio.index[-1])}"
        valor_anio = f"{int(por_anio.iloc[-1]):,}"
        delta_anio = None
    else:
        label_anio, valor_anio, delta_anio = "Casos (año)", "—", None

    # Semana pico
    if "semana" in casos.columns and not casos["semana"].dropna().empty:
        sem = casos.groupby("semana").size()
        semana_pico  = int(sem.idxmax())
        casos_pico   = int(sem.max())
        semana_label = f"Sem. {semana_pico}"
        semana_help  = f"{casos_pico:,} casos en esa semana"
    else:
        semana_label, semana_help = "—", None

    # Municipio con mayor carga (mas util que subregion cuando se filtra por subregion)
    if "nom_mun_o" in casos.columns:
        mun = casos["nom_mun_o"].dropna().value_counts()
        if not mun.empty:
            top_mun  = str(mun.index[0])
            top_help = f"{int(mun.iloc[0]):,} casos notificados"
        else:
            top_mun, top_help = "—", None
    else:
        top_mun, top_help = "—", None

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Casos totales", f"{total:,}")
    with c2:
        st.metric(label_anio, valor_anio, delta=delta_anio)
    with c3:
        st.metric("Semana pico", semana_label, help=semana_help)
    with c4:
        st.metric("Municipio mas afectado", top_mun, help=top_help)


# ---------------------------------------------------------------------------
# 1.1  Casos por año
# ---------------------------------------------------------------------------

def _mostrar_casos_por_anio(casos: pd.DataFrame) -> None:
    st.subheader(":material/bar_chart: Casos por año")

    por_anio = casos.groupby("ano").size().reset_index(name="casos")

    fig = px.bar(por_anio, x="ano", y="casos", text="casos",
                 labels={"ano": "Año", "casos": "Casos"})
    fig.update_xaxes(type="category")
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE)
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 1.5  Mapa del Magdalena
# ---------------------------------------------------------------------------

def _mostrar_mapa(casos: pd.DataFrame) -> None:
    """Click-to-drill: vista general de subregiones → clic → zoom a municipios."""
    st.subheader(":material/map: Mapa del Magdalena")

    subregion_activa = st.session_state.get("mapa_subregion_seleccionada")

    con_geo = casos[casos["mun_valido"]].dropna(subset=["cod_mun_completo", "subregion"])
    if con_geo.empty:
        st.info("Sin casos con geografia valida.", icon=":material/info:")
        return

    con_geo = con_geo.copy()
    con_geo["cod_mun_completo"] = con_geo["cod_mun_completo"].astype(int)

    tiene_nom_mun = "nom_mun_o" in con_geo.columns
    cols_grupo = ["cod_mun_completo", "subregion"] + (["nom_mun_o"] if tiene_nom_mun else [])
    conteo = con_geo.groupby(cols_grupo).size().reset_index(name="casos_mun")
    conteo["cod_str"] = conteo["cod_mun_completo"].apply(lambda x: f"{x:05d}")

    geojson = obtener_geojson_municipios_magdalena()

    if subregion_activa:
        # DRILL-DOWN: solo los municipios de la subregion clicada
        col_volver, col_titulo = st.columns([1, 4], vertical_alignment="center")
        with col_volver:
            if st.button("Volver", icon=":material/arrow_back:", key="mapa_volver", width="stretch"):
                st.session_state["mapa_subregion_seleccionada"] = None
                st.rerun()
        with col_titulo:
            st.caption(f":material/location_on: Subregion {subregion_activa} — municipios por casos")

        datos_mapa = conteo[conteo["subregion"] == subregion_activa].copy()
        datos_mapa["casos"] = datos_mapa["casos_mun"]
        hover = {"cod_str": False, "subregion": False, "casos": True}
        if tiene_nom_mun:
            hover["nom_mun_o"] = True
        chart_key = "mapa_drill"

    else:
        # VISTA GENERAL: subregiones (cada municipio hereda el total de su subregion)
        st.caption(":material/touch_app: Haz clic en cualquier zona para ver el detalle por municipio.")
        datos_mapa = conteo.copy()
        datos_mapa["casos"] = datos_mapa.groupby("subregion")["casos_mun"].transform("sum")
        hover = {"cod_str": False, "subregion": True, "casos": True}
        chart_key = "mapa_overview"

    fig = px.choropleth(
        datos_mapa,
        geojson=geojson,
        locations="cod_str",
        featureidkey="properties.mpio_cdpmp",
        color="casos",
        labels={"casos": "Casos"},
        hover_data=hover,
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=360)

    resultado = st.plotly_chart(
        fig,
        width="stretch",
        on_select="rerun",
        selection_mode="points",
        key=chart_key,
    )

    # Manejo del click de drill-down (solo desde la vista general)
    if not subregion_activa:
        try:
            puntos = resultado.selection.points
        except AttributeError:
            puntos = []
        if puntos:
            cod_clickeado = puntos[0].get("location")
            if cod_clickeado:
                fila = conteo[conteo["cod_str"] == cod_clickeado]
                if not fila.empty:
                    st.session_state["mapa_subregion_seleccionada"] = str(fila.iloc[0]["subregion"])
                    st.rerun()

    st.caption("Conteo de casos. La incidencia por poblacion en riesgo se incorpora junto a los KPIs.")


# ---------------------------------------------------------------------------
# 1.2 / 1.3 / 1.4  Analisis semanal (selector de anio local)
# ---------------------------------------------------------------------------

def _mostrar_seccion_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/show_chart: Analisis semanal")

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        st.caption("Sin datos.")
        return

    col_sel, col_nota = st.columns([1, 3], vertical_alignment="center")
    with col_sel:
        anio = st.selectbox(
            "Año de analisis",
            options=anios,
            key="tendencia_anio_semanal",
        )
    with col_nota:
        st.caption(
            ":material/info: El año de analisis es un selector propio de esta seccion "
            "e ignora el filtro temporal global."
        )

    col_12, col_13 = st.columns(2)
    with col_12:
        _grafica_semanal_anio(casos, anio)          # 1.2
    with col_13:
        _grafica_comparacion_vs_anterior(casos, anio)  # 1.3

    _grafica_variacion_porcentual(casos, anio)       # 1.4


def _grafica_semanal_anio(casos: pd.DataFrame, anio: int) -> None:
    """1.2  Casos semanales del año con linea de promedio."""
    subset = casos[casos["ano"] == anio]
    if subset.empty or "semana" not in subset.columns:
        st.caption(f"Sin datos semanales para {anio}.")
        return

    semanal = subset.groupby("semana").size().reset_index(name="casos")
    promedio = float(semanal["casos"].mean())

    fig = px.bar(
        semanal, x="semana", y="casos",
        labels={"semana": "Semana epidemiologica", "casos": "Casos"},
        title=f"Casos semanales {anio}",
    )
    fig.add_hline(
        y=promedio,
        line_dash="dot",
        line_color=NARANJA_INSTITUCIONAL,
        annotation_text=f"Prom. {promedio:.0f}",
        annotation_position="top right",
    )
    fig.update_layout(**_LAYOUT_BASE, showlegend=False)
    st.plotly_chart(fig, width="stretch")


def _grafica_comparacion_vs_anterior(casos: pd.DataFrame, anio: int) -> None:
    """1.3  Barras (año anterior) + linea (año seleccionado)."""
    anio_prev = anio - 1

    def _semanal(df: pd.DataFrame, year: int) -> pd.DataFrame:
        s = df[df["ano"] == year]
        if s.empty:
            return pd.DataFrame(columns=["semana", "casos"])
        return s.groupby("semana").size().reset_index(name="casos")

    df_prev = _semanal(casos, anio_prev)
    df_act  = _semanal(casos, anio)

    if df_prev.empty and df_act.empty:
        st.caption("Sin datos suficientes para comparar.")
        return

    fig = go.Figure()

    if not df_prev.empty:
        fig.add_trace(go.Bar(
            x=df_prev["semana"], y=df_prev["casos"],
            name=str(anio_prev),
            marker_color=NARANJA_INSTITUCIONAL,
            opacity=0.65,
        ))

    if not df_act.empty:
        fig.add_trace(go.Scatter(
            x=df_act["semana"], y=df_act["casos"],
            mode="lines+markers",
            name=str(anio),
            line=dict(color=AZUL_INSTITUCIONAL, width=2),
            marker=dict(size=4),
        ))

    fig.update_layout(
        title=f"Comparacion {anio} vs {anio_prev}",
        xaxis_title="Semana epidemiologica",
        yaxis_title="Casos",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, width="stretch")


def _grafica_variacion_porcentual(casos: pd.DataFrame, anio: int) -> None:
    """1.4  Variacion porcentual semanal frente al año anterior."""
    anio_prev = anio - 1

    def _por_semana(df: pd.DataFrame, year: int) -> pd.Series:
        s = df[df["ano"] == year]
        return s.groupby("semana").size() if not s.empty else pd.Series(dtype=float)

    s_act  = _por_semana(casos, anio)
    s_prev = _por_semana(casos, anio_prev)

    semanas_comunes = s_act.index.intersection(s_prev.index)
    if semanas_comunes.empty or (s_prev[semanas_comunes] == 0).all():
        return

    variacion = pd.DataFrame({
        "semana": semanas_comunes,
        "variacion": (
            (s_act[semanas_comunes] - s_prev[semanas_comunes])
            / s_prev[semanas_comunes]
            * 100
        ).values,
    }).dropna()

    if variacion.empty:
        return

    colores = [
        AZUL_INSTITUCIONAL if v >= 0 else NARANJA_INSTITUCIONAL
        for v in variacion["variacion"]
    ]

    fig = px.bar(
        variacion, x="semana", y="variacion",
        labels={"semana": "Semana epidemiologica", "variacion": "Variacion (%)"},
        title=f"Variacion porcentual semanal: {anio} vs {anio_prev}",
    )
    fig.update_traces(marker_color=colores)
    fig.add_hline(y=0, line_color="#9ca3af", line_width=1)
    fig.update_layout(**_LAYOUT_BASE, showlegend=False)
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 1.6  Evolucion temporal por subregion o municipio
# ---------------------------------------------------------------------------

def _mostrar_evolucion_temporal(casos: pd.DataFrame) -> None:
    st.subheader(":material/timeline: Evolucion temporal")

    nivel = st.segmented_control(
        "Agrupar por",
        _NIVEL_OPCIONES,
        default="Subregion",
        required=True,
        format_func=lambda o: _NIVEL_ETIQUETAS[o],
        key="tendencia_evolucion_nivel",
    )
    col_nivel = "subregion" if nivel == "Subregion" else "nom_mun_o"

    subset = casos.dropna(subset=[col_nivel])
    if subset.empty:
        st.info("Sin casos con geografia valida.", icon=":material/info:")
        return

    evolucion = subset.groupby(["ano", col_nivel]).size().reset_index(name="casos")
    evolucion["ano"] = evolucion["ano"].astype(str)

    fig = px.line(
        evolucion, x="ano", y="casos", color=col_nivel, markers=True,
        labels={"ano": "Año", "casos": "Casos", col_nivel: nivel},
    )
    fig.update_layout(
        **_LAYOUT_BASE,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, width="stretch")
