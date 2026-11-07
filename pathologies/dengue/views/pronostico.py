"""Pestana Pronostico: pronostico semanal de casos de dengue a nivel
departamental (Magdalena), de 1 a 6 semanas, con el mejor modelo de cada familia
(estadistico, aprendizaje automatico, aprendizaje profundo). La metodologia
completa esta en docs/pronostico.md, que el dialogo de Fundamentacion muestra.

La pestana SOLO MUESTRA: no entrena, no sube ni cambia modelos (eso es de
Gestion, perfil de administracion). Usa la version activa de cada familia
(core/storage/modelos.py).

Dos vistas que no se mezclan:
- Pronostico en vivo: el modelo definitivo (entrenado con el 100 % del rango)
  pronostica las proximas 6 semanas desde la ultima semana cargada. Se calcula al
  abrir la pestana (cache por version) y no se guarda en ningun archivo. Lo
  acompanan, en un bloque aparte, las metricas de la prueba por horizonte: el
  rendimiento historico del modelo de evaluacion, no el error de estos
  pronosticos.
- Pronostico de una semana pasada: los resultados individuales de la prueba,
  leidos del CSV de la version (pronosticos_prueba.csv). No se reconstruyen con
  el modelo definitivo ni se entrena nada.

Presentacion: los calculos usan valores sin redondear; las tablas y la grafica
muestran 1 decimal.

Serie DEPARTAMENTAL unica: no depende de los filtros globales; usa siempre el
consolidado completo de la sesion. Tasa con poblacion TOTAL del Magdalena (no la
poblacion en riesgo): ver CLAUDE.md.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from epiweeks import Week

from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    COLOR_DATO_REAL,
    NARANJA_INSTITUCIONAL,
    mostrar_grafica,
)
from core.dashboard_base.filtros import CLAVE_FILTROS
from core.dashboard_base.gestion_entrenamiento import (
    FORMATO_COLUMNAS_METRICAS,
    formatear_fecha_larga,
    tabla_metricas,
    tabla_metricas_global,
)
from core.ingestion.entrenamiento import describir_rango
from core.storage import modelos as almacen_modelos
from pathologies.dengue.poblacion import obtener_poblacion_total_departamental
from pathologies.dengue.pronostico import catalogo, documentacion
from pathologies.dengue.pronostico.configuracion import (
    FAMILIA_APRENDIZAJE_AUTOMATICO,
    FAMILIA_APRENDIZAJE_PROFUNDO,
    FAMILIA_ESTADISTICO,
    FAMILIAS,
    HORIZONTE_MAXIMO_SEMANAS,
    HORIZONTE_RECOMENDADO_SEMANAS,
)
from pathologies.dengue.pronostico.evaluacion import calcular_metricas
from pathologies.dengue.pronostico.inferencia import pronosticar
from pathologies.dengue.pronostico.manifest import es_formato_vigente
from pathologies.dengue.pronostico.paquete import leer_pronosticos_prueba
from pathologies.dengue.pronostico.serie import agregar_semana_epidemiologica, construir_serie_semanal_departamental

PATOLOGIA = "dengue"

# Un color por familia, fijo en toda la pestana. El negro queda reservado para
# el dato real.
COLORES_FAMILIA = {
    FAMILIA_ESTADISTICO: AZUL_INSTITUCIONAL,
    FAMILIA_APRENDIZAJE_AUTOMATICO: NARANJA_INSTITUCIONAL,
    # Verde azulado y no violeta: el violeta se confundia con el azul.
    FAMILIA_APRENDIZAJE_PROFUNDO: "#0891b2",
}
_FAMILIA_POR_DEFECTO = FAMILIA_ESTADISTICO
_COLOR_GRIS = "#6b7280"

_OPCION_COMPARAR = "comparar"
_METRICAS = ["Casos", "Tasa semanal (x100.000 hab.)"]
_MODO_EN_VIVO = "Pronóstico en vivo (próximas semanas)"
_MODO_HISTORICO = "Pronóstico de una semana pasada (prueba)"

_SEMANAS_CONTEXTO_REAL_HISTORICO = 8
_SEMANAS_VISTA_INICIAL = 104

_NOTA_REDONDEO = (
    "Valores mostrados con 1 decimal; todos los cálculos usan los valores sin redondear."
)

_FORMATO_COLUMNAS_CASOS = {
    "Pronóstico": st.column_config.NumberColumn("Pronóstico", format="%.1f"),
    "±RMSE": st.column_config.NumberColumn("±RMSE", format="%.1f"),
    "Casos reales": st.column_config.NumberColumn("Casos reales", format="%.0f"),
    "Error absoluto": st.column_config.NumberColumn("Error absoluto", format="%.1f"),
    "Persistencia": st.column_config.NumberColumn("Persistencia", format="%.1f"),
    "Error absoluto persistencia": st.column_config.NumberColumn("Error absoluto persistencia", format="%.1f"),
}


# ---------------------------------------------------------------------------
# Modelos activos y sus archivos (cacheados)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _cargar_modelo(modelo: str, version: str):
    """El modelo definitivo de una version se carga una vez por proceso. Las
    redes importan TensorFlow aqui. Cargar no entrena."""
    manifest = almacen_modelos.leer_manifest(PATOLOGIA, modelo, version)
    clase = catalogo.obtener_modelo(modelo)
    instancia = clase(manifest["hiperparametros"])
    instancia.cargar(almacen_modelos.ruta_version(PATOLOGIA, modelo, version))
    return instancia


@st.cache_data(show_spinner=False)
def _pronosticar_en_vivo(modelo: str, version: str, serie: pd.DataFrame) -> pd.DataFrame:
    """Las 6 semanas siguientes a la ultima semana del consolidado, con el
    modelo definitivo. El selector de horizonte solo recorta. No se guarda en
    ningun archivo."""
    instancia = _cargar_modelo(modelo, version)
    return pronosticar(instancia, serie, HORIZONTE_MAXIMO_SEMANAS)


@st.cache_data(show_spinner=False)
def _registros_prueba(modelo: str, version: str) -> pd.DataFrame | None:
    manifest = almacen_modelos.leer_manifest(PATOLOGIA, modelo, version) or {}
    carpeta = almacen_modelos.ruta_version(PATOLOGIA, modelo, version)
    return leer_pronosticos_prueba(carpeta, manifest)


def _modelos_activos() -> dict[str, dict]:
    """{familia: {"modelo", "version", "manifest", "nombre"}} de las familias con
    version activa, en el orden de FAMILIAS."""
    punteros = almacen_modelos.leer_activos(PATOLOGIA)
    activos = {}
    for familia in FAMILIAS:
        puntero = punteros.get(familia)
        if puntero is None:
            continue
        manifest = almacen_modelos.leer_manifest(PATOLOGIA, puntero["modelo"], puntero["version"]) or {}
        activos[familia] = {
            "modelo": puntero["modelo"],
            "version": puntero["version"],
            "manifest": manifest,
            "nombre": manifest.get("nombre") or puntero["modelo"],
        }
    return activos


def _rotulo(familia: str, activo: dict) -> str:
    return f"{activo['nombre']} ({FAMILIAS[familia].lower()})"


def _metricas_horizonte(manifest: dict, horizonte: int, pronosticador: str = "modelo") -> dict:
    por_horizonte = manifest.get("metricas_prueba", {}).get("por_horizonte", {})
    return por_horizonte.get(str(horizonte), {}).get(pronosticador, {})


def _texto_semana(fecha: pd.Timestamp) -> str:
    semana = Week.fromdate(pd.Timestamp(fecha).date(), system="CDC")
    return f"Sem. {semana.week} · {semana.year}"


# ---------------------------------------------------------------------------
# Tasa
# ---------------------------------------------------------------------------

def _poblacion_por_anio(anios: list[int]) -> dict[int, float | None]:
    return {anio: obtener_poblacion_total_departamental([anio]) for anio in sorted(set(anios))}


def _agregar_tasa(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Agrega '<columna>_tasa' dividiendo por la poblacion TOTAL del Magdalena
    del anio de cada fila. None (no disponible) si falta poblacion para ese
    anio, nunca un numero inventado."""
    df = df.copy()
    poblacion = _poblacion_por_anio(df["ano"].tolist())
    for columna in columnas:
        tasas = []
        for _, fila in df.iterrows():
            poblacion_anio = poblacion[fila["ano"]]
            if poblacion_anio and pd.notna(fila[columna]):
                tasas.append(fila[columna] / poblacion_anio * 100_000)
            else:
                tasas.append(None)
        df[f"{columna}_tasa"] = tasas
    return df


