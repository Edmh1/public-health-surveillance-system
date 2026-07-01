"""Pestana 5 Mortalidad: muertes por dengue (cod_eve 580).

Historia: cuantas muertes, cuando, quien, donde, y si la letalidad supera la meta.
Diseno sobrio — sin alarmar visualmente pero sin suavizar la realidad.

El unico lugar del dashboard donde se usa color de estado (alerta/epidemia) en
un KPI es aqui: la letalidad se colorea cuando supera la meta nacional de 0.10 %,
segun la regla de DESIGN.md de "umbral epidemiologico definido".

Tasas por poblacion (mortalidad / 100.000 hab.) quedan pendientes de datos DANE.
Se muestran en su lugar: letalidad = 580/(210+220) y letalidad grave = 580/220,
que no requieren denominador poblacional.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL

COD_MUERTE       = 580
CODIGOS_CASOS    = {210, 220}
META_LETALIDAD   = 0.10  # meta nacional INS/MSPS

_BINS_EDAD  = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 200]
_LABS_EDAD  = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34",
               "35-39","40-44","45-49","50-54","55-59","60-64","65+"]

_TIP_SS_MAP = {
    "s": "Subsidiado", "c": "Contributivo", "n": "No asegurado",
    "p": "Excepcion",  "i": "Indigena",      "e": "Especial",
}

_LAYOUT = dict(margin=dict(l=0, r=0, t=40, b=0))

_TOP_N = 10


def _pct(n: float, total: float, dec: int = 2) -> float:
    return round(n / total * 100, dec) if total else 0.0


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def mostrar_mortalidad(datos: pd.DataFrame) -> None:
    muertes = datos[datos["cod_eve"] == COD_MUERTE]
    casos   = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]
    graves  = datos[datos["cod_eve"] == 220]

    if muertes.empty:
        st.info(
            "No hay muertes por dengue registradas para los filtros actuales.",
            icon=":material/info:",
        )
        return

    _mostrar_kpis(muertes, casos, graves)

    st.space("small")

    # Distribucion temporal
    with st.container(border=True):
        _mostrar_temporal(muertes)

    st.space("small")

    # Grid 2x2: perfil + indicadores territoriales
    col_izq, col_der = st.columns(2)
    with col_izq:
        with st.container(border=True):
            _mostrar_edad_sexo(muertes)
        st.space("small")
        with st.container(border=True):
            _mostrar_regimen(muertes)
    with col_der:
        with st.container(border=True):
            _mostrar_eps(muertes)
        st.space("small")
        with st.container(border=True, height="stretch"):
            _mostrar_tasas_subregion(muertes, casos, graves)

    st.space("small")

    # Tabla drill-down — full width
    with st.container(border=True):
        _mostrar_tabla_territorial(muertes, casos, graves)

    st.space("small")

    # CIE-10
    with st.container(border=True):
        _mostrar_cie10(muertes)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(muertes: pd.DataFrame, casos: pd.DataFrame, graves: pd.DataFrame) -> None:
    n_total = len(muertes)
    n_casos = len(casos)
    n_graves = len(graves)

    letalidad       = _pct(n_total, n_casos, 4)
    letalidad_grave = _pct(n_total, n_graves, 2)

    # Menores de 15 (grupo de atencion prioritaria en mortalidad por dengue)
    if "edad_anios" in muertes.columns:
        n_men15 = int((muertes["edad_anios"].dropna().astype(float) < 15).sum())
    else:
        n_men15 = 0

    supera_meta = letalidad > META_LETALIDAD

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Muertes por dengue", f"{n_total:,}")
    with c2:
        st.metric(
            "Menores de 15 anos",
            f"{n_men15:,}",
            delta=f"{_pct(n_men15, n_total, 1):.1f}% del total",
            delta_color="off",
            help="Grupo de atencion prioritaria en mortalidad por dengue",
        )
    with c3:
        # delta_color="inverse": si letalidad > META_LETALIDAD (0.10%) es una
        # señal epidemiologica real — uso legitimo de color de alerta (DESIGN.md).
        st.metric(
            "Letalidad",
            f"{letalidad:.4f}%",
            delta=f"Meta INS < {META_LETALIDAD}%" if supera_meta else None,
            delta_color="inverse" if supera_meta else "off",
            help=(
                "Muertes (580) / Casos dengue (210+220) x 100. "
                f"La meta nacional INS establece una letalidad < {META_LETALIDAD}%: "
                "cada 1.000 casos de dengue deberia haber menos de 1 muerte."
            ),
        )
    with c4:
        st.metric(
            "Letalidad grave",
            f"{letalidad_grave:.2f}%",
            help="Muertes (580) / Casos de dengue grave (220) x 100",
        )


# ---------------------------------------------------------------------------
# 5.1  Distribucion temporal
# ---------------------------------------------------------------------------

def _mostrar_temporal(muertes: pd.DataFrame) -> None:
    st.subheader(":material/calendar_month: Muertes por semana epidemiologica")

    if "semana" not in muertes.columns:
        st.caption("Sin datos de semana.")
        return

    anios = sorted(muertes["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        return

    col_sel, col_nota = st.columns([1, 3], vertical_alignment="center")
    with col_sel:
        anio = st.selectbox("Año", anios, key="mort_anio_temporal")
    with col_nota:
        st.caption(":material/info: Selector propio — ignora el filtro temporal global.")

    subset = muertes[muertes["ano"] == anio]

    # Notificadas vs confirmadas por semana
    semanal_total = subset.groupby("semana").size().reset_index(name="n")
    semanal_total["tipo"] = "Notificadas"

    if "confirmados" in subset.columns:
        semanal_conf = (
            subset[subset["confirmados"] == 1]
            .groupby("semana")
            .size()
            .reset_index(name="n")
        )
        semanal_conf["tipo"] = "Confirmadas"
        df_plot = pd.concat([semanal_total, semanal_conf], ignore_index=True)
    else:
        df_plot = semanal_total

    fig = px.bar(
        df_plot,
        x="semana",
        y="n",
        color="tipo",
        barmode="group",
        text="n",
        labels={"semana": "Semana epidemiologica", "n": "Muertes", "tipo": ""},
        color_discrete_map={
            "Notificadas":  AZUL_INSTITUCIONAL,
            "Confirmadas":  NARANJA_INSTITUCIONAL,
        },
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT)
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 5.2  Edad y sexo
# ---------------------------------------------------------------------------

def _mostrar_edad_sexo(muertes: pd.DataFrame) -> None:
    st.subheader(":material/groups: Muertes por sexo y edad")

    if not {"edad_anios", "sexo"}.issubset(muertes.columns):
        st.caption("Sin datos de edad o sexo.")
        return

    df = muertes[["edad_anios", "sexo"]].dropna()
    df = df[df["sexo"].isin(["m", "f"])].copy()

    if df.empty:
        st.caption("Sin datos.")
        return

    df["grupo"] = pd.cut(
        df["edad_anios"].astype(float),
        bins=_BINS_EDAD,
        labels=_LABS_EDAD,
        right=False,
    )
    conteo = df.groupby(["grupo", "sexo"]).size().reset_index(name="n")
    conteo["sexo_label"] = conteo["sexo"].map({"m": "Masculino", "f": "Femenino"})

    total = conteo["n"].sum()
    conteo["pct"] = (conteo["n"] / total * 100).round(1)
    conteo["etiqueta"] = conteo.apply(
        lambda r: f"{r['n']}  ({r['pct']:.1f}%)" if r["n"] > 0 else "", axis=1
    )

    fig = px.bar(
        conteo,
        x="n",
        y="grupo",
        color="sexo_label",
        barmode="group",
        text="etiqueta",
        orientation="h",
        labels={"n": "Muertes", "grupo": "Grupo etario", "sexo_label": "Sexo"},
        color_discrete_map={"Masculino": AZUL_INSTITUCIONAL, "Femenino": NARANJA_INSTITUCIONAL},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        **_LAYOUT,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis={"categoryorder": "array", "categoryarray": _LABS_EDAD},
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 5.5  Regimen SGSSS
# ---------------------------------------------------------------------------

def _mostrar_regimen(muertes: pd.DataFrame) -> None:
    st.subheader(":material/health_and_safety: Regimen SGSSS")

    if "tip_ss" not in muertes.columns:
        st.caption("Sin datos.")
        return

    conteo = muertes["tip_ss"].dropna().map(_TIP_SS_MAP).value_counts()
    if conteo.empty:
        st.caption("Sin datos.")
        return

    total = conteo.sum()
    df = conteo.reset_index()
    df.columns = ["regimen", "n"]
    df["etiqueta"] = df.apply(
        lambda r: f"{r['n']}  ({r['n']/total*100:.1f}%)", axis=1
    )

    fig = px.bar(
        df, x="n", y="regimen", text="etiqueta", orientation="h",
        labels={"n": "Muertes", "regimen": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 5.3  EPS
# ---------------------------------------------------------------------------

def _mostrar_eps(muertes: pd.DataFrame) -> None:
    st.subheader(":material/local_hospital: EPS de afiliacion")

    if "nom_ase" not in muertes.columns:
        st.caption("Sin datos.")
        return

    conteo = muertes["nom_ase"].dropna().value_counts().head(_TOP_N)
    if conteo.empty:
        st.caption("Sin datos.")
        return

    df = conteo.reset_index()
    df.columns = ["eps", "n"]
    df["eps_short"] = df["eps"].apply(lambda s: s[:33] + "…" if len(s) > 33 else s)

    fig = px.bar(
        df, x="n", y="eps_short", text="n", orientation="h",
        labels={"n": "Muertes", "eps_short": ""},
        hover_data={"eps": True, "eps_short": False, "n": True},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 5.6  Indicadores por territorio (tabla drill-down)
# ---------------------------------------------------------------------------

def _mostrar_tabla_territorial(
    muertes: pd.DataFrame, casos: pd.DataFrame, graves: pd.DataFrame
) -> None:
    st.subheader(":material/table_chart: Indicadores por territorio")
    st.caption(
        "Letalidad = muertes / (casos 210+220). "
        "Letalidad grave = muertes / casos 220. "
        "Tasa por 100.000 hab.: pendiente de datos DANE."
    )

    nivel = st.segmented_control(
        "Nivel de agregacion",
        ["Magdalena", "Subregion", "Municipio"],
        default="Subregion",
        required=True,
        key="mort_nivel_tabla",
    )

    def _calcular(key: str, m_df: pd.DataFrame, c_df: pd.DataFrame, g_df: pd.DataFrame) -> pd.DataFrame:
        if key == "Magdalena":
            return pd.DataFrame([{
                "Territorio": "Magdalena",
                "Muertes": len(m_df),
                "Casos (210+220)": len(c_df),
                "Casos graves (220)": len(g_df),
                "Letalidad (%)": round(_pct(len(m_df), len(c_df), 4), 4),
                "Letalidad grave (%)": round(_pct(len(m_df), len(g_df), 2), 2),
            }])

        col = "subregion" if key == "Subregion" else "nom_mun_o"
        if col not in m_df.columns:
            return pd.DataFrame()

        filas = []
        for territorio in sorted(m_df[col].dropna().unique()):
            n_m = int((m_df[col] == territorio).sum())
            n_c = int((c_df[col] == territorio).sum()) if col in c_df.columns else 0
            n_g = int((g_df[col] == territorio).sum()) if col in g_df.columns else 0
            filas.append({
                "Territorio": territorio,
                "Muertes": n_m,
                "Casos (210+220)": n_c,
                "Casos graves (220)": n_g,
                "Letalidad (%)": round(_pct(n_m, n_c, 4), 4),
                "Letalidad grave (%)": round(_pct(n_m, n_g, 2), 2),
            })

        if not filas:
            return pd.DataFrame()

        df = pd.DataFrame(filas).sort_values("Muertes", ascending=False)
        # Fila de total al final
        total_row = pd.DataFrame([{
            "Territorio": "TOTAL",
            "Muertes": len(m_df),
            "Casos (210+220)": len(c_df),
            "Casos graves (220)": len(g_df),
            "Letalidad (%)": round(_pct(len(m_df), len(c_df), 4), 4),
            "Letalidad grave (%)": round(_pct(len(m_df), len(g_df), 2), 2),
        }])
        return pd.concat([df, total_row], ignore_index=True)

    tabla = _calcular(nivel, muertes, casos, graves)
    if tabla.empty:
        st.caption(f"Sin datos de {nivel.lower()} disponibles.")
        return

    st.dataframe(tabla, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# 5.7  Tasas / indicadores por subregion (con selector)
# ---------------------------------------------------------------------------

def _mostrar_tasas_subregion(
    muertes: pd.DataFrame, casos: pd.DataFrame, graves: pd.DataFrame
) -> None:
    st.subheader(":material/bar_chart: Indicadores por subregion")

    col_sub = "subregion"
    if col_sub not in muertes.columns or col_sub not in casos.columns:
        st.caption("Sin datos de subregion (se deriva del mapeo DIVIPOLA en los filtros).")
        return

    indicador = st.segmented_control(
        "Indicador",
        ["Muertes (conteo)", "Letalidad (%)", "Letalidad grave (%)"],
        default="Letalidad (%)",
        required=True,
        key="mort_indicador_sub",
    )

    # Construir DataFrame por subregion
    subregiones = sorted(
        set(muertes[col_sub].dropna()) | set(casos[col_sub].dropna())
    )
    filas = []
    for sub in subregiones:
        n_m = int((muertes[col_sub] == sub).sum())
        n_c = int((casos[col_sub] == sub).sum())
        n_g = int((graves[col_sub] == sub).sum()) if col_sub in graves.columns else 0
        filas.append({"subregion": sub, "muertes": n_m, "casos": n_c, "graves": n_g})

    df = pd.DataFrame(filas)
    if df.empty:
        st.caption("Sin datos.")
        return

    # Referencia departamental
    ref_m   = len(muertes)
    ref_c   = len(casos)
    ref_g   = len(graves)

    if indicador == "Muertes (conteo)":
        df["valor"] = df["muertes"]
        ref_val = ref_m
        etiqueta_eje = "Muertes"
        formato = ",.0f"
    elif indicador == "Letalidad (%)":
        df["valor"] = df.apply(lambda r: _pct(r["muertes"], r["casos"], 4), axis=1)
        ref_val = _pct(ref_m, ref_c, 4)
        etiqueta_eje = "Letalidad (%)"
        formato = ".4f"
    else:
        df["valor"] = df.apply(lambda r: _pct(r["muertes"], r["graves"], 2), axis=1)
        ref_val = _pct(ref_m, ref_g, 2)
        etiqueta_eje = "Letalidad grave (%)"
        formato = ".2f"

    df = df.sort_values("valor")
    df["etiqueta"] = df["valor"].apply(lambda v: f"{v:{formato}}")

    fig = px.bar(
        df,
        x="valor",
        y="subregion",
        text="etiqueta",
        orientation="h",
        labels={"valor": etiqueta_eje, "subregion": ""},
    )
    # Linea de referencia departamental
    fig.add_vline(
        x=ref_val,
        line_dash="dot",
        line_color=NARANJA_INSTITUCIONAL,
        annotation_text=f"Dpto: {ref_val:{formato}}",
        annotation_position="top right",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT)
    st.plotly_chart(fig, width="stretch")

    if indicador == "Letalidad (%)" and ref_val > META_LETALIDAD:
        st.caption(
            f":material/warning: Letalidad departamental {ref_val:.4f}% "
            f"supera la meta nacional de {META_LETALIDAD}%."
        )


# ---------------------------------------------------------------------------
# 5.8  Causas de muerte CIE-10
# ---------------------------------------------------------------------------

def _mostrar_cie10(muertes: pd.DataFrame) -> None:
    st.subheader(":material/medical_information: Causas de muerte asociadas (CIE-10)")

    col_cod  = "cbmte"
    col_nom  = "nom_cbmte"

    if col_nom not in muertes.columns and col_cod not in muertes.columns:
        st.caption("Sin datos de causas CIE-10.")
        return

    if col_nom in muertes.columns:
        conteo = muertes[col_nom].dropna().value_counts().head(_TOP_N)
    else:
        conteo = muertes[col_cod].dropna().value_counts().head(_TOP_N)

    if conteo.empty:
        st.caption("Sin datos.")
        return

    total = conteo.sum()
    df = conteo.reset_index()
    df.columns = ["causa", "n"]
    df["causa_short"] = df["causa"].apply(lambda s: s[:55] + "…" if len(s) > 55 else s)
    df["etiqueta"] = df["n"].apply(lambda v: f"{v:,}  ({v/total*100:.1f}%)")

    fig = px.bar(
        df,
        x="n",
        y="causa_short",
        text="etiqueta",
        orientation="h",
        labels={"n": "Muertes", "causa_short": ""},
        hover_data={"causa": True, "causa_short": False, "n": True, "etiqueta": False},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(**_LAYOUT, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")
