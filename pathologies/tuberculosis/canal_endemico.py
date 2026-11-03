"""Canal endemico de dengue: casos agregados por semana epidemiologica, comparados
contra percentiles historicos de esa misma semana en anios anteriores (metodo
Bortman o cuartiles). No depende de poblacion en riesgo (eso es indicators.py).

A diferencia de clean.py (que deja un dato por caso), esto agrega sobre todo
el conjunto. Modulo de calculo puro: sin Streamlit, sin colores ni graficas
(eso vive en la vista, pathologies/dengue/views/situacion.py).

datos_procesados debe llegar ya acotado a un solo territorio (una subregion o
un municipio); la escala geografica es decision de quien llama.

Nomenclatura institucional de las 3 lineas (la vista las usa tal cual en las
graficas, ver situacion.py):

Metodo cuartiles (INS Colombia, no parametrico):
  Cuartil inferior (Q1/P25) = frontera Exito/Seguridad
  Mediana (Q2/P50)          = frontera Seguridad/Alerta
  Cuartil superior (Q3/P75) = frontera Alerta/Epidemia

Metodo Bortman (1999, parametrico, media geometrica):
  Se trabaja en escala logaritmica con correccion de Kirkwood (+1) para poder
  incluir semanas en cero. Limite inferior y superior son el intervalo de
  confianza al 95% de la media historica en esa escala, no +-1 desviacion
  estandar.
    Limite inferior IC 95% = exp(mu - t*DE/raiz(n)) - 1  frontera Exito/Seguridad
    Umbral estacional      = exp(mu) - 1                 frontera Seguridad/Alerta (media geometrica)
    Limite superior IC 95% = exp(mu + t*DE/raiz(n)) - 1  frontera Alerta/Epidemia

Los anios que entran a la linea base (anios_base) los elige explicitamente quien
llama, no este modulo: no hay ninguna deteccion automatica de anios atipicos
(ej. un brote epidemico), porque un brote real y un anio con dato incompleto se
ven parecido en las cifras crudas y solo una persona con el contexto puede
distinguirlos con certeza.
"""

import numpy as np
import pandas as pd

ZONA_EXITO = "Éxito"
ZONA_SEGURIDAD = "Seguridad"
ZONA_ALERTA = "Alerta"
ZONA_EPIDEMIA = "Epidemia"
ZONAS_ORDEN = [ZONA_EXITO, ZONA_SEGURIDAD, ZONA_ALERTA, ZONA_EPIDEMIA]

SEMANA_MIN = 1
SEMANA_MAX = 53

METODOS_DISPONIBLES = {"cuartiles", "bortman"}

# El INS Colombia recomienda una linea base historica de 5 a 7 anios: menos de 5
# no es estadisticamente confiable, mas de 7 diluye el comportamiento reciente.
# Se usan en calcular_situacion_actual_por_subregion (configuracion por defecto,
# ventana maxima) y en la vista (situacion.py, con ventana ajustable por la persona).
VENTANA_MINIMA = 5
VENTANA_MAXIMA = 7

# Nomenclatura institucional de las 3 lineas del canal, especifica por metodo
# (ver docstring del modulo). La vista la usa directamente en las graficas.
ETIQUETAS_LINEAS = {
    "cuartiles": {
        "inferior": "Cuartil inferior",
        "central": "Mediana",
        "superior": "Cuartil superior",
    },
    "bortman": {
        "inferior": "Límite inferior IC 95%",
        "central": "Umbral estacional",
        "superior": "Límite superior IC 95%",
    },
}

# Valor t de Student para IC95% bilateral con df = n-1 (Bortman, 1999).
# n=3..20: tabla exacta del articulo original. n>30: aproximacion normal z=1.96.
_TABLA_T_IC95 = {
    3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 7: 2.45,
    8: 2.36, 9: 2.31, 10: 2.26, 11: 2.23, 12: 2.20,
    13: 2.18, 14: 2.16, 15: 2.14, 16: 2.12, 17: 2.11,
    18: 2.10, 19: 2.09, 20: 2.09, 25: 2.06, 30: 2.04,
}


