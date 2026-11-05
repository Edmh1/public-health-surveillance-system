"""Lectura de fechas de las exportaciones de SIVIGILA sin adivinar el formato.

SIVIGILA ha cambiado como escribe las fechas entre exportaciones: las viejas traen
2024-09-02 (a veces con hora) y las de finales de 2026 traen 9/06/2024 12:00:00 a. m.
Pedirle a la persona que reescriba cientos de miles de fechas no es razonable, asi que
el sistema deduce el formato de los propios datos y convierte todo a un solo tipo
(datetime). Lo que nunca hace es dejar que un parser adivine el orden de dia y mes:
asi se volteaban en silencio todas las fechas con dia menor o igual a 12.

Como se deduce el orden, por archivo y por familia de formato:
- Familia "anio al final" (dd/mm/aaaa o mm/dd/aaaa, separador /, - o .) y familia
  "anio al inicio" (aaaa-mm-dd o aaaa-dd-mm). Pueden convivir en un mismo archivo
  (celdas con fecha real de Excel salen como aaaa-mm-dd; celdas de texto, como
  vengan escritas), por eso cada familia decide su orden por separado.
- Evidencia directa: si algun valor tiene mas de 12 en la primera posicion, esa
  posicion es el dia; si lo tiene en la segunda, el dia va segundo. Un archivo de un
  anio completo siempre trae dias mayores a 12, asi que casi siempre se decide aqui.
- Si hay evidencia en las dos posiciones, el archivo mezcla ordenes: se rechaza.
- Sin evidencia (archivo chico con todos los dias <= 12): en la familia "anio al
  inicio" se usa aaaa-mm-dd, que es el estandar ISO y lo que entrega Excel. En la
  familia "anio al final" se desempata comparando la fecha de notificacion con la
  columna de semana epidemiologica; si ni asi se puede decidir, se rechaza.
Tambien se acepta el numero de serie de Excel (dias desde 1899-12-30). Cualquier valor
escrito que no encaje en nada, o que sea una fecha imposible (31/02), detiene el
procesamiento con ejemplos.
"""

import pandas as pd

FAMILIA_ANIO_AL_FINAL = "anio_al_final"
FAMILIA_ANIO_AL_INICIO = "anio_al_inicio"

ORDEN_DIA_MES = "dia_mes"
ORDEN_MES_DIA = "mes_dia"

# Grupos: (primero, segundo, anio) y (anio, primero, segundo). La hora que venga
# despues de la fecha se ignora.
PATRON_ANIO_AL_FINAL = r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?:\D|$)"
PATRON_ANIO_AL_INICIO = r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})(?:\D|$)"
PATRON_SERIAL_EXCEL = r"^(\d{5})(?:\.0+)?$"
ORIGEN_SERIAL_EXCEL = "1899-12-30"

COLUMNA_FECHA_DESEMPATE = "fec_not"
COLUMNA_SEMANA_DESEMPATE = "semana"
# Una interpretacion gana el desempate si al menos esta fraccion de fechas cae a
# 2 semanas o menos de la semana epidemiologica reportada, y supera a la otra
# interpretacion por al menos el margen.
COINCIDENCIA_MINIMA_DESEMPATE = 0.6
MARGEN_MINIMO_DESEMPATE = 0.2
SEMANAS_DE_TOLERANCIA = 2


def _limpiar_texto(serie):
    texto = serie.astype("string").str.strip()
    texto = texto.replace("", pd.NA)
    return texto


def _extraer_partes(texto, familia):
    """Devuelve un DataFrame con anio, primero y segundo (Int64, nulo si el valor no
    es de esa familia)."""
    if familia == FAMILIA_ANIO_AL_FINAL:
        partes = texto.str.extract(PATRON_ANIO_AL_FINAL)
        partes.columns = ["primero", "segundo", "anio"]
    else:
        partes = texto.str.extract(PATRON_ANIO_AL_INICIO)
        partes.columns = ["anio", "primero", "segundo"]
    partes = partes.apply(pd.to_numeric, errors="coerce")
    partes = partes.astype("Int64")
    return partes


def _armar_fechas(partes, orden):
    if orden == ORDEN_DIA_MES:
        dia = partes["primero"]
        mes = partes["segundo"]
    else:
        mes = partes["primero"]
        dia = partes["segundo"]
    componentes = pd.DataFrame({
        "year": partes["anio"].astype("float64"),
        "month": mes.astype("float64"),
        "day": dia.astype("float64"),
    })
    fechas = pd.to_datetime(componentes, errors="coerce")
    return fechas


def _semana_epidemiologica(fechas):
    """Semana epidemiologica CDC (inicio domingo): la semana ISO del dia siguiente."""
    dia_siguiente = fechas + pd.Timedelta(days=1)
    semana = dia_siguiente.dt.isocalendar().week
    return semana.astype("Int64")


def _fraccion_coincidente_con_semana(fechas, semana_reportada):
    semana_calculada = _semana_epidemiologica(fechas)
    distancia = (semana_calculada - semana_reportada).abs()
    # Cerca del cambio de anio la semana 52 y la 1 son vecinas.
    distancia_circular = distancia.where(distancia < 26, 53 - distancia)
    comparables = distancia_circular.notna()
    if not comparables.any():
        return 0.0
    coincidentes = distancia_circular[comparables] <= SEMANAS_DE_TOLERANCIA
    return float(coincidentes.mean())


