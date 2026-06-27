"""Piezas activas de la patologia: eliminarlas (soft delete a papelera) o editarlas.

Editar no tiene formulario propio con campos de anio/codigo: selecciona la pieza
en la tabla y sube el archivo corregido para ese mismo anio+codigo. El worker
decide solo que ya existe una pieza activa y la reemplaza (ver gestion_subida.py).
"""

import pandas as pd
import streamlit as st

from core.audit.registro_piezas import listar_piezas_activas
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.gestion_subida import encolar_subida
from core.ingestion.papelera import mover_a_papelera
from core.registry import obtener_patologia
from core.storage import rutas

COLUMNAS_TABLA = {"anio": "Anio", "codigo": "Codigo", "archivo_original": "Archivo"}

CLAVE_EDITANDO = "piezas_editando"


def mostrar_piezas_activas(patologia: str, usuario) -> None:
    st.subheader(":material/folder_open: Piezas activas")

    piezas = listar_piezas_activas(patologia)
    if not piezas:
        st.caption(f"Aun no hay piezas activas. Sube el primer archivo de {patologia} para empezar.")
        return

    tabla = pd.DataFrame(piezas)[list(COLUMNAS_TABLA.keys())].rename(columns=COLUMNAS_TABLA)
    seleccion = st.dataframe(
        tabla,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"tabla_piezas_activas_{patologia}",
    )

    filas_seleccionadas = seleccion.selection.rows
    if not filas_seleccionadas:
        st.caption("Selecciona una fila de la tabla para editarla o eliminarla.")
        return

    pieza = piezas[filas_seleccionadas[0]]
    clave_pieza = f"{patologia}_{pieza['anio']}_{pieza['codigo']}"

    columna_editar, columna_eliminar = st.columns(2)
    with columna_editar:
        if st.button(
            "Editar (reemplazar archivo)",
            icon=":material/edit:",
            key=f"editar_{clave_pieza}",
            use_container_width=True,
        ):
            st.session_state.setdefault(CLAVE_EDITANDO, {})[clave_pieza] = True

    with columna_eliminar:
        if st.button(
            "Eliminar",
            icon=":material/delete:",
            key=f"eliminar_{clave_pieza}",
            use_container_width=True,
        ):
            _eliminar(patologia, pieza["anio"], pieza["codigo"], usuario)

    if st.session_state.get(CLAVE_EDITANDO, {}).get(clave_pieza):
        _mostrar_formulario_editar(patologia, pieza, usuario, clave_pieza)


def _mostrar_formulario_editar(patologia: str, pieza: dict, usuario, clave_pieza: str) -> None:
    anio = pieza["anio"]
    codigo = pieza["codigo"]

    with st.form(f"editar_pieza_{clave_pieza}"):
        st.caption(
            f"Subir version corregida de anio {anio}, codigo {codigo}. "
            f"Reemplaza por completo a {pieza['archivo_original']}; el historico de otros anios no se toca."
        )
        archivo_corregido = st.file_uploader("Archivo SIVIGILA (.xls o .xlsx)", type=["xls", "xlsx"])
        confirmado = st.form_submit_button("Confirmar y procesar", type="primary", icon=":material/check_circle:")

    if not confirmado:
        return

    if archivo_corregido is None:
        st.warning("Selecciona un archivo antes de confirmar.")
        return

    encolar_subida(patologia, anio, codigo, archivo_corregido, usuario)
    st.session_state[CLAVE_EDITANDO][clave_pieza] = False


def _eliminar(patologia: str, anio: int, codigo: int, usuario) -> None:
    plugin = obtener_patologia(patologia)
    mover_a_papelera(
        patologia,
        rutas.directorio_piezas(patologia),
        rutas.directorio_papelera(patologia),
        rutas.ruta_consolidado(patologia),
        plugin.columna_anio,
        plugin.columna_codigo,
        anio,
        codigo,
        usuario.nombre_usuario,
    )
    modulo_datos.actualizar(patologia)
    st.rerun()
