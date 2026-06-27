"""Carga y cache del consolidado en la sesion del usuario.

Regla critica del CLAUDE.md (seccion "Manejo de cache y estado de sesion"):
- El consolidado se carga UNA vez y se mantiene en session_state.
- Filtrar opera sobre lo que ya esta en memoria; nunca relee el archivo.
- Recargar desde disco ocurre SOLO en tres momentos explicitos: el usuario
  pulsa "Actualizar", refresca la pagina, o inicia sesion. Un refresh de
  pagina o un login nuevo arrancan con session_state vacio, asi que
  cargar_si_falta() ya cubre esos dos casos sin logica adicional.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from core.storage import rutas
from core.storage.consolidado import cargar_consolidado

CLAVE_DATOS = "consolidado_por_patologia"
CLAVE_MTIME = "mtime_cargado_por_patologia"


def _leer_mtime(ruta: Path) -> float | None:
    if not ruta.exists():
        return None
    return ruta.stat().st_mtime


def _recargar_desde_disco(patologia: str) -> None:
    ruta = rutas.ruta_consolidado(patologia)
    consolidado = cargar_consolidado(ruta)
    if consolidado is None:
        consolidado = pd.DataFrame()

    st.session_state.setdefault(CLAVE_DATOS, {})[patologia] = consolidado
    st.session_state.setdefault(CLAVE_MTIME, {})[patologia] = _leer_mtime(ruta)


def cargar_si_falta(patologia: str) -> None:
    """Carga el consolidado a session_state solo si todavia no esta ahi en esta sesion."""
    if patologia in st.session_state.get(CLAVE_DATOS, {}):
        return
    _recargar_desde_disco(patologia)


def actualizar(patologia: str) -> None:
    """Recarga el consolidado desde disco de forma explicita (boton Actualizar)."""
    _recargar_desde_disco(patologia)


def obtener_datos(patologia: str) -> pd.DataFrame:
    """Devuelve el dataframe en memoria de la sesion para esta patologia. No toca el disco."""
    return st.session_state[CLAVE_DATOS][patologia]


def mtime_oficial(patologia: str) -> float | None:
    """Mtime actual del consolidado oficial en disco. Chequeo liviano: no lo lee, solo lo stat-ea."""
    ruta = rutas.ruta_consolidado(patologia)
    return _leer_mtime(ruta)


def hay_datos_nuevos(patologia: str) -> bool:
    """Compara el mtime del consolidado oficial contra el cargado en la sesion.

    Es un chequeo liviano (stat del archivo), no una relectura del consolidado.
    """
    mtime_actual = mtime_oficial(patologia)
    mtime_cargado = st.session_state.get(CLAVE_MTIME, {}).get(patologia)
    return mtime_actual != mtime_cargado
