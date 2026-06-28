"""Apartado de Procesamientos: historial permanente de cargues, exitosos y fallidos.

Visible solo para Editor y Admin (lo gatea quien llama, segun core/auth/permisos.py).
Es la pieza permanente que complementa al banner efimero: si alguien cierra el
banner o no lo vio, el motivo de un fallo sigue consultable aqui.

La tabla muestra el estado como texto neutro ("listo" o "fallo"), sin colorear
filas completas: el verde y el rojo quedan reservados para el canal endemico
(ver DESIGN.md). Cada fallo trae su motivo en la propia tabla.
"""

import pandas as pd
import streamlit as st

from core.audit.procesamientos import listar_procesamientos
from core.audit.zona_horaria import formatear_fecha_local

COLUMNAS_TABLA = {
    "fecha": "Fecha",
    "archivo_original": "Archivo",
    "anio": "Anio",
    "codigo": "Codigo",
    "usuario": "Usuario",
    "estado": "Estado",
    "motivo_fallo": "Motivo del fallo",
}


def mostrar_procesamientos(patologia: str) -> None:
    st.subheader(":material/task_alt: Procesamientos")

    procesamientos = listar_procesamientos(patologia=patologia)
    if not procesamientos:
        st.caption("Aqui vas a ver el historial de cargues en cuanto subas el primer archivo.")
        return

    tabla = pd.DataFrame(procesamientos)
    tabla["motivo_fallo"] = tabla["motivo_fallo"].fillna("")
    tabla["fecha"] = tabla["fecha"].map(formatear_fecha_local)
    tabla = tabla[list(COLUMNAS_TABLA.keys())].rename(columns=COLUMNAS_TABLA)

    st.dataframe(tabla, hide_index=True, width="stretch", height=280)
