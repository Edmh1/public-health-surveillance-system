"""Esquema estable y documentado de los datos procesados de dengue.

Pendiente de construir. Ver CLAUDE.md, seccion "LLM a futuro": no se agrega
ninguna dependencia de LLM ahora, pero los datos procesados deben tener un
esquema estable y documentado, porque un LLM futuro va a consumir los mismos
Parquet de la consolidada (y el registro de patologias) para responder
preguntas sobre los datos. Este archivo es esa puerta dejada abierta.

Cuando se construya, PathologyPlugin.obtener_esquema() (hoy NotImplementedError
en plugin.py) debe devolver el contenido de este modulo: para cada una de las
~56 columnas del consolidado (ver clean.py y la tabla ya documentada en
PROGRESO.md), su nombre, tipo (Int64/Float64/str/bool/datetime), y para las
columnas categoricas el dominio de valores validos con su significado (ej.
cod_eve: 210=dengue, 220=dengue grave, 580=mortalidad). El objetivo es que un
LLM (o cualquier consumidor externo) pueda leer este esquema y entender el
dato sin tener que inferirlo del propio Parquet ni leer clean.py.

No es prioridad hasta que haya un consumidor real (LLM u otro) que lo
necesite; construirlo antes seria trabajo especulativo.
"""
