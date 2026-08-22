"""Piezas activas de la patologia: editarlas o moverlas a la papelera.

Vista por defecto: matriz de semaforos (filas = codigo esperado del manifest,
columnas = anio) para ver en segundos que anio+codigo falta, sin abrir cada
pieza. Verde = subido (popover con detalle, Editar, Eliminar), gris = falta
(popover con subida directa). El detalle en tarjetas de siempre (busqueda +
paginacion) sigue disponible abajo, colapsado, para quien necesite buscar por
nombre de archivo en vez de por anio+codigo.
"""

import streamlit as st

from core.audit.registro_piezas import listar_piezas_activas
from core.audit.zona_horaria import formatear_fecha_local
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.gestion_subida import encolar_subida
from core.dashboard_base.paginacion import buscar_y_paginar, mostrar_controles_paginacion
from core.ingestion.papelera import mover_a_papelera
from core.registry import obtener_patologia
from core.storage import rutas

CLAVE_EDITANDO = "piezas_editando"
CLAVE_CONTADOR_UPLOADER_EDITAR = "piezas_contador_widget_uploader_editar"
CLAVE_CONTADOR_UPLOADER_MATRIZ = "piezas_contador_widget_uploader_matriz"


def mostrar_piezas_activas(patologia: str, usuario) -> None:
    piezas = listar_piezas_activas(patologia)

    if not piezas:
        with st.container(border=True):
            st.info(
                f":material/folder_open: Aun no hay piezas activas para {patologia}. "
                "Usa la pestana Subir para agregar la primera.",
                icon=":material/info:",
            )
        return

    _mostrar_matriz_piezas(patologia, piezas, usuario)

    st.space("small")
    with st.expander("Ver todas las piezas (búsqueda y detalle)", icon=":material/list_alt:"):
        _mostrar_lista_piezas(patologia, piezas, usuario)


# ---------------------------------------------------------------------------
# Matriz de semaforos: codigo (fila) x anio (columna). Vista por defecto.
# ---------------------------------------------------------------------------

def _inyectar_estilos_matriz() -> None:
    """Azul institucional (completo) / gris claro (falta), NO verde/rojo: esa
    pareja de colores es exclusiva del canal endemico y los estados
    epidemiologicos (regla de DESIGN.md). Selector por substring de clase
    (st-key-celda_completa_* / st-key-celda_faltante_*): cada celda tiene una
    key unica por año+codigo, pero todas comparten el mismo prefijo, asi una
    sola regla CSS pinta todas las celdas de ese tipo. Streamlit renderiza el
    contenido expandido del popover en una capa flotante fuera del arbol del
    boton disparador, asi que esto solo debe afectar al icono cerrado, no a los
    botones Editar/Eliminar/Confirmar de adentro (verificar en navegador si
    algun tema de Streamlit cambia ese comportamiento).
    """
    st.html(
        """
        <style>
        div[class*="st-key-celda_completa_"] button {
            background-color: #1b3a6b !important;
            border-color: #1b3a6b !important;
            color: #ffffff !important;
        }
        div[class*="st-key-celda_faltante_"] button {
            background-color: #f4f5f7 !important;
            border-color: #c9ccd1 !important;
            color: #8a8f98 !important;
        }
        </style>
        """
    )


