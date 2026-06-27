"""Vista de bitacora: quien hizo que movimiento, sobre que pieza, y cuando.

Visible solo para Editor y Admin (lo gatea quien llama, segun core/auth/permisos.py).
"""

import streamlit as st

from core.audit.bitacora import listar_movimientos


def mostrar_bitacora(patologia: str) -> None:
    st.subheader("Bitacora")

    movimientos = listar_movimientos(patologia=patologia)
    if not movimientos:
        st.caption("Todavia no hay movimientos registrados para esta patologia.")
        return

    for movimiento in movimientos:
        descripcion = (
            f"{movimiento['fecha']} - {movimiento['accion']} - "
            f"anio {movimiento['anio']}, codigo {movimiento['codigo']} - "
            f"por {movimiento['usuario']}"
        )
        st.write(descripcion)
