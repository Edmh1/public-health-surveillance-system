"""Apartado de Procesamientos: historial permanente de cargues, exitosos y fallidos.

Visible solo para Editor y Admin (lo gatea quien llama, segun core/auth/permisos.py).
Es la pieza permanente que complementa al banner efimero: si alguien cierra el
banner o no lo vio, el motivo de un fallo sigue consultable aqui.
"""

import streamlit as st

from core.audit.procesamientos import listar_procesamientos


def mostrar_procesamientos(patologia: str) -> None:
    st.subheader("Procesamientos")

    procesamientos = listar_procesamientos(patologia=patologia)
    if not procesamientos:
        st.caption("Todavia no hay procesamientos registrados para esta patologia.")
        return

    for procesamiento in procesamientos:
        descripcion = (
            f"{procesamiento['fecha']} - {procesamiento['archivo_original']} "
            f"(anio {procesamiento['anio']}, codigo {procesamiento['codigo']}) - "
            f"subido por {procesamiento['usuario']}"
        )

        if procesamiento["estado"] == "listo":
            st.success(f"{descripcion} - listo")
        else:
            motivo_fallo = procesamiento["motivo_fallo"] or "sin motivo registrado"
            st.error(f"{descripcion} - fallo. Motivo: {motivo_fallo}")
