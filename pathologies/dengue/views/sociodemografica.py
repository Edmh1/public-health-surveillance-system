"""Pestana 3 Sociodemografica: perfil de la poblacion afectada por dengue.

Historia que cuenta:
  1. KPIs de vulnerabilidad (total, gestantes, menores de 5, mayores de 65)
  2. Piramide poblacional (protagonista) + Explorador demografico interactivo
     (selector para ver Area / Estrato / Etnia / Regimen en el panel derecho)
  3. Pueblos indigenas (condicional)
  4. EPS y UPGD notificadoras (actores del sistema)
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL

CODIGOS_CASOS = {210, 220}
_TOP_N = 10

_BINS_EDAD   = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 200]
_LABELS_EDAD = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34",
                "35-39","40-44","45-49","50-54","55-59","60-64","65+"]

_AREA_MAP = {1: "Cabecera\nmunicipal", 2: "Centro\npoblado", 3: "Rural\ndisperso"}
_AREA_MAP_FULL = {1: "Cabecera municipal", 2: "Centro poblado", 3: "Rural disperso"}

_TIP_SS_MAP = {
    "s": "Subsidiado",
    "c": "Contributivo",
    "n": "No asegurado",
    "p": "Excepcion",
    "i": "Indigena",
    "e": "Especial",
}

_ETN_MAP = {
    1: "Indigena",
    2: "ROM",
    3: "Raizal",
    4: "Palenquero",
    5: "Afrocolombiano",
    6: "Ninguno / sin dato",
}

_SIN_INFO = {"sin informacion", "sin información", "sin info", "", "nan", "none"}

_LAYOUT = dict(margin=dict(l=0, r=0, t=40, b=0))


# ---------------------------------------------------------------------------
# Helper: porcentaje con decimales inteligentes
# ---------------------------------------------------------------------------

def _pct(n: float, total: float) -> str:
    """Devuelve porcentaje con la precision justa para que nunca salga '0%'
    cuando hay casos reales."""
    if total == 0:
        return "—"
    p = n / total * 100
    if p >= 10:
        return f"{p:.1f}%"
    elif p >= 1:
        return f"{p:.1f}%"
    elif p >= 0.1:
        return f"{p:.2f}%"
    elif p > 0:
        return f"{p:.3f}%"
    return "0%"


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def mostrar_sociodemografica(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    # 1. KPIs de vulnerabilidad
    _mostrar_kpis(casos)

    st.space("small")

    # 2. Piramide + Explorador interactivo
    col_pir, col_exp = st.columns([1.15, 1])
    with col_pir:
        with st.container(border=True, height="stretch"):
            _mostrar_piramide(casos)
    with col_exp:
        with st.container(border=True, height="stretch"):
            _explorador_demografico(casos)

    # 3. Pueblos indigenas (condicional)
    tiene_indigenas = (
        "per_etn" in casos.columns and (casos["per_etn"] == 1).any()
    )
    if tiene_indigenas:
        st.space("small")
        with st.container(border=True):
            _mostrar_pueblos_indigenas(casos)

    st.space("small")

    # 4. Actores del sistema: EPS y UPGD
    col_eps, col_upgd = st.columns(2)
    with col_eps:
        with st.container(border=True):
            _mostrar_eps(casos)
    with col_upgd:
        with st.container(border=True):
            _mostrar_upgd(casos)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)

    if "gp_gestan" in casos.columns:
        n_gest = int((casos["gp_gestan"] == 1).sum())
    else:
        n_gest = 0

    if "edad_anios" in casos.columns:
        edad = casos["edad_anios"].dropna().astype(float)
        n_men5  = int((edad < 5).sum())
        n_may65 = int((edad >= 65).sum())
    else:
        n_men5 = n_may65 = 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Casos totales", f"{total:,}")
    with c2:
        st.metric(
            "Gestantes",
            f"{n_gest:,}",
            delta=_pct(n_gest, total),
            delta_color="off",
        )
    with c3:
        st.metric(
            "Menores de 5 años",
            f"{n_men5:,}",
            delta=_pct(n_men5, total),
            delta_color="off",
        )
    with c4:
        st.metric(
            "Mayores de 65 años",
            f"{n_may65:,}",
            delta=_pct(n_may65, total),
            delta_color="off",
        )


# ---------------------------------------------------------------------------
# Pirámide poblacional (3.1)
# ---------------------------------------------------------------------------

def _mostrar_piramide(casos: pd.DataFrame) -> None:
    st.subheader(":material/groups: Piramide por sexo y edad")

    if not {"edad_anios", "sexo"}.issubset(casos.columns):
        st.caption("Sin datos de edad o sexo.")
        return

    df = casos[["edad_anios", "sexo"]].dropna()
    df = df[df["sexo"].isin(["m", "f"])].copy()
    if df.empty:
        st.caption("Sin datos suficientes.")
        return

    df["grupo"] = pd.cut(
        df["edad_anios"].astype(float),
        bins=_BINS_EDAD,
        labels=_LABELS_EDAD,
        right=False,
    )

    conteo = df.groupby(["grupo", "sexo"]).size().reset_index(name="n")
    hombres = conteo[conteo["sexo"] == "m"].set_index("grupo")["n"].reindex(_LABELS_EDAD, fill_value=0)
    mujeres = conteo[conteo["sexo"] == "f"].set_index("grupo")["n"].reindex(_LABELS_EDAD, fill_value=0)

    max_val = max(int(hombres.max()), int(mujeres.max()), 1) * 1.2

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=_LABELS_EDAD,
        x=[-v for v in hombres.values],
        name="Masculino",
        orientation="h",
        marker_color=AZUL_INSTITUCIONAL,
        hovertemplate="%{y}: %{customdata:,} casos<extra>Masculino</extra>",
        customdata=hombres.values,
    ))
    fig.add_trace(go.Bar(
        y=_LABELS_EDAD,
        x=list(mujeres.values),
        name="Femenino",
        orientation="h",
        marker_color=NARANJA_INSTITUCIONAL,
        hovertemplate="%{y}: %{x:,} casos<extra>Femenino</extra>",
    ))

    paso = max(1, int(max_val // 4))
    tick_vals = [-3*paso, -2*paso, -paso, 0, paso, 2*paso, 3*paso]
    tick_text = [str(abs(v)) for v in tick_vals]

    fig.update_layout(
        barmode="overlay",
        xaxis=dict(
            range=[-max_val, max_val],
            tickvals=tick_vals,
            ticktext=tick_text,
            title="Casos",
        ),
        yaxis_title="Grupo etario",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=420,
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Explorador demografico interactivo (panel derecho)
# ---------------------------------------------------------------------------

_OPCIONES_EXPLORADOR = ["Area", "Estrato", "Etnia", "Regimen"]
_ICONOS_EXPLORADOR = {
    "Area":    ":material/home:",
    "Estrato": ":material/apartment:",
    "Etnia":   ":material/diversity_2:",
    "Regimen": ":material/health_and_safety:",
}


def _explorador_demografico(casos: pd.DataFrame) -> None:
    st.subheader(":material/tune: Distribucion demografica")

    seleccion = st.segmented_control(
        "Ver distribucion por",
        _OPCIONES_EXPLORADOR,
        default="Area",
        required=True,
        format_func=lambda o: f"{_ICONOS_EXPLORADOR[o]} {o}",
        key="sociodem_explorador",
    )

    if seleccion == "Area":
        _chart_area(casos, height=380)
    elif seleccion == "Estrato":
        _chart_estrato(casos, height=380)
    elif seleccion == "Etnia":
        _chart_etnia(casos, height=380)
    elif seleccion == "Regimen":
        _chart_regimen(casos, height=380)


def _chart_area(casos: pd.DataFrame, height: int = 300) -> None:
    if "area" not in casos.columns:
        st.caption("Sin datos de area.")
        return
    conteo = casos["area"].dropna().map(_AREA_MAP_FULL).value_counts()
    if conteo.empty:
        st.caption("Sin datos.")
        return
    total = conteo.sum()
    fig = px.pie(
        names=conteo.index,
        values=conteo.values,
        hole=0.5,
    )
    fig.update_traces(
        texttemplate="%{label}<br>%{value:,} · %{percent:.2%}",
        textposition="outside",
    )
    fig.update_layout(
        margin=dict(l=20, r=20, t=30, b=20),
        height=height,
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")


def _chart_estrato(casos: pd.DataFrame, height: int = 300) -> None:
    if "estrato" not in casos.columns:
        st.caption("Sin datos de estrato.")
        return
    conteo = casos["estrato"].dropna().astype(int).value_counts().sort_index()
    if conteo.empty:
        st.caption("Sin datos.")
        return
    total = conteo.sum()
    df = pd.DataFrame({
        "estrato": [f"Estrato {e}" for e in conteo.index],
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="estrato", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "estrato": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=height, **_LAYOUT, yaxis={"categoryorder": "category ascending"})
    st.plotly_chart(fig, width="stretch")


def _chart_etnia(casos: pd.DataFrame, height: int = 300) -> None:
    if "per_etn" not in casos.columns:
        st.caption("Sin datos de etnia.")
        return
    conteo = casos["per_etn"].dropna().astype(int).map(_ETN_MAP).value_counts()
    if conteo.empty:
        st.caption("Sin datos.")
        return
    total = conteo.sum()
    df = pd.DataFrame({
        "etnia": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="etnia", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "etnia": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=height, **_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


def _chart_regimen(casos: pd.DataFrame, height: int = 300) -> None:
    if "tip_ss" not in casos.columns:
        st.caption("Sin datos de regimen.")
        return
    conteo = casos["tip_ss"].dropna().map(_TIP_SS_MAP).value_counts()
    if conteo.empty:
        st.caption("Sin datos.")
        return
    total = conteo.sum()
    df = pd.DataFrame({
        "regimen": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="regimen", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "regimen": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=height, **_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Pueblos indígenas — condicional (3.3)
# ---------------------------------------------------------------------------

def _mostrar_pueblos_indigenas(casos: pd.DataFrame) -> None:
    st.subheader(":material/forest: Pueblos indigenas afectados")

    if "nom_grupo" not in casos.columns:
        st.caption("Sin datos de pueblo indigena.")
        return

    indigenas = casos[(casos["per_etn"] == 1) & casos["nom_grupo"].notna()].copy()
    # Filtrar valores sin informacion
    indigenas = indigenas[
        ~indigenas["nom_grupo"].str.lower().str.strip().isin(_SIN_INFO)
    ]
    conteo = indigenas["nom_grupo"].value_counts().head(_TOP_N)

    if conteo.empty:
        st.caption("Sin registros de pueblo indigena identificado.")
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "pueblo": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="pueblo", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "pueblo": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# EPS (3.5) y UPGD (3.6)
# ---------------------------------------------------------------------------

def _mostrar_eps(casos: pd.DataFrame) -> None:
    st.subheader(":material/local_hospital: EPS de afiliacion")
    st.caption(f"Top {_TOP_N} por casos notificados")

    if "nom_ase" not in casos.columns:
        st.caption("Sin datos.")
        return
    conteo = casos["nom_ase"].dropna().value_counts().head(_TOP_N)
    if conteo.empty:
        st.caption("Sin datos.")
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "eps": conteo.index,
        "casos": conteo.values,
        "eps_short": [s[:33] + "…" if len(s) > 33 else s for s in conteo.index],
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="eps_short", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "eps_short": ""},
        hover_data={"eps": True, "eps_short": False, "casos": True, "etiqueta": False},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


def _mostrar_upgd(casos: pd.DataFrame) -> None:
    st.subheader(":material/medical_services: UPGD notificadora")
    st.caption(f"Top {_TOP_N} unidades por casos reportados")

    if "nom_upgd" not in casos.columns:
        st.caption("Sin datos.")
        return
    conteo = casos["nom_upgd"].dropna().str.title().value_counts().head(_TOP_N)
    if conteo.empty:
        st.caption("Sin datos.")
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "upgd": conteo.index,
        "casos": conteo.values,
        "upgd_short": [s[:33] + "…" if len(s) > 33 else s for s in conteo.index],
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="upgd_short", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "upgd_short": ""},
        hover_data={"upgd": True, "upgd_short": False, "casos": True, "etiqueta": False},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")
