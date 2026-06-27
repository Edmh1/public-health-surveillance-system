"""Papelera: restaurar (con el conflicto si ya hay una pieza activa del mismo
anio+codigo) o eliminar para siempre (solo Admin, con confirmacion explicita).
"""

import streamlit as st

from core.auth.permisos import PERMISO_ELIMINAR_PARA_SIEMPRE, tiene_permiso
from core.audit.registro_piezas import listar_piezas_en_papelera
from core.dashboard_base import datos as modulo_datos
from core.ingestion.papelera import ConflictoDeRestauracion, eliminar_para_siempre, restaurar_pieza
from core.registry import obtener_patologia
from core.storage import rutas

CLAVE_CONFLICTO_RESTAURAR = "papelera_conflicto_restaurar"
CLAVE_CONFIRMAR_ELIMINAR = "papelera_confirmar_eliminar_para_siempre"


def mostrar_papelera(patologia: str, usuario) -> None:
    st.subheader("Papelera")

    piezas = listar_piezas_en_papelera(patologia)
    if not piezas:
        st.caption("La papelera esta vacia para esta patologia.")
        return

    for pieza in piezas:
        _mostrar_fila(patologia, pieza, usuario)


def _mostrar_fila(patologia: str, pieza: dict, usuario) -> None:
    anio = pieza["anio"]
    codigo = pieza["codigo"]
    clave = f"{patologia}_{anio}_{codigo}"

    columna_info, columna_restaurar, columna_eliminar = st.columns([6, 2, 2])
    with columna_info:
        st.write(f"Anio {anio}, codigo {codigo} - {pieza['archivo_original']}")

    with columna_restaurar:
        if st.button("Restaurar", key=f"restaurar_{clave}"):
            _restaurar(patologia, anio, codigo, usuario, clave, forzar=False)

    with columna_eliminar:
        if tiene_permiso(usuario.rol, PERMISO_ELIMINAR_PARA_SIEMPRE):
            if st.button("Eliminar para siempre", key=f"eliminar_siempre_{clave}"):
                st.session_state.setdefault(CLAVE_CONFIRMAR_ELIMINAR, {})[clave] = True

    if st.session_state.get(CLAVE_CONFLICTO_RESTAURAR, {}).get(clave):
        _mostrar_confirmacion_restaurar(patologia, anio, codigo, usuario, clave)

    if st.session_state.get(CLAVE_CONFIRMAR_ELIMINAR, {}).get(clave):
        _mostrar_confirmacion_eliminar(patologia, anio, codigo, usuario, clave)


def _mostrar_confirmacion_restaurar(patologia: str, anio: int, codigo: int, usuario, clave: str) -> None:
    st.warning("Ya existe una pieza activa con el mismo anio y codigo. Restaurar la reemplazara.")
    columna_si, columna_no = st.columns(2)
    with columna_si:
        if st.button("Si, reemplazar", key=f"confirmar_restaurar_si_{clave}"):
            _restaurar(patologia, anio, codigo, usuario, clave, forzar=True)
    with columna_no:
        if st.button("Cancelar", key=f"confirmar_restaurar_no_{clave}"):
            st.session_state[CLAVE_CONFLICTO_RESTAURAR][clave] = False
            st.rerun()


def _mostrar_confirmacion_eliminar(patologia: str, anio: int, codigo: int, usuario, clave: str) -> None:
    st.warning("Esto destruye el archivo de forma irreversible. No se puede deshacer.")
    columna_si, columna_no = st.columns(2)
    with columna_si:
        if st.button("Si, eliminar para siempre", key=f"confirmar_eliminar_si_{clave}"):
            eliminar_para_siempre(
                patologia,
                rutas.directorio_papelera(patologia),
                anio,
                codigo,
                usuario.nombre_usuario,
                rol=usuario.rol,
                confirmado=True,
            )
            st.session_state[CLAVE_CONFIRMAR_ELIMINAR][clave] = False
            st.rerun()
    with columna_no:
        if st.button("Cancelar", key=f"confirmar_eliminar_no_{clave}"):
            st.session_state[CLAVE_CONFIRMAR_ELIMINAR][clave] = False
            st.rerun()


def _restaurar(patologia: str, anio: int, codigo: int, usuario, clave: str, forzar: bool) -> None:
    plugin = obtener_patologia(patologia)
    try:
        restaurar_pieza(
            patologia,
            rutas.directorio_piezas(patologia),
            rutas.directorio_papelera(patologia),
            rutas.ruta_consolidado(patologia),
            plugin.columna_anio,
            plugin.columna_codigo,
            anio,
            codigo,
            usuario.nombre_usuario,
            reemplazar_si_existe=forzar,
        )
    except ConflictoDeRestauracion:
        st.session_state.setdefault(CLAVE_CONFLICTO_RESTAURAR, {})[clave] = True
        st.rerun()
        return

    st.session_state.setdefault(CLAVE_CONFLICTO_RESTAURAR, {})[clave] = False
    modulo_datos.actualizar(patologia)
    st.rerun()