def _valor_t_ic95(n: int) -> float:
    if n in _TABLA_T_IC95:
        return _TABLA_T_IC95[n]
    if n > 30:
        return 1.96
    claves_menores = sorted(clave for clave in _TABLA_T_IC95 if clave <= n)
    claves_mayores = sorted(clave for clave in _TABLA_T_IC95 if clave >= n)
    clave_baja = claves_menores[-1] if claves_menores else min(_TABLA_T_IC95)
    clave_alta = claves_mayores[0] if claves_mayores else max(_TABLA_T_IC95)
    if clave_baja == clave_alta:
        return _TABLA_T_IC95[clave_baja]
    t_baja, t_alta = _TABLA_T_IC95[clave_baja], _TABLA_T_IC95[clave_alta]
    return t_baja + (t_alta - t_baja) * (n - clave_baja) / (clave_alta - clave_baja)


def _tabla_anio_semana(datos: pd.DataFrame) -> pd.DataFrame:
    """Pivotea a una tabla anio (filas) x semana epidemiologica 1-53 (columnas) con
    el conteo de casos. Las combinaciones anio+semana sin casos se llenan en 0, no
    se dejan nulas: que una semana no tenga casos notificados es un dato real para
    el calculo de percentiles, no informacion faltante.
    """
    conteo = datos.groupby(["ano", "semana"]).size().reset_index(name="casos")
    tabla = conteo.pivot(index="ano", columns="semana", values="casos")
    tabla = tabla.reindex(columns=range(SEMANA_MIN, SEMANA_MAX + 1), fill_value=0)
    return tabla.fillna(0)


