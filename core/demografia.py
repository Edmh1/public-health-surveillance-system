"""Agrupacion de edad por curso de vida (Resolucion 3208 de 2018).

Las piramides poblacionales usan estos seis grupos definidos por el Ministerio
de Salud y Proteccion Social. Los limites son semiabiertos ([minimo, maximo)),
de modo que una edad con decimales (por ejemplo 5,9 anios) cae en el grupo que
le corresponde segun la resolucion.
"""

import pandas as pd

GRUPOS_CURSO_VIDA = [
    (0, 6, "Primera infancia"),
    (6, 12, "Infancia"),
    (12, 18, "Adolescencia"),
    (18, 29, "Juventud"),
    (29, 60, "Adultez"),
    (60, float("inf"), "Vejez"),
]

ETIQUETAS_CURSO_VIDA = [etiqueta for _, _, etiqueta in GRUPOS_CURSO_VIDA]
LIMITES_CURSO_VIDA = [minimo for minimo, _, _ in GRUPOS_CURSO_VIDA] + [GRUPOS_CURSO_VIDA[-1][1]]

FUENTE_GRUPOS_CURSO_VIDA = (
    "Agrupación por curso de vida según la Resolución 3208 de 2018 "
    "del Ministerio de Salud y Protección Social."
)


def clasificar_grupo_curso_vida(edad) -> str:
    """Devuelve el grupo de curso de vida para una edad en anios."""
    for minimo, maximo, etiqueta in GRUPOS_CURSO_VIDA:
        if pd.notna(edad) and minimo <= edad < maximo:
            return etiqueta
    return "Sin dato"
