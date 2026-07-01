"""Pestana 4 Morbilidad: notificacion, clasificacion y hospitalizacion.

Historia que cuenta:
  1. KPIs: casos totales, hospitalizados, graves, hospitalizados graves
  2. Panorama general: tipo de caso / flujo clasificacion (Sankey) / fuente
  3. Evolucion semanal: casos por tipo + % graves (selector anio local)
  4. Hospitalizacion: temporal + territorial (selector tipo de caso)
  5. Clasificacion final: dona + distribucion semanal

4.10 (incidencia por subregion) requiere poblacion DANE: pendiente.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL

CODIGOS_CASOS = {210, 220}
COD_DENGUE       = 210
COD_DENGUE_GRAVE = 220

_TIP_CAS_MAP = {
    "1": "Sospechoso",
    "2": "Probable",
    "3": "Conf. laboratorio",
    "4": "Conf. clinica",
    "5": "Conf. nexo epidemiologico",
}

_ESTADO_FINAL_MAP = {
    "2": "Probable",
    "3": "Conf. laboratorio",
    "4": "Conf. clinica",
    "5": "Conf. nexo epidemiologico",
    "6": "Descartado",
    "7": "Otro",
    "0": "Sin ajuste",
}

_FUENTE_MAP = {
    1: "Rutinaria",
    2: "Busqueda activa institucional",
    3: "Vigilancia intensificada",
    4: "Busqueda activa comunitaria",
    5: "Investigacion",
}

_TIPO_CASO_OPTS = {
    "Ambos": [COD_DENGUE, COD_DENGUE_GRAVE],
    "Dengue (210)": [COD_DENGUE],
    "Dengue grave (220)": [COD_DENGUE_GRAVE],
}

_LAYOUT = dict(margin=dict(l=0, r=0, t=40, b=0))


def _pct(n: float, total: float) -> str:
    if total == 0:
        return "—"
    p = n / total * 100
    if p >= 1:
        return f"{p:.1f}%"
    elif p >= 0.1:
        return f"{p:.2f}%"
    elif p > 0:
        return f"{p:.3f}%"
    return "0%"


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def mostrar_morbilidad(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(casos)
    st.space("small")

    # Panorama: tipo / flujo clasificacion / fuente comparativa (3 columnas)
    c1, c2, c3 = st.columns([1, 1.7, 1])
    with c1:
        with st.container(border=True, height="stretch"):
            _mostrar_tipo_caso(casos)
    with c2:
        with st.container(border=True, height="stretch"):
            _mostrar_sankey_clasificacion(casos)
    with c3:
        with st.container(border=True, height="stretch"):
            _mostrar_fuente(casos)

    st.space("small")

    # Evolucion semanal (selector anio local) — full width
    with st.container(border=True):
        _mostrar_evolucion_semanal(casos)

    st.space("small")

    # Hospitalizacion temporal — FULL WIDTH
    with st.container(border=True):
        _mostrar_hospitalizacion_semanal(casos)

    st.space("small")

    # Clasificacion final por semana + dona apiladas | Hospitalizacion territorial
    c_izq, c_der = st.columns([1, 1])
    with c_izq:
        with st.container(border=True):
            _mostrar_clasificacion_final_semanal(casos)
        st.space("small")
        with st.container(border=True):
            _mostrar_clasificacion_final_dona(casos)
    with c_der:
        with st.container(border=True, height="stretch"):
            _mostrar_hospitalizacion_territorial(casos)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)
    graves = int((casos["cod_eve"] == COD_DENGUE_GRAVE).sum())

    hosp = 0
    hosp_graves = 0
    if "pac_hos" in casos.columns:
        hosp = int((casos["pac_hos"] == 1).sum())
        hosp_graves = int(
            ((casos["cod_eve"] == COD_DENGUE_GRAVE) & (casos["pac_hos"] == 1)).sum()
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Casos totales", f"{total:,}")
    with c2:
        st.metric(
            "Hospitalizados",
            f"{hosp:,}",
            delta=_pct(hosp, total),
            delta_color="off",
        )
    with c3:
        st.metric(
            "Dengue grave (220)",
            f"{graves:,}",
            delta=_pct(graves, total),
            delta_color="off",
        )
    with c4:
        st.metric(
            "Hospitalizados graves",
            f"{hosp_graves:,}",
            delta=_pct(hosp_graves, graves),
            delta_color="off",
            help="Hospitalizados de dengue grave sobre el total de casos graves",
        )


# ---------------------------------------------------------------------------
# 4.3  Tipo de caso (dona)
# ---------------------------------------------------------------------------

def _mostrar_tipo_caso(casos: pd.DataFrame) -> None:
    st.subheader(":material/pie_chart: Tipo de caso")

    conteo = casos["cod_eve"].value_counts()
    labels = {COD_DENGUE: "Dengue (210)", COD_DENGUE_GRAVE: "Dengue grave (220)"}
    df = pd.DataFrame({
        "tipo": [labels.get(k, str(k)) for k in conteo.index],
        "casos": conteo.values,
    })
    total = df["casos"].sum()

    # Sin color_discrete_sequence: el tema de Streamlit aplica chartCategoricalColors
    # (azul institucional primero, naranja segundo) de forma automatica y consistente.
    fig = px.pie(df, names="tipo", values="casos", hole=0.55)
    fig.update_traces(
        texttemplate="%{label}<br>%{value:,}",
        textposition="outside",
    )
    fig.update_layout(
        showlegend=False,
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 4.2  Flujo clasificacion inicial → final (Sankey)
# ---------------------------------------------------------------------------

def _hex_rgba(hex_color: str, alpha: float) -> str:
    """Convierte un color hex a rgba(r,g,b,alpha) para usarlo en Plotly."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _mostrar_sankey_clasificacion(casos: pd.DataFrame) -> None:
    st.subheader(":material/account_tree: Clasificacion: inicial → final")

    cols_req = {"tip_cas", "estado_final_de_caso"}
    if not cols_req.issubset(casos.columns):
        st.caption("Sin datos de clasificacion.")
        return

    df = casos[["tip_cas", "estado_final_de_caso"]].dropna().copy()
    df["inicial"] = df["tip_cas"].astype(str).map(_TIP_CAS_MAP).fillna("Otro (inicial)")
    df["final"]   = df["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro (final)")

    flujo = df.groupby(["inicial", "final"]).size().reset_index(name="n")
    flujo = flujo[flujo["n"] > 0]

    if flujo.empty:
        st.caption("Sin datos de flujo de clasificacion.")
        return

    # Colores por estado (no por posicion izq/der): mismo color para un estado
    # independientemente de si aparece como clasificacion inicial o final.
    _PALETA_ESTADOS = {
        "Probable":                   "#64748b",
        "Conf. laboratorio":          "#1b3a6b",
        "Conf. nexo epidemiologico":  "#e8852c",
        "Conf. clinica":              "#5b88b3",
        "Descartado":                 "#94a3b8",
        "Sin ajuste":                 "#d1d5db",
        "Sospechoso":                 "#475569",
        "Otro (inicial)":             "#9ca3af",
        "Otro":                       "#9ca3af",
    }
    todos_estados = sorted(set(flujo["inicial"]) | set(flujo["final"]))
    nodos_izq = sorted(flujo["inicial"].unique())
    nodos_der = [n for n in todos_estados if n not in nodos_izq]
    nodos = nodos_izq + nodos_der
    idx = {n: i for i, n in enumerate(nodos)}

    colores_nodos = [_PALETA_ESTADOS.get(n, "#6b7280") for n in nodos]

    # Flujos coloreados por nodo de ORIGEN con transparencia:
    # el ojo puede seguir "que le paso a cada clasificacion inicial" por color.
    colores_links = [
        _hex_rgba(_PALETA_ESTADOS.get(row["inicial"], "#6b7280"), 0.45)
        for _, row in flujo.iterrows()
    ]

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=nodos,
            color=colores_nodos,
            pad=24,
            thickness=22,
            line=dict(color="white", width=0.8),
        ),
        link=dict(
            source=[idx[r["inicial"]] for _, r in flujo.iterrows()],
            target=[idx[r["final"]]   for _, r in flujo.iterrows()],
            value=flujo["n"].tolist(),
            color=colores_links,
            hovertemplate="%{source.label} → %{target.label}: %{value:,} casos<extra></extra>",
        ),
        textfont=dict(size=12, color="#1a1a1a", family="sans-serif"),
    ))
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=44, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        ":material/info: Los flujos heredan el color del estado inicial. "
        "Traza cada clasificacion de izquierda a derecha para ver como se ajusto."
    )


