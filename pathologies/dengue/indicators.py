"""KPIs de dengue: cocientes simples sobre el consolidado filtrado.

- Incidencia de dengue: casos (210+220) / poblacion en riesgo (DANE) x 100.000.
- Mortalidad por dengue: muertes (580) / poblacion en riesgo x 100.000.
- Letalidad por dengue: muertes (580) / casos (210+220).
- Letalidad por dengue grave: muertes (580) / casos graves (220).
- % de casos confirmados dengue grave.
- % de hospitalizados dengue grave.

Si falta una pieza necesaria para alguno de estos (ej. la poblacion en riesgo,
o el codigo 580), ese indicador queda "no disponible", nunca en cero.
"""
