"""Vista de bitacora: quien hizo que movimiento, sobre que pieza, y cuando.

Visible solo para Editor y Admin (lo gatea quien llama, segun core/auth/permisos.py).
"""

import streamlit as st

from core.audit.bitacora import listar_movimientos

ICONOS_POR_ACCION = {
    "agregar": ":material/add_circle:",
    "editar": ":material/edit:",
    "eliminar": ":material/delete:",
    "restaurar": ":material/restore:",
    "eliminar_permanente": ":material/delete_forever:",
}


def mostrar_bitacora(patologia: str) -> None:
    st.subheader(":material/history: Bitacora")

    movimientos = listar_movimientos(patologia=patologia)
    if not movimientos:
        st.caption("Aqui vas a ver el historial de movimientos en cuanto haya el primero.")
        return

    for movimiento in movimientos:
        icono = ICONOS_POR_ACCION.get(movimiento["accion"], ":material/circle:")
        descripcion = (
            f"{icono} {movimiento['fecha']} · {movimiento['accion']} · "
            f"anio {movimiento['anio']}, codigo {movimiento['codigo']} · "
            f"por {movimiento['usuario']}"
        )
        st.markdown(descripcion)
