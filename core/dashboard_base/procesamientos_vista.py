"""Apartado de Procesamientos: historial permanente de cargues, exitosos y fallidos.

Rediseñado con badges de estado, busqueda libre y paginacion de 10 en 10.
"""

import streamlit as st

from core.audit.procesamientos import listar_procesamientos
from core.audit.zona_horaria import formatear_fecha_local
from core.dashboard_base.paginacion import buscar_y_paginar, mostrar_controles_paginacion


def mostrar_procesamientos(patologia: str) -> None:
    st.subheader(":material/task_alt: Procesamientos")

    procesamientos = listar_procesamientos(patologia=patologia)
    if not procesamientos:
        st.caption("Aqui apareceran los cargues en cuanto subas el primer archivo.")
        return

    # Resumen rapido (exitosos / con error)
    n_listo = sum(1 for p in procesamientos if p["estado"] == "listo")
    n_fallo = len(procesamientos) - n_listo
    col_ok, col_err, col_total = st.columns(3)
    col_ok.metric("Exitosos", n_listo)
    col_err.metric("Con error", n_fallo)
    col_total.metric("Total", len(procesamientos))

    st.space("small")

    pagina_items, pagina, total = buscar_y_paginar(
        procesamientos,
        clave="procesamientos",
        campos_busqueda=["archivo_original", "anio", "codigo", "usuario"],
        placeholder="Buscar por archivo, año, código o usuario...",
    )

    for proc in pagina_items:
        _mostrar_tarjeta_procesamiento(proc)

    mostrar_controles_paginacion("procesamientos", pagina, total)


def _mostrar_tarjeta_procesamiento(proc: dict) -> None:
    with st.container(border=True):
        col_info, col_estado = st.columns([4, 1], vertical_alignment="center")

        with col_info:
            st.markdown(f"**{proc['archivo_original']}**")
            st.caption(
                f"Año {proc['anio']} · Código {proc['codigo']} · "
                f"{formatear_fecha_local(proc['fecha'])} · {proc['usuario']}"
            )
            if proc["estado"] == "fallo" and proc.get("motivo_fallo"):
                with st.expander(":material/error: Ver motivo del error"):
                    st.code(proc["motivo_fallo"], language=None)

        with col_estado:
            if proc["estado"] == "listo":
                st.badge("Procesado", icon=":material/check_circle:", color="blue")
            else:
                st.badge("Error", icon=":material/error:", color="red")