def _mostrar_matriz_piezas(patologia: str, piezas: list[dict], usuario) -> None:
    plugin = obtener_patologia(patologia)
    codigos = sorted(plugin.codigos_esperados)

    piezas_por_celda = {(pieza["anio"], pieza["codigo"]): pieza for pieza in piezas}
    anios_con_datos = sorted({pieza["anio"] for pieza in piezas})
    # Rango CONTINUO de anios (no solo los que ya tienen algo): un anio sin
    # ninguna pieza tambien debe aparecer como columna vacia, no desaparecer
    # del todo, o nadie lo notaria como faltante.
    todos_los_anios = list(range(anios_con_datos[0], anios_con_datos[-1] + 1))

    # Solo años con pendientes: si a alguien le interesa un año YA completo lo
    # busca en "Ver todas las piezas" (la lista de abajo), no hace falta que la
    # matriz lo muestre tambien.
    anios_mostrados = [
        anio for anio in todos_los_anios
        if sum((anio, codigo) in piezas_por_celda for codigo in codigos) < len(codigos)
    ]

    st.subheader(":material/grid_view: Años con pendientes")

    if not anios_mostrados:
        st.info("Todos los años tienen los códigos completos.", icon=":material/check_circle:")
        return

    _inyectar_estilos_matriz()
    st.caption(
        "Azul = subido, gris = falta. Pasa el cursor sobre un ícono para ver el detalle; "
        "haz clic para editar, eliminar o subir el archivo que falta."
    )

    anchos_columnas = [1.1] + [1] * len(anios_mostrados)
    encabezado = st.columns(anchos_columnas)
    with encabezado[0]:
        st.markdown("**Código**")
    for columna, anio in zip(encabezado[1:], anios_mostrados):
        with columna:
            st.markdown(f"**{anio}**")

    for codigo in codigos:
        fila = st.columns(anchos_columnas)
        with fila[0]:
            st.markdown(f"**{codigo}**")
        for columna, anio in zip(fila[1:], anios_mostrados):
            with columna:
                pieza = piezas_por_celda.get((anio, codigo))
                if pieza is not None:
                    _celda_completa(patologia, pieza, usuario)
                else:
                    _celda_faltante(patologia, anio, codigo, usuario)

    pie = st.columns(anchos_columnas)
    with pie[0]:
        st.caption("Completo")
    for columna, anio in zip(pie[1:], anios_mostrados):
        with columna:
            completos = sum((anio, codigo) in piezas_por_celda for codigo in codigos)
            st.caption(f"{completos}/{len(codigos)}")


def _celda_completa(patologia: str, pieza: dict, usuario) -> None:
    # Prefijo "grid_" para que las keys de widgets (y CLAVE_EDITANDO, que es un
    # dict compartido) nunca choquen con la misma pieza mostrada en la lista de
    # tarjetas de abajo: Streamlit ejecuta AMBAS secciones en cada rerun, aunque
    # el expander de la lista este colapsado.
    clave_pieza = f"grid_{patologia}_{pieza['anio']}_{pieza['codigo']}"
    # Key del popover con prefijo "celda_completa_" (distinto de clave_pieza):
    # es lo que engancha el CSS de _inyectar_estilos_matriz.
    clave_popover = f"celda_completa_{patologia}_{pieza['anio']}_{pieza['codigo']}"
    fecha = formatear_fecha_local(pieza["fecha_creacion"])

    with st.popover(
        "",
        icon=":material/check_circle:",
        help=f"{pieza['archivo_original']} · {fecha}",
        width="stretch",
        key=clave_popover,
    ):
        st.markdown(f":material/description: **{pieza['archivo_original']}**")
        st.caption(fecha)

        if st.button("Editar", icon=":material/edit:", key=f"{clave_pieza}_editar", width="stretch"):
            editando = st.session_state.setdefault(CLAVE_EDITANDO, {})
            editando[clave_pieza] = not editando.get(clave_pieza, False)
        if st.session_state.get(CLAVE_EDITANDO, {}).get(clave_pieza):
            _mostrar_formulario_editar(patologia, pieza, usuario, clave_pieza)

        if st.button("Eliminar", icon=":material/delete:", key=f"{clave_pieza}_eliminar", width="stretch"):
            _eliminar(patologia, pieza["anio"], pieza["codigo"], usuario)


def _celda_faltante(patologia: str, anio: int, codigo: int, usuario) -> None:
    clave_celda = f"grid_{patologia}_{anio}_{codigo}"
    clave_popover = f"celda_faltante_{patologia}_{anio}_{codigo}"

    with st.popover(
        "",
        icon=":material/error:",
        help=f"Falta año {anio}, código {codigo}. Haz clic para subir el archivo.",
        width="stretch",
        key=clave_popover,
    ):
        st.caption(f"Subir archivo para año {anio}, código {codigo}.")

        contadores = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER_MATRIZ, {})
        contador = contadores.get(clave_celda, 0)
        archivo = st.file_uploader(
            "Archivo SIVIGILA (.xls o .xlsx)",
            type=["xls", "xlsx"],
            key=f"{clave_celda}_archivo_{contador}",
        )
        if archivo is not None and st.button(
            "Confirmar y procesar",
            type="primary",
            icon=":material/check_circle:",
            key=f"{clave_celda}_confirmar",
            width="stretch",
        ):
            encolar_subida(patologia, anio, codigo, archivo.name, archivo.getvalue(), usuario)
            contadores[clave_celda] = contador + 1
            st.rerun()


