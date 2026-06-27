"""Layout base del dashboard: login, selector de patologia, filtros globales,
banner de datos nuevos y apartado de Procesamientos.

No dibuja pestanas de graficos todavia; eso lo expone cada patologia via
obtener_vistas() cuando esten construidas.
"""

import streamlit as st

from core.auth.permisos import (
    PERMISO_ELIMINAR_PIEZA,
    PERMISO_SUBIR_PIEZA,
    PERMISO_VER_BITACORA,
    PERMISO_VER_PAPELERA,
    PERMISO_VER_PROCESAMIENTOS,
    tiene_permiso,
)
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base import filtros as modulo_filtros
from core.dashboard_base import sesion as modulo_sesion
from core.dashboard_base.banner import fragmento_banner_datos_nuevos
from core.dashboard_base.bitacora_vista import mostrar_bitacora
from core.dashboard_base.gestion_papelera import mostrar_papelera
from core.dashboard_base.gestion_piezas import mostrar_piezas_activas
from core.dashboard_base.gestion_subida import fragmento_subidas_pendientes, mostrar_formulario_subida
from core.dashboard_base.procesamientos_vista import mostrar_procesamientos
from core.registry import listar_patologias, obtener_patologia


def ejecutar_dashboard() -> None:
    st.set_page_config(page_title="Vigilancia Epidemiologica - Magdalena", layout="wide")

    usuario = modulo_sesion.usuario_actual()
    if usuario is None:
        modulo_sesion.mostrar_formulario_login()
        return

    patologias_disponibles = listar_patologias()
    if not patologias_disponibles:
        st.error("No hay patologias registradas en el sistema.")
        return

    st.sidebar.write(f"Sesion: {usuario.nombre_usuario} ({usuario.rol})")
    if st.sidebar.button("Cerrar sesion"):
        modulo_sesion.cerrar_sesion()
        st.rerun()

    patologia = st.sidebar.selectbox("Patologia", patologias_disponibles)
    plugin = obtener_patologia(patologia)

    modulo_datos.cargar_si_falta(patologia)
    fragmento_banner_datos_nuevos(patologia)

    if st.sidebar.button("Actualizar datos"):
        modulo_datos.actualizar(patologia)
        st.rerun()

    datos_completos = modulo_datos.obtener_datos(patologia)
    filtros = modulo_filtros.mostrar_filtros_globales(datos_completos, plugin.columna_anio)
    datos_filtrados = modulo_filtros.aplicar_filtros(datos_completos, filtros)

    st.title(f"Vigilancia de {plugin.nombre}")
    st.caption(
        f"{len(datos_filtrados):,} registros tras los filtros, de {len(datos_completos):,} en el consolidado."
    )

    _mostrar_seccion_gestion(patologia, usuario)


def _mostrar_seccion_gestion(patologia: str, usuario) -> None:
    hay_algo_que_gestionar = any(
        tiene_permiso(usuario.rol, permiso)
        for permiso in (
            PERMISO_SUBIR_PIEZA,
            PERMISO_ELIMINAR_PIEZA,
            PERMISO_VER_PAPELERA,
            PERMISO_VER_BITACORA,
            PERMISO_VER_PROCESAMIENTOS,
        )
    )
    if not hay_algo_que_gestionar:
        return

    st.divider()
    st.header("Gestion")

    if tiene_permiso(usuario.rol, PERMISO_SUBIR_PIEZA):
        mostrar_formulario_subida(patologia, usuario)
        fragmento_subidas_pendientes(usuario.nombre_usuario)

    if tiene_permiso(usuario.rol, PERMISO_ELIMINAR_PIEZA):
        mostrar_piezas_activas(patologia, usuario)

    if tiene_permiso(usuario.rol, PERMISO_VER_PAPELERA):
        mostrar_papelera(patologia, usuario)

    if tiene_permiso(usuario.rol, PERMISO_VER_BITACORA):
        mostrar_bitacora(patologia)

    if tiene_permiso(usuario.rol, PERMISO_VER_PROCESAMIENTOS):
        mostrar_procesamientos(patologia)
