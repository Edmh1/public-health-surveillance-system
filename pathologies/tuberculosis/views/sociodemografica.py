"""Pestana 3 Sociodemografica: perfil de la poblacion afectada por TB.

KPIs: casos totales, gestantes, menores de 5, mayores de 65.
Graficas: piramide poblacional, grupo etario/sexo, etnia, regimen, EPS, UPGD,
poblaciones vulnerables.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from pathologies.tuberculosis.views.utils import aplicar_filtro_tipo_tb

CODIGOS_TB = {810, 820, 825}

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


def mostrar_sociodemografica(datos: pd.DataFrame) -> None:
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

    col_piramide, col_etnia = st.columns(2)
    with col_piramide:
        with st.container(border=True):
            _mostrar_piramide_poblacional(casos)
    with col_etnia:
        with st.container(border=True):
            _mostrar_etnia(casos)

    st.space("small")

    col_regimen, col_eps = st.columns(2)
    with col_regimen:
        with st.container(border=True):
            _mostrar_regimen(casos)
    with col_eps:
        with st.container(border=True):
            _mostrar_eps(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_upgd(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_poblaciones_vulnerables(casos)


def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)

    gestantes = int((casos["gp_gestan"] == 1).sum()) if "gp_gestan" in casos.columns else 0
    menores_5 = int((casos["edad_anios"] < 5).sum()) if "edad_anios" in casos.columns else 0
    mayores_65 = int((casos["edad_anios"] >= 65).sum()) if "edad_anios" in casos.columns else 0

    cols = st.columns(4)
    cols[0].metric("Casos totales", f"{total:,}")
    cols[1].metric("Gestantes", f"{gestantes:,}", f"{gestantes / total * 100:.1f}%" if total else None)
    cols[2].metric("Menores de 5", f"{menores_5:,}", f"{menores_5 / total * 100:.1f}%" if total else None)
    cols[3].metric("Mayores de 65", f"{mayores_65:,}", f"{mayores_65 / total * 100:.1f}%" if total else None)


def _mostrar_piramide_poblacional(casos: pd.DataFrame) -> None:
    if "edad_anios" not in casos.columns or "sexo" not in casos.columns:
        st.info("Datos insuficientes para la pirámide poblacional.", icon=":material/info:")
        return

    copia = casos.copy()
    copia["grupo_etario"] = copia["edad_anios"].apply(_clasificar_grupo_etario)

    masc = copia[copia["sexo"].isin(["m", "masculino"])]
    fem = copia[copia["sexo"].isin(["f", "femenino"])]

    por_edad_masc = masc.groupby("grupo_etario").size()
    por_edad_fem = fem.groupby("grupo_etario").size()

    etiquetas = [g[2] for g in GRUPOS_ETARIOS]
    valores_masc = [-por_edad_masc.get(e, 0) for e in etiquetas]
    valores_fem = [por_edad_fem.get(e, 0) for e in etiquetas]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=etiquetas, x=valores_masc, orientation="h",
        name="Masculino", marker_color=AZUL_INSTITUCIONAL,
        text=[abs(v) for v in valores_masc], textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=etiquetas, x=valores_fem, orientation="h",
        name="Femenino", marker_color=NARANJA_INSTITUCIONAL,
        text=valores_fem, textposition="inside",
    ))
    fig.update_layout(
        title="Pirámide poblacional",
        barmode="relative",
        xaxis_title="Casos",
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_etnia(casos: pd.DataFrame) -> None:
    if "per_etn" not in casos.columns:
        st.info("Datos de pertenencia étnica no disponibles.", icon=":material/info:")
        return

    etiquetas_etnia = {1: "Indígena", 2: "ROM", 3: "Raizal", 4: "Palenquero", 5: "Afro", 6: "Ninguna"}
    copia = casos.copy()
    copia["etnia_nombre"] = copia["per_etn"].map(etiquetas_etnia).fillna("Sin dato")

    por_etnia = copia.groupby("etnia_nombre").size().sort_values(ascending=True).reset_index(name="casos")
    total = por_etnia["casos"].sum()
    por_etnia["pct"] = (por_etnia["casos"] / total * 100).round(1)

    fig = px.bar(
        por_etnia, x="casos", y="etnia_nombre", orientation="h",
        title="Casos por pertenencia étnica",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text="pct",
    )
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_regimen(casos: pd.DataFrame) -> None:
    if "tip_ss" not in casos.columns:
        return

    etiquetas_reg = {
        "c": "Contributivo", "s": "Subsidiado", "n": "No afiliado",
        "e": "Especial", "i": "Indeterminado",
    }
    copia = casos.copy()
    copia["regimen"] = copia["tip_ss"].astype(str).str.strip().str.lower().map(etiquetas_reg).fillna("Sin dato")

    por_reg = copia.groupby("regimen").size().sort_values(ascending=True).reset_index(name="casos")
    total = por_reg["casos"].sum()
    por_reg["pct"] = (por_reg["casos"] / total * 100).round(1)

    fig = px.bar(
        por_reg, x="casos", y="regimen", orientation="h",
        title="Casos por régimen de afiliación",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text="pct",
    )
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_eps(casos: pd.DataFrame) -> None:
    if "nom_ase" not in casos.columns:
        return

    copia = casos.copy()
    copia["eps"] = copia["nom_ase"].fillna("Sin dato")

    por_eps = copia.groupby("eps").size().sort_values(ascending=True).reset_index(name="casos")
    por_eps = por_eps.tail(10)

    total = por_eps["casos"].sum()
    por_eps["pct"] = (por_eps["casos"] / total * 100).round(1)

    fig = px.bar(
        por_eps, x="casos", y="eps", orientation="h",
        title="Top 10 EAPB (EPS)",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text="pct",
    )
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_upgd(casos: pd.DataFrame) -> None:
    if "nom_upgd" not in casos.columns:
        return

    copia = casos.copy()
    copia["upgd"] = copia["nom_upgd"].fillna("Sin dato")

    por_upgd = copia.groupby("upgd").size().sort_values(ascending=True).reset_index(name="casos")
    por_upgd = por_upgd.tail(10)

    total = por_upgd["casos"].sum()
    por_upgd["pct"] = (por_upgd["casos"] / total * 100).round(1)

    fig = px.bar(
        por_upgd, x="casos", y="upgd", orientation="h",
        title="Top 10 UPGD notificadoras",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
        text="pct",
    )
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


def _mostrar_poblaciones_vulnerables(casos: pd.DataFrame) -> None:
    columnas_vulnerables = {
        "gp_migrant": "Migrante",
        "gp_carcela": "PPL (Privado de libertad)",
        "gp_desplaz": "Desplazado",
        "gp_discapa": "Discapacidad",
        "gp_indigen": "Indígena",
        "gp_desmovi": "Desmovilizado",
        "gp_vic_vio": "Víctima de violencia",
    }

    disponibles = {col: label for col, label in columnas_vulnerables.items() if col in casos.columns}
    if not disponibles:
        return

    conteos = []
    for col, label in disponibles.items():
        n = int((casos[col] == 1).sum())
        conteos.append({"grupo": label, "casos": n})

    df = pd.DataFrame(conteos).sort_values("casos", ascending=True)
    total = len(casos)

    fig = px.bar(
        df, x="casos", y="grupo", orientation="h",
        title="Poblaciones vulnerables",
        color_discrete_sequence=[AZUL_INSTITUCIONAL],
    )
    fig.update_layout(**_LAYOUT_BASE, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)