# ---------------------------------------------------------------------------
# Vista
# ---------------------------------------------------------------------------

def mostrar_pronostico(_datos_filtrados: pd.DataFrame) -> None:
    """_datos_filtrados llega por el contrato uniforme de pestana, pero se
    ignora a proposito: esta pestana siempre usa el consolidado completo."""
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
        "Pronóstico de casos notificados (probables y confirmados, los mismos que el resto del "
        "tablero) a nivel departamental, todo el Magdalena, con el mejor modelo de cada familia. "
        "No depende de los filtros de la barra lateral: usa siempre el histórico completo."
    )
    _avisar_si_hay_filtros_geograficos_activos()

    activos = _modelos_activos()
    if not activos:
        st.info(
            "Todavía no hay modelos de pronóstico activos. El perfil de administración los entrena "
            "o los sube desde Gestión, apartado Pronóstico.",
            icon=":material/info:",
        )
        return

    serie = construir_serie_semanal_departamental(datos_completos)
    if serie.empty:
        st.warning("No hay casos en el consolidado para pronosticar.", icon=":material/warning:")
        return

    modo = st.segmented_control(
        "Modo",
        [_MODO_EN_VIVO, _MODO_HISTORICO],
        default=_MODO_EN_VIVO,
        required=True,
        key="pronostico_modo",
        help=(
            "En vivo: el modelo definitivo pronostica las próximas semanas. Semana pasada: los "
            "pronósticos que hizo el modelo de evaluación durante la prueba, en semanas que no "
            "había visto, comparados con lo que ocurrió."
        ),
    )

    opciones_modelo = list(activos)
    if len(activos) > 1:
        opciones_modelo.append(_OPCION_COMPARAR)
    if _FAMILIA_POR_DEFECTO in activos:
        indice_defecto = opciones_modelo.index(_FAMILIA_POR_DEFECTO)
    else:
        indice_defecto = 0

    def _rotulo_opcion(opcion: str) -> str:
        if opcion == _OPCION_COMPARAR:
            return f"Comparar los {len(activos)}"
        return _rotulo(opcion, activos[opcion])

    col_modelo, col_horizonte, col_metrica = st.columns([2.2, 2, 1.8], vertical_alignment="bottom")
    with col_modelo:
        opcion_modelo = st.selectbox(
            "Modelo", opciones_modelo, index=indice_defecto, format_func=_rotulo_opcion, key="pronostico_modelo"
        )
    with col_horizonte:
        horizonte = st.select_slider(
            "Horizonte (semanas)",
            options=list(range(1, HORIZONTE_MAXIMO_SEMANAS + 1)),
            value=HORIZONTE_RECOMENDADO_SEMANAS,
            key="pronostico_horizonte",
        )
    with col_metrica:
        metrica = st.segmented_control(
            "Métrica", _METRICAS, default=_METRICAS[0], key="pronostico_metrica", required=True
        )

    if opcion_modelo == _OPCION_COMPARAR:
        familias_elegidas = list(activos)
    else:
        familias_elegidas = [opcion_modelo]
    elegidos = {familia: activos[familia] for familia in familias_elegidas}

    if horizonte > HORIZONTE_RECOMENDADO_SEMANAS:
        st.warning(
            f"Se recomienda pronosticar hasta {HORIZONTE_RECOMENDADO_SEMANAS} semanas. Más allá el "
            "error crece: compara las métricas de la prueba de cada horizonte.",
            icon=":material/warning:",
        )

    if modo == _MODO_EN_VIVO:
        _mostrar_en_vivo(serie, elegidos, horizonte, metrica)
    else:
        _mostrar_historico(serie, elegidos, horizonte, metrica)


