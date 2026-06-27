"""Vista de bitacora: quien hizo que movimiento, sobre que pieza, y cuando.

Visible solo para Editor y Admin (lo gatea quien llama, segun core/auth/permisos.py).
"""

import pandas as pd
import streamlit as st

from core.audit.bitacora import listar_movimientos

ETIQUETAS_ACCION = {
    "agregar": "Agregar",
    "editar": "Editar",
    "eliminar": "Eliminar",
    "restaurar": "Restaurar",
    "eliminar_permanente": "Eliminar para siempre",
}

COLUMNAS_TABLA = {
    "fecha": "Fecha",
    "accion": "Accion",
    "anio": "Anio",
    "codigo": "Codigo",
    "usuario": "Usuario",
}


def mostrar_bitacora(patologia: str) -> None:
    st.subheader(":material/history: Bitacora")

    movimientos = listar_movimientos(patologia=patologia)
    if not movimientos:
        st.caption("Aqui vas a ver el historial de movimientos en cuanto haya el primero.")
        return

    tabla = pd.DataFrame(movimientos)
    tabla["accion"] = tabla["accion"].map(lambda accion: ETIQUETAS_ACCION.get(accion, accion))
    tabla = tabla[list(COLUMNAS_TABLA.keys())].rename(columns=COLUMNAS_TABLA)

    st.dataframe(tabla, hide_index=True, width="stretch", height=280)
