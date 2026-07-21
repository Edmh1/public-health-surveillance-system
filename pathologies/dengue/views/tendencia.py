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

from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    LEYENDA_SUPERIOR,
    NARANJA_INSTITUCIONAL,
    eje_semanal,
    rango_con_margen,
)
from core.geografia import obtener_geojson_municipios_magdalena, obtener_geojson_subregiones
from pathologies.dengue.geografia import obtener_mapeo_subregion
from pathologies.dengue.poblacion import (
    calcular_tasa_por_municipio,
    calcular_tasa_por_subregion,
    calcular_tasa_por_zona_municipio,
    obtener_poblacion_por_municipio_anio,
    obtener_poblacion_por_subregion_anio,
)

CODIGOS_CASOS = {210, 220}

# Escala azul para los mapas de coropletas. NO arranca en blanco: la escala
# "Blues" de Plotly llega casi a blanco en su extremo bajo, y la subregion de
# menor valor se perdia contra el fondo blanco de la pagina. El piso es un azul
# claro pero visible; el techo, el azul institucional oscuro.
ESCALA_INCIDENCIA = ["#9ecae1", "#5ba3d0", "#2a6db0", "#1b3a6b"]

_NIVEL_OPCIONES = ["Subregión", "Municipio"]
_NIVEL_ETIQUETAS = {
    "Subregión": ":material/map: Subregión",
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

    # --- Fila principal: serie anual + mapa (40/60, prioridad al mapa) ---
    col_serie, col_mapa = st.columns([2, 3])
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

    por_anio = casos.groupby("ano").size().sort_index()
    anios_ordenados = [int(a) for a in por_anio.index]
    anio_actual = anios_ordenados[-1] if anios_ordenados else None

    # Variacion vs anio anterior
    if len(por_anio) >= 2:
        anio_anterior = anios_ordenados[-2]
        n_actual   = int(por_anio.iloc[-1])
        n_anterior = int(por_anio.iloc[-2])
        pct = (n_actual - n_anterior) / n_anterior * 100 if n_anterior else 0
        # "Casos 2024" deja claro de que año es el número y el delta explica la variacion
        label_anio = f"Casos {anio_actual}"
        valor_anio = f"{n_actual:,}"
        delta_anio = f"{pct:+.1f}% vs {anio_anterior}"
    elif len(por_anio) == 1:
        label_anio = f"Casos {anio_actual}"
        valor_anio = f"{int(por_anio.iloc[-1]):,}"
        delta_anio = None
    else:
        label_anio, valor_anio, delta_anio = "Casos (año)", "—", None

    # Semana pico y municipio mas afectado se calculan SOBRE EL ANIO MAS RECIENTE
    # (no sobre todos los anios combinados, que daria una semana/municipio "pico"
    # sumando anios distintos, poco interpretable). El periodo queda explicito en
    # el label y en la leyenda de arriba de las tarjetas.
    casos_anio = casos[casos["ano"] == anio_actual] if anio_actual is not None else casos

    if "semana" in casos_anio.columns and not casos_anio["semana"].dropna().empty:
        sem = casos_anio.groupby("semana").size()
        semana_pico  = int(sem.idxmax())
        casos_pico   = int(sem.max())
        semana_label = f"Sem. {semana_pico}"
        semana_help  = f"{casos_pico:,} casos en la semana {semana_pico} de {anio_actual}"
    else:
        semana_label, semana_help = "—", None

    if "nom_mun_o" in casos_anio.columns:
        mun = casos_anio["nom_mun_o"].dropna().value_counts()
        if not mun.empty:
            top_mun  = str(mun.index[0])
            top_help = f"{int(mun.iloc[0]):,} casos en {anio_actual}"
        else:
            top_mun, top_help = "—", None
    else:
        top_mun, top_help = "—", None

    if anio_actual is not None:
        st.caption(
            f":material/calendar_today: **Casos totales** cubren todo el período filtrado; "
            f"**semana pico** y **municipio más afectado** corresponden a {anio_actual} "
            "(el año más reciente)."
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Casos totales", f"{total:,}", help="Total en todos los años filtrados.", border=True)
    with c2:
        # delta con flecha SI es legitimo aqui: compara contra el año anterior
        # (una variacion real que subio o bajo), a diferencia de los KPI de "% del
        # total" del resto del dashboard.
        st.metric(label_anio, valor_anio, delta=delta_anio, border=True)
    with c3:
        etiqueta_semana = f"Semana pico {anio_actual}" if anio_actual is not None else "Semana pico"
        st.metric(etiqueta_semana, semana_label, help=semana_help, border=True)
    with c4:
        st.metric("Municipio más afectado", top_mun, help=top_help, border=True)


# ---------------------------------------------------------------------------
# 1.1  Casos por año
# ---------------------------------------------------------------------------

def _mostrar_casos_por_anio(casos: pd.DataFrame) -> None:
    st.subheader(":material/bar_chart: Casos por año")

    por_anio = casos.groupby("ano").size().reset_index(name="casos")

    fig = px.bar(por_anio, x="ano", y="casos", text="casos",
                 labels={"ano": "Año", "casos": "Casos"})
    fig.update_xaxes(type="category")
    fig.update_traces(
        texttemplate="%{text:,}",
        textposition="outside",
        name="Casos",
        showlegend=True,
    )

    # Linea de promedio anual: da una referencia de "año alto vs año bajo".
    promedio = float(por_anio["casos"].mean())
    fig.add_hline(
        y=promedio,
        line_dash="dot",
        line_color=NARANJA_INSTITUCIONAL,
        annotation_text=f"Promedio {promedio:,.0f}",
        annotation_position="top left",
    )
    fig.update_layout(
        **_LAYOUT_BASE,
        yaxis={"range": rango_con_margen(por_anio["casos"].max())},
        legend=LEYENDA_SUPERIOR,
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 1.5  Mapa del Magdalena
# ---------------------------------------------------------------------------

_ZONA_AREA_MAP = {1: "Cabecera municipal", 2: "Centro poblado", 3: "Rural disperso"}
_ZONA_AREA_COLORES = {
    "Cabecera municipal": AZUL_INSTITUCIONAL,
    "Centro poblado": NARANJA_INSTITUCIONAL,
    "Rural disperso": "#7c3aed",
}


def _mostrar_mapa(casos: pd.DataFrame) -> None:
    """Vista general por subregion (incidencia); al pasar el mouse se resalta la
    subregion completa (un poligono por subregion). Tres niveles de detalle,
    todos en incidencia (x100.000 hab.): clic en subregion -> municipios de esa
    subregion; clic en un municipio -> division por zona (cabecera municipal,
    centro poblado, rural disperso).
    """
    st.subheader(":material/map: Mapa del Magdalena")

    subregion_activa = st.session_state.get("mapa_subregion_seleccionada")
    municipio_activo = st.session_state.get("mapa_municipio_seleccionado")

    con_geo = casos[casos["mun_valido"]].dropna(subset=["cod_mun_completo", "subregion"])
    if con_geo.empty:
        st.info("Sin casos con geografia valida.", icon=":material/info:")
        return

    con_geo = con_geo.copy()
    con_geo["cod_mun_completo"] = con_geo["cod_mun_completo"].astype(int)

    if subregion_activa and municipio_activo:
        _mostrar_mapa_zonas(con_geo, subregion_activa, municipio_activo)
    elif subregion_activa:
        _mostrar_mapa_drilldown(con_geo, subregion_activa)
    else:
        _mostrar_mapa_overview(con_geo)


def _mostrar_mapa_overview(con_geo: pd.DataFrame) -> None:
    st.caption(":material/touch_app: Haz clic en una subregión para ver el detalle por municipio.")

    anios_en_alcance = sorted(int(a) for a in con_geo["ano"].dropna().unique())
    mapeo_subregion = obtener_mapeo_subregion()
    incidencia_por_subregion = calcular_tasa_por_subregion(con_geo, anios_en_alcance, mapeo_subregion)
    casos_por_subregion = con_geo["subregion"].value_counts().to_dict()

    todas_subregiones = sorted(set(mapeo_subregion.values()))
    datos_mapa = pd.DataFrame({"subregion": todas_subregiones})
    datos_mapa["incidencia"] = datos_mapa["subregion"].map(incidencia_por_subregion)
    datos_mapa["casos"] = datos_mapa["subregion"].map(casos_por_subregion).fillna(0).astype(int)

    geojson = obtener_geojson_subregiones(mapeo_subregion)

    fig = px.choropleth(
        datos_mapa,
        geojson=geojson,
        locations="subregion",
        featureidkey="properties.subregion",
        color="incidencia",
        color_continuous_scale=ESCALA_INCIDENCIA,
        labels={"casos": "Casos", "incidencia": "Incidencia (x100.000 hab.)", "subregion": "Subregión"},
        hover_data={"subregion": True, "casos": True, "incidencia": ":.1f"},
    )
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=1)
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=360)

    resultado = st.plotly_chart(
        fig, width="stretch", on_select="rerun", selection_mode="points", key="mapa_overview",
    )

    try:
        puntos = resultado.selection.points
    except AttributeError:
        puntos = []
    if puntos:
        # locations="subregion" -> el click devuelve el nombre de la subregion directo.
        subregion_clickeada = puntos[0].get("location")
        if subregion_clickeada:
            st.session_state["mapa_subregion_seleccionada"] = str(subregion_clickeada)
            st.rerun()

    st.caption(
        "Incidencia = casos (210+220) / población en riesgo x 100.000. "
        "Subregiones en gris no tienen población DANE para el período filtrado."
    )


def _mostrar_mapa_drilldown(con_geo: pd.DataFrame, subregion_activa: str) -> None:
    col_volver, col_titulo = st.columns([1, 4], vertical_alignment="center")
    with col_volver:
        if st.button("Volver", icon=":material/arrow_back:", key="mapa_volver", width="stretch"):
            st.session_state["mapa_subregion_seleccionada"] = None
            st.session_state["mapa_municipio_seleccionado"] = None
            st.rerun()
    with col_titulo:
        st.caption(
            f":material/location_on: Subregión {subregion_activa} — municipios por incidencia. "
            "Haz clic en un municipio para ver sus zonas."
        )

    mapeo_subregion = obtener_mapeo_subregion()
    municipios_subregion = sorted(
        cod for cod, sub in mapeo_subregion.items() if sub == subregion_activa
    )

    anios_en_alcance = sorted(int(a) for a in con_geo["ano"].dropna().unique())
    tasas_municipio = calcular_tasa_por_municipio(con_geo, anios_en_alcance, municipios_subregion)
    casos_por_municipio = con_geo["cod_mun_completo"].value_counts().to_dict()

    tiene_nom_mun = "nom_mun_o" in con_geo.columns
    nombres_municipio = {}
    if tiene_nom_mun:
        nombres_municipio = (
            con_geo.dropna(subset=["nom_mun_o"])
            .drop_duplicates(subset=["cod_mun_completo"])
            .set_index("cod_mun_completo")["nom_mun_o"]
            .to_dict()
        )

    datos_mapa = pd.DataFrame({"cod_mun_completo": municipios_subregion})
    datos_mapa["incidencia"] = datos_mapa["cod_mun_completo"].map(tasas_municipio)
    datos_mapa["casos"] = datos_mapa["cod_mun_completo"].map(casos_por_municipio).fillna(0).astype(int)
    datos_mapa["cod_str"] = datos_mapa["cod_mun_completo"].apply(lambda x: f"{x:05d}")
    if tiene_nom_mun:
        datos_mapa["nom_mun_o"] = datos_mapa["cod_mun_completo"].map(nombres_municipio).fillna("")

    hover = {"cod_str": False, "casos": True, "incidencia": ":.1f"}
    if tiene_nom_mun:
        hover["nom_mun_o"] = True

    geojson = obtener_geojson_municipios_magdalena()

    fig = px.choropleth(
        datos_mapa,
        geojson=geojson,
        locations="cod_str",
        featureidkey="properties.mpio_cdpmp",
        color="incidencia",
        color_continuous_scale=ESCALA_INCIDENCIA,
        labels={"casos": "Casos", "incidencia": "Incidencia (x100.000 hab.)", "nom_mun_o": "Municipio"},
        hover_data=hover,
    )
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=1)
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=360)
    resultado = st.plotly_chart(
        fig, width="stretch", key="mapa_drill",
        on_select="rerun", selection_mode="points",
    )

    try:
        puntos = resultado.selection.points
    except AttributeError:
        puntos = []
    if puntos:
        # locations="cod_str" -> el click devuelve el codigo DIVIPOLA del municipio.
        codigo_clickeado = puntos[0].get("location")
        if codigo_clickeado:
            st.session_state["mapa_municipio_seleccionado"] = str(codigo_clickeado)
            st.rerun()

    st.caption(
        "Incidencia = casos (210+220) / población en riesgo del municipio x 100.000. "
        "Municipios en gris no tienen población DANE para el período filtrado."
    )


