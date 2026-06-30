"""Layout base del dashboard: login, barra superior, filtros globales, banner de
datos nuevos, las pestanas de la patologia y la pestana de Gestion. Ver DESIGN.md
para la identidad visual.

Las primeras pestanas las expone cada patologia via obtener_vistas(); la ultima
(Gestion) es del core y solo aparece si el rol del usuario habilita algo que
gestionar (ver core/auth/permisos.py).
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
from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    RUTA_ICONO_SIVIDEM,
    RUTA_ICONO_SIVIDEM_PNG,
    aplicar_estilos,
    imagen_a_data_uri,
)
from core.dashboard_base.gestion_papelera import mostrar_papelera
from core.dashboard_base.gestion_piezas import mostrar_piezas_activas
from core.dashboard_base.gestion_subida import fragmento_subidas_pendientes, mostrar_formulario_subida
from core.dashboard_base.procesamientos_vista import mostrar_procesamientos
from core.registry import listar_patologias, obtener_patologia


def ejecutar_dashboard() -> None:
    # page_icon no acepta SVG; se usa el PNG rasterizado a partir del mismo icono
    # (ver assets/icono_sividem.png), generado una vez a partir de icono_sividem.svg.
    st.set_page_config(page_title="SIVIDEM - CITES", page_icon=str(RUTA_ICONO_SIVIDEM_PNG), layout="wide")
    aplicar_estilos()

    usuario = modulo_sesion.usuario_actual()
    if usuario is None:
        modulo_sesion.mostrar_formulario_login()
        return

    patologias_disponibles = listar_patologias()
    if not patologias_disponibles:
        st.error("No hay patologias registradas en el sistema.")
        return

    with st.container(key="encabezado_fijo"):
        # El titulo y el contador de registros van visualmente arriba de la barra de marca
        # (logo/patologia/usuario), pero su texto depende de la patologia que se elige EN
        # esa barra. Se reserva el espacio con st.empty() y se llena despues, una vez ya se
        # conoce la patologia: el placeholder mantiene su posicion (arriba), aunque se
        # escriba en el mas tarde en el orden del script.
        marcador_titulo = st.empty()

        patologia = _mostrar_barra_superior(usuario, patologias_disponibles)
        plugin = obtener_patologia(patologia)

        modulo_datos.cargar_si_falta(patologia)

        datos_completos = modulo_datos.obtener_datos(patologia)
        mapeo_subregion = plugin.obtener_mapeo_subregion()
        filtros = _mostrar_filtros_en_sidebar(patologia, datos_completos, plugin.columna_anio, mapeo_subregion)
        datos_filtrados = modulo_filtros.aplicar_filtros(datos_completos, filtros, mapeo_subregion)

        with marcador_titulo.container():
            st.title(f"Vigilancia de {plugin.nombre}")
            st.caption(
                f"{len(datos_filtrados):,} registros tras los filtros, de {len(datos_completos):,} en el consolidado."
            )

    fragmento_banner_datos_nuevos(patologia)

    _mostrar_pestanas(patologia, usuario, plugin, datos_filtrados)


ICONOS_PESTANAS = {
    "Tendencia": ":material/trending_up:",
    "Situacion": ":material/insights:",
    "Sociodemografica": ":material/groups:",
    "Morbilidad": ":material/healing:",
    "Mortalidad": ":material/bar_chart:",
    "Gestion": ":material/admin_panel_settings:",
}


def _mostrar_pestanas(patologia: str, usuario, plugin, datos_filtrados) -> None:
    """Las 5 pestanas que expone la patologia, mas la pestana de Gestion al final
    (solo si el rol del usuario habilita algo que gestionar).
    """
    vistas = plugin.obtener_vistas()
    nombres_pestanas = [nombre for nombre, _ in vistas]

    mostrar_gestion = _tiene_algo_que_gestionar(usuario)
    if mostrar_gestion:
        nombres_pestanas = nombres_pestanas + ["Gestion"]

    etiquetas_pestanas = [f"{ICONOS_PESTANAS.get(nombre, '')} {nombre}".strip() for nombre in nombres_pestanas]
    pestanas = st.tabs(etiquetas_pestanas)

    for pestana, (_, funcion_render) in zip(pestanas, vistas):
        with pestana:
            funcion_render(datos_filtrados)

    if mostrar_gestion:
        with pestanas[-1]:
            _mostrar_seccion_gestion(patologia, usuario)


def _mostrar_barra_superior(usuario, patologias_disponibles: list[str]) -> str:
    """Marca a la izquierda, selector de patologia al centro, identidad y rol a la derecha."""
    with st.container(key="barra_superior"):
        columna_marca, columna_patologia, columna_usuario = st.columns([3, 2, 2], vertical_alignment="center")

        with columna_marca:
            icono_data_uri = imagen_a_data_uri(RUTA_ICONO_SIVIDEM)
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:10px; padding-bottom:6px;">
                    <img src="{icono_data_uri}" style="width:32px; height:32px; flex-shrink:0;" />
                    <div>
                        <div style="color:{AZUL_INSTITUCIONAL}; font-size:18px; font-weight:500; letter-spacing:0.3px;">
                            SIVIDEM
                        </div>
                        <div style="color:#666666; font-size:12px;">CITES - Universidad del Magdalena</div>
                    </div>
                </div>
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


def _mostrar_filtros_en_sidebar(
    patologia: str, datos_completos, columna_anio: str, mapeo_subregion: dict[int, str]
) -> dict:
    if st.sidebar.button(
        "Actualizar datos", icon=":material/refresh:", use_container_width=True, key="actualizar_datos_sidebar"
    ):
        modulo_datos.actualizar(patologia)
        st.rerun()

    return modulo_filtros.mostrar_filtros_globales(datos_completos, columna_anio, mapeo_subregion)


def _tiene_algo_que_gestionar(usuario) -> bool:
    return any(
        tiene_permiso(usuario.rol, permiso)
        for permiso in (
            PERMISO_SUBIR_PIEZA,
            PERMISO_ELIMINAR_PIEZA,
            PERMISO_VER_PAPELERA,
            PERMISO_VER_BITACORA,
            PERMISO_VER_PROCESAMIENTOS,
        )
    )


def _mostrar_seccion_gestion(patologia: str, usuario) -> None:
    columna_titulo, columna_actualizar = st.columns([6, 1])
    with columna_titulo:
        st.caption("Piezas, papelera, bitacora y procesamientos no se autoactualizan; usa este boton para refrescarlos.")
    with columna_actualizar:
        if st.button(
            "Actualizar", icon=":material/refresh:", use_container_width=True, key=f"actualizar_gestion_{patologia}",
        ):
            st.rerun()

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