# ---------------------------------------------------------------------------
# 4.1  Fuente de notificacion (dona)
# ---------------------------------------------------------------------------

def _mostrar_fuente(casos: pd.DataFrame) -> None:
    """Barras horizontales para comparar todas las fuentes a la vez.
    Se prefiere barra sobre dona: la dona dificulta comparar magnitudes entre
    categorias cuando hay grandes diferencias (ej. Rutinaria vs. BAC).
    """
    st.subheader(":material/notification_important: Fuente")

    if "fuente" not in casos.columns:
        st.caption("Sin datos de fuente.")
        return

    conteo = casos["fuente"].dropna().astype(int).map(_FUENTE_MAP).value_counts()
    if conteo.empty:
        st.caption("Sin datos.")
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "fuente": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })

    fig = px.bar(
        df,
        x="casos",
        y="fuente",
        text="etiqueta",
        orientation="h",
        labels={"casos": "Casos", "fuente": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=60, t=40, b=0),
        yaxis={"categoryorder": "total ascending"},
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 4.4  Evolucion semanal por tipo de caso (selector anio local)
# ---------------------------------------------------------------------------

def _mostrar_evolucion_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/show_chart: Casos semanales por tipo")

    if "semana" not in casos.columns:
        st.caption("Sin datos de semana.")
        return

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        return

    col_sel, col_nota = st.columns([1, 3], vertical_alignment="center")
    with col_sel:
        anio = st.selectbox("Año de analisis", anios, key="morbilidad_anio_semanal")
    with col_nota:
        st.caption(":material/info: Selector propio — ignora el filtro temporal global.")

    subset = casos[casos["ano"] == anio].copy()
    if subset.empty:
        st.caption(f"Sin datos para {anio}.")
        return

    subset["tipo"] = subset["cod_eve"].map({
        COD_DENGUE: "Dengue (210)",
        COD_DENGUE_GRAVE: "Dengue grave (220)",
    })
    semanal = subset.groupby(["semana", "tipo"]).size().reset_index(name="casos")

    # Total por semana para calcular % graves
    total_sem = subset.groupby("semana").size().rename("total")
    graves_sem = subset[subset["cod_eve"] == COD_DENGUE_GRAVE].groupby("semana").size().rename("graves")
    pct_df = pd.concat([total_sem, graves_sem], axis=1).fillna(0).reset_index()
    pct_df["pct_grave"] = pct_df["graves"] / pct_df["total"] * 100

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="tipo",
        barmode="group",
        labels={"semana": "Semana epidemiologica", "casos": "Casos", "tipo": "Tipo"},
        color_discrete_map={
            "Dengue (210)": AZUL_INSTITUCIONAL,
            "Dengue grave (220)": NARANJA_INSTITUCIONAL,
        },
    )
    # Linea de % graves sobre eje secundario
    fig.add_trace(go.Scatter(
        x=pct_df["semana"],
        y=pct_df["pct_grave"],
        name="% Graves",
        mode="lines+markers",
        marker=dict(size=5),
        line=dict(dash="dot", width=1.5, color="#555555"),
        yaxis="y2",
    ))
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", title="% Graves", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 4.5  Hospitalizacion por semana y tipo de caso
# ---------------------------------------------------------------------------