def _mostrar_mapa_zonas(con_geo: pd.DataFrame, subregion_activa: str, codigo_municipio: str) -> None:
    datos_municipio = con_geo[con_geo["cod_mun_completo"] == int(codigo_municipio)]

    nombre_municipio = codigo_municipio
    if "nom_mun_o" in datos_municipio.columns and not datos_municipio["nom_mun_o"].dropna().empty:
        nombre_municipio = str(datos_municipio["nom_mun_o"].dropna().iloc[0]).title()

    col_volver, col_titulo = st.columns([1, 4], vertical_alignment="center")
    with col_volver:
        if st.button("Volver", icon=":material/arrow_back:", key="mapa_volver_zona", width="stretch"):
            st.session_state["mapa_municipio_seleccionado"] = None
            st.rerun()
    with col_titulo:
        st.caption(
            f":material/location_on: {nombre_municipio} (subregión {subregion_activa}) — incidencia por zona"
        )

    if datos_municipio.empty:
        st.info("Sin casos para este municipio con los filtros actuales.", icon=":material/info:")
        return

    anios_en_alcance = sorted(int(a) for a in datos_municipio["ano"].dropna().unique())
    codigo_int = int(codigo_municipio)

    col_mapa, col_zonas = st.columns([1, 1])

    with col_mapa:
        # El poligono del municipio como referencia visual del territorio elegido.
        incidencia_municipio = calcular_tasa_por_municipio(
            datos_municipio, anios_en_alcance, [codigo_int]
        ).get(codigo_int)
        datos_mapa = pd.DataFrame({
            "cod_str": [f"{codigo_int:05d}"],
            "municipio": [nombre_municipio],
            "casos": [len(datos_municipio)],
            "incidencia": [incidencia_municipio],
        })
        geojson = obtener_geojson_municipios_magdalena()
        fig = px.choropleth(
            datos_mapa,
            geojson=geojson,
            locations="cod_str",
            featureidkey="properties.mpio_cdpmp",
            color="incidencia",
            color_continuous_scale=ESCALA_INCIDENCIA,
            labels={"casos": "Casos", "incidencia": "Incidencia (x100.000 hab.)", "municipio": "Municipio"},
            hover_data={"cod_str": False, "municipio": True, "casos": True, "incidencia": ":.1f"},
        )
        fig.update_traces(marker_line_color="#ffffff", marker_line_width=1)
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=360,
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, width="stretch", key="mapa_zona")

    with col_zonas:
        conteo = pd.Series(dtype=int)
        if "area" in datos_municipio.columns:
            conteo = (
                datos_municipio["area"].dropna().astype(int).map(_ZONA_AREA_MAP).value_counts()
            )
        if conteo.empty:
            st.caption("Sin datos de zona (área de ocurrencia) para este municipio.")
        else:
            tasas_zona = calcular_tasa_por_zona_municipio(
                conteo.to_dict(), codigo_int, anios_en_alcance
            )
            df_zonas = pd.DataFrame({
                "zona": list(tasas_zona.keys()),
                "incidencia": list(tasas_zona.values()),
            })
            df_zonas = df_zonas.dropna(subset=["incidencia"])
            if df_zonas.empty:
                st.caption("Sin población DANE disponible para el período filtrado.")
            else:
                df_zonas["etiqueta"] = df_zonas["incidencia"].apply(lambda v: f"{v:,.1f}")
                fig_zonas = px.bar(
                    df_zonas, x="incidencia", y="zona", color="zona", text="etiqueta",
                    orientation="h",
                    labels={"incidencia": "Incidencia x100.000 hab.", "zona": ""},
                    color_discrete_map=_ZONA_AREA_COLORES,
                )
                fig_zonas.update_traces(textposition="outside")
                fig_zonas.update_layout(
                    height=360,
                    margin=dict(l=0, r=40, t=40, b=0),
                    xaxis={"range": rango_con_margen(df_zonas["incidencia"].max())},
                    yaxis={"categoryorder": "total ascending", "showticklabels": False},
                    legend={**LEYENDA_SUPERIOR, "xanchor": "left", "x": 0, "font": {"size": 10}},
                )
                st.plotly_chart(fig_zonas, width="stretch", key="mapa_zona_bar")

    st.caption(
        "Zona según el área de ocurrencia del caso (cabecera municipal, centro poblado "
        "o rural disperso). Incidencia x100.000 hab."
    )


