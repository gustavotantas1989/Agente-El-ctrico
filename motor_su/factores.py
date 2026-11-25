"""
Factores de corrección de la ampacidad de cables subterráneos (sesión 4).

Idea clave (hallazgo del 18/11/2026): la ampacidad del catálogo (Indeco) está
calculada en SUS condiciones base (20 °C, 0.8 m, 1.5 K·m/W), pero las tablas del
CNE tienen OTRAS bases (0.70 m y 100 °C·cm/W = 1.0 K·m/W). Si se aplica el factor
del CNE directo, la corrección se cuenta mal. Por eso cada factor se NORMALIZA:

    F real = F_tabla(condición real) / F_tabla(condición base del catálogo)

Analogía: es como corregir la lectura de un medidor; la curva de corrección tiene
que referirse a las mismas condiciones en que se calibró el medidor.

Entre dos valores de una tabla se interpola linealmente. Fuera del rango de la
tabla se da error (no se extrapola).
"""

from .conductores import BASE_PROFUNDIDAD_M, BASE_RESISTIVIDAD_KMW, BASE_T_TERRENO_C


def interpolar(tabla: dict[float, float], x: float, nombre: str) -> float:
    """Interpolación lineal en una tabla {x: factor}. Error si x sale del rango."""
    xs = sorted(tabla)
    if not xs[0] <= x <= xs[-1]:
        raise ValueError(f"{nombre}: {x:g} está fuera de la tabla ({xs[0]:g} a {xs[-1]:g})")
    for x0, x1 in zip(xs, xs[1:]):
        if x0 <= x <= x1:
            y0, y1 = tabla[x0], tabla[x1]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return tabla[xs[-1]]


# ---------------------------------------------------------------------------
# 1. Temperatura del terreno — conductor XLPE a 90 °C, base 20 °C
#    Fuente: ficha CELSA N2XSY 18/30 kV (anexo Exp. Minera Vicus OV-2300525),
#    basada en IEC 60502-2. Misma base que Indeco (20 °C): no requiere normalizar.
# ---------------------------------------------------------------------------
TABLA_TEMPERATURA_TERRENO_90C = {
    10: 1.07, 15: 1.04, 20: 1.00, 25: 0.96, 30: 0.93,
    35: 0.89, 40: 0.85, 45: 0.80, 50: 0.76,
}

# ---------------------------------------------------------------------------
# 2. Resistividad térmica del suelo — sistemas de cables unipolares
#    Fuente: CNE Distribución 2011, Tabla 2-XXXII (citada en tesis Bravo, UCSM 2018).
#    Unidad de la tabla: °C·cm/W (100 °C·cm/W = 1.0 K·m/W). Base de la tabla: 100.
# ---------------------------------------------------------------------------
TABLA_RESISTIVIDAD_TERMICA = {
    50: 1.39, 70: 1.17, 80: 1.11, 100: 1.00, 120: 0.92,
    150: 0.83, 200: 0.73, 250: 0.65, 300: 0.60,
}

# ---------------------------------------------------------------------------
# 3. Profundidad de tendido — Fuente: CNE Distribución 2011, Tabla 2-XXXV.
#    Base de la tabla: 0.70 m.
# ---------------------------------------------------------------------------
TABLA_PROFUNDIDAD_HASTA_300 = {0.5: 1.02, 0.6: 1.01, 0.7: 1.00, 0.8: 0.98,
                               1.0: 0.96, 1.2: 0.95, 1.5: 0.94}
TABLA_PROFUNDIDAD_MAYOR_300 = {0.5: 1.03, 0.6: 1.02, 0.7: 1.00, 0.8: 0.97,
                               1.0: 0.95, 1.2: 0.94, 1.5: 0.92}

# ---------------------------------------------------------------------------
# 4. Tendido en ductos (sistema de unipolares) — Fuente: CNE Distribución 2011,
#    Tabla 2-XXXVI. Rangos de sección: (hasta 50, 70-150, 185-400, 500 o más).
# ---------------------------------------------------------------------------
TABLA_DUCTOS = {
    "directo": (1.00, 1.00, 1.00, 1.00),
    "un_ducto": (0.81, 0.79, 0.76, 0.69),
    "tres_ductos_plano": (0.82, 0.80, 0.77, 0.70),
    "tres_ductos_trebol": (0.83, 0.81, 0.78, 0.71),
}
INSTALACIONES = list(TABLA_DUCTOS)


def factor_temperatura_terreno(t_c: float) -> float:
    base = interpolar(TABLA_TEMPERATURA_TERRENO_90C, BASE_T_TERRENO_C, "Temperatura del terreno")
    return interpolar(TABLA_TEMPERATURA_TERRENO_90C, t_c, "Temperatura del terreno (°C)") / base


def factor_resistividad_termica(rho_kmw: float) -> float:
    """rho en K·m/W (1.5 típico). Normalizado a la base del catálogo (1.5 K·m/W)."""
    real = interpolar(TABLA_RESISTIVIDAD_TERMICA, rho_kmw * 100, "Resistividad térmica (°C·cm/W)")
    base = interpolar(TABLA_RESISTIVIDAD_TERMICA, BASE_RESISTIVIDAD_KMW * 100, "Resistividad base")
    return real / base


def factor_profundidad(profundidad_m: float, seccion_mm2: float) -> float:
    """Normalizado a la base del catálogo (0.8 m)."""
    tabla = TABLA_PROFUNDIDAD_HASTA_300 if seccion_mm2 <= 300 else TABLA_PROFUNDIDAD_MAYOR_300
    real = interpolar(tabla, profundidad_m, "Profundidad de tendido (m)")
    return real / interpolar(tabla, BASE_PROFUNDIDAD_M, "Profundidad base")


def factor_ducto(instalacion: str, seccion_mm2: float) -> float:
    if instalacion not in TABLA_DUCTOS:
        raise ValueError(f"Instalación '{instalacion}' no válida. Opciones: {INSTALACIONES}")
    fila = TABLA_DUCTOS[instalacion]
    if seccion_mm2 <= 50:
        return fila[0]
    if seccion_mm2 <= 150:
        return fila[1]
    if seccion_mm2 <= 400:
        return fila[2]
    return fila[3]
