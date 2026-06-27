"""Piezas activas de la patologia, con boton para eliminarlas (soft delete a papelera).

Editar una pieza no tiene pantalla propia: subir un archivo con el mismo
anio+codigo de una pieza activa ya la reemplaza (ver gestion_subida.py); el
worker decide solo si es agregar o editar.
"""

import streamlit as st

from core.audit.registro_piezas import listar_piezas_activas
from core.dashboard_base import datos as modulo_datos
from core.ingestion.papelera import mover_a_papelera
from core.registry import obtener_patologia
from core.storage import rutas


def mostrar_piezas_activas(patologia: str, usuario) -> None:
    st.subheader(":material/folder_open: Piezas activas")

    piezas = listar_piezas_activas(patologia)
    if not piezas:
        st.caption(f"Aun no hay piezas activas. Sube el primer archivo de {patologia} para empezar.")
        return

    for pieza in piezas:
        anio = pieza["anio"]
        codigo = pieza["codigo"]
        clave = f"eliminar_{patologia}_{anio}_{codigo}"

        columna_info, columna_accion = st.columns([8, 2], vertical_alignment="center")
        with columna_info:
            st.write(f"Anio {anio}, codigo {codigo} · {pieza['archivo_original']}")
        with columna_accion:
            if st.button("Eliminar", icon=":material/delete:", key=clave, use_container_width=True):
                _eliminar(patologia, anio, codigo, usuario)


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