# ---------------------------------------------------------------------------
# 1.2 / 1.3 / 1.4  Analisis semanal (selector de anio local)
# ---------------------------------------------------------------------------

def _mostrar_seccion_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/show_chart: Análisis semanal")

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        st.caption("Sin datos.")
        return

    col_sel, col_nota = st.columns([1, 3], vertical_alignment="center")
    with col_sel:
        anio = st.selectbox(
            "Año de análisis",
            options=anios,
            key="tendencia_anio_semanal",
        )
    with col_nota:
        st.caption(
            ":material/info: El año de análisis es un selector propio de esta sección "
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
        labels={"semana": "Semana epidemiológica", "casos": "Casos"},
        title=f"Casos semanales {anio}",
    )
    fig.update_traces(name="Casos", showlegend=True)
    fig.add_hline(
        y=promedio,
        line_dash="dot",
        line_color=NARANJA_INSTITUCIONAL,
        annotation_text=f"Prom. {promedio:.0f}",
        annotation_position="top right",
    )
    fig.update_layout(**_LAYOUT_BASE, legend=LEYENDA_SUPERIOR)
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
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

    # Hover propio "Semana X · Y casos (año)" en vez de la coordenada (x, y) cruda.
    if not df_prev.empty:
        fig.add_trace(go.Bar(
            x=df_prev["semana"], y=df_prev["casos"],
            name=str(anio_prev),
            marker_color=NARANJA_INSTITUCIONAL,
            opacity=0.65,
            hovertemplate=f"Semana %{{x}} · %{{y:,}} casos ({anio_prev})<extra></extra>",
        ))

    if not df_act.empty:
        fig.add_trace(go.Scatter(
            x=df_act["semana"], y=df_act["casos"],
            mode="lines+markers",
            name=str(anio),
            line=dict(color=AZUL_INSTITUCIONAL, width=2),
            marker=dict(size=4),
            hovertemplate=f"Semana %{{x}} · %{{y:,}} casos ({anio})<extra></extra>",
        ))

    fig.update_layout(
        title=f"Comparación {anio} vs {anio_prev}",
        xaxis_title="Semana epidemiológica",
        yaxis_title="Casos",
        legend=LEYENDA_SUPERIOR,
        **_LAYOUT_BASE,
    )
    ultima_semana = int(pd.concat([df_prev["semana"], df_act["semana"]]).max())
    fig.update_xaxes(**eje_semanal(ultima_semana))
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

    variacion["signo"] = [
        "Aumento" if v >= 0 else "Disminución" for v in variacion["variacion"]
    ]

    fig = px.bar(
        variacion, x="semana", y="variacion",
        color="signo",
        color_discrete_map={
            "Aumento": AZUL_INSTITUCIONAL,
            "Disminución": NARANJA_INSTITUCIONAL,
        },
        labels={"semana": "Semana epidemiológica", "variacion": "Variación (%)", "signo": ""},
        title=f"Variación porcentual semanal: {anio} vs {anio_prev}",
    )
    fig.add_hline(y=0, line_color="#9ca3af", line_width=1)
    fig.update_layout(**_LAYOUT_BASE, legend=LEYENDA_SUPERIOR)
    fig.update_xaxes(**eje_semanal(int(variacion["semana"].max())))
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 1.6  Evolucion temporal por subregion o municipio
# ---------------------------------------------------------------------------

