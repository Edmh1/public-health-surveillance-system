"""Pestana 4 Morbilidad: notificacion, clasificacion y hospitalizacion.

Historia que cuenta:
  1. KPIs: casos totales, hospitalizados, graves, hospitalizados graves
  2. Panorama general: tipo de caso / flujo clasificacion (Sankey)
  3. Incidencia por subregion (4.10) / fuente
  4. Evolucion semanal: casos por tipo + % graves (selector anio local)
  5. Clasificacion final: dona + distribucion semanal / hospitalizacion territorial
  6. Hospitalizacion por semana (selector tipo de caso)
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    LEYENDA_SUPERIOR,
    NARANJA_INSTITUCIONAL,
    eje_semanal,
    rango_con_margen,
)
from core.dashboard_base.filtros import CLAVE_FILTROS
from pathologies.dengue.geografia import obtener_mapeo_subregion
from pathologies.dengue.indicators import calcular_indicadores
from pathologies.dengue.poblacion import calcular_tasa_por_municipio, calcular_tasa_por_subregion

CODIGOS_CASOS = {210, 220}
COD_DENGUE       = 210
COD_DENGUE_GRAVE = 220

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

    # Incidencia (tasa poblacional) vive aca ademas de en Situacion: en Situacion
    # es de un solo anio; aca sigue el filtro global, asi que se puede ver por
    # rangos de anios. Respeta la regla de "no disponible" (municipio / sin DANE)
    # porque sale del mismo calcular_indicadores.
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

    # Panorama: tipo de caso | Sankey (el Sankey ocupa tambien el ancho que
    # antes tenia Fuente)
    c1, c2 = st.columns([1, 2.7])
    with c1:
        with st.container(border=True, height="stretch"):
            _mostrar_tipo_caso(casos)
    with c2:
        with st.container(border=True, height="stretch"):
            _mostrar_sankey_clasificacion(casos)

    st.space("small")

    # Incidencia por subregion (4.10) | Fuente (50/50)
    c_inc, c_fuente = st.columns([1, 1])
    with c_inc:
        with st.container(border=True, height="stretch"):
            _mostrar_incidencia_subregion(casos)
    with c_fuente:
        with st.container(border=True, height="stretch"):
            _mostrar_fuente(casos)

    st.space("small")

    # Evolucion semanal (selector anio local) — FULL WIDTH
    with st.container(border=True):
        _mostrar_evolucion_semanal(casos)

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

    st.space("small")

    # Hospitalizacion por semana — FULL WIDTH
    with st.container(border=True):
        _mostrar_hospitalizacion_semanal(casos)

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame, incidencia: float | None) -> None:
    total = len(casos)
    graves = int((casos["cod_eve"] == COD_DENGUE_GRAVE).sum())

    hosp = 0
    hosp_graves = 0
    if "pac_hos" in casos.columns:
        hosp = int((casos["pac_hos"] == 1).sum())
        hosp_graves = int(
            ((casos["cod_eve"] == COD_DENGUE_GRAVE) & (casos["pac_hos"] == 1)).sum()
        )

    incidencia_txt = f"{incidencia:,.1f}" if incidencia is not None else "No disponible"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Casos totales", f"{total:,}", border=True)
    with c2:
        st.metric(
            "Incidencia",
            incidencia_txt,
            help=(
                "Casos (210+220) / población en riesgo x 100.000. No disponible si falta "
                "población DANE, o el sistema todavía no tiene los 6 años de histórico "
                "que pide el lineamiento MSPS/INS para calcular la estratificación de "
                "riesgo."
            ),
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
            "Dengue grave (220)",
            f"{graves:,}",
            delta=_pct(graves, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )
    with c5:
        st.metric(
            "Hospitalizados graves",
            f"{hosp_graves:,}",
            delta=_pct(hosp_graves, graves),
            delta_color="off",
            delta_arrow="off",
            delta_description="de los graves",
            help="Hospitalizados de dengue grave sobre el total de casos graves",
            border=True,
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

    fig = px.pie(
        df, names="tipo", values="casos", hole=0.55,
        color_discrete_sequence=[AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL],
    )
    fig.update_traces(
        texttemplate="%{value:,} (%{percent})",
        textposition="outside",
    )
    # Altura pareja con el Sankey vecino: la tarjeta se estira con la fila y con
    # la altura anterior la dona quedaba pegada arriba con un vacio debajo.
    fig.update_layout(
        showlegend=True,
        legend=LEYENDA_SUPERIOR,
        height=520,
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
    st.subheader(":material/account_tree: Gráfico de Sankey")

    cols_req = {"tip_cas", "estado_final_de_caso"}
    if not cols_req.issubset(casos.columns):
        st.caption("Sin datos de clasificación.")
        return

    df = casos[["tip_cas", "estado_final_de_caso"]].dropna().copy()
    df["inicial"] = df["tip_cas"].astype(str).map(_TIP_CAS_MAP).fillna("Otro (inicial)")
    df["final"]   = df["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro (final)")

    if df.empty:
        st.caption("Sin datos de flujo de clasificación.")
        return

    conteo_inicial = df.groupby("inicial").size().reset_index(name="n")

    # Solo interesan los cambios de clasificacion: un caso que empieza y termina
    # en el mismo estado no aporta flujo que leer, y ademas dibujaria un lazo
    # circular sobre su propio nodo.
    transiciones = df.groupby(["inicial", "final"]).size().reset_index(name="n")
    transiciones = transiciones[transiciones["inicial"] != transiciones["final"]]

    # Colores por estado (no por posicion izq/der): mismo color para un estado
    # independientemente de si aparece como clasificacion inicial o final.
    # Paleta viva y distinguible; verde/amarillo/rojo quedan reservados para el
    # canal endemico segun DESIGN.md.
    _PALETA_ESTADOS = {
        "Probable":                    "#7c3aed",
        "Conf. laboratorio":           "#2563eb",
        "Conf. nexo epidemiológico":   "#f97316",
        "Conf. clínica":               "#0891b2",
        "Sospechoso":                  "#c026d3",
        "Descartado":                  "#475569",
        "Sin ajuste":                  "#a8a29e",
        "Otro (inicial)":              "#795548",
        "Otro (final)":                "#795548",
        "Otro":                        "#795548",
    }
    # Tres columnas de nodos: casos totales | clasificacion inicial | clasificacion
    # final. Inicial y final llevan nodos SEPARADOS aunque compartan etiqueta: si
    # "Probable" fuera un solo nodo, la transicion sin cambio se dibujaria como un
    # lazo circular sobre si misma.
    NODO_TOTAL = "Casos totales"
    nodos_iniciales = (
        conteo_inicial.sort_values("n", ascending=False)["inicial"].tolist()
    )

    # Orden vertical de la columna final: cada estado se coloca a la altura
    # promedio (ponderada por casos) de las clasificaciones iniciales que lo
    # alimentan, para minimizar el cruce de enlaces.
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

    # Posicion fija por columna: sin la x, un nodo inicial sin casos que cambien
    # de clasificacion (sin flujo de salida) se iria a la columna derecha por el
    # acomodo automatico de Plotly. La y fija el orden vertical calculado arriba,
    # apilando cada columna de arriba hacia abajo con altura proporcional.
    total_casos = int(conteo_inicial["n"].sum())

    def _centros_verticales(valores_columna: list[int]) -> list[float]:
        # La pila de cada columna se centra verticalmente: una columna con poco
        # flujo (la final solo lleva los casos que cambiaron) queda alineada al
        # medio del diagrama en vez de amontonada arriba.
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

    # Flujos coloreados por la clasificacion inicial con transparencia:
    # el ojo puede seguir "que le paso a cada clasificacion inicial" por color.
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

    # Encabezados de etapa sobre cada columna, para leer el diagrama sin adivinar.
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

    # Leyenda de colores por estado. El trazo Sankey no genera leyenda propia,
    # asi que se agregan puntos invisibles (sin datos) solo por su entrada de
    # leyenda; los ejes cartesianos que introducen se ocultan.
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

    # Cada fuente con su color y el nombre en la leyenda: los nombres largos
    # ("Busqueda activa institucional") como etiquetas del eje se comian el
    # ancho de la grafica en esta tarjeta angosta.
    colores_fuente = {
        "Rutinaria":                     AZUL_INSTITUCIONAL,
        "Busqueda activa institucional": "#f97316",
        "Vigilancia intensificada":      "#7c3aed",
        "Busqueda activa comunitaria":   "#0891b2",
        "Investigacion":                 "#c026d3",
    }
    fig = px.bar(
        df,
        x="casos",
        y="fuente",
        color="fuente",
        text="etiqueta",
        orientation="h",
        labels={"casos": "Casos", "fuente": ""},
        color_discrete_map=colores_fuente,
    )
    fig.update_traces(textposition="outside")
    # Leyenda anclada a la izquierda: a la derecha se solapa con la barra de
    # herramientas de Plotly.
    fig.update_layout(
        height=480,
        margin=dict(l=0, r=60, t=70, b=0),
        xaxis={"range": rango_con_margen(df["casos"].max())},
        yaxis={"categoryorder": "total ascending", "showticklabels": False},
        legend={**LEYENDA_SUPERIOR, "xanchor": "left", "x": 0, "font": {"size": 10}},
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
        anio = st.selectbox("Año de análisis", anios, key="morbilidad_anio_semanal")
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
    if semanal.empty:
        st.caption(f"Sin datos para {anio}.")
        return

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
        labels={"semana": "Semana epidemiológica", "casos": "Casos", "tipo": "Tipo"},
        color_discrete_map={
            "Dengue (210)": AZUL_INSTITUCIONAL,
            "Dengue grave (220)": NARANJA_INSTITUCIONAL,
        },
    )
    # Linea de % graves sobre eje secundario. Hover propio: "Semana X · Y%" en
    # vez de la coordenada (x, y) cruda que muestra Plotly por defecto.
    fig.add_trace(go.Scatter(
        x=pct_df["semana"],
        y=pct_df["pct_grave"],
        name="% Graves",
        mode="lines+markers",
        marker=dict(size=5),
        line=dict(dash="dot", width=1.5, color="#555555"),
        yaxis="y2",
        hovertemplate="Semana %{x} · %{y:.1f}% graves<extra></extra>",
    ))
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", title="% Graves", showgrid=False),
        legend=LEYENDA_SUPERIOR,
        **_LAYOUT,
    )
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# 4.5  Hospitalizacion por semana y tipo de caso
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
        COD_DENGUE: "Dengue",
        COD_DENGUE_GRAVE: "Grave",
    })
    subset["categoria"] = subset["tipo"] + " — " + subset["estado_hosp"]

    semanal = subset.groupby(["semana", "categoria"]).size().reset_index(name="casos")
    if semanal.empty:
        st.caption(f"Sin datos para {anio}.")
        return

    # Colores explícitos: Dengue=azul institucional, Grave=naranja;
    # Hospitalizado=color sólido, No hospitalizado=versión más suave.
    # Sin esto, la 3.ª categoria recibiría el azul cielo del tema.
    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="categoria",
        barmode="group",
        labels={"semana": "Semana", "casos": "Casos", "categoria": ""},
        color_discrete_map={
            "Dengue — Hospitalizado":     AZUL_INSTITUCIONAL,
            "Dengue — No hospitalizado":  "#8ba5c5",
            "Grave — Hospitalizado":      NARANJA_INSTITUCIONAL,
            "Grave — No hospitalizado":   "#d4a87a",
        },
    )
    fig.update_layout(
        legend=dict(**LEYENDA_SUPERIOR, font=dict(size=10)),
        **_LAYOUT,
    )
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# 4.6 + 4.7  Hospitalizacion territorial (subregion y municipio, ambas en tasa)
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
    codigos = _TIPO_CASO_OPTS.get(tipo_sel, list(CODIGOS_CASOS))
    subset = casos[(casos["cod_eve"].isin(codigos)) & (casos["pac_hos"] == 1)]

    if subset.empty:
        st.caption("Sin hospitalizados para ese filtro.")
        return

    anios_en_alcance = sorted(int(a) for a in casos["ano"].dropna().unique())

    # Subregion: TASA por 100.000 hab.
    if "subregion" in subset.columns:
        mapeo_subregion = obtener_mapeo_subregion()
        tasas = calcular_tasa_por_subregion(subset, anios_en_alcance, mapeo_subregion)

        sub = pd.DataFrame({"territorio": list(tasas.keys()), "tasa": list(tasas.values())})
        sub = sub.dropna(subset=["tasa"]).sort_values("tasa")
        if sub.empty:
            st.caption("Sin población DANE disponible para el período filtrado.")
        else:
            fig_sub = px.bar(
                sub, x="tasa", y="territorio", text="tasa",
                orientation="h",
                labels={"tasa": "Hospitalizados x100.000 hab.", "territorio": ""},
            )
            fig_sub.update_traces(
                textposition="outside",
                texttemplate="%{text:.1f}",
                name="Tasa x100.000 hab.",
                showlegend=True,
            )
            fig_sub.update_layout(
                title="Por subregión (tasa x100.000 hab.)",
                margin=dict(l=0, r=0, t=70, b=0),
                xaxis={"range": rango_con_margen(sub["tasa"].max())},
                legend=LEYENDA_SUPERIOR,
            )
            st.plotly_chart(fig_sub, width="stretch")

    # Municipio — top 15 por TASA x100.000 hab.
    if "nom_mun_o" in subset.columns and "cod_mun_completo" in subset.columns:
        municipios_con_casos = sorted(subset["cod_mun_completo"].dropna().unique().astype(int))
        tasas_municipio = calcular_tasa_por_municipio(subset, anios_en_alcance, municipios_con_casos)

        nombres_municipio = (
            subset.dropna(subset=["nom_mun_o"])
            .drop_duplicates(subset=["cod_mun_completo"])
            .set_index("cod_mun_completo")["nom_mun_o"]
        )

        mun = pd.DataFrame({
            "cod_mun_completo": list(tasas_municipio.keys()),
            "tasa": list(tasas_municipio.values()),
        })
        mun["municipio"] = mun["cod_mun_completo"].map(nombres_municipio)
        mun = mun.dropna(subset=["tasa", "municipio"]).sort_values("tasa", ascending=False).head(15)
        mun = mun.sort_values("tasa")

        if mun.empty:
            st.caption("Sin población DANE disponible para el período filtrado.")
        else:
            fig_mun = px.bar(
                mun, x="tasa", y="municipio", text="tasa",
                orientation="h",
                labels={"tasa": "Hospitalizados x100.000 hab.", "municipio": ""},
            )
            fig_mun.update_traces(
                textposition="outside",
                texttemplate="%{text:.1f}",
                name="Tasa x100.000 hab.",
                showlegend=True,
            )
            fig_mun.update_layout(
                title="Por municipio — Top 15 (tasa x100.000 hab.)",
                margin=dict(l=0, r=0, t=70, b=0),
                xaxis={"range": rango_con_margen(mun["tasa"].max())},
                legend=LEYENDA_SUPERIOR,
            )
            st.plotly_chart(fig_mun, width="stretch")

    st.caption("Tasa = hospitalizados / población en riesgo x 100.000, en ambos niveles.")

# ---------------------------------------------------------------------------
# 4.10  Incidencia por subregion
# ---------------------------------------------------------------------------

def _mostrar_incidencia_subregion(casos: pd.DataFrame) -> None:
    st.subheader(":material/bar_chart: Incidencia por subregión")

    if "subregion" not in casos.columns:
        st.caption("Sin datos de subregión.")
        return

    anios_en_alcance = sorted(int(a) for a in casos["ano"].dropna().unique())
    mapeo_subregion = obtener_mapeo_subregion()
    tasas = calcular_tasa_por_subregion(casos, anios_en_alcance, mapeo_subregion)

    df = pd.DataFrame({"subregion": list(tasas.keys()), "incidencia": list(tasas.values())})
    df = df.dropna(subset=["incidencia"]).sort_values("incidencia")
    if df.empty:
        st.caption("Sin población DANE disponible para el período filtrado.")
        return

    fig = px.bar(
        df, x="incidencia", y="subregion", text="incidencia",
        orientation="h",
        labels={"incidencia": "Incidencia x100.000 hab.", "subregion": ""},
    )
    fig.update_traces(
        textposition="outside",
        texttemplate="%{text:.1f}",
        name="Incidencia x100.000 hab.",
        showlegend=True,
    )
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["incidencia"].max())},
        legend=LEYENDA_SUPERIOR,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Incidencia = casos (210+220) / población en riesgo x 100.000, por subregión.")

# ---------------------------------------------------------------------------
# 4.8  Clasificacion final (dona)
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

    # Colores explícitos para evitar que el 3.ª slice reciba azul cielo.
    _COLORES_ESTADO_DONA = [
        AZUL_INSTITUCIONAL,   # Conf. laboratorio (el más frecuente → color primario)
        NARANJA_INSTITUCIONAL, # Conf. nexo
        "#7c3aed",             # Probable (mismo violeta del Sankey)
        "#374151",             # Descartado / Otro
    ]
    fig = px.pie(
        names=conteo.index,
        values=conteo.values,
        hole=0.55,
        color_discrete_sequence=_COLORES_ESTADO_DONA,
    )
    fig.update_traces(
        texttemplate="%{value:,} (%{percent})",
        textposition="outside",
    )
    fig.update_layout(
        showlegend=True,
        legend=LEYENDA_SUPERIOR,
        height=300,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# 4.9  Clasificacion final por semana
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
    if semanal.empty:
        st.caption(f"Sin datos para {anio}.")
        return

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="clasificacion",
        barmode="stack",
        labels={"semana": "Semana epidemiológica", "casos": "Casos", "clasificacion": "Clasificación"},
    )
    fig.update_layout(
        legend=dict(**LEYENDA_SUPERIOR, font=dict(size=10)),
        height=380,
        **_LAYOUT,
    )
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
    st.plotly_chart(fig, width="stretch")
