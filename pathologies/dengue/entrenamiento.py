"""Reentrenamiento del pronostico de dengue: lo que corre el worker cuando el
perfil de administracion lo lanza desde Gestion (ver core/ingestion/
entrenamiento.py, que es quien lo orquesta, versiona y deja traza).

Orden, igual que la especificacion de la tarea:
1. Valida walk-forward los tres modelos (y la persistencia) en los horizontes de
   1 a 6 semanas, con los datos cargados en este momento.
2. Entrena los tres modelos con TODO el historico cargado.
3. Exporta los modelos y escribe el manifest.json con fecha, usuario, rango de
   datos, hiperparametros, la tabla de metricas por horizonte y la version del
   codigo. Sin el manifest no hay forma de saber que esta pronosticando el tablero.

La validacion va primero a proposito: es la parte que puede fallar por historico
insuficiente, y asi falla antes de gastar tiempo entrenando los modelos finales.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.registry import ModuloPronostico
from pathologies.dengue import prediccion

# Version del codigo de pronostico: se sube a mano cuando cambia la logica de
# entrenamiento o de prediccion, para que el manifest de cada version exportada
# diga con que codigo se genero. Se complementa con el commit de git cuando el
# repositorio esta disponible (en la imagen Docker no lo esta).
VERSION_CODIGO_PRONOSTICO = "2026.11.1"


def _commit_git() -> str | None:
    raiz = Path(__file__).resolve().parents[2]
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=raiz,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultado.returncode != 0:
        return None
    return resultado.stdout.strip() or None


def _describir_rango(serie: pd.DataFrame) -> dict[str, Any]:
    primera = serie.iloc[0]
    ultima = serie.iloc[-1]
    return {
        "anio_inicio": int(primera["ano"]),
        "semana_inicio": int(primera["semana"]),
        "anio_fin": int(ultima["ano"]),
        "semana_fin": int(ultima["semana"]),
        "fecha_ultima_semana": pd.Timestamp(ultima["fecha_semana"]).strftime("%Y-%m-%d"),
    }


class PronosticoDengue(ModuloPronostico):
    """Implementacion del contrato ModuloPronostico para dengue."""

    def entrenar_y_exportar(self, datos: pd.DataFrame, carpeta: Path, usuario: str) -> dict[str, Any]:
        serie = prediccion.construir_serie_semanal_departamental(datos)
        if len(serie) < prediccion.SEMANAS_MINIMAS_ENTRENAMIENTO:
            raise ValueError(
                f"Histórico insuficiente: hay {len(serie)} semanas y el pronóstico necesita "
                f"al menos {prediccion.SEMANAS_MINIMAS_ENTRENAMIENTO}."
            )

        validacion = prediccion.evaluar_walk_forward(serie)

        archivos = {}
        for tipo in prediccion.MODELOS_DISPONIBLES:
            modelo = prediccion.entrenar_modelo(serie, tipo)
            archivos[tipo] = prediccion.guardar_modelo(modelo, carpeta)

        manifest = {
            "patologia": "dengue",
            "fecha_entrenamiento": datetime.now(timezone.utc).isoformat(),
            "usuario": usuario,
            "rango": _describir_rango(serie),
            "semanas": int(len(serie)),
            "modelos": dict(prediccion.NOMBRES_MODELOS),
            "modelo_por_defecto": prediccion.MODELO_POR_DEFECTO,
            "archivos": archivos,
            "hiperparametros": prediccion.HIPERPARAMETROS,
            "horizonte_maximo_semanas": prediccion.HORIZONTE_MAXIMO_SEMANAS,
            "validacion": {
                "metodo": (
                    "Walk-forward multipaso: ultimo 15 % de la serie como prueba, modelos "
                    "entrenados con el resto; desde cada semana de origen se pronostican las "
                    "6 siguientes realimentando la propia prediccion."
                ),
                "semanas_entrenamiento": validacion["semanas_entrenamiento"],
                "semanas_prueba": validacion["semanas_prueba"],
                "origenes": validacion["origenes"],
                "inicio_prueba": validacion["inicio_prueba"],
                "fin_prueba": validacion["fin_prueba"],
            },
            "metricas": validacion["metricas"],
            "version_codigo": VERSION_CODIGO_PRONOSTICO,
            "commit_git": _commit_git(),
        }

        ruta_manifest = carpeta / "manifest.json"
        ruta_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
