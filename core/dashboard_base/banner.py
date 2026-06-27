"""Banner de "datos nuevos" (opcion B del CLAUDE.md).

Se puede cerrar con una x sin perder informacion: lo que generó el aviso ya
quedo registrado de forma permanente en Procesamientos, asi que cerrar el
banner no borra nada, solo deja de mostrarlo para esta version del dato.

El chequeo de "hay datos nuevos" es liviano (un stat del archivo, no una
relectura del consolidado), asi que se puede repetir en un fragmento con
temporizador sin violar la regla de cache de core/dashboard_base/datos.py.
"""

import streamlit as st

from core.dashboard_base import datos as modulo_datos

CLAVE_CERRADO = "banner_datos_nuevos_cerrado_para_mtime"


@st.fragment(run_every="4s")
def fragmento_banner_datos_nuevos(patologia: str) -> None:
    hay_nuevos = modulo_datos.hay_datos_nuevos(patologia)
    _mostrar_banner(patologia, hay_nuevos)


def _mostrar_banner(patologia: str, hay_datos_nuevos: bool) -> None:
    mtime_actual = modulo_datos.mtime_oficial(patologia)
    cerrados_por_patologia = st.session_state.setdefault(CLAVE_CERRADO, {})

    if not hay_datos_nuevos:
        return

    if cerrados_por_patologia.get(patologia) == mtime_actual:
        return

    columna_mensaje, columna_actualizar, columna_cerrar = st.columns([8, 2, 1])

    with columna_mensaje:
        st.info(":material/new_releases: Hay datos nuevos disponibles para esta patologia.")

    with columna_actualizar:
        if st.button(
            "Actualizar", type="primary", icon=":material/refresh:",
            key=f"actualizar_banner_{patologia}", use_container_width=True,
        ):
            modulo_datos.actualizar(patologia)
            st.rerun()

    with columna_cerrar:
        if st.button("", icon=":material/close:", help="Cerrar este aviso", key=f"cerrar_banner_{patologia}"):
            cerrados_por_patologia[patologia] = mtime_actual
            st.rerun()