def _avisar_si_hay_filtros_geograficos_activos() -> None:
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    if filtros.get("subregion") or filtros.get("nom_mun_o"):
        st.info(
            "Tienes un filtro de subregión o municipio activo: no afecta a esta pestaña, "
            "el pronóstico siempre es departamental.",
            icon=":material/info:",
        )


# ---------------------------------------------------------------------------
# En vivo
# ---------------------------------------------------------------------------

def _mostrar_procedencia(elegidos: dict[str, dict], serie: pd.DataFrame) -> None:
    fecha_ultima_datos = pd.Timestamp(serie["fecha_semana"].iloc[-1])
    lineas = []
    desactualizados = []
    for activo in elegidos.values():
        manifest = activo["manifest"]
        rango = manifest.get("rango", {})
        fecha = manifest.get("fecha_entrenamiento")
        fecha_texto = formatear_fecha_larga(fecha) if fecha else "fecha desconocida"
        rango_texto = describir_rango(rango) if rango else "rango desconocido"
        lineas.append(f"{activo['nombre']}: modelo definitivo entrenado el {fecha_texto} con {rango_texto}.")
        fecha_ultima_modelo = rango.get("fecha_ultima_semana")
        if fecha_ultima_modelo and fecha_ultima_datos > pd.Timestamp(fecha_ultima_modelo):
            desactualizados.append(activo["nombre"])

    st.caption(":material/model_training: " + "  \n".join(lineas))
    if desactualizados:
        ultima = serie.iloc[-1]
        st.warning(
            f"El consolidado llega hasta la semana {int(ultima['semana'])} de {int(ultima['ano'])}, "
            f"más reciente que los datos con que se entrenó {', '.join(desactualizados)}. El "
            "pronóstico parte de la última semana cargada, pero el modelo no aprendió de esas "
            "semanas nuevas. El perfil de administración puede reentrenarlo desde Gestión.",
            icon=":material/update:",
        )


def _con_limites(pronostico: pd.DataFrame, manifest: dict) -> pd.DataFrame:
    """Agrega a cada semana el RMSE de la prueba de su horizonte y el rango
    orientativo pronostico +- RMSE (el limite inferior no baja de 0)."""
    tabla = pronostico.copy()
    errores = []
    for horizonte in tabla["horizonte_semanas"]:
        errores.append(_metricas_horizonte(manifest, int(horizonte)).get("RMSE"))
    tabla["rmse"] = pd.to_numeric(pd.Series(errores, index=tabla.index), errors="coerce")
    limite_inferior = tabla["casos_pronosticados"] - tabla["rmse"]
    tabla["limite_inferior"] = limite_inferior.clip(lower=0)
    tabla["limite_superior"] = tabla["casos_pronosticados"] + tabla["rmse"]
    return tabla


def _mostrar_en_vivo(serie: pd.DataFrame, elegidos: dict[str, dict], horizonte: int, metrica: str) -> None:
    _mostrar_procedencia(elegidos, serie)

    pronosticos = {}
    for familia, activo in elegidos.items():
        try:
            with st.spinner(f"Calculando el pronóstico con {activo['nombre']}..."):
                completo = _pronosticar_en_vivo(activo["modelo"], activo["version"], serie)
        except Exception as error:
            st.warning(
                f"No se pudo usar {activo['nombre']}: {error}. El perfil de administración puede "
                "revisarlo en Gestión.",
                icon=":material/error:",
            )
            continue
        recortado = completo[completo["horizonte_semanas"] <= horizonte]
        pronosticos[familia] = _con_limites(recortado, activo["manifest"])
    if not pronosticos:
        return

    st.markdown("#### Pronóstico de las próximas semanas")
    st.caption(
        "Modelo definitivo, entrenado con el 100 % de su rango, a partir de los casos reales hasta "
        "la última semana cargada. Rango orientativo: pronóstico ± el RMSE de la prueba de ese "
        "horizonte; no es un intervalo de confianza. " + _NOTA_REDONDEO
    )
    _dibujar(serie, pronosticos, elegidos, metrica, contexto_real=None, etiqueta_corte="Última semana cargada")
    _mostrar_tabla_futuro(pronosticos, elegidos)

    st.markdown("#### Desempeño histórico en la prueba")
    primer_manifest = next(iter(elegidos.values()))["manifest"]
    alcance = primer_manifest.get("metricas_prueba", {}).get("alcance")
    if alcance:
        st.markdown(alcance + " Sirven como referencia del error esperado en cada horizonte.")
    _mostrar_metricas_prueba(elegidos, horizonte)


def _rango_texto(fila) -> str:
    return f"{fila['limite_inferior']:,.1f} a {fila['limite_superior']:,.1f}"


def _mostrar_tabla_futuro(pronosticos: dict[str, pd.DataFrame], elegidos: dict[str, dict]) -> None:
    if len(pronosticos) == 1:
        pronostico = next(iter(pronosticos.values()))
        filas = []
        for _, fila in pronostico.iterrows():
            filas.append({
                "Semana": _texto_semana(fila["fecha_semana"]),
                "Horizonte": f"H{int(fila['horizonte_semanas'])}",
                "Pronóstico": fila["casos_pronosticados"],
                "±RMSE": fila["rmse"],
                "Rango orientativo (±RMSE)": _rango_texto(fila),
            })
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch", column_config=_FORMATO_COLUMNAS_CASOS)
        return

    primer = next(iter(pronosticos.values()))
    tabla = pd.DataFrame({
        "Semana": [_texto_semana(fecha) for fecha in primer["fecha_semana"]],
        "Horizonte": [f"H{int(valor)}" for valor in primer["horizonte_semanas"]],
    })
    for familia, pronostico in pronosticos.items():
        valores = []
        for _, fila in pronostico.iterrows():
            valores.append(f"{fila['casos_pronosticados']:,.1f} ({_rango_texto(fila)})")
        tabla[elegidos[familia]["nombre"]] = valores
    st.dataframe(tabla, hide_index=True, width="stretch")


