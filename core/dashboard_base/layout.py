"""Layout base del dashboard: login, selector de patologia, filtros globales,
banner de datos nuevos y apartado de Procesamientos.

No dibuja pestanas de graficos todavia; eso lo expone cada patologia via
obtener_vistas() cuando esten construidas.
"""

import streamlit as st

from core.auth.permisos import PERMISO_VER_PROCESAMIENTOS, tiene_permiso
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base import filtros as modulo_filtros
from core.dashboard_base import sesion as modulo_sesion
from core.dashboard_base.banner import fragmento_banner_datos_nuevos
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

    if tiene_permiso(usuario.rol, PERMISO_VER_PROCESAMIENTOS):
        mostrar_procesamientos(patologia)
