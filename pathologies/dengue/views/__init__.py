"""Las 5 pestanas del dashboard de dengue: Situacion, Tendencia, Sociodemografica,
Morbilidad y Mortalidad; ver CLAUDE.md para el detalle de cada pestana. Situacion va
primero (KPIs + mapa de situacion + canal endemico): es el resumen ejecutivo de
"como estamos ahora", antes de entrar al detalle historico de Tendencia. Solo el
pronostico (2.3) queda pendiente en Situacion, ver PROGRESO.md.
"""

from pathologies.dengue.views.morbilidad import mostrar_morbilidad
from pathologies.dengue.views.mortalidad import mostrar_mortalidad
from pathologies.dengue.views.situacion import mostrar_situacion
from pathologies.dengue.views.sociodemografica import mostrar_sociodemografica
from pathologies.dengue.views.tendencia import mostrar_tendencia


def obtener_vistas_dengue() -> list[tuple[str, callable]]:
    """Nombre de cada pestana y su funcion de render, en el orden en que se muestran."""
    return [
        ("Situación", mostrar_situacion),
        ("Tendencia", mostrar_tendencia),
        ("Sociodemográfica", mostrar_sociodemografica),
        ("Morbilidad", mostrar_morbilidad),
        ("Mortalidad", mostrar_mortalidad),
    ]
