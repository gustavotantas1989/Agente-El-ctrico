"""
Ejemplo del Revisor v1: contrasta lo que DECLARA el expediente Sol de Olmos
contra lo que RECALCULA el motor, y muestra las observaciones.

Cómo correrlo (en la terminal de VS Code, dentro de la carpeta "Agente electrico"):
    py revisar_sol_de_olmos.py
"""

from motor_su.calculos import calcular_proyecto
from motor_su.ejemplos import declarados_sol_de_olmos, sol_de_olmos
from motor_su.modelos import ProyectoSU
from motor_su.revisor import ValorDeclarado, comparar, informe_revision

# 1. Datos del proyecto, tal como los declara el expediente
proyecto = ProyectoSU(**sol_de_olmos())

# 2. El motor recalcula todo (el "instrumento patrón")
resultados = calcular_proyecto(proyecto)

# 3. Valores que el proyectista declara en su expediente (el "medidor bajo prueba")
declarados = [ValorDeclarado(**d) for d in declarados_sol_de_olmos()]

# 4. Contraste con tolerancia de ±2 % e informe
comparaciones = comparar(resultados, declarados)
print(informe_revision(comparaciones))