def _mostrar_metricas_prueba(elegidos: dict[str, dict], horizonte: int) -> None:
    filas = []
    for activo in elegidos.values():
        manifest = activo["manifest"]
        por_horizonte = tabla_metricas(manifest)
        if por_horizonte.empty:
            continue
        horizontes_elegidos = [f"H{numero}" for numero in range(1, horizonte + 1)]
        por_horizonte = por_horizonte[por_horizonte["Horizonte"].isin(horizontes_elegidos)]
        global_ = tabla_metricas_global(manifest).rename(columns={"Alcance": "Horizonte"})
        combinada = pd.concat([por_horizonte, global_], ignore_index=True)
        combinada.insert(0, "Modelo", activo["nombre"])
        filas.append(combinada)
    if not filas:
        st.markdown("Los modelos elegidos no tienen métricas de la prueba.")
        return
    tabla = pd.concat(filas, ignore_index=True)
    columnas = ["Modelo", "Horizonte", "n", "RMSE", "MAE", "MAPE (%)", "R²", "RMSE persistencia", "Razón RMSE vs persistencia"]
    st.dataframe(tabla[columnas], hide_index=True, width="stretch", column_config=FORMATO_COLUMNAS_METRICAS)
    st.caption(
        "Cada fila H se calcula con todos los pronósticos de ese horizonte en la prueba (n "
        "registros); la fila global, con todos los registros de H1 a H6 a la vez. La semana 1 "
        "futura se acompaña del RMSE de H1, la 6 del de H6. " + _NOTA_REDONDEO
    )


# ---------------------------------------------------------------------------
# Semana pasada: resultados individuales de la prueba
# ---------------------------------------------------------------------------

def _mostrar_historico(serie: pd.DataFrame, elegidos: dict[str, dict], horizonte: int, metrica: str) -> None:
    con_registros = {}
    sin_registros = []
    for familia, activo in elegidos.items():
        registros = None
        if es_formato_vigente(activo["manifest"]):
            registros = _registros_prueba(activo["modelo"], activo["version"])
        if registros is None or registros.empty:
            sin_registros.append(activo["nombre"])
        else:
            con_registros[familia] = registros
    if sin_registros:
        st.info(
            f"{', '.join(sin_registros)}: su versión no tiene resultados de la prueba guardados.",
            icon=":material/info:",
        )
    if not con_registros:
        return

    conjuntos = [set(registros["fecha_origen"]) for registros in con_registros.values()]
    origenes = sorted(set.intersection(*conjuntos))
    if not origenes:
        st.info("Los modelos elegidos no tienen semanas de prueba en común. Elige uno solo.", icon=":material/info:")
        return

    primeros = next(iter(con_registros.values()))
    horizontes_por_origen = primeros.groupby("fecha_origen")["horizonte_semanas"].apply(sorted).to_dict()
    completos = [origen for origen in origenes if len(horizontes_por_origen.get(origen, [])) == HORIZONTE_MAXIMO_SEMANAS]
    if completos:
        defecto = origenes.index(completos[-1])
    else:
        defecto = len(origenes) - 1

    def _rotulo_origen(posicion: int) -> str:
        origen = origenes[posicion]
        horizontes = horizontes_por_origen.get(origen, [])
        semana = Week.fromdate(origen.date(), system="CDC")
        if not horizontes:
            disponibles = "sin horizontes"
        elif len(horizontes) == 1:
            disponibles = f"H{horizontes[0]}"
        else:
            disponibles = f"H{horizontes[0]} a H{horizontes[-1]}"
        return f"Semana {semana.week} de {semana.year} ({formatear_fecha_larga(origen.isoformat())}) · evaluables: {disponibles}"

    posicion = st.selectbox(
        "Pronosticar desde la semana (semana de origen)",
        list(range(len(origenes))),
        index=defecto,
        format_func=_rotulo_origen,
        key="pronostico_origen_historico",
        help=(
            "Semanas de origen de la prueba. Solo se muestran los horizontes cuya semana objetivo "
            "pertenece a la prueba, por eso al principio y al final hay menos de 6."
        ),
    )
    origen = origenes[posicion]

    pronosticos = {}
    filas_tabla = []
    for familia, registros in con_registros.items():
        activo = elegidos[familia]
        del_origen = registros[(registros["fecha_origen"] == origen) & (registros["horizonte_semanas"] <= horizonte)]
        del_origen = del_origen.sort_values("horizonte_semanas")
        if del_origen.empty:
            continue
        para_grafica = pd.DataFrame({
            "fecha_semana": del_origen["fecha_objetivo"].to_numpy(),
            "horizonte_semanas": del_origen["horizonte_semanas"].to_numpy(),
            "casos_pronosticados": del_origen["pronostico_modelo"].to_numpy(),
        })
        para_grafica = agregar_semana_epidemiologica(para_grafica)
        pronosticos[familia] = _con_limites(para_grafica, activo["manifest"])
        for _, fila in del_origen.iterrows():
            filas_tabla.append(_fila_resultado_individual(activo["nombre"], fila))

    if not pronosticos:
        horizontes = horizontes_por_origen.get(origen, [])
        st.info(
            f"Desde esta semana el primer horizonte evaluable es H{horizontes[0]}: sube el horizonte "
            "para verlo.",
            icon=":material/info:",
        )
        return

    cortes = []
    for activo in elegidos.values():
        prueba = activo["manifest"].get("prueba", {})
        if prueba.get("inicio_prueba"):
            ultimo_dia = pd.Timestamp(prueba["inicio_prueba"]) - pd.Timedelta(weeks=1)
            cortes.append(f"{activo['nombre']}, hasta el {formatear_fecha_larga(ultimo_dia.isoformat())}")
    st.warning(
        "Estás viendo resultados individuales de la PRUEBA, no el pronóstico de hoy. Los hizo el "
        "modelo de evaluación, entrenado solo con el 85 % de los datos "
        f"({'; '.join(cortes)}), que no había visto estas semanas. No es el modelo definitivo.",
        icon=":material/history_edu:",
    )

    serie_hasta_origen = serie[serie["fecha_semana"] <= origen].reset_index(drop=True)
    fin_contexto = origen + pd.Timedelta(weeks=horizonte + _SEMANAS_CONTEXTO_REAL_HISTORICO)
    contexto_real = serie[(serie["fecha_semana"] > origen) & (serie["fecha_semana"] <= fin_contexto)].reset_index(drop=True)
    _dibujar(serie_hasta_origen, pronosticos, elegidos, metrica, contexto_real=contexto_real, etiqueta_corte="Semana de origen")

    tabla = pd.DataFrame(filas_tabla)
    if len(pronosticos) == 1:
        tabla = tabla.drop(columns=["Modelo"])
    st.dataframe(tabla, hide_index=True, width="stretch", column_config=_FORMATO_COLUMNAS_CASOS)
    st.caption(
        "Cada fila es un registro de pronosticos_prueba.csv: semana objetivo, horizonte, casos "
        "reales, pronóstico del modelo de evaluación y su error, y la persistencia (repetir los "
        "casos de la semana de origen) con su error. " + _NOTA_REDONDEO + " Con 0 casos reales el "
        "error porcentual no está definido."
    )


