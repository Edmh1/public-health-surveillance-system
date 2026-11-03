"""KPIs de tuberculosis: cocientes simples sobre el consolidado filtrado.

Formulas:
- Incidencia TB = (casos 810+820 / poblacion en riesgo) x 100.000
- Mortalidad por TB = (muertes TB / poblacion en riesgo) x 100.000
- Letalidad TB = (muertes TB / total casos 810+820) x 100
- % TB resistente = (casos 825 / total casos 810+820) x 100

La muerte se identifica por presencia de fecha de defuncion (fec_def no nula).
El codigo 825 (farmacoresistente) no se suma al total: es un subregistro de
resistencia sobre casos ya notificados como 810 o 820.
"""

from typing import Any

import pandas as pd

from pathologies.tuberculosis.geografia import obtener_mapeo_subregion
from pathologies.tuberculosis.poblacion import obtener_poblacion_por_municipio_anio

COD_TB_EXTRAPULMONAR = 810
COD_TB_PULMONAR = 820
COD_TB_FARMACORESISTENTE = 825
CODIGOS_TB = {COD_TB_EXTRAPULMONAR, COD_TB_PULMONAR}


def _poblacion_en_riesgo(anios: list[int], subregiones: list[str] | None) -> float | None:
    """Suma la poblacion en riesgo (persona-anios) de los municipios en alcance
    para el periodo filtrado. None si falta poblacion para alguno de los anios.
    TB usa TODOS los municipios del Magdalena (sin filtro de transmision vectorial).
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
    """Implementacion TB del contrato PathologyPlugin.calcular_indicadores.
    
    total_casos = 810 (extrapulmonar) + 820 (pulmonar). 825 (farmacoresistente)
    no se suma: es un subregistro de resistencia sobre casos ya notificados.
    """
    casos = datos_filtrados[datos_filtrados["cod_eve"].isin(CODIGOS_TB)]
    resistentes = datos_filtrados[datos_filtrados["cod_eve"] == COD_TB_FARMACORESISTENTE]

    # Mortalidad: casos con fecha de defuncion no nula (solo sobre 810+820)
    if "fec_def" in datos_filtrados.columns:
        muertes = datos_filtrados[datos_filtrados["cod_eve"].isin(CODIGOS_TB) & datos_filtrados["fec_def"].notna()]
        total_muertes = len(muertes)
    else:
        total_muertes = 0

    total_casos = len(casos)
    total_resistentes = len(resistentes)

    letalidad = (total_muertes / total_casos * 100) if total_casos else None

    pct_resistentes = (total_resistentes / total_casos * 100) if total_casos else None

    municipios_filtrados = filtros.get("nom_mun_o")
    if municipios_filtrados:
        incidencia = None
        mortalidad_tasa = None
        poblacion_en_riesgo = None
    else:
        anios_filtrados = filtros.get("ano") or []
        subregiones_filtradas = filtros.get("subregion")
        poblacion_en_riesgo = _poblacion_en_riesgo(anios_filtrados, subregiones_filtradas)
        if poblacion_en_riesgo:
            incidencia = total_casos / poblacion_en_riesgo * 100_000
            mortalidad_tasa = total_muertes / poblacion_en_riesgo * 100_000
        else:
            incidencia = None
            mortalidad_tasa = None

    return {
        "incidencia": incidencia,
        "mortalidad": mortalidad_tasa,
        "letalidad": letalidad,
        "pct_resistentes": pct_resistentes,
        "poblacion_en_riesgo": poblacion_en_riesgo,
        "total_casos": total_casos,
        "total_muertes": total_muertes,
        "total_resistentes": total_resistentes,
        "total_pulmonar": int((casos["cod_eve"] == COD_TB_PULMONAR).sum()),
        "total_extrapulmonar": int((casos["cod_eve"] == COD_TB_EXTRAPULMONAR).sum()),
    }
