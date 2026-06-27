"""Apartado de Procesamientos: historial permanente de cargues, exitosos y fallidos.

Visible solo para Editor y Admin (lo gatea quien llama, segun core/auth/permisos.py).
Es la pieza permanente que complementa al banner efimero: si alguien cierra el
banner o no lo vio, el motivo de un fallo sigue consultable aqui.

Los procesamientos listos se muestran como filas neutras (no en verde): es un
historial largo, no un mensaje puntual, y el verde queda reservado para el
canal endemico (ver DESIGN.md). Los fallos si usan st.error: son la excepcion,
no la norma, y necesitan llamar la atencion para que alguien los corrija.
"""

import streamlit as st

from core.audit.procesamientos import listar_procesamientos


def mostrar_procesamientos(patologia: str) -> None:
    st.subheader(":material/task_alt: Procesamientos")

    procesamientos = listar_procesamientos(patologia=patologia)
    if not procesamientos:
        st.caption("Aqui vas a ver el historial de cargues en cuanto subas el primer archivo.")
        return

    for procesamiento in procesamientos:
        descripcion = (
            f"{procesamiento['fecha']} · {procesamiento['archivo_original']} "
            f"(anio {procesamiento['anio']}, codigo {procesamiento['codigo']}) · "
            f"subido por {procesamiento['usuario']}"
        )

        if procesamiento["estado"] == "listo":
            st.markdown(f":material/check_circle: {descripcion} · listo")
        else:
            motivo_fallo = procesamiento["motivo_fallo"] or "sin motivo registrado"
            st.error(f"{descripcion} · fallo. Motivo: {motivo_fallo}")