def _texto_error_porcentual(valor) -> str:
    if pd.isna(valor):
        return "no definido (0 casos reales)"
    return f"{valor:,.1f} %"


def _fila_resultado_individual(nombre_modelo: str, fila) -> dict:
    return {
        "Modelo": nombre_modelo,
        "Semana objetivo": _texto_semana(fila["fecha_objetivo"]),
        "Horizonte": f"H{int(fila['horizonte_semanas'])}",
        "Casos reales": fila["casos_reales"],
        "Pronóstico": fila["pronostico_modelo"],
        "Error absoluto": fila["error_absoluto"],
        "Error porcentual": _texto_error_porcentual(fila["error_porcentual"]),
        "Persistencia": fila["pronostico_persistencia"],
        "Error absoluto persistencia": fila["error_absoluto_persistencia"],
    }


# ---------------------------------------------------------------------------
# Grafica de pronostico
# ---------------------------------------------------------------------------

def _dibujar(
    serie: pd.DataFrame,
    pronosticos: dict[str, pd.DataFrame],
    elegidos: dict[str, dict],
    metrica: str,
    contexto_real: pd.DataFrame | None,
    etiqueta_corte: str,
) -> None:
    usar_tasa = metrica == _METRICAS[1]
    serie_grafica = serie
    contexto_grafica = contexto_real
    pronosticos_grafica = pronosticos
    if usar_tasa:
        serie_grafica = _agregar_tasa(serie, ["casos"])
        if contexto_real is not None and not contexto_real.empty:
            contexto_grafica = _agregar_tasa(contexto_real, ["casos"])
        pronosticos_grafica = {}
        for familia, pronostico in pronosticos.items():
            columnas = ["casos_pronosticados", "limite_inferior", "limite_superior"]
            pronosticos_grafica[familia] = _agregar_tasa(pronostico, columnas)

    mostrar_banda = len(pronosticos) == 1
    figura = _graficar_pronostico(
        serie_grafica, pronosticos_grafica, elegidos, usar_tasa, contexto_grafica, mostrar_banda, etiqueta_corte
    )
    anio_inicio = int(serie["ano"].iloc[0])
    anio_fin = int(serie["ano"].iloc[-1])
    contexto_texto = f"Dengue · Magdalena · casos semanales {anio_inicio}-{anio_fin} y pronóstico"
    mostrar_grafica(figura, "Pronóstico de casos de dengue", contexto_texto, key="pronostico_grafica")


def _color_translucido(color_hex: str, opacidad: float) -> str:
    color = color_hex.lstrip("#")
    rojo = int(color[0:2], 16)
    verde = int(color[2:4], 16)
    azul = int(color[4:6], 16)
    return f"rgba({rojo}, {verde}, {azul}, {opacidad})"


def _graficar_pronostico(
    serie: pd.DataFrame,
    pronosticos: dict[str, pd.DataFrame],
    elegidos: dict[str, dict],
    usar_tasa: bool,
    contexto_real: pd.DataFrame | None,
    mostrar_banda: bool,
    etiqueta_corte: str,
) -> go.Figure:
    """Negro continuo = dato real. Punteado con marcadores = pronostico, un
    color fijo por familia. Con un solo modelo, banda del rango orientativo
    (+- RMSE de la prueba de cada horizonte)."""
    sufijo = "_tasa" if usar_tasa else ""
    columna_real = f"casos{sufijo}"
    columna_pronostico = f"casos_pronosticados{sufijo}"
    columna_inferior = f"limite_inferior{sufijo}"
    columna_superior = f"limite_superior{sufijo}"
    etiqueta_eje = "Tasa semanal (x100.000 hab.)" if usar_tasa else "Casos"
    formato_real = ",.2f" if usar_tasa else ",.0f"
    formato_pronostico = ",.2f" if usar_tasa else ",.1f"

    fechas_reales = serie["fecha_semana"]
    valores_reales = serie[columna_real]
    if contexto_real is not None and not contexto_real.empty:
        fechas_reales = pd.concat([fechas_reales, contexto_real["fecha_semana"]])
        valores_reales = pd.concat([valores_reales, contexto_real[columna_real]])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fechas_reales,
        y=valores_reales,
        mode="lines",
        line=dict(color=COLOR_DATO_REAL, width=1.4),
        name="Casos reales",
        hovertemplate=f"%{{x|%d %b %Y}} · %{{y:{formato_real}}}<extra>Real</extra>",
    ))

    fecha_corte = serie["fecha_semana"].iloc[-1]
    valor_corte = serie[columna_real].iloc[-1]
    for familia, pronostico in pronosticos.items():
        color = COLORES_FAMILIA.get(familia, AZUL_INSTITUCIONAL)
        nombre = elegidos[familia]["nombre"]
        fechas = [fecha_corte] + pronostico["fecha_semana"].tolist()

        if mostrar_banda:
            fig.add_trace(go.Scatter(
                x=fechas,
                y=[valor_corte] + pronostico[columna_superior].tolist(),
                mode="lines",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=fechas,
                y=[valor_corte] + pronostico[columna_inferior].tolist(),
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor=_color_translucido(color, 0.18),
                name="Rango orientativo (±RMSE de la prueba)",
                hoverinfo="skip",
            ))

        errores = [None] + pronostico["rmse"].tolist()
        fig.add_trace(go.Scatter(
            x=fechas,
            y=[valor_corte] + pronostico[columna_pronostico].tolist(),
            customdata=errores,
            mode="lines+markers",
            line=dict(color=color, width=2.2, dash="dot"),
            marker=dict(size=8, color=color),
            name=nombre,
            hovertemplate=(
                f"%{{x|%d %b %Y}} · %{{y:{formato_pronostico}}} (±RMSE %{{customdata:,.1f}} casos)"
                f"<extra>{nombre}</extra>"
            ),
        ))

    fig.add_vline(x=fecha_corte, line_width=1.2, line_dash="dot", line_color=_COLOR_GRIS)
    fig.add_annotation(
        x=fecha_corte, y=1, yref="paper", xanchor="right", yanchor="bottom",
        text=etiqueta_corte, showarrow=False, font=dict(size=14, color="#4b5563"),
    )

    fecha_fin_visible = max(pronostico["fecha_semana"].iloc[-1] for pronostico in pronosticos.values())
    if contexto_real is not None and not contexto_real.empty:
        fecha_fin_visible = max(fecha_fin_visible, contexto_real["fecha_semana"].iloc[-1])
    semanas_visibles = min(len(serie), _SEMANAS_VISTA_INICIAL)
    inicio_visible = serie["fecha_semana"].iloc[-semanas_visibles]

    fig.update_layout(
        xaxis=dict(
            title="Semana epidemiológica (fecha de inicio)",
            range=[inicio_visible, fecha_fin_visible + pd.Timedelta(weeks=1)],
            rangeslider=dict(visible=True, thickness=0.08),
        ),
        yaxis=dict(title=etiqueta_eje, rangemode="tozero"),
        margin=dict(l=0, r=10, b=70),
        height=560,
    )
    return fig


