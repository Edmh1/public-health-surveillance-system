"""KPIs de dengue: cocientes simples sobre el consolidado filtrado.

Formulas (Listado de Graficas e Indicadores):
- Incidencia de dengue = (casos 210+220 / poblacion en riesgo) x 100.000
- Mortalidad por dengue = (casos fatales 580 / poblacion en riesgo) x 100.000
- Letalidad por dengue = (casos fatales 580 / total casos 210+220) x 100
- Letalidad por dengue grave = (casos fatales 580 / total casos 220) x 100
- % Confirmados de dengue grave = (confirmados 220 / total notificados 220) x 100
- % Hospitalizados de dengue grave = (hospitalizados 220 / total casos 220) x 100

Regla central: si falta una pieza necesaria para un indicador (poblacion, o el
codigo 580), ese indicador queda "no disponible" (None), nunca en cero: el
sistema no publica numeros falsos.

Incidencia y mortalidad dependen de poblacion en riesgo, que solo es confiable
a escala subregion o mas amplia (nunca municipio: a esa escala el denominador
poblacional no refleja donde se atendio al paciente, por el desplazamiento de
pacientes entre municipios). Si el filtro geografico esta acotado a
municipio(s) especificos, estos dos indicadores quedan "no disponible" aunque
haya poblacion: el problema no es el dato, es que a esa escala no es confiable.

Letalidad, letalidad grave y los dos porcentajes de dengue grave son cocientes
de columnas de caso (no dependen de poblacion), asi que se calculan igual sin
importar la escala geografica del filtro.

Cuando el filtro de anios cubre varios anios, la poblacion en riesgo se suma
anio a anio (persona-anios: poblacion de cada anio del periodo, sumada), no se
usa un solo anio de referencia. Es la practica estandar para tasas de periodos
multi-anio y mantiene el KPI consistente con el resto del dashboard, donde
todos los KPIs agregan sobre lo que este filtrado en cada momento.
"""

from typing import Any

import pandas as pd

from pathologies.dengue.geografia import obtener_mapeo_subregion
from pathologies.dengue.poblacion import obtener_poblacion_por_municipio_anio

COD_DENGUE = 210
COD_DENGUE_GRAVE = 220
COD_MORTALIDAD = 580
CODIGOS_CASOS = {COD_DENGUE, COD_DENGUE_GRAVE}


def _poblacion_en_riesgo(anios: list[int], subregiones: list[str] | None) -> float | None:
    """Suma la poblacion en riesgo (persona-anios) de los municipios en alcance
    para el periodo filtrado. None si falta poblacion para alguno de los anios
    pedidos (una suma parcial daria un numero enganosamente bajo).
    """
    if not anios:
        return None

    poblacion = obtener_poblacion_por_municipio_anio()

    if subregiones:
        mapeo_subregion = obtener_mapeo_subregion()
        municipios_en_alcance = {
            cod_municipio for cod_municipio, subregion in mapeo_subregion.items()
            if subregion in subregiones
        }
        poblacion = poblacion[poblacion["cod_mun_completo"].isin(municipios_en_alcance)]

    poblacion_periodo = poblacion[poblacion["ano"].isin(anios)]

    anios_con_poblacion = set(poblacion_periodo["ano"].unique())
    if not set(anios).issubset(anios_con_poblacion):
        return None

    return float(poblacion_periodo["poblacion"].sum())


def calcular_indicadores(datos_filtrados: pd.DataFrame, filtros: dict[str, Any]) -> dict[str, Any]:
    """Implementacion dengue del contrato PathologyPlugin.calcular_indicadores.
    Ver core/registry.py para el contrato completo.
    """
    casos = datos_filtrados[datos_filtrados["cod_eve"].isin(CODIGOS_CASOS)]
    graves = datos_filtrados[datos_filtrados["cod_eve"] == COD_DENGUE_GRAVE]
    muertes = datos_filtrados[datos_filtrados["cod_eve"] == COD_MORTALIDAD]

    total_casos = len(casos)
    total_graves = len(graves)
    total_muertes = len(muertes)

    letalidad = (total_muertes / total_casos * 100) if total_casos else None
    letalidad_grave = (total_muertes / total_graves * 100) if total_graves else None

    if total_graves and "confirmados" in graves.columns:
        confirmados_graves = int((graves["confirmados"] == 1).sum())
        pct_confirmados_grave = confirmados_graves / total_graves * 100
    else:
        pct_confirmados_grave = None

    if total_graves and "pac_hos" in graves.columns:
        hospitalizados_graves = int((graves["pac_hos"] == 1).sum())
        pct_hospitalizados_grave = hospitalizados_graves / total_graves * 100
    else:
        pct_hospitalizados_grave = None

    municipios_filtrados = filtros.get("nom_mun_o")
    if municipios_filtrados:
        # Tasa no confiable a escala municipio (ver docstring del modulo).
        incidencia = None
        mortalidad = None
        poblacion_en_riesgo = None
    else:
        anios_filtrados = filtros.get("ano") or []
        subregiones_filtradas = filtros.get("subregion")
        poblacion_en_riesgo = _poblacion_en_riesgo(anios_filtrados, subregiones_filtradas)
        if poblacion_en_riesgo:
            incidencia = total_casos / poblacion_en_riesgo * 100_000
            mortalidad = total_muertes / poblacion_en_riesgo * 100_000
        else:
            incidencia = None
            mortalidad = None

    return {
        "incidencia": incidencia,
        "mortalidad": mortalidad,
        "letalidad": letalidad,
        "letalidad_grave": letalidad_grave,
        "pct_confirmados_grave": pct_confirmados_grave,
        "pct_hospitalizados_grave": pct_hospitalizados_grave,
        "poblacion_en_riesgo": poblacion_en_riesgo,
        "total_casos": total_casos,
        "total_graves": total_graves,
        "total_muertes": total_muertes,
    }
