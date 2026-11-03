"""Pestana de Morbilidad: carga de enfermedad por tipo, clasificacion,
hospitalizacion y notificacion.

Estructura inspirada en la morbilidad de dengue: KPIs, Sankey (flujo
clasificacion), fuente de notificacion, evolucion semanal por tipo,
hospitalizacion temporal y territorial, clasificacion final.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL
from core.dashboard_base.filtros import CLAVE_FILTROS
from core.geografia import obtener_geojson_municipios_magdalena
from pathologies.tuberculosis.indicators import calcular_indicadores

COD_PULMONAR = 820
COD_EXTRAPULMONAR = 810
COD_RESISTENTE = 825

_TIP_CAS_MAP = {
    "1": "Sospechoso",
    "2": "Probable",
    "3": "Conf. laboratorio",
    "4": "Conf. clínica",
    "5": "Conf. nexo epidemiológico",
}

_ESTADO_FINAL_MAP = {
    "2": "Probable",
    "3": "Conf. laboratorio",
    "4": "Conf. clínica",
    "5": "Conf. nexo epidemiológico",
    "6": "Descartado",
    "7": "Otro",
    "0": "Sin ajuste",
}

_FUENTE_MAP = {
    1: "Rutinaria",
    2: "Búsqueda activa institucional",
    3: "Vigilancia intensificada",
    4: "Búsqueda activa comunitaria",
    5: "Investigación",
}

_TIPO_CASO_OPTS = {
    "Ambos": [COD_PULMONAR, COD_EXTRAPULMONAR],
    "Pulmonar (820)": [COD_PULMONAR],
    "Extrapulmonar (810)": [COD_EXTRAPULMONAR],
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


def _casos_total(datos: pd.DataFrame) -> pd.DataFrame:
    codigos = set(datos["cod_eve"].unique())
    if codigos == {COD_RESISTENTE}:
        return datos
    return datos[datos["cod_eve"].isin({COD_PULMONAR, COD_EXTRAPULMONAR})]


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def mostrar_morbilidad(datos: pd.DataFrame) -> None:
    if datos.empty or "cod_eve" not in datos.columns:
        st.info("No hay datos de tuberculosis cargados. Sube archivos SIVIGILA en la pestaña de Gestión.", icon=":material/info:")
        return

    casos = _casos_total(datos)

    if casos.empty:
        st.info("No hay casos de tuberculosis para los filtros actuales.", icon=":material/info:")
        return

    filtros_actuales = st.session_state.get(CLAVE_FILTROS, {})
    resultado_indicadores = calcular_indicadores(datos, filtros_actuales)

    anios = sorted(int(a) for a in casos["ano"].dropna().unique())
    if anios:
        periodo = str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}"
        st.caption(
            f":material/calendar_today: Indicadores del período filtrado ({periodo}). "
            "La incidencia es una tasa anual por 100.000 habitantes."
        )

    _mostrar_kpis(casos, resultado_indicadores["incidencia"])
    st.space("small")

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

    with st.container(border=True):
        _mostrar_evolucion_semanal(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_hospitalizacion_semanal(casos)

    st.space("small")

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

def _mostrar_kpis(casos: pd.DataFrame, incidencia: float | None) -> None:
    total = len(casos)
    pulmonar = int((casos["cod_eve"] == COD_PULMONAR).sum())
    extrapulmonar = int((casos["cod_eve"] == COD_EXTRAPULMONAR).sum())

    hosp = 0
    if "pac_hos" in casos.columns:
        hosp = int((casos["pac_hos"] == 1).sum())

    incidencia_txt = f"{incidencia:,.1f}" if incidencia is not None else "No disponible"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Casos totales", f"{total:,}", border=True)
    with c2:
        st.metric(
            "Incidencia",
            incidencia_txt,
            help="Casos (810+820) / población x 100.000. No disponible si el filtro está a nivel municipio o falta población DANE.",
            border=True,
        )
    with c3:
        st.metric(
            "Hospitalizados",
            f"{hosp:,}",
            delta=_pct(hosp, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )
    with c4:
        st.metric(
            "Pulmonar (820)",
            f"{pulmonar:,}",
            delta=_pct(pulmonar, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )
    with c5:
        st.metric(
            "Extrapulmonar (810)",
            f"{extrapulmonar:,}",
            delta=_pct(extrapulmonar, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )


# ---------------------------------------------------------------------------
# Tipo de caso (dona)
# ---------------------------------------------------------------------------

def _mostrar_tipo_caso(casos: pd.DataFrame) -> None:
    st.subheader(":material/pie_chart: Tipo de caso")

    conteo = casos["cod_eve"].value_counts()
    labels = {COD_PULMONAR: "Pulmonar (820)", COD_EXTRAPULMONAR: "Extrapulmonar (810)"}
    df = pd.DataFrame({
        "tipo": [labels.get(k, str(k)) for k in conteo.index],
        "casos": conteo.values,
    })

    fig = px.pie(
        df, names="tipo", values="casos", hole=0.55,
        color_discrete_sequence=[AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL],
    )
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
# Flujo clasificacion inicial → final (Sankey)
# ---------------------------------------------------------------------------

def _mostrar_sankey_clasificacion(casos: pd.DataFrame) -> None:
    st.subheader(":material/account_tree: Gráfico de Sankey")

    cols_req = {"tip_cas", "estado_final_de_caso"}
    if not cols_req.issubset(casos.columns):
        st.caption("Sin datos de clasificación.")
        return

    df = casos[["tip_cas", "estado_final_de_caso"]].dropna().copy()
    df["inicial"] = df["tip_cas"].astype(str).map(_TIP_CAS_MAP).fillna("Otro (inicial)")
    df["final"] = df["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro (final)")

    if df.empty:
        st.caption("Sin datos de flujo de clasificación.")
        return

    conteo_inicial = df.groupby("inicial").size().reset_index(name="n")

    transiciones = df.groupby(["inicial", "final"]).size().reset_index(name="n")
    transiciones = transiciones[transiciones["inicial"] != transiciones["final"]]

    _PALETA_ESTADOS = {
        "Probable":                    "#7c3aed",
        "Conf. laboratorio":           "#1b3a6b",
        "Conf. nexo epidemiológico":   "#e8852c",
        "Conf. clínica":               "#0891b2",
        "Sospechoso":                  "#c026d3",
        "Descartado":                  "#475569",
        "Sin ajuste":                  "#a8a29e",
        "Otro (inicial)":              "#795548",
        "Otro (final)":                "#795548",
        "Otro":                        "#795548",
    }

    NODO_TOTAL = "Casos totales"
    nodos_iniciales = (
        conteo_inicial.sort_values("n", ascending=False)["inicial"].tolist()
    )

    posicion_inicial = {nombre: i for i, nombre in enumerate(nodos_iniciales)}
    altura_promedio_final = {}
    for nombre_final, grupo in transiciones.groupby("final"):
        peso = grupo["n"].sum()
        suma_ponderada = sum(
            posicion_inicial[fila["inicial"]] * fila["n"] for _, fila in grupo.iterrows()
        )
        altura_promedio_final[nombre_final] = suma_ponderada / peso
    nodos_finales = sorted(altura_promedio_final, key=altura_promedio_final.get)

    etiquetas = [NODO_TOTAL] + nodos_iniciales + nodos_finales
    idx_inicial = {nombre: 1 + i for i, nombre in enumerate(nodos_iniciales)}
    idx_final = {
        nombre: 1 + len(nodos_iniciales) + i for i, nombre in enumerate(nodos_finales)
    }

    total_casos = int(conteo_inicial["n"].sum())

    def _centros_verticales(valores_columna: list[int]) -> list[float]:
        separacion = 0.04
        margen = 0.02
        cantidad = len(valores_columna)
        util = 1.0 - 2 * margen - separacion * max(cantidad - 1, 0)
        altos = [util * valor / total_casos for valor in valores_columna]
        alto_pila = sum(altos) + separacion * max(cantidad - 1, 0)
        cursor = max((1.0 - alto_pila) / 2, margen)
        centros = []
        for alto in altos:
            centros.append(min(max(cursor + alto / 2, 0.01), 0.99))
            cursor += alto + separacion
        return centros

    casos_por_inicial = conteo_inicial.set_index("inicial")["n"]
    casos_por_final = transiciones.groupby("final")["n"].sum()

    posiciones_x = (
        [0.01] + [0.5] * len(nodos_iniciales) + [0.99] * len(nodos_finales)
    )
    posiciones_y = (
        [0.5]
        + _centros_verticales([int(casos_por_inicial[n]) for n in nodos_iniciales])
        + _centros_verticales([int(casos_por_final[n]) for n in nodos_finales])
    )

    colores_nodos = (
        [AZUL_INSTITUCIONAL]
        + [_PALETA_ESTADOS.get(n, "#6b7280") for n in nodos_iniciales]
        + [_PALETA_ESTADOS.get(n, "#6b7280") for n in nodos_finales]
    )

    fuentes, destinos, valores, colores_links = [], [], [], []

    for _, fila in conteo_inicial.iterrows():
        fuentes.append(0)
        destinos.append(idx_inicial[fila["inicial"]])
        valores.append(int(fila["n"]))
        colores_links.append(_hex_rgba(_PALETA_ESTADOS.get(fila["inicial"], "#6b7280"), 0.45))

    for _, fila in transiciones.iterrows():
        fuentes.append(idx_inicial[fila["inicial"]])
        destinos.append(idx_final[fila["final"]])
        valores.append(int(fila["n"]))
        colores_links.append(_hex_rgba(_PALETA_ESTADOS.get(fila["inicial"], "#6b7280"), 0.45))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=etiquetas,
            x=posiciones_x,
            y=posiciones_y,
            color=colores_nodos,
            pad=24,
            thickness=22,
            line=dict(color="white", width=0.8),
        ),
        link=dict(
            source=fuentes,
            target=destinos,
            value=valores,
            color=colores_links,
            hovertemplate="%{source.label} → %{target.label}: %{value:,} casos<extra></extra>",
        ),
        textfont=dict(size=12, color="#1a1a1a", family="sans-serif"),
    ))

    encabezados = [
        (0.01, "left", "Total"),
        (0.5, "center", "Clasificación inicial"),
        (0.99, "right", "Clasificación final"),
    ]
    for pos_x, ancla, texto in encabezados:
        fig.add_annotation(
            x=pos_x, y=1.05, xref="paper", yref="paper",
            text=f"<b>{texto}</b>", showarrow=False,
            xanchor=ancla, font=dict(size=12, color="#374151"),
        )

    estados_en_leyenda = set()
    for nombre in nodos_iniciales + nodos_finales:
        canonico = nombre.replace(" (inicial)", "").replace(" (final)", "")
        if canonico in estados_en_leyenda:
            continue
        estados_en_leyenda.add(canonico)
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, symbol="square", color=_PALETA_ESTADOS.get(nombre, "#6b7280")),
            name=canonico,
            hoverinfo="skip",
        ))

    fig.update_layout(
        height=540,
        margin=dict(l=10, r=10, t=100, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.14,
            xanchor="center", x=0.5, font=dict(size=10),
        ),
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Fuente de notificacion
# ---------------------------------------------------------------------------

def _mostrar_fuente(casos: pd.DataFrame) -> None:
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
        df, x="casos", y="fuente", text="etiqueta",
        orientation="h",
        labels={"casos": "Casos", "fuente": ""},
    )
    fig.update_traces(marker_color=AZUL_INSTITUCIONAL, textposition="outside")
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=60, t=40, b=0),
        yaxis={"categoryorder": "total ascending"},
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Evolucion semanal por tipo de caso
# ---------------------------------------------------------------------------

def _mostrar_evolucion_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/show_chart: Casos semanales por tipo")

    if "semana" not in casos.columns:
        return

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        return

    col_sel, col_nota = st.columns([1, 3], vertical_alignment="center")
    with col_sel:
        anio = st.selectbox("Año de análisis", anios, key="morbilidad_anio_semanal")
    with col_nota:
        st.caption(":material/info: Selector propio — ignora el filtro temporal global.")

    subset = casos[casos["ano"] == anio].copy()
    subset["tipo"] = subset["cod_eve"].map({
        COD_PULMONAR: "Pulmonar (820)",
        COD_EXTRAPULMONAR: "Extrapulmonar (810)",
    })
    semanal = subset.groupby(["semana", "tipo"]).size().reset_index(name="casos")

    # % pulmonar por semana
    total_sem = subset.groupby("semana").size().rename("total")
    pulm_sem = subset[subset["cod_eve"] == COD_PULMONAR].groupby("semana").size().rename("pulmonar")
    pct_df = pd.concat([total_sem, pulm_sem], axis=1).fillna(0).reset_index()
    pct_df["pct_pulmonar"] = pct_df["pulmonar"] / pct_df["total"] * 100

    fig = px.bar(
        semanal, x="semana", y="casos", color="tipo",
        barmode="group",
        labels={"semana": "Semana epidemiológica", "casos": "Casos", "tipo": "Tipo"},
        color_discrete_map={
            "Pulmonar (820)": AZUL_INSTITUCIONAL,
            "Extrapulmonar (810)": NARANJA_INSTITUCIONAL,
        },
    )
    fig.add_trace(go.Scatter(
        x=pct_df["semana"], y=pct_df["pct_pulmonar"],
        name="% Pulmonar",
        mode="lines+markers",
        marker=dict(size=5),
        line=dict(dash="dot", width=1.5, color="#555555"),
        yaxis="y2",
        hovertemplate="Semana %{x} · %{y:.1f}% pulmonar<extra></extra>",
    ))
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", title="% Pulmonar", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Hospitalizacion por semana
# ---------------------------------------------------------------------------

def _mostrar_hospitalizacion_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/local_hospital: Hospitalización por semana")

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
        COD_PULMONAR: "Pulmonar",
        COD_EXTRAPULMONAR: "Extrapulmonar",
    })
    subset["categoria"] = subset["tipo"] + " — " + subset["estado_hosp"]

    semanal = subset.groupby(["semana", "categoria"]).size().reset_index(name="casos")

    fig = px.bar(
        semanal, x="semana", y="casos", color="categoria",
        barmode="group",
        labels={"semana": "Semana", "casos": "Casos", "categoria": ""},
        color_discrete_map={
            "Pulmonar — Hospitalizado": AZUL_INSTITUCIONAL,
            "Pulmonar — No hospitalizado": "#8ba5c5",
            "Extrapulmonar — Hospitalizado": NARANJA_INSTITUCIONAL,
            "Extrapulmonar — No hospitalizado": "#d4a87a",
        },
    )
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Hospitalizacion territorial
# ---------------------------------------------------------------------------

def _mostrar_hospitalizacion_territorial(casos: pd.DataFrame) -> None:
    st.subheader(":material/map: Hospitalización por territorio")

    if "pac_hos" not in casos.columns:
        st.caption("Sin datos de hospitalización.")
        return

    tipo_sel = st.segmented_control(
        "Tipo de caso",
        list(_TIPO_CASO_OPTS.keys()),
        default="Ambos",
        required=True,
        key="morbilidad_tipo_hosp",
    )
    codigos = _TIPO_CASO_OPTS.get(tipo_sel, [COD_PULMONAR, COD_EXTRAPULMONAR])
    subset = casos[(casos["cod_eve"].isin(codigos)) & (casos["pac_hos"] == 1)]

    if subset.empty:
        st.caption("Sin hospitalizados para ese filtro.")
        return

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
        "Conteo de hospitalizados por municipio. Las tasas a nivel municipal no son "
        "confiables (denominador poblacional no refleja movilidad de pacientes)."
    )


# ---------------------------------------------------------------------------
# Clasificacion final (dona)
# ---------------------------------------------------------------------------

def _mostrar_clasificacion_final_dona(casos: pd.DataFrame) -> None:
    st.subheader(":material/fact_check: Clasificación final")

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

    _COLORES_ESTADO_DONA = [
        AZUL_INSTITUCIONAL,
        NARANJA_INSTITUCIONAL,
        "#6f5499",
        "#374151",
    ]
    fig = px.pie(
        names=conteo.index,
        values=conteo.values,
        hole=0.55,
        color_discrete_sequence=_COLORES_ESTADO_DONA,
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
# Clasificacion final por semana
# ---------------------------------------------------------------------------

def _mostrar_clasificacion_final_semanal(casos: pd.DataFrame) -> None:
    st.subheader(":material/stacked_bar_chart: Clasificación final por semana")

    if "semana" not in casos.columns or "estado_final_de_caso" not in casos.columns:
        st.caption("Sin datos.")
        return

    anios = sorted(casos["ano"].dropna().unique().tolist(), reverse=True)
    if not anios:
        return

    anio = st.selectbox(
        "Año", anios,
        key="morbilidad_clas_final_anio",
        label_visibility="collapsed",
    )
    subset = casos[casos["ano"] == anio].copy()
    subset["clasificacion"] = (
        subset["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro")
    )

    semanal = subset.groupby(["semana", "clasificacion"]).size().reset_index(name="casos")

    fig = px.bar(
        semanal, x="semana", y="casos", color="clasificacion",
        barmode="stack",
        labels={"semana": "Semana epidemiológica", "casos": "Casos", "clasificacion": "Clasificación"},
    )
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        height=380,
        **_LAYOUT,
    )
    st.plotly_chart(fig, width="stretch")