# ---------------------------------------------------------------------------
# Fundamentacion: secciones de docs/pronostico.md con graficas del modelo activo
# ---------------------------------------------------------------------------

_PESTANAS_FUNDAMENTACION = [
    ("Resumen", [1, 2]),
    ("Ciclo de vida y formatos", [3, 4, 5]),
    ("División y evaluación", [6, 7, 8]),
    ("Pronóstico en vivo", [9, 11]),
    ("Métricas y persistencia", [10, 12, 13]),
    ("Clima y estudio de modelado", [14, 15]),
]


def _carpeta_y_registros(activo: dict):
    carpeta = almacen_modelos.ruta_version(PATOLOGIA, activo["modelo"], activo["version"])
    registros = None
    if es_formato_vigente(activo["manifest"]):
        registros = _registros_prueba(activo["modelo"], activo["version"])
    return carpeta, registros


def _marcador_diagrama_ciclo_de_vida(activo: dict) -> None:
    azul = AZUL_INSTITUCIONAL
    naranja = NARANJA_INSTITUCIONAL
    gris = _COLOR_GRIS
    diagrama = f"""
    digraph {{
        rankdir=LR;
        node [shape=box, style="rounded,filled", fontcolor=white, fontsize=12, fontname="Helvetica"];
        edge [color="{gris}"];
        A [label="A. Entrenamiento\\nGestión o fuera de la app", fillcolor="{azul}"];
        B [label="B. Evaluación\\nmodelo de evaluación (85 %)\\npronostica la prueba (15 %)", fillcolor="{naranja}"];
        CSV [label="pronosticos_prueba.csv\\n+ métricas en el manifest", fillcolor="{naranja}"];
        C [label="C. Exportación\\nmodelo definitivo (100 %)\\nformato nativo + manifest", fillcolor="{azul}"];
        D [label="D. Importación\\nrevisa y carga\\n(sin entrenar)", fillcolor="{gris}"];
        E [label="E. Inferencia\\npróximas 6 semanas\\n(sin entrenar)", fillcolor="{gris}"];
        H [label="Semana pasada\\n(resultados individuales)", fillcolor="{naranja}"];
        R [label="±RMSE por horizonte\\n(métricas de la prueba)", fillcolor="{naranja}"];
        A -> B -> CSV;
        B -> C -> D -> E;
        CSV -> H;
        CSV -> R -> E;
    }}
    """
    st.graphviz_chart(diagrama, width="stretch")
    st.caption("Azul: entrenamiento. Naranja: evaluación en la prueba y lo que sale de ella. Gris: uso del modelo ya entrenado.")


def _marcador_arbol_zip(activo: dict) -> None:
    carpeta, _ = _carpeta_y_registros(activo)
    if not es_formato_vigente(activo["manifest"]):
        return
    st.markdown(f"Paquete real de {activo['nombre']} (versión {activo['version']}):")
    st.code(documentacion.arbol_del_paquete(carpeta, activo["manifest"]), language="text")


def _marcador_ejemplos_archivos(activo: dict) -> None:
    carpeta, _ = _carpeta_y_registros(activo)
    if not es_formato_vigente(activo["manifest"]):
        return
    st.markdown(f"Contenido real de cada archivo de {activo['nombre']}:")
    for archivo in documentacion.ejemplos_de_archivos(carpeta, activo["manifest"]):
        with st.expander(archivo["titulo"]):
            st.code(archivo["contenido"], language=archivo["lenguaje"])


def _fecha_corta(fecha: pd.Timestamp) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{meses[fecha.month - 1]} {fecha.year}"


