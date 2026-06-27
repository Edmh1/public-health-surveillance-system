"""Papelera: soft delete a nivel de pieza, recuperable, con eliminacion permanente solo para Admin.

La consolidada nunca tiene piezas en papelera: una pieza enviada a papelera sale del
consolidado y su Parquet se mueve de piezas/ a papelera/. Restaurar la reincorpora al
consolidado, verificando antes si ya existe una pieza activa con el mismo anio+codigo
para no sobrescribirla a ciegas.
"""

from pathlib import Path

import pandas as pd

from core.audit.bitacora import registrar_movimiento
from core.audit.registro_piezas import (
    eliminar_registro_pieza,
    marcar_pieza_activa,
    marcar_pieza_inactiva,
    obtener_pieza_activa,
)
from core.storage.consolidado import agregar_pieza, eliminar_pieza
from core.storage.piezas import ruta_pieza


class ConflictoDeRestauracion(Exception):
    """Ya existe una pieza activa con el mismo anio+codigo; hay que confirmar el reemplazo."""


def mover_a_papelera(
    patologia: str,
    directorio_piezas: Path,
    directorio_papelera: Path,
    ruta_consolidado: Path,
    columna_anio: str,
    columna_codigo: str,
    anio: int,
    codigo: int,
    usuario: str,
) -> Path:
    """Saca la pieza del consolidado y mueve su Parquet de piezas/ a papelera/."""
    eliminar_pieza(ruta_consolidado, columna_anio, columna_codigo, anio, codigo)

    origen = ruta_pieza(directorio_piezas, anio, codigo)
    destino = ruta_pieza(directorio_papelera, anio, codigo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen.replace(destino)

    marcar_pieza_inactiva(patologia, anio, codigo)
    registrar_movimiento(patologia, anio, codigo, "eliminar", usuario)

    return destino


def restaurar_pieza(
    patologia: str,
    directorio_piezas: Path,
    directorio_papelera: Path,
    ruta_consolidado: Path,
    columna_anio: str,
    columna_codigo: str,
    anio: int,
    codigo: int,
    usuario: str,
    reemplazar_si_existe: bool = False,
) -> Path:
    """Reincorpora una pieza desde la papelera al consolidado y a piezas/.

    Si ya existe una pieza activa con el mismo anio+codigo, exige
    reemplazar_si_existe=True; de lo contrario lanza ConflictoDeRestauracion
    para que quien llama le pregunte al usuario si reemplaza o cancela.
    """
    pieza_activa_existente = obtener_pieza_activa(patologia, anio, codigo)
    if pieza_activa_existente is not None and not reemplazar_si_existe:
        mensaje = (
            f"Ya existe una pieza activa de {patologia} {anio}+{codigo}. "
            "Confirma con reemplazar_si_existe=True para reemplazarla, o cancela."
        )
        raise ConflictoDeRestauracion(mensaje)

    origen = ruta_pieza(directorio_papelera, anio, codigo)
    pieza_restaurada = pd.read_parquet(origen)

    agregar_pieza(ruta_consolidado, columna_anio, columna_codigo, anio, codigo, pieza_restaurada)

    destino = ruta_pieza(directorio_piezas, anio, codigo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen.replace(destino)

    marcar_pieza_activa(patologia, anio, codigo)
    registrar_movimiento(patologia, anio, codigo, "restaurar", usuario)

    return destino


def eliminar_para_siempre(
    patologia: str,
    directorio_papelera: Path,
    anio: int,
    codigo: int,
    usuario: str,
    rol: str,
    confirmado: bool,
) -> None:
    """Destruye el Parquet de la papelera de forma irreversible. Solo Admin, con confirmacion explicita."""
    if rol != "Admin":
        raise PermissionError("Solo Admin puede eliminar una pieza para siempre")
    if not confirmado:
        raise ValueError("Eliminar para siempre requiere confirmacion explicita")

    ruta = ruta_pieza(directorio_papelera, anio, codigo)
    ruta.unlink()

    eliminar_registro_pieza(patologia, anio, codigo)
    registrar_movimiento(patologia, anio, codigo, "eliminar_permanente", usuario)