# ---------------------------------------------------------------------------
# Lista de tarjetas (busqueda + paginacion): detalle, colapsada por defecto.
# ---------------------------------------------------------------------------

def _mostrar_lista_piezas(patologia: str, piezas: list[dict], usuario) -> None:
    # Primero el año mas reciente; dentro de cada año, orden por codigo
    piezas_ordenadas = sorted(piezas, key=lambda p: (-p["anio"], p["codigo"]))

    pagina_items, pagina, total = buscar_y_paginar(
        piezas_ordenadas,
        clave="piezas_activas",
        campos_busqueda=["archivo_original", "anio", "codigo"],
        placeholder="Buscar por archivo, año o código...",
    )

    for pieza in pagina_items:
        clave_pieza = f"{patologia}_{pieza['anio']}_{pieza['codigo']}"
        _mostrar_tarjeta_pieza(patologia, pieza, usuario, clave_pieza)
        if st.session_state.get(CLAVE_EDITANDO, {}).get(clave_pieza):
            _mostrar_formulario_editar(patologia, pieza, usuario, clave_pieza)

    mostrar_controles_paginacion("piezas_activas", pagina, total)


def _mostrar_tarjeta_pieza(patologia: str, pieza: dict, usuario, clave_pieza: str) -> None:
    with st.container(border=True):
        col_info, col_acciones = st.columns([3, 1], vertical_alignment="center")

        with col_info:
            st.markdown(f":material/description: **{pieza['archivo_original']}**")
            fecha = formatear_fecha_local(pieza["fecha_creacion"])
            st.caption(f"Año {pieza['anio']} · Código {pieza['codigo']} · {fecha}")

        with col_acciones:
            if st.button(
                "Editar",
                icon=":material/edit:",
                key=f"editar_{clave_pieza}",
                width="stretch",
                help="Reemplaza el archivo de esta pieza con una versión corregida.",
            ):
                editando = st.session_state.setdefault(CLAVE_EDITANDO, {})
                editando[clave_pieza] = not editando.get(clave_pieza, False)

            if st.button(
                "Eliminar",
                icon=":material/delete:",
                key=f"eliminar_{clave_pieza}",
                width="stretch",
                help="Mueve esta pieza a la papelera. Es recuperable desde la pestaña Papelera.",
            ):
                _eliminar(patologia, pieza["anio"], pieza["codigo"], usuario)


def _mostrar_formulario_editar(patologia: str, pieza: dict, usuario, clave_pieza: str) -> None:
    anio = pieza["anio"]
    codigo = pieza["codigo"]

    contadores = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER_EDITAR, {})
    contador = contadores.get(clave_pieza, 0)

    with st.container(border=True):
        st.caption(
            f"Sube la versión corregida de **{pieza['archivo_original']}** "
            f"(Año {anio} · Código {codigo}). El histórico de otras piezas no se toca."
        )
        with st.form(f"editar_pieza_{clave_pieza}", border=False):
            archivo = st.file_uploader(
                "Archivo SIVIGILA (.xls o .xlsx)",
                type=["xls", "xlsx"],
                key=f"archivo_editar_{clave_pieza}_{contador}",
            )
            col_cancelar, col_confirmar = st.columns(2)
            with col_cancelar:
                cancelar = st.form_submit_button("Cancelar", width="stretch")
            with col_confirmar:
                confirmar = st.form_submit_button(
                    "Confirmar y procesar",
                    type="primary",
                    icon=":material/check_circle:",
                    width="stretch",
                )

    if cancelar:
        st.session_state.setdefault(CLAVE_EDITANDO, {})[clave_pieza] = False
        st.rerun()

    if not confirmar:
        return

    if archivo is None:
        st.warning("Selecciona un archivo antes de confirmar.")
        return

    encolar_subida(patologia, anio, codigo, archivo.name, archivo.getvalue(), usuario)
    st.session_state.setdefault(CLAVE_EDITANDO, {})[clave_pieza] = False
    contadores[clave_pieza] = contador + 1


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