def _marcador_linea_de_tiempo(activo: dict) -> None:
    manifest = activo["manifest"]
    rango = manifest.get("rango", {})
    prueba = manifest.get("prueba", {})
    if not rango.get("fecha_primera_semana") or not prueba.get("inicio_prueba"):
        return
    primera = pd.Timestamp(rango["fecha_primera_semana"])
    ultima = pd.Timestamp(rango["fecha_ultima_semana"])
    inicio_prueba = pd.Timestamp(prueba["inicio_prueba"])
    fin_prueba = pd.Timestamp(prueba["fin_prueba"])
    fin_entrenamiento = inicio_prueba - pd.Timedelta(weeks=1)
    fin_en_vivo = ultima + pd.Timedelta(weeks=HORIZONTE_MAXIMO_SEMANAS)

    etapas = pd.DataFrame([
        {
            "Etapa": "Modelo de evaluación: entrenamiento",
            "Inicio": primera,
            "Fin": fin_entrenamiento,
            "Texto": f"{_fecha_corta(primera)} a {_fecha_corta(fin_entrenamiento)} (85 %)",
            "Grupo": "entrenamiento",
        },
        {
            "Etapa": "Prueba: orígenes móviles",
            "Inicio": inicio_prueba,
            "Fin": fin_prueba,
            "Texto": f"{_fecha_corta(inicio_prueba)} a {_fecha_corta(fin_prueba)} (15 %)",
            "Grupo": "prueba",
        },
        {
            "Etapa": "Modelo definitivo: entrenamiento",
            "Inicio": primera,
            "Fin": ultima,
            "Texto": f"{_fecha_corta(primera)} a {_fecha_corta(ultima)} (100 %)",
            "Grupo": "definitivo",
        },
        {
            "Etapa": "Pronóstico en vivo",
            "Inicio": ultima + pd.Timedelta(weeks=1),
            "Fin": fin_en_vivo,
            "Texto": f"{HORIZONTE_MAXIMO_SEMANAS} semanas",
            "Grupo": "en_vivo",
        },
    ])
    colores = {
        "entrenamiento": _color_translucido(AZUL_INSTITUCIONAL, 0.45),
        "prueba": NARANJA_INSTITUCIONAL,
        "definitivo": AZUL_INSTITUCIONAL,
        "en_vivo": _COLOR_GRIS,
    }
    figura = px.timeline(
        etapas, x_start="Inicio", x_end="Fin", y="Etapa", color="Grupo", color_discrete_map=colores, text="Texto"
    )
    figura.update_traces(textposition="inside", insidetextanchor="middle", hovertemplate="%{text}<extra></extra>")
    figura.update_yaxes(autorange="reversed", title=None)
    figura.update_xaxes(title=None)
    figura.update_layout(showlegend=False, height=330, bargap=0.25, margin=dict(l=0, r=10))
    mostrar_grafica(
        figura,
        "División temporal de la versión activa",
        f"Dengue · Magdalena · {activo['nombre']} · versión {activo['version']}",
        key="fundamentacion_linea_de_tiempo",
    )


def _marcador_origenes_moviles(activo: dict) -> None:
    """Tres semanas de origen consecutivas, cada una con sus 6 pronosticos del
    CSV, en el tramo de la prueba donde mas subieron los casos."""
    _, registros = _carpeta_y_registros(activo)
    if registros is None:
        return
    serie = construir_serie_semanal_departamental(modulo_datos.obtener_datos(PATOLOGIA))
    reales = serie.set_index("fecha_semana")["casos"]
    conteo = registros.groupby("fecha_origen")["horizonte_semanas"].count()
    completos = sorted(conteo[conteo == HORIZONTE_MAXIMO_SEMANAS].index)
    if len(completos) < 3:
        return

    mejor = None
    mayor_subida = None
    for posicion in range(len(completos) - 2):
        origen = completos[posicion]
        sexta = registros[(registros["fecha_origen"] == origen) & (registros["horizonte_semanas"] == HORIZONTE_MAXIMO_SEMANAS)]
        subida = float(sexta["casos_reales"].iloc[0]) - float(reales.get(origen, 0))
        if mayor_subida is None or subida > mayor_subida:
            mayor_subida = subida
            mejor = posicion
    origenes = completos[mejor:mejor + 3]

    inicio = origenes[0] - pd.Timedelta(weeks=6)
    fin = origenes[-1] + pd.Timedelta(weeks=HORIZONTE_MAXIMO_SEMANAS + 1)
    tramo = serie[(serie["fecha_semana"] >= inicio) & (serie["fecha_semana"] <= fin)]

    figura = go.Figure()
    figura.add_trace(go.Scatter(
        x=tramo["fecha_semana"], y=tramo["casos"], mode="lines+markers",
        line=dict(color=COLOR_DATO_REAL, width=1.6), marker=dict(size=5, color=COLOR_DATO_REAL),
        name="Casos reales", hovertemplate="%{x|%d %b %Y} · %{y:,.0f}<extra>Real</extra>",
    ))
    colores = [AZUL_INSTITUCIONAL, NARANJA_INSTITUCIONAL, _COLOR_GRIS]
    for posicion, origen in enumerate(origenes):
        color = colores[posicion]
        filas = registros[registros["fecha_origen"] == origen].sort_values("horizonte_semanas")
        semana = Week.fromdate(origen.date(), system="CDC")
        nombre = f"Desde la semana {semana.week} de {semana.year}"
        figura.add_trace(go.Scatter(
            x=[origen] + filas["fecha_objetivo"].tolist(),
            y=[reales.get(origen)] + filas["pronostico_modelo"].tolist(),
            mode="lines+markers", line=dict(color=color, width=2.2, dash="dot"), marker=dict(size=8, color=color),
            name=nombre, hovertemplate=f"%{{x|%d %b %Y}} · %{{y:,.1f}}<extra>{nombre}</extra>",
        ))
        figura.add_trace(go.Scatter(
            x=[origen], y=[reales.get(origen)], mode="markers",
            marker=dict(size=15, color=color, line=dict(color=COLOR_DATO_REAL, width=2)),
            showlegend=False, hovertemplate=f"Dato real de partida · %{{y:,.0f}}<extra>{nombre}</extra>",
        ))
    figura.update_layout(
        xaxis=dict(title="Semana epidemiológica (fecha de inicio)"),
        yaxis=dict(title="Casos", rangemode="tozero"),
        height=430, margin=dict(l=0, r=10),
    )
    mostrar_grafica(
        figura,
        "Seis pronósticos desde cada semana de origen",
        f"Dengue · Magdalena · {activo['nombre']} · tres orígenes consecutivos de la prueba",
        key="fundamentacion_origenes_moviles",
    )
    st.markdown(
        "Cada círculo es el dato real de una semana de origen. Desde ahí salen sus 6 pronósticos "
        "(H1 a H6). Una semana después, el siguiente origen vuelve a partir del dato real."
    )


