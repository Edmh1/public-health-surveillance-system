"""Utilidades de busqueda y paginacion para las vistas de gestion.

Centraliza la logica de: campo de busqueda libre, filtrado de lista,
corte por pagina y controles anterior/siguiente. Todas las vistas
de gestion la usan con la misma clave unica para que el estado de
pagina de piezas, papelera y procesamientos sea independiente.
"""

import streamlit as st

N_POR_PAGINA = 10


def buscar_y_paginar(
    items: list,
    clave: str,
    campos_busqueda: list[str],
    placeholder: str = "Buscar...",
) -> tuple[list, int, int]:
    """Muestra campo de busqueda y devuelve la tajada de la pagina actual.

    Resetea a pagina 1 cuando el termino de busqueda cambia, para que
    el usuario siempre empiece a ver resultados desde el principio tras
    una nueva busqueda.

    Returns
    -------
    (items_de_la_pagina, pagina_actual, total_despues_de_filtro)
    total_paginas se puede calcular externamente si hace falta, pero lo
    mas comodo es llamar mostrar_controles_paginacion() con el valor de
    pagina_actual que devuelve esta funcion.
    """
    n_total_sin_filtrar = len(items)

    col_buscar, col_info = st.columns([4, 1], vertical_alignment="center")
    with col_buscar:
        busqueda = st.text_input(
            "Buscar",
            placeholder=placeholder,
            key=f"busqueda_{clave}",
            label_visibility="collapsed",
        )
    with col_info:
        st.caption(f"{n_total_sin_filtrar} elementos", text_alignment="right")

    # Detecta cambio de busqueda → reset a pagina 1
    prev_key = f"busqueda_prev_{clave}"
    pagina_key = f"pagina_{clave}"
    prev_busqueda = st.session_state.get(prev_key, "")
    if busqueda != prev_busqueda:
        st.session_state[pagina_key] = 1
        st.session_state[prev_key] = busqueda

    # Filtro por busqueda
    if busqueda:
        termino = busqueda.lower().strip()
        items = [
            item for item in items
            if any(termino in str(item.get(campo, "")).lower() for campo in campos_busqueda)
        ]

    total = len(items)
    if total == 0:
        if busqueda:
            st.caption("Sin resultados para esa busqueda.")
        return [], 1, 0

    total_paginas = max(1, (total + N_POR_PAGINA - 1) // N_POR_PAGINA)
    pagina = max(1, min(st.session_state.get(pagina_key, 1), total_paginas))
    st.session_state[pagina_key] = pagina

    inicio = (pagina - 1) * N_POR_PAGINA
    return items[inicio : inicio + N_POR_PAGINA], pagina, total


def mostrar_controles_paginacion(clave: str, pagina: int, total: int) -> None:
    """Controles anterior / indicador / siguiente. No renderiza nada si cabe todo en una pagina."""
    total_paginas = max(1, (total + N_POR_PAGINA - 1) // N_POR_PAGINA)
    if total_paginas <= 1:
        return

    st.space("small")
    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button(
            "Anterior",
            icon=":material/arrow_back:",
            key=f"prev_{clave}",
            disabled=pagina <= 1,
            width="stretch",
        ):
            st.session_state[f"pagina_{clave}"] = pagina - 1
            st.rerun()
    with col_info:
        st.caption(
            f"Página {pagina} de {total_paginas}  ·  {total} elementos",
            text_alignment="center",
        )
    with col_next:
        if st.button(
            "Siguiente",
            icon=":material/arrow_forward:",
            key=f"next_{clave}",
            disabled=pagina >= total_paginas,
            width="stretch",
        ):
            st.session_state[f"pagina_{clave}"] = pagina + 1
            st.rerun()
