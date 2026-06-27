"""Layout base del dashboard: login, barra superior, filtros globales, banner de
datos nuevos y apartado de Gestion. Ver DESIGN.md para la identidad visual.

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
from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, aplicar_estilos
from core.dashboard_base.gestion_papelera import mostrar_papelera
from core.dashboard_base.gestion_piezas import mostrar_piezas_activas
from core.dashboard_base.gestion_subida import fragmento_subidas_pendientes, mostrar_formulario_subida
from core.dashboard_base.procesamientos_vista import mostrar_procesamientos
from core.registry import listar_patologias, obtener_patologia


def ejecutar_dashboard() -> None:
    st.set_page_config(page_title="Vigilancia epidemiologica - CITES", layout="wide")
    aplicar_estilos()

    usuario = modulo_sesion.usuario_actual()
    if usuario is None:
        modulo_sesion.mostrar_formulario_login()
        return

    patologias_disponibles = listar_patologias()
    if not patologias_disponibles:
        st.error("No hay patologias registradas en el sistema.")
        return

    patologia = _mostrar_barra_superior(usuario, patologias_disponibles)
    plugin = obtener_patologia(patologia)

    modulo_datos.cargar_si_falta(patologia)
    fragmento_banner_datos_nuevos(patologia)

    datos_completos = modulo_datos.obtener_datos(patologia)
    filtros = _mostrar_filtros_en_sidebar(patologia, datos_completos, plugin.columna_anio)
    datos_filtrados = modulo_filtros.aplicar_filtros(datos_completos, filtros)

    st.title(f"Vigilancia de {plugin.nombre}")
    st.caption(
        f"{len(datos_filtrados):,} registros tras los filtros, de {len(datos_completos):,} en el consolidado."
    )

    _mostrar_seccion_gestion(patologia, usuario)


def _mostrar_barra_superior(usuario, patologias_disponibles: list[str]) -> str:
    """Marca a la izquierda, selector de patologia al centro, identidad y rol a la derecha."""
    with st.container(border=True):
        columna_marca, columna_patologia, columna_usuario = st.columns([3, 2, 2], vertical_alignment="center")

        with columna_marca:
            st.markdown(
                f"""
                <div style="color:{AZUL_INSTITUCIONAL}; font-size:18px; font-weight:500;">
                    Vigilancia epidemiologica
                </div>
                <div style="color:#666666; font-size:12px;">CITES - Universidad del Magdalena</div>
                """,
                unsafe_allow_html=True,
            )

        with columna_patologia:
            patologia = st.selectbox(
                "Patologia", patologias_disponibles, label_visibility="collapsed", key="selector_patologia"
            )

        with columna_usuario:
            subcolumna_identidad, subcolumna_salir = st.columns([3, 1], vertical_alignment="center")
            with subcolumna_identidad:
                st.markdown(f"**{usuario.nombre_usuario}** &nbsp;·&nbsp; {usuario.rol}")
            with subcolumna_salir:
                if st.button("", icon=":material/logout:", help="Cerrar sesion", key="cerrar_sesion_barra"):
                    modulo_sesion.cerrar_sesion()
                    st.rerun()

    return patologia


def _mostrar_filtros_en_sidebar(patologia: str, datos_completos, columna_anio: str) -> dict:
    if st.sidebar.button(
        "Actualizar datos", icon=":material/refresh:", use_container_width=True, key="actualizar_datos_sidebar"
    ):
        modulo_datos.actualizar(patologia)
        st.rerun()

    return modulo_filtros.mostrar_filtros_globales(datos_completos, columna_anio)


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
    st.header(":material/admin_panel_settings: Gestion")

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