def _mostrar_hospitalizacion_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/local_hospital: Hospitalizacion por semana")

    if "pac_hos" not in casos.columns or "semana" not in casos.columns:
        st.caption("Sin datos.")
        return

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    anio = st.selectbox("Año", anios, key="morbilidad_hosp_anio") if anios else None
    if anio is None:
        return

    subset = casos[casos["ano"] == anio].copy()
    subset["estado_hosp"] = subset["pac_hos"].map({1: "Hospitalizado", 2: "No hospitalizado"})
    subset["tipo"] = subset["cod_eve"].map({
        COD_DENGUE: "Dengue",
        COD_DENGUE_GRAVE: "Grave",
    })
    subset["categoria"] = subset["tipo"] + " — " + subset["estado_hosp"]

    semanal = subset.groupby(["semana", "categoria"]).size().reset_index(name="casos")

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="categoria",
        barmode="group",
        labels={"semana": "Semana", "casos": "Casos", "categoria": ""},
    )
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 4.6 + 4.7  Hospitalizacion territorial (subregion + municipio)
# ---------------------------------------------------------------------------

def _mostrar_hospitalizacion_territorial(casos: pd.DataFrame) -> None:
    st.subheader(":material/map: Hospitalizacion por territorio")

    if "pac_hos" not in casos.columns:
        st.caption("Sin datos de hospitalizacion.")
        return

    tipo_sel = st.segmented_control(
        "Tipo de caso",
        list(_TIPO_CASO_OPTS.keys()),
        default="Ambos",
        required=True,
        key="morbilidad_tipo_hosp",
    )
    codigos = _TIPO_CASO_OPTS.get(tipo_sel, list(CODIGOS_CASOS))
    subset = casos[(casos["cod_eve"].isin(codigos)) & (casos["pac_hos"] == 1)]

    if subset.empty:
        st.caption("Sin hospitalizados para ese filtro.")
        return

    # Subregion
    if "subregion" in subset.columns:
        sub = subset["subregion"].dropna().value_counts().reset_index()
        sub.columns = ["territorio", "hospitalizados"]
        sub = sub.sort_values("hospitalizados")
        fig_sub = px.bar(
            sub, x="hospitalizados", y="territorio", text="hospitalizados",
            orientation="h",
            labels={"hospitalizados": "Hospitalizados", "territorio": ""},
        )
        fig_sub.update_traces(textposition="outside", texttemplate="%{text:,}")
        fig_sub.update_layout(
            title="Por subregion (conteo)",
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig_sub, width="stretch")

    # Municipio — top 15
    if "nom_mun_o" in subset.columns:
        mun = subset["nom_mun_o"].dropna().value_counts().head(15).reset_index()
        mun.columns = ["municipio", "hospitalizados"]
        mun = mun.sort_values("hospitalizados")
        fig_mun = px.bar(
            mun, x="hospitalizados", y="municipio", text="hospitalizados",
            orientation="h",
            labels={"hospitalizados": "Hospitalizados", "municipio": ""},
        )
        fig_mun.update_traces(textposition="outside", texttemplate="%{text:,}")
        fig_mun.update_layout(
            title="Por municipio — Top 15 (conteo)",
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig_mun, width="stretch")

    st.caption(
        ":material/construction: Tasa por 100.000 hab. pendiente de datos poblacionales DANE."
    )


