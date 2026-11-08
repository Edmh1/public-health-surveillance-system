"""Pronostico desde la ultima semana de la serie, con cualquier modelo del catalogo."""

import pandas as pd

from core.registry import ModeloPronostico
from pathologies.dengue.pronostico.configuracion import (
    HORIZONTE_MAXIMO_SEMANAS,
    HORIZONTE_RECOMENDADO_SEMANAS,
)
from pathologies.dengue.pronostico.serie import agregar_semana_epidemiologica


def pronosticar(
    modelo: ModeloPronostico, serie: pd.DataFrame, horizonte_semanas: int = HORIZONTE_RECOMENDADO_SEMANAS
) -> pd.DataFrame:
    """Pronostico de las proximas horizonte_semanas semanas desde la ultima
    semana de la serie. Devuelve columnas: fecha_semana, ano, semana,
    horizonte_semanas, casos_pronosticados.

    Sin banda de incertidumbre: solo Prophet la produce de forma nativa y
    mostrarla en uno de los modelos los haria ver de distinta calidad. La
    incertidumbre se expresa como el error esperado de cada horizonte, medido en
    la validacion walk-forward (igual de valida para todos).
    """
    horizonte = int(min(max(horizonte_semanas, 1), HORIZONTE_MAXIMO_SEMANAS))
    serie_ordenada = serie.sort_values("fecha_semana").reset_index(drop=True)
    origen = len(serie_ordenada) - 1
    trayectorias = modelo.pronosticar_trayectorias(serie_ordenada, [origen], horizonte)
    trayectoria = trayectorias[0]

    ultima_fecha = pd.Timestamp(serie_ordenada["fecha_semana"].iloc[-1])
    pasos = list(range(1, horizonte + 1))
    fechas = [ultima_fecha + pd.Timedelta(weeks=paso) for paso in pasos]
    pronostico = pd.DataFrame({
        "fecha_semana": fechas,
        "horizonte_semanas": pasos,
        "casos_pronosticados": trayectoria,
    })
    pronostico = agregar_semana_epidemiologica(pronostico)
    return pronostico[["fecha_semana", "ano", "semana", "horizonte_semanas", "casos_pronosticados"]]