def _marcador_tabla_csv_ejemplo(activo: dict) -> None:
    _, registros = _carpeta_y_registros(activo)
    if registros is None:
        return
    conteo = registros.groupby("fecha_origen")["horizonte_semanas"].count()
    completos = sorted(conteo[conteo == HORIZONTE_MAXIMO_SEMANAS].index)
    ultimo = registros["fecha_origen"].max()
    st.markdown(
        f"Registros reales de {activo['nombre']}: {len(registros)} filas, {registros['fecha_origen'].nunique()} "
        "semanas de origen. Valores tal como están en el CSV (sin redondear)."
    )
    if completos:
        origen = completos[0]
        st.markdown(f"Una semana de origen con sus 6 horizontes ({formatear_fecha_larga(origen.isoformat())}):")
        st.dataframe(registros[registros["fecha_origen"] == origen], hide_index=True, width="stretch")
    st.markdown(f"Última semana de origen evaluable ({formatear_fecha_larga(ultimo.isoformat())}):")
    st.dataframe(registros[registros["fecha_origen"] == ultimo], hide_index=True, width="stretch")


def _marcador_ejemplo_metricas(activo: dict) -> None:
    _, registros = _carpeta_y_registros(activo)
    if registros is None:
        return
    manifest = activo["manifest"]
    h1 = registros[registros["horizonte_semanas"] == 1].sort_values("fecha_origen")
    muestra = h1.head(5)
    tabla = pd.DataFrame({
        "Semana objetivo": [_texto_semana(fecha) for fecha in muestra["fecha_objetivo"]],
        "y": muestra["casos_reales"].to_numpy(),
        "ŷ": muestra["pronostico_modelo"].to_numpy(),
        "|y − ŷ|": muestra["error_absoluto"].to_numpy(),
        "(y − ŷ)²": (muestra["casos_reales"] - muestra["pronostico_modelo"]).pow(2).to_numpy(),
        "APE (%)": muestra["error_porcentual"].to_numpy(),
    })
    st.markdown(f"Con los datos de {activo['nombre']}: los 5 primeros registros de H1 del CSV.")
    st.dataframe(tabla, hide_index=True, width="stretch")
    de_la_muestra = calcular_metricas(muestra["casos_reales"], muestra["pronostico_modelo"])
    suma_absolutos = float(muestra["error_absoluto"].sum())
    suma_cuadrados = float((muestra["casos_reales"] - muestra["pronostico_modelo"]).pow(2).sum())
    st.markdown(
        f"$$MAE = \\frac{{{suma_absolutos:.3f}}}{{5}} = {de_la_muestra['MAE']:.3f} \\qquad "
        f"RMSE = \\sqrt{{\\frac{{{suma_cuadrados:.3f}}}{{5}}}} = {de_la_muestra['RMSE']:.3f}$$"
    )

    completo = calcular_metricas(h1["casos_reales"], h1["pronostico_modelo"])
    declarado = _metricas_horizonte(manifest, 1)
    global_csv = calcular_metricas(registros["casos_reales"], registros["pronostico_modelo"])
    global_manifest = manifest.get("metricas_prueba", {}).get("global", {}).get("modelo", {})
    comprobacion = pd.DataFrame([
        {"Métrica": "H1 (todos sus registros)", "n": completo["n"], "RMSE desde el CSV": completo["RMSE"], "RMSE del manifest": declarado.get("RMSE"), "MAE desde el CSV": completo["MAE"], "MAE del manifest": declarado.get("MAE")},
        {"Métrica": "Global (H1 a H6)", "n": global_csv["n"], "RMSE desde el CSV": global_csv["RMSE"], "RMSE del manifest": global_manifest.get("RMSE"), "MAE desde el CSV": global_csv["MAE"], "MAE del manifest": global_manifest.get("MAE")},
    ])
    st.markdown("Comprobación: las métricas recalculadas aquí desde el CSV coinciden con las del manifest.")
    st.dataframe(comprobacion, hide_index=True, width="stretch")


def _marcador_tabla_persistencia(activo: dict) -> None:
    manifest = activo["manifest"]
    if not manifest.get("metricas_prueba"):
        return
    st.markdown(f"{activo['nombre']}, métricas de la prueba contra la persistencia en los mismos registros:")
    st.dataframe(tabla_metricas_global(manifest), hide_index=True, width="stretch", column_config=FORMATO_COLUMNAS_METRICAS)
    st.dataframe(tabla_metricas(manifest), hide_index=True, width="stretch", column_config=FORMATO_COLUMNAS_METRICAS)


_MARCADORES = {
    "diagrama_ciclo_de_vida": _marcador_diagrama_ciclo_de_vida,
    "arbol_zip": _marcador_arbol_zip,
    "ejemplos_archivos": _marcador_ejemplos_archivos,
    "linea_de_tiempo": _marcador_linea_de_tiempo,
    "origenes_moviles": _marcador_origenes_moviles,
    "tabla_csv_ejemplo": _marcador_tabla_csv_ejemplo,
    "ejemplo_metricas": _marcador_ejemplo_metricas,
    "tabla_persistencia": _marcador_tabla_persistencia,
}


def _mostrar_seccion(numero: int, secciones: dict, activo: dict | None) -> None:
    seccion = secciones.get(numero)
    if seccion is None:
        return
    st.markdown(f"#### {numero}. {seccion['titulo']}")
    for tipo, contenido in documentacion.partir_por_marcadores(seccion["contenido"]):
        if tipo == documentacion.TIPO_TEXTO:
            st.markdown(contenido)
        elif activo is not None and contenido in _MARCADORES:
            _MARCADORES[contenido](activo)


@st.dialog("Fundamentación del pronóstico", width="large")
def _dialogo_fundamentacion() -> None:
    secciones = documentacion.leer_secciones()
    activos = _modelos_activos()
    activo = None
    if activos:
        familia = st.selectbox(
            "Modelo activo para las gráficas y tablas de ejemplo",
            list(activos),
            format_func=lambda clave: _rotulo(clave, activos[clave]),
            key="fundamentacion_modelo",
        )
        activo = activos[familia]

    pestanas = st.tabs([titulo for titulo, _ in _PESTANAS_FUNDAMENTACION])
    for pestana, (_, numeros) in zip(pestanas, _PESTANAS_FUNDAMENTACION):
        with pestana:
            for numero in numeros:
                _mostrar_seccion(numero, secciones, activo)

    st.caption("Fuente: docs/pronostico.md del repositorio del tablero.")
    if st.button("Cerrar", width="stretch"):
        st.rerun()