def _desempatar_con_semana(datos, familia):
    if COLUMNA_FECHA_DESEMPATE not in datos.columns or COLUMNA_SEMANA_DESEMPATE not in datos.columns:
        return None
    texto_fecha = _limpiar_texto(datos[COLUMNA_FECHA_DESEMPATE])
    partes = _extraer_partes(texto_fecha, familia)
    semana_reportada = pd.to_numeric(datos[COLUMNA_SEMANA_DESEMPATE], errors="coerce").astype("Int64")

    coincidencia_dia_mes = _fraccion_coincidente_con_semana(_armar_fechas(partes, ORDEN_DIA_MES), semana_reportada)
    coincidencia_mes_dia = _fraccion_coincidente_con_semana(_armar_fechas(partes, ORDEN_MES_DIA), semana_reportada)

    gana_dia_mes = (
        coincidencia_dia_mes >= COINCIDENCIA_MINIMA_DESEMPATE
        and coincidencia_dia_mes - coincidencia_mes_dia >= MARGEN_MINIMO_DESEMPATE
    )
    gana_mes_dia = (
        coincidencia_mes_dia >= COINCIDENCIA_MINIMA_DESEMPATE
        and coincidencia_mes_dia - coincidencia_dia_mes >= MARGEN_MINIMO_DESEMPATE
    )
    if gana_dia_mes:
        return ORDEN_DIA_MES
    if gana_mes_dia:
        return ORDEN_MES_DIA
    return None


def _ejemplos(texto, mascara):
    return texto[mascara].unique()[:3].tolist()


def _detectar_orden_familia(datos, columnas_fecha, familia):
    textos = []
    partes_por_columna = []
    for columna in columnas_fecha:
        texto = _limpiar_texto(datos[columna])
        textos.append(texto)
        partes_por_columna.append(_extraer_partes(texto, familia))
    texto_total = pd.concat(textos, ignore_index=True)
    partes = pd.concat(partes_por_columna, ignore_index=True)

    hay_valores = partes["anio"].notna()
    if not hay_valores.any():
        return None

    primero_es_dia = (partes["primero"] > 12).fillna(False)
    segundo_es_dia = (partes["segundo"] > 12).fillna(False)

    if primero_es_dia.any() and segundo_es_dia.any():
        mensaje = (
            "Las fechas del archivo mezclan dia/mes y mes/dia, no se puede saber cual es cual. "
            f"Ejemplos con el dia primero: {_ejemplos(texto_total, primero_es_dia)}; "
            f"con el mes primero: {_ejemplos(texto_total, segundo_es_dia)}"
        )
        raise ValueError(mensaje)
    if primero_es_dia.any():
        return ORDEN_DIA_MES
    if segundo_es_dia.any():
        return ORDEN_MES_DIA

    # Sin evidencia directa. Si dia y mes son iguales en todos, el orden no cambia nada.
    mismo_valor = (partes["primero"] == partes["segundo"])[hay_valores]
    if mismo_valor.all():
        return ORDEN_DIA_MES
    if familia == FAMILIA_ANIO_AL_INICIO:
        return ORDEN_MES_DIA

    orden_por_semana = _desempatar_con_semana(datos, familia)
    if orden_por_semana is not None:
        return orden_por_semana

    mensaje = (
        "No se pudo determinar si las fechas vienen como dia/mes o mes/dia: ningun valor tiene "
        "un dia mayor a 12 y no coinciden con la semana epidemiologica. "
        f"Ejemplos: {_ejemplos(texto_total, hay_valores)}"
    )
    raise ValueError(mensaje)


def detectar_ordenes(datos, columnas_fecha):
    """Decide, para todo el archivo, el orden de dia y mes de cada familia de formato.
    Devuelve {familia: orden o None si el archivo no trae fechas de esa familia}."""
    ordenes = {}
    for familia in (FAMILIA_ANIO_AL_FINAL, FAMILIA_ANIO_AL_INICIO):
        ordenes[familia] = _detectar_orden_familia(datos, columnas_fecha, familia)
    return ordenes


def convertir_columna_fecha(serie, ordenes):
    """Convierte una columna de fechas en texto a datetime con los ordenes ya decididos
    para el archivo. Un valor escrito que no se pueda convertir detiene el procesamiento."""
    texto = _limpiar_texto(serie)
    fechas = pd.Series(pd.NaT, index=texto.index, dtype="datetime64[us]")

    for familia, orden in ordenes.items():
        if orden is None:
            continue
        partes = _extraer_partes(texto, familia)
        fechas_familia = _armar_fechas(partes, orden)
        fechas = fechas.fillna(fechas_familia)

    serial = texto.str.extract(PATRON_SERIAL_EXCEL, expand=False)
    serial_numerico = pd.to_numeric(serial, errors="coerce")
    fechas_serial = pd.to_datetime(serial_numerico, unit="D", origin=ORIGEN_SERIAL_EXCEL, errors="coerce")
    fechas = fechas.fillna(fechas_serial)

    fechas = fechas.astype("datetime64[us]")

    no_reconocidas = texto.notna() & fechas.isna()
    if no_reconocidas.any():
        cantidad = int(no_reconocidas.sum())
        mensaje = (
            f"La columna {str(serie.name).upper()} tiene {cantidad} valores que no son una fecha valida. "
            f"Ejemplos: {_ejemplos(texto, no_reconocidas)}"
        )
        raise ValueError(mensaje)

    return fechas