def _mostrar_evolucion_temporal(casos: pd.DataFrame) -> None:
    st.subheader(":material/timeline: Evolución temporal")

    nivel = st.segmented_control(
        "Agrupar por",
        _NIVEL_OPCIONES,
        default="Subregión",
        required=True,
        format_func=lambda o: _NIVEL_ETIQUETAS[o],
        key="tendencia_evolucion_nivel",
    )
    col_nivel = "subregion" if nivel == "Subregión" else "nom_mun_o"

    subset = casos.dropna(subset=[col_nivel, "cod_mun_completo"])
    if subset.empty:
        st.info("Sin casos con geografia valida.", icon=":material/info:")
        return

    evolucion_casos = subset.groupby(["ano", col_nivel]).size().reset_index(name="casos")

    if nivel == "Subregión":
        poblacion = obtener_poblacion_por_subregion_anio(obtener_mapeo_subregion())
        evolucion = evolucion_casos.merge(poblacion, on=["ano", "subregion"], how="left")
    else:
        # Agrupa poblacion por municipio a nivel de nombre (col_nivel es
        # nom_mun_o): un municipio solo tiene un cod_mun_completo, asi que el
        # merge por cod_mun_completo + ano no duplica filas.
        cod_por_municipio = subset.drop_duplicates(subset=["nom_mun_o"]).set_index("nom_mun_o")["cod_mun_completo"]
        evolucion_casos["cod_mun_completo"] = evolucion_casos["nom_mun_o"].map(cod_por_municipio)
        poblacion = obtener_poblacion_por_municipio_anio()
        evolucion = evolucion_casos.merge(poblacion, on=["ano", "cod_mun_completo"], how="left")

    evolucion["incidencia"] = evolucion["casos"] / evolucion["poblacion"] * 100_000
    evolucion = evolucion.dropna(subset=["incidencia"])
    if evolucion.empty:
        st.caption("Sin población DANE disponible para el período filtrado.")
        return

    evolucion["ano"] = evolucion["ano"].astype(str)

    # Paleta de alto contraste, curada a mano: prioriza que cada linea se
    # distinga de las demas, no la estetica. Sin rosados ni fucsias, que se
    # confunden con el rojo. Light24 solo como reserva para los 30 municipios.
    paleta_contraste = [
        "#2E91E5",  # azul
        "#FB0D0D",  # rojo
        "#1CA71C",  # verde
        "#B68100",  # ambar
        "#750D86",  # morado
        "#00A08B",  # verde azulado
        "#511CFB",  # indigo
        "#EB663B",  # naranja
        "#222A2A",  # grafito
        "#0D2A63",  # azul marino
        "#6C7C32",  # oliva
        "#A777F1",  # lila
        "#620042",  # vinotinto
        "#1616A7",  # azul profundo
        "#6C4516",  # cafe
    ] + px.colors.qualitative.Light24

    fig = px.line(
        evolucion, x="ano", y="incidencia", color=col_nivel, markers=True,
        color_discrete_sequence=paleta_contraste,
        labels={"ano": "Año", "incidencia": "Incidencia x100.000 hab.", col_nivel: nivel},
    )
    fig.update_layout(
        **_LAYOUT_BASE,
        legend=LEYENDA_SUPERIOR,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Incidencia = casos (210+220) / población en riesgo x 100.000.")
