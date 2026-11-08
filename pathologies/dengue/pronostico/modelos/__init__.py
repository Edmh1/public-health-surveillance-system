"""Modelos de pronostico de dengue: un archivo por modelo.

Para agregar un modelo:
1. Crear un archivo aqui con una subclase de core.registry.ModeloPronostico que
   declare clave, nombre, familia (ver configuracion.FAMILIAS),
   paquetes_requeridos e hiperparametros_por_defecto, e implemente entrenar,
   pronosticar_trayectorias, guardar y cargar.
2. Importar su libreria DENTRO de los metodos, nunca al inicio del archivo.
3. Agregar la libreria a requirements.txt (y al entorno de experimentacion).

El catalogo (pronostico/catalogo.py) lo descubre solo; no hay que registrarlo
en ningun otro lado.
"""