def _bandas_cuartiles(tabla_base: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for semana in range(SEMANA_MIN, SEMANA_MAX + 1):
        valores = tabla_base[semana].to_numpy(dtype=float) if semana in tabla_base.columns else np.array([], dtype=float)
        if len(valores) == 0:
            filas.append({"semana": semana, "inferior": 0.0, "central": 0.0, "superior": 0.0})
            continue
        filas.append({
            "semana": semana,
            "inferior": float(np.percentile(valores, 25)),
            "central": float(np.percentile(valores, 50)),
            "superior": float(np.percentile(valores, 75)),
        })
    return pd.DataFrame(filas)


def _bandas_bortman(tabla_base: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for semana in range(SEMANA_MIN, SEMANA_MAX + 1):
        valores = tabla_base[semana].to_numpy(dtype=float) if semana in tabla_base.columns else np.array([], dtype=float)
        n = len(valores)
        if n < 2:
            central = float(max(0.0, valores[0])) if n == 1 else 0.0
            filas.append({"semana": semana, "inferior": 0.0, "central": central, "superior": central})
            continue
        # Correccion de Kirkwood (+1) para poder logaritmizar semanas en cero.
        log_valores = np.log(valores + 1.0)
        media = float(np.mean(log_valores))
        desviacion = float(np.std(log_valores, ddof=1))
        margen = _valor_t_ic95(n) * desviacion / np.sqrt(n)
        filas.append({
            "semana": semana,
            "inferior": float(max(0.0, np.exp(media - margen) - 1.0)),
            "central": float(max(0.0, np.exp(media) - 1.0)),
            "superior": float(np.exp(media + margen) - 1.0),
        })
    return pd.DataFrame(filas)


def _clasificar_zona(valor: float, fila_bandas: pd.Series) -> str:
    if pd.isna(valor):
        return ZONA_SEGURIDAD
    if valor < fila_bandas["inferior"]:
        return ZONA_EXITO
    if valor < fila_bandas["central"]:
        return ZONA_SEGURIDAD
    if valor < fila_bandas["superior"]:
        return ZONA_ALERTA
    return ZONA_EPIDEMIA


def calcular_canal_endemico(
    datos_procesados: pd.DataFrame,
    metodo: str,
    anio_vigilancia: int,
    anios_base: list[int],
) -> dict:
    """Implementacion dengue del contrato PathologyPlugin.calcular_canal_endemico.
    Ver core/registry.py para el contrato completo.
    """
    if metodo not in METODOS_DISPONIBLES:
        raise ValueError(f"Metodo de canal endemico desconocido: {metodo}")

    anios_base_pedidos = set(anios_base)
    tabla = _tabla_anio_semana(datos_procesados)

    # La linea base solo puede construirse con anios anteriores al anio de
    # vigilancia (nunca con el mismo anio ni con anios posteriores): el canal
    # endemico compara el presente contra el pasado, nunca contra el futuro.
    # Se aplica aqui como garantia, aunque venga distinto en anios_base.
    anios_base = sorted(
        int(anio) for anio in tabla.index if anio in anios_base_pedidos and anio < anio_vigilancia
    )
    tabla_base = tabla.loc[anios_base]

    if metodo == "cuartiles":
        bandas = _bandas_cuartiles(tabla_base)
    else:
        bandas = _bandas_bortman(tabla_base)

    casos_vigilancia = datos_procesados[datos_procesados["ano"] == anio_vigilancia]
    ultima_semana_observada = int(casos_vigilancia["semana"].max()) if not casos_vigilancia.empty else 0

    if ultima_semana_observada > 0 and anio_vigilancia in tabla.index:
        semanas_serie = list(range(SEMANA_MIN, ultima_semana_observada + 1))
        casos_serie = [float(tabla.loc[anio_vigilancia, semana]) for semana in semanas_serie]
        # zip en vez de iterrows: iterrows fuerza un dtype comun por fila y
        # convertiria "semana" (int) a float al compartir fila con "casos".
        zonas_serie = [
            _clasificar_zona(casos, bandas.iloc[semana - SEMANA_MIN])
            for semana, casos in zip(semanas_serie, casos_serie)
        ]
        serie_actual = pd.DataFrame({
            "semana": semanas_serie,
            "casos": casos_serie,
            "zona": zonas_serie,
        })
    else:
        # Sin datos para el anio de vigilancia: no se inventan semanas en cero
        # (regla del proyecto: "no disponible", nunca cero).
        serie_actual = pd.DataFrame(columns=["semana", "casos", "zona"])

    return {
        "bandas": bandas,
        "serie_actual": serie_actual,
        "anios_base": anios_base,
        "metodo": metodo,
    }


def calcular_situacion_actual_por_subregion(
    datos_con_subregion: pd.DataFrame,
    anio_vigilancia: int,
    anios_base: list[int],
    metodo: str = "cuartiles",
) -> pd.DataFrame:
    """Situacion (zona del canal endemico) de cada subregion en su propia ultima
    semana con datos observados de anio_vigilancia, contra la linea base historica
    anios_base. Alimenta el mapa 2.1 de la pestana Situacion (situacion.py).

    anio_vigilancia y anios_base los elige explicitamente quien llama (mismo
    principio que calcular_canal_endemico: esta funcion no decide por su cuenta
    que anio o linea base usar). Se aplican igual a las 5 subregiones, pero cada
    una calcula su propia ultima semana observada dentro de anio_vigilancia: si
    una subregion reporta con mas rezago que otra, su semana de referencia queda
    distinta, y eso se refleja en el resultado en vez de ocultarse.

    Una subregion sin datos en anio_vigilancia no aparece en el resultado (no se
    inventa una situacion sin datos).

    datos_con_subregion debe tener columna "subregion" ya derivada (ver
    filtros.py) y las columnas de caso habituales (ano, semana).

    Devuelve columnas: subregion, ano, semana, situacion.
    """
    filas = []
    for subregion, datos_subregion in datos_con_subregion.groupby("subregion"):
        resultado = calcular_canal_endemico(
            datos_subregion, metodo=metodo, anio_vigilancia=anio_vigilancia, anios_base=anios_base
        )
        serie_actual = resultado["serie_actual"]
        if serie_actual.empty:
            continue

        ultima_fila = serie_actual.iloc[-1]
        filas.append({
            "subregion": subregion,
            "ano": anio_vigilancia,
            "semana": int(ultima_fila["semana"]),
            "situacion": ultima_fila["zona"],
        })

    return pd.DataFrame(filas, columns=["subregion", "ano", "semana", "situacion"])