# ---------------------------------------------------------------------------
# 4.8  Clasificacion final (dona)
# ---------------------------------------------------------------------------

def _mostrar_clasificacion_final_dona(casos: pd.DataFrame) -> None:
    st.subheader(":material/fact_check: Clasificacion final")

    if "estado_final_de_caso" not in casos.columns:
        st.caption("Sin datos.")
        return

    conteo = (
        casos["estado_final_de_caso"]
        .dropna()
        .astype(str)
        .map(_ESTADO_FINAL_MAP)
        .value_counts()
    )
    if conteo.empty:
        st.caption("Sin datos.")
        return

    fig = px.pie(
        names=conteo.index,
        values=conteo.values,
        hole=0.55,
    )
    fig.update_traces(
        texttemplate="%{label}<br>%{value:,}",
        textposition="outside",
    )
    fig.update_layout(
        showlegend=False,
        height=300,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 4.9  Clasificacion final por semana
# ---------------------------------------------------------------------------

def _mostrar_clasificacion_final_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/stacked_bar_chart: Clasificacion final por semana")

    if "semana" not in casos.columns or "estado_final_de_caso" not in casos.columns:
        st.caption("Sin datos.")
        return

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        return

    anio = st.selectbox(
        "Año",
        anios,
        key="morbilidad_clas_final_anio",
        label_visibility="collapsed",
    )
    subset = casos[casos["ano"] == anio].copy()
    subset["clasificacion"] = (
        subset["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro")
    )

    semanal = subset.groupby(["semana", "clasificacion"]).size().reset_index(name="casos")

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="clasificacion",
        barmode="stack",
        labels={"semana": "Semana epidemiologica", "casos": "Casos", "clasificacion": "Clasificacion"},
    )
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        height=380,
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")
