"""Pestana Pronostico: pronostico semanal de casos de dengue a nivel
departamental (Magdalena), hasta 4 semanas, con el modelo Prophet-AR sin clima
validado en el documento tecnico de modelado (ver dialogo de "Fundamentacion").

Serie DEPARTAMENTAL unica: esta pestana NO depende de los filtros globales de
subregion/municipio/anio/semana (el modelo se valido a escala departamental, sin
desagregacion territorial), por eso usa siempre el consolidado COMPLETO de la
sesion en vez del datos_filtrados que le llega por el contrato de pestana (mismo
principio que el canal endemico de Situacion, que usa toda la historia
disponible para su linea base en vez del recorte de un selector local).

Tasa (casos x100.000 hab.): es una tasa SEMANAL (casos de esa semana, no de un
anio), por eso el numero se ve chico comparado con la Incidencia anual de
Situacion; no son comparables entre si y no se etiquetan igual a proposito.
Usa poblacion TOTAL del Magdalena (los 30 municipios, sin excluir por
estratificacion de riesgo), NO la poblacion en riesgo que usan Incidencia/
Mortalidad y las demas tasas del dashboard. Motivo: el pronostico es una unica
serie departamental, no filtrable por territorio, y depender de la
estratificacion de riesgo (que necesita 6 anios de historico para calcularse)
acoplaria innecesariamente dos piezas independientes. Ver CLAUDE.md, seccion
de la pestana Pronostico.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, LEYENDA_SUPERIOR, NARANJA_INSTITUCIONAL
from core.dashboard_base.filtros import CLAVE_FILTROS
from pathologies.dengue.poblacion import obtener_poblacion_total_departamental
from pathologies.dengue.prediccion import (
    HORIZONTE_MAXIMO_SEMANAS,
    SEMANAS_MINIMAS_ENTRENAMIENTO,
    construir_serie_semanal_departamental,
    entrenar_modelo,
    pronosticar,
)

PATOLOGIA = "dengue"

_SEMANAS_HISTORIAL_VISIBLE_POR_DEFECTO = 12  # 3 meses: zoom inicial del grafico, el historico completo sigue disponible haciendo zoom-out

_METRICAS = ["Casos", "Tasa semanal (x100.000 hab.)"]

_MODO_EN_VIVO = "Pronóstico en vivo (hoy)"
_MODO_PERSONALIZADO = "Elegir otra semana..."

# Ejemplos historicos para presentaciones/validacion: el modelo entrena SOLO con
# datos hasta esa fecha (nunca ve lo que paso despues) y el grafico superpone lo
# que realmente ocurrio, para comparar. Nunca inventa ni fuerza un resultado: es
# el mismo modelo de produccion, corrido sobre un origen pasado real.
#
# Dos ejemplos A PROPOSITO (no uno solo), en direcciones distintas, para que no
# se vea como un caso aislado elegido a mano: una subida real (inicio del brote
# de octubre 2018, camino al pico de 177 casos/semana en diciembre) y un
# descenso real (tras ese mismo pico, enero 2019). Ademas esta _MODO_
# PERSONALIZADO (mas abajo), que deja probar CUALQUIER semana del historico,
# no solo estas dos: es lo que evita que el conjunto se sienta "maquillado",
# porque cualquiera puede pedir otra fecha y verificar por su cuenta.
_EJEMPLOS_HISTORICOS = {
    "Ejemplo histórico: inicio del brote de octubre 2018": pd.Timestamp("2018-10-28"),
    "Ejemplo histórico: descenso tras el pico de enero 2019": pd.Timestamp("2019-01-06"),
}
_SEMANAS_CONTEXTO_REAL_HISTORICO = 8  # se muestra mas alla del horizonte de 4 semanas, para ver hacia donde iba realmente


# Entrenar Prophet es lo caro (unos segundos); el resultado (un DataFrame chico
# de pronostico) es trivialmente serializable, asi que @st.cache_data alcanza
# y es consistente con el resto del proyecto (ver _calcular_canal_endemico_
# cacheado en situacion.py). No se necesita @st.cache_resource: el objeto
# Prophet en si nunca sale de esta funcion ni se reutiliza en otro lado.
@st.cache_data(show_spinner="Entrenando modelo de pronóstico (Prophet)...")
def _entrenar_y_pronosticar_cacheado(serie: pd.DataFrame, horizonte: int) -> pd.DataFrame | None:
    modelo = entrenar_modelo(serie)
    if modelo is None:
        return None
    return pronosticar(modelo, serie, horizonte_semanas=horizonte)


def _poblacion_por_anio(anios: list[int]) -> dict[int, float | None]:
    return {anio: obtener_poblacion_total_departamental([anio]) for anio in sorted(set(anios))}


def _agregar_tasa(df: pd.DataFrame, columnas_casos: list[str]) -> pd.DataFrame:
    """Agrega una columna '<col>_tasa' por cada columna de casos, dividiendo por
    la poblacion TOTAL del Magdalena del anio correspondiente a cada fila. None
    (no disponible) si falta poblacion para ese anio, nunca un numero inventado.
    """
    df = df.copy()
    poblacion = _poblacion_por_anio(df["ano"].tolist())
    for columna in columnas_casos:
        df[f"{columna}_tasa"] = df.apply(
            lambda fila, columna=columna: (
                fila[columna] / poblacion[fila["ano"]] * 100_000 if poblacion[fila["ano"]] else None
            ),
            axis=1,
        )
    return df


def mostrar_pronostico(_datos_filtrados: pd.DataFrame) -> None:
    """_datos_filtrados llega por el contrato uniforme de pestana (ver
    obtener_vistas_dengue), pero se ignora a proposito: esta pestana siempre usa
    el consolidado completo de la sesion, ver docstring del modulo.
    """
    datos_completos = modulo_datos.obtener_datos(PATOLOGIA)

    col_titulo, col_fundamentacion = st.columns([5, 1.6], vertical_alignment="center")
    with col_titulo:
        st.subheader(":material/query_stats: Pronóstico de casos de dengue")
    with col_fundamentacion:
        if st.button(
            "Fundamentación", icon=":material/school:", key="pronostico_fundamentacion", width="stretch"
        ):
            _dialogo_fundamentacion()

    st.caption(
        "Pronóstico a nivel departamental (todo el Magdalena). No depende de los filtros "
        "de la barra lateral: usa siempre el histórico completo, igual que el canal "
        "endémico de Situación."
    )
    _avisar_si_hay_filtros_geograficos_activos()

    serie = construir_serie_semanal_departamental(datos_completos)
    if len(serie) < SEMANAS_MINIMAS_ENTRENAMIENTO:
        st.warning(
            f"No es posible calcular el pronóstico: hacen falta al menos "
            f"{SEMANAS_MINIMAS_ENTRENAMIENTO // 52} años de histórico semanal continuo "
            f"para estimar la estacionalidad anual del modelo, y hay "
            f"{len(serie)} semanas ({len(serie) / 52:.1f} años) disponibles.",
            icon=":material/warning:",
        )
        return

    # selectbox, no segmented_control ni un boton por ejemplo: con varios
    # ejemplos historicos (y "elegir otra semana" es, en la practica, un
    # numero abierto de opciones) una fila de botones se ve saturada.
    modo = st.selectbox(
        "Modo",
        [_MODO_EN_VIVO] + list(_EJEMPLOS_HISTORICOS.keys()) + [_MODO_PERSONALIZADO],
        key="pronostico_modo",
        help=(
            "Los modos históricos entrenan el mismo modelo como si solo conociera datos "
            "hasta esa fecha pasada (nunca ve lo que pasó después) y comparan contra los "
            "casos reales que ocurrieron: sirven para validar el modelo con casos reales, no "
            "son el pronóstico de hoy. \"Elegir otra semana\" deja probar CUALQUIER semana del "
            "histórico, no solo los ejemplos preseleccionados."
        ),
    )

    origen = None
    if modo == _MODO_PERSONALIZADO:
        origen = _seleccionar_semana_personalizada(serie)
        if origen is None:
            return
    elif modo != _MODO_EN_VIVO:
        origen = _EJEMPLOS_HISTORICOS[modo]

    serie_contexto_real = None
    if origen is None:
        serie_modelo = serie
    else:
        serie_modelo = serie[serie["fecha_semana"] <= origen].reset_index(drop=True)
        fin_contexto = origen + pd.Timedelta(weeks=_SEMANAS_CONTEXTO_REAL_HISTORICO)
        serie_contexto_real = serie[
            (serie["fecha_semana"] > origen) & (serie["fecha_semana"] <= fin_contexto)
        ].reset_index(drop=True)
        st.warning(
            f"Estás viendo un EJEMPLO HISTÓRICO, no el pronóstico de hoy: el modelo entrenado "
            f"solo con datos hasta el {origen.strftime('%d de %B de %Y')}, comparado con los "
            "casos reales que ocurrieron después.",
            icon=":material/history_edu:",
        )

    if len(serie_modelo) < SEMANAS_MINIMAS_ENTRENAMIENTO:
        st.warning(
            "No hay suficiente histórico antes de esta fecha para entrenar el modelo.",
            icon=":material/warning:",
        )
        return

    pronostico = _entrenar_y_pronosticar_cacheado(serie_modelo, HORIZONTE_MAXIMO_SEMANAS)
    if pronostico is None:
        st.warning("No fue posible entrenar el modelo con el histórico disponible.", icon=":material/warning:")
        return

    anios_entrenamiento = int(serie_modelo["ano"].min()), int(serie_modelo["ano"].max())
    st.caption(
        f":material/history: Modelo entrenado con {len(serie_modelo)} semanas de histórico "
        f"({anios_entrenamiento[0]}-{anios_entrenamiento[1]})."
    )

    metrica = st.segmented_control(
        "Métrica", _METRICAS, default=_METRICAS[1], key="pronostico_metrica", required=True
    )

    serie_con_tasa = _agregar_tasa(serie_modelo, ["casos"])
    pronostico_con_tasa = _agregar_tasa(pronostico, ["casos_pronosticados", "casos_min", "casos_max"])
    contexto_con_tasa = (
        _agregar_tasa(serie_contexto_real, ["casos"])
        if serie_contexto_real is not None and not serie_contexto_real.empty
        else None
    )

    st.plotly_chart(
        _graficar_pronostico(serie_con_tasa, pronostico_con_tasa, metrica, contexto_con_tasa),
        width="stretch",
    )

    st.space("small")
    _mostrar_kpis_semanales(pronostico_con_tasa, es_historico=(modo != _MODO_EN_VIVO))


def _seleccionar_semana_personalizada(serie: pd.DataFrame) -> pd.Timestamp | None:
    """Deja elegir CUALQUIER semana del historico como origen, no solo los dos
    ejemplos preseleccionados: quien presenta (o cualquier stakeholder en la
    sala) puede pedir otra fecha y verificar por su cuenta, sin depender de que
    confien en que los ejemplos fijos fueron elegidos de buena fe.

    La fecha elegida se ajusta a la semana epidemiologica mas cercana hacia
    atras (convencion CDC, igual que el resto del sistema). None si todavia no
    hay suficiente historico para ofrecer ninguna fecha valida (aviso propio).
    """
    fechas_disponibles = serie["fecha_semana"]
    if len(fechas_disponibles) <= SEMANAS_MINIMAS_ENTRENAMIENTO:
        st.info(
            "Todavía no hay suficiente histórico para elegir una semana personalizada.",
            icon=":material/info:",
        )
        return None

    primera_fecha_valida = fechas_disponibles.iloc[SEMANAS_MINIMAS_ENTRENAMIENTO - 1]
    ultima_fecha_valida = fechas_disponibles.iloc[-2]  # deja al menos 1 semana real de contexto despues

    fecha_elegida = st.date_input(
        "Semana de origen (se ajusta al inicio de esa semana epidemiológica)",
        value=primera_fecha_valida.date(),
        min_value=primera_fecha_valida.date(),
        max_value=ultima_fecha_valida.date(),
        key="pronostico_fecha_personalizada",
    )
    fecha_elegida = pd.Timestamp(fecha_elegida)

    semanas_hasta_fecha = fechas_disponibles[fechas_disponibles <= fecha_elegida]
    return semanas_hasta_fecha.iloc[-1] if not semanas_hasta_fecha.empty else primera_fecha_valida


def _avisar_si_hay_filtros_geograficos_activos() -> None:
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    if filtros.get("subregion") or filtros.get("nom_mun_o"):
        st.info(
            "Tienes un filtro de subregión o municipio activo: no afecta a esta pestaña, "
            "el pronóstico siempre es departamental.",
            icon=":material/info:",
        )


def _graficar_pronostico(
    serie: pd.DataFrame, pronostico: pd.DataFrame, metrica: str, contexto_real: pd.DataFrame | None = None
) -> go.Figure:
    usar_tasa = metrica == _METRICAS[1]
    columna_historial = "casos_tasa" if usar_tasa else "casos"
    columna_pronostico = "casos_pronosticados_tasa" if usar_tasa else "casos_pronosticados"
    columna_min = "casos_min_tasa" if usar_tasa else "casos_min"
    columna_max = "casos_max_tasa" if usar_tasa else "casos_max"
    etiqueta_eje = "Tasa semanal (x100.000 hab.)" if usar_tasa else "Casos"

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=serie["fecha_semana"], y=serie[columna_historial],
        mode="lines",
        line=dict(color=AZUL_INSTITUCIONAL, width=1.5),
        name="Histórico",
    ))

    # Puente entre la ultima semana real y la primera pronosticada: sin este
    # punto, la banda/linea de pronostico queda visualmente desconectada del
    # historico (dos series separadas en vez de una continuacion).
    puente = serie.iloc[[-1]].rename(columns={columna_historial: columna_pronostico})
    fechas_banda = pd.concat([puente["fecha_semana"], pronostico["fecha_semana"]])
    valores_min = pd.concat([puente[columna_pronostico], pronostico[columna_min]])
    valores_max = pd.concat([puente[columna_pronostico], pronostico[columna_max]])

    fig.add_trace(go.Scatter(
        x=pd.concat([fechas_banda, fechas_banda[::-1]]),
        y=pd.concat([valores_max, valores_min[::-1]]),
        fill="toself",
        fillcolor="rgba(232, 133, 44, 0.18)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Banda de incertidumbre",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=pd.concat([puente["fecha_semana"], pronostico["fecha_semana"]]),
        y=pd.concat([puente[columna_pronostico], pronostico[columna_pronostico]]),
        mode="lines+markers",
        line=dict(color=NARANJA_INSTITUCIONAL, width=2, dash="dash"),
        marker=dict(size=6),
        name="Pronóstico",
    ))

    # En modo ejemplo historico: lo que realmente paso despues, mas alla del
    # horizonte de 4 semanas del modelo, para que se vea hacia donde iba de
    # verdad la curva (linea solida gris, distinta del pronostico naranja
    # punteado: no se puede confundir una con la otra).
    if contexto_real is not None and not contexto_real.empty:
        fig.add_trace(go.Scatter(
            x=pd.concat([puente["fecha_semana"], contexto_real["fecha_semana"]]),
            y=pd.concat([puente[columna_pronostico], contexto_real[columna_historial]]),
            mode="lines+markers",
            line=dict(color="#5a5f66", width=2),
            marker=dict(size=5),
            name="Real (después, para comparar)",
        ))

    ultima_fecha_real = serie["fecha_semana"].iloc[-1]
    fig.add_vline(x=ultima_fecha_real, line_width=1, line_dash="dot", line_color="#9aa0a8")

    fecha_fin_visible = pronostico["fecha_semana"].iloc[-1]
    if contexto_real is not None and not contexto_real.empty:
        fecha_fin_visible = max(fecha_fin_visible, contexto_real["fecha_semana"].iloc[-1])

    inicio_visible = serie["fecha_semana"].iloc[-min(len(serie), _SEMANAS_HISTORIAL_VISIBLE_POR_DEFECTO)]
    fig.update_layout(
        xaxis=dict(title="Semana", range=[inicio_visible, fecha_fin_visible]),
        yaxis=dict(title=etiqueta_eje, rangemode="tozero", minallowed=0),
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(**LEYENDA_SUPERIOR),
        height=380,
    )
    return fig


def _mostrar_kpis_semanales(pronostico: pd.DataFrame, es_historico: bool = False) -> None:
    etiqueta = "Semanas siguientes al ejemplo histórico" if es_historico else "Próximas semanas"
    st.caption(f":material/calendar_month: {etiqueta}")
    columnas = st.columns(len(pronostico))
    for columna, (_, fila) in zip(columnas, pronostico.iterrows()):
        with columna:
            tasa_texto = f"{fila['casos_pronosticados_tasa']:,.1f}" if fila["casos_pronosticados_tasa"] is not None else "No disponible"
            st.metric(
                f"Semana {int(fila['semana'])} · {int(fila['ano'])}",
                f"{fila['casos_pronosticados']:,.0f} casos",
                help=(
                    f"Banda de incertidumbre (80%): {fila['casos_min']:,.0f} - {fila['casos_max']:,.0f} casos. "
                    f"Tasa semanal: {tasa_texto} x100.000 hab. (población total del Magdalena, no "
                    "es comparable con la Incidencia anual de Situación). "
                    f"Horizonte: {int(fila['horizonte_semanas'])} semana(s) desde la última semana con datos reales."
                ),
                border=True,
            )


# ---------------------------------------------------------------------------
# Dialogo de fundamentacion: resume el documento tecnico de modelado (repo de
# modelado, notebooks 03_dengue_modeling y 05_dengue_ablacion_clima_vs_lags).
# ---------------------------------------------------------------------------

@st.dialog("Fundamentación del pronóstico", width="large")
def _dialogo_fundamentacion() -> None:
    st.markdown(
        "Resumen del documento técnico de modelado: por qué Prophet, por qué sin variables "
        "climáticas, y por qué el horizonte se limita a 4 semanas."
    )

    tab_resumen, tab_clima, tab_horizonte, tab_datos = st.tabs(
        ["Resumen", "¿Por qué sin clima?", "¿Por qué 4 semanas?", "Datos y validación"]
    )

    with tab_resumen:
        st.markdown(
            "Se evaluaron 6 familias de modelos (SARIMAX, Prophet, XGBoost, LightGBM, LSTM, "
            "N-BEATS) con pronóstico multi-paso walk-forward (origen móvil, sin ver los casos "
            "intermedios): la evaluación honesta para alerta temprana, a diferencia de la "
            "comparación a un paso, que está inflada por la autocorrelación semanal de la serie "
            "(todos los modelos usan el caso real de la semana anterior)."
        )
        st.markdown(
            "**Modelo elegido: Prophet sin variables climáticas** (estacionalidad anual + "
            "regresores autorregresivos de los casos de 1, 2, 4 y 8 semanas atrás), por tres "
            "razones verificadas contra los resultados:\n\n"
            "- Menor dependencia del clima de las 6 familias en todo el rango de horizontes "
            "(pérdida de R2 entre 0.006 y 0.026 al quitar el clima, la más baja de todas).\n"
            "- Mejor desempeño absoluto entre los modelos sin clima a partir de 2 semanas de "
            "horizonte, por encima de ARIMA/SARIMA, XGBoost, LightGBM y LSTM sin clima.\n"
            "- A 4 semanas queda cerca de los mejores modelos CON clima en ese horizonte "
            "(R2 0.73 sin clima vs. 0.77 de LSTM/XGBoost con clima), una diferencia que no "
            "justifica la complejidad operativa de mantener variables climáticas actualizadas "
            "en producción."
        )

    with tab_clima:
        st.markdown(
            "Se comparó cada modelo entrenado con y sin variables climáticas (humedad, "
            "precipitación, temperatura), mismos hiperparámetros, única diferencia el clima."
        )
        st.markdown(
            "| Modelo | Δ R2 h=1 | Δ R2 h=3 | Δ R2 h=4 | Δ R2 h=6 |\n"
            "|---|---|---|---|---|\n"
            "| **Prophet** | -0.006 | -0.012 | -0.016 | -0.026 |\n"
            "| ARIMA / SARIMA | -0.003 | -0.035 | -0.053 | -0.120 |\n"
            "| XGBoost | -0.010 | -0.056 | -0.080 | -0.154 |\n"
            "| LightGBM | -0.017 | -0.050 | -0.081 | -0.093 |\n"
            "| LSTM | -0.022 | -0.064 | -0.081 | -0.119 |\n"
            "| N-BEATS | -0.026 | -0.218 | -0.481 | -1.555 |"
        )
        st.caption(
            "Δ R2 = R2 sin clima menos R2 con clima (más negativo = el clima ayuda más). Prophet "
            "es el único modelo cuya pérdida se mantiene marginal en todo el rango; N-BEATS "
            "colapsa sin clima a partir de 3-4 semanas."
        )
        st.markdown(
            "Se optó por no usar covariables climáticas: el costo de adquisición, actualización "
            "y validación continua de series climáticas recae sobre la operación del sistema, y "
            "para el modelo elegido (Prophet) esa mejora no es significativa en el horizonte "
            "donde el pipeline entrega decisiones útiles (1 a 4 semanas)."
        )

    with tab_horizonte:
        st.markdown(
            "Evaluación walk-forward de origen móvil: desde cada semana de origen se pronostican "
            "las siguientes semanas sin usar los casos intermedios, para horizontes de 1 a 6 "
            "semanas."
        )
        st.markdown(
            "| Horizonte | R2 (Prophet sin clima) | RMSE (casos) |\n"
            "|---|---|---|\n"
            "| 1 semana | 0.87 | 12.3 |\n"
            "| 2 semanas | 0.83 | 14.0 |\n"
            "| 3 semanas | 0.77 | 16.3 |\n"
            "| 4 semanas | 0.73 | 17.5 |\n"
            "| 6 semanas | 0.62 | 20.8 |"
        )
        st.markdown(
            "El margen de Prophet sobre una línea base de persistencia (pronosticar el último "
            "valor observado) crece de 3 a 4 semanas (+0.037 a +0.081 de R2): el modelo aporta "
            "relativamente más cuanto más se aleja la persistencia de la realidad. A 6 semanas "
            "la exactitud absoluta ya baja de forma notoria (MAPE ~35%) y varias familias "
            "alternativas fallan frente a la persistencia; por eso el dashboard limita la "
            "ventana útil a **4 semanas**, no ofrece horizontes mayores."
        )

    with tab_datos:
        st.markdown(
            "La serie semanal departamental de referencia usada para validar este modelo cubre "
            "940 semanas epidemiológicas (2007-2024, 18 años), dividida cronológicamente en 70% "
            "entrenamiento, 15% validación y 15% prueba (2022-2024), sin barajar."
        )
        st.markdown(
            "El modelo que corre en este dashboard se reentrena automáticamente con el histórico "
            "que el sistema tenga cargado en cada momento (crece a medida que se suben más años "
            "de datos por la Gestión de piezas). Si el histórico actualmente cargado es más corto "
            "que los 18 años de la validación original, el modelo sigue siendo Prophet-AR con la "
            "misma configuración, pero su estimación de estacionalidad anual mejora a medida que "
            "haya más años disponibles."
        )
        st.markdown(
            "Rezagos usados como regresores: 1, 2, 4 y 8 semanas de log1p(casos). Para pronosticar "
            "más de 1 semana adelante, los rezagos que caen dentro del horizonte se completan con "
            "la propia predicción del modelo (pronóstico recursivo), la misma lógica que la "
            "evaluación walk-forward que valida estos resultados."
        )
        st.markdown(
            "El selector \"Modo\" de la pestaña incluye ejemplos históricos (una subida real y "
            "un descenso real) que corren este mismo modelo como si solo conocieran datos hasta "
            "una fecha pasada, y comparan contra lo que efectivamente ocurrió después. También "
            "deja elegir cualquier otra semana del histórico, no solo esos dos ejemplos: ninguno "
            "inventa ni ajusta el resultado, y cualquiera puede verificarlo con la fecha que "
            "quiera. No reemplazan el pronóstico de hoy."
        )

    if st.button("Cerrar", width="stretch"):
        st.rerun()
