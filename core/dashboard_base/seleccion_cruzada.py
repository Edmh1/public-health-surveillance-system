"""Filtro cruzado dentro de un par de graficas complementarias (regla 1.5 de
DESIGN.md): seleccionar en una grafica filtra la otra del mismo par.

Reutiliza el patron que ya usaba el mapa de Tendencia: st.plotly_chart con
on_select="rerun", selection_mode="points" y key. Lo que agrega este modulo es
lo que evita dejar a la persona atrapada en una vista sin entender por que:

- La seleccion vive en st.session_state con una clave por par (nunca en
  variables de modulo).
- Sobre el par se muestra en texto que esta filtrado ("Mostrando solo: ...")
  con un boton para quitar la seleccion.
- La seleccion se borra sola cuando cambia cualquier filtro global de la barra
  lateral (se compara la huella de los filtros, ver filtros.firma_filtros_globales).

Como se lee una seleccion: la seleccion de Plotly es un EVENTO, no el estado.
Cada grafica del par se dibuja con una key que lleva un contador; al detectar
puntos seleccionados en la key vigente (leyendo st.session_state ANTES de
dibujar), se guarda lo elegido como valores (no como indices de punto, que
dejan de corresponder en cuanto los datos de la grafica cambian) y se sube el
contador, de modo que la grafica vuelve a dibujarse limpia. Asi una grafica que
cambia de datos por la seleccion de su pareja nunca arrastra una seleccion vieja
que ya no corresponde a lo que muestra.
"""

import streamlit as st
from streamlit.errors import StreamlitAPIException

from core.dashboard_base.filtros import firma_filtros_globales

_PREFIJO_ESTADO = "seleccion_cruzada"


def recargar_seccion() -> None:
    """Vuelve a dibujar solo la pestana (el fragmento) cuando se puede; si la
    pagina entera ya se esta recargando, Streamlit no admite scope="fragment"
    y lanza una excepcion, asi que en ese caso recarga la pagina completa."""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def _clave_estado(clave_par: str) -> str:
    return f"{_PREFIJO_ESTADO}_{clave_par}"


def _estado(clave_par: str) -> dict:
    clave = _clave_estado(clave_par)
    if clave not in st.session_state:
        st.session_state[clave] = {"firma": None, "contador": 0, "seleccion": None}
    return st.session_state[clave]


def sincronizar_con_filtros(clave_par: str, claves_extra: tuple[str, ...] = ()) -> None:
    """Borra la seleccion del par si cambiaron los filtros globales desde la
    ultima vez. claves_extra son otras claves de session_state que forman parte
    de la seleccion del par y que tambien hay que limpiar (ej. el nivel de
    detalle del mapa de Tendencia)."""
    estado = _estado(clave_par)
    firma_actual = firma_filtros_globales()
    if estado["firma"] is None:
        estado["firma"] = firma_actual
        return
    if estado["firma"] == firma_actual:
        return
    estado["firma"] = firma_actual
    estado["seleccion"] = None
    estado["contador"] = estado["contador"] + 1
    for clave in claves_extra:
        st.session_state.pop(clave, None)


def clave_grafica(clave_par: str, nombre_grafica: str) -> str:
    """Key de st.plotly_chart para una grafica del par. Cambia cada vez que la
    seleccion se consume o se borra, para que la grafica se dibuje limpia."""
    estado = _estado(clave_par)
    return f"{clave_par}_{nombre_grafica}_{estado['contador']}"


def leer_puntos(clave_par: str, nombre_grafica: str) -> list[dict]:
    """Puntos seleccionados en la grafica del par en la interaccion anterior.
    Se llama ANTES de dibujar las graficas del par. Lista vacia si no hubo."""
    clave = clave_grafica(clave_par, nombre_grafica)
    estado_widget = st.session_state.get(clave)
    if not estado_widget:
        return []
    try:
        puntos = estado_widget["selection"]["points"]
    except (KeyError, TypeError):
        try:
            puntos = estado_widget.selection.points
        except AttributeError:
            return []
    return list(puntos or [])


def fijar_seleccion(clave_par: str, origen: str, valores: list, descripcion: str) -> None:
    """Guarda lo elegido (origen = grafica donde se hizo clic, valores = lo que
    filtra a la otra) y sube el contador para limpiar la seleccion visual."""
    estado = _estado(clave_par)
    estado["seleccion"] = {"origen": origen, "valores": list(valores), "descripcion": descripcion}
    estado["contador"] = estado["contador"] + 1


def obtener_seleccion(clave_par: str) -> dict | None:
    """{"origen", "valores", "descripcion"} de la seleccion vigente, o None."""
    return _estado(clave_par)["seleccion"]


def limpiar_seleccion(clave_par: str, claves_extra: tuple[str, ...] = ()) -> None:
    estado = _estado(clave_par)
    estado["seleccion"] = None
    estado["contador"] = estado["contador"] + 1
    for clave in claves_extra:
        st.session_state.pop(clave, None)


def mostrar_aviso_seleccion(clave_par: str, descripcion: str | None, claves_extra: tuple[str, ...] = ()) -> None:
    """Texto visible sobre el par con lo que esta filtrado y un boton para quitar
    la seleccion. No dibuja nada si no hay seleccion."""
    if not descripcion:
        return
    columna_texto, columna_boton = st.columns([5, 1.4], vertical_alignment="center")
    with columna_texto:
        st.info(f"Mostrando solo: {descripcion}", icon=":material/filter_alt:")
    with columna_boton:
        if st.button(
            "Quitar selección",
            icon=":material/filter_alt_off:",
            key=f"{clave_par}_quitar_seleccion",
            width="stretch",
        ):
            limpiar_seleccion(clave_par, claves_extra)
            recargar_seccion()
