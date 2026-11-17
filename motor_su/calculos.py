"""
Motor de cálculo del Agente Eléctrico — Fase 2.

Funciones Python puras: sin inteligencia artificial, sin internet.
Reciben números y devuelven números, siempre los mismos para los mismos datos.

Cada verificación devuelve un ResultadoCalculo: una fila del "protocolo de pruebas"
con el valor, su unidad, el límite contra el que se compara y si cumple.

Sesión 1: corriente nominal y corriente de diseño.
Sesión 2: corriente de cortocircuito y cortocircuito admisible del cable (Ikm).
Sesión 3: caída de tensión (incluida la caída previa hasta el punto de diseño).
"""

import math
from dataclasses import dataclass
from typing import Optional

from .conductores import K_IKM, buscar_conductor
from .modelos import BaseCorriente, ProyectoSU


# ---------------------------------------------------------------------------
# El formato de resultado: una fila del protocolo
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCalculo:
    nombre: str                      # ej. "Corriente de diseño a 20 kV"
    valor: float                     # ej. 22.74
    unidad: str                      # ej. "A"
    formula: str                     # ej. "Idis = 1.25 × S / (√3 × V)"
    limite: Optional[float] = None   # contra qué se compara (si aplica)
    cumple: Optional[bool] = None    # None = es un dato, no una verificación
    norma: Optional[str] = None      # se completa en la Fase 3 con el RAG

    def __str__(self) -> str:
        # 4 cifras significativas: 18.19 A, 3.193 V, 0.03193 %
        texto = f"{self.nombre}: {self.valor:.4g} {self.unidad}"
        if self.cumple is not None:
            estado = "CUMPLE" if self.cumple else "NO CUMPLE"
            texto += f" (límite {self.limite:.4g} {self.unidad}) → {estado}"
        return texto


# ---------------------------------------------------------------------------
# Funciones básicas (solo números)
# ---------------------------------------------------------------------------

FACTOR_DISENO = 1.25  # Idis = 1.25 × In, criterio usado en los 14 casos revisados


def corriente_nominal(s_kva: float, v_kv: float) -> float:
    """
    Corriente nominal trifásica: In = S / (√3 × V).
    s_kva: potencia aparente en kVA; v_kv: tensión de línea en kV. Devuelve amperios.
    """
    if s_kva <= 0:
        raise ValueError(f"La potencia debe ser positiva (llegó {s_kva} kVA)")
    if v_kv <= 0:
        raise ValueError(f"La tensión debe ser positiva (llegó {v_kv} kV)")
    return s_kva / (math.sqrt(3) * v_kv)


def corriente_diseno(s_kva: float, v_kv: float, factor: float = FACTOR_DISENO) -> float:
    """Corriente de diseño: Idis = factor × In (por defecto 1.25 × In)."""
    return factor * corriente_nominal(s_kva, v_kv)


# ---------------------------------------------------------------------------
# Funciones que leen el proyecto completo
# ---------------------------------------------------------------------------

def potencia_base_kva(proyecto: ProyectoSU) -> float:
    """
    Potencia con la que se calcula la corriente (decisión 1 de la Fase 0):
    - potencia_instalada (por defecto): suma de kVA de todos los transformadores.
    - maxima_demanda: MD / cos φ.
    """
    if proyecto.sitio.base_corriente == BaseCorriente.POTENCIA_INSTALADA:
        return proyecto.potencia_instalada_kva
    cuadro = proyecto.cuadro_de_cargas
    return cuadro.maxima_demanda_kw / cuadro.cos_phi


def tensiones_de_calculo(proyecto: ProyectoSU) -> list[float]:
    """
    Tensiones en las que hay que calcular.
    En doble tensión (20 kV con operación inicial en 10 kV) se calcula en ambas.
    """
    pd = proyecto.punto_de_diseno
    tensiones = [pd.tension_nominal_kv]
    if pd.tension_operacion_inicial_kv:
        tensiones.append(pd.tension_operacion_inicial_kv)
    return tensiones


def calcular_corrientes(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """Corriente nominal y de diseño para cada tensión del proyecto."""
    s = potencia_base_kva(proyecto)
    resultados = []
    for v in tensiones_de_calculo(proyecto):
        resultados.append(ResultadoCalculo(
            nombre=f"Corriente nominal a {v:g} kV",
            valor=corriente_nominal(s, v),
            unidad="A",
            formula=f"In = S / (√3 × V) = {s:g} / (√3 × {v:g})",
        ))
        resultados.append(ResultadoCalculo(
            nombre=f"Corriente de diseño a {v:g} kV",
            valor=corriente_diseno(s, v),
            unidad="A",
            formula=f"Idis = {FACTOR_DISENO} × In",
        ))
    return resultados


# ---------------------------------------------------------------------------
# Sesión 2: cortocircuito
# ---------------------------------------------------------------------------

def corriente_cortocircuito(pcc_mva: float, v_kv: float) -> float:
    """
    Corriente de cortocircuito trifásica en el punto de diseño: Icc = Pcc / (√3 × V).
    pcc_mva en MVA, v_kv en kV. Devuelve kA.
    """
    if pcc_mva <= 0:
        raise ValueError(f"La Pcc debe ser positiva (llegó {pcc_mva} MVA)")
    if v_kv <= 0:
        raise ValueError(f"La tensión debe ser positiva (llegó {v_kv} kV)")
    return pcc_mva / (math.sqrt(3) * v_kv)


def ikm_admisible(material: str, seccion_mm2: float, t_s: float) -> float:
    """
    Corriente de cortocircuito que soporta el cable: Ikm = k × S / √t  (kA).
    La constante k sale del catálogo según el material (regla R7),
    nunca la escribe el proyectista.
    """
    if material not in K_IKM:
        raise ValueError(f"Material '{material}' sin constante k en el catálogo")
    if t_s <= 0:
        raise ValueError(f"El tiempo de apertura debe ser positivo (llegó {t_s} s)")
    return K_IKM[material] * seccion_mm2 / math.sqrt(t_s)


def pcc_por_tension(proyecto: ProyectoSU) -> dict[float, float]:
    """Pcc de la carta para cada tensión de cálculo: {kV: MVA}."""
    pd = proyecto.punto_de_diseno
    pcc = {pd.tension_nominal_kv: pd.pcc_3f_mva}
    if pd.tension_operacion_inicial_kv:
        pcc[pd.tension_operacion_inicial_kv] = pd.pcc_3f_operacion_inicial_mva
    return pcc


def calcular_cortocircuito(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """
    Para cada tensión: Icc en el punto de diseño (dato) y, para cada conductor
    distinto del recorrido, la verificación Ikm ≥ Icc.
    """
    t = proyecto.punto_de_diseno.t_apertura_s
    conductores = sorted({tramo.conductor for tramo in proyecto.tramos})
    resultados = []
    for v, pcc in pcc_por_tension(proyecto).items():
        icc = corriente_cortocircuito(pcc, v)
        resultados.append(ResultadoCalculo(
            nombre=f"Corriente de cortocircuito a {v:g} kV",
            valor=icc,
            unidad="kA",
            formula=f"Icc = Pcc / (√3 × V) = {pcc:g} / (√3 × {v:g})",
        ))
        for codigo in conductores:
            c = buscar_conductor(codigo)
            ikm = ikm_admisible(c.material, c.seccion_mm2, t)
            resultados.append(ResultadoCalculo(
                nombre=f"Cortocircuito admisible {codigo} a {v:g} kV",
                valor=ikm,
                unidad="kA",
                formula=f"Ikm = {K_IKM[c.material]} × {c.seccion_mm2:g} / √{t:g}",
                limite=icc,
                cumple=ikm >= icc,
            ))
    return resultados


# ---------------------------------------------------------------------------
# Sesión 3: caída de tensión
# ---------------------------------------------------------------------------

def caida_tension_v(i_a: float, l_km: float, r_ohm_km: float, x_ohm_km: float,
                    cos_phi: float) -> float:
    """
    Caída de tensión trifásica en un tramo: ΔV = √3 × I × L × (R cos φ + X sen φ).
    Devuelve voltios. Es la forma en voltios; las otras 3 formas vistas en los
    expedientes son la misma ecuación reordenada.
    """
    if not 0 < cos_phi <= 1:
        raise ValueError(f"cos φ debe estar entre 0 y 1 (llegó {cos_phi})")
    if l_km < 0:
        raise ValueError(f"La longitud no puede ser negativa (llegó {l_km} km)")
    sen_phi = math.sqrt(1 - cos_phi ** 2)
    return math.sqrt(3) * i_a * l_km * (r_ohm_km * cos_phi + x_ohm_km * sen_phi)


def caida_tension_pct(dv_v: float, v_kv: float) -> float:
    """ΔV% = ΔV / V × 100, con V en voltios de línea."""
    return dv_v / (v_kv * 1000) * 100


def calcular_caida_tension(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """
    Para cada tensión: ΔV de cada tramo (del punto de diseño a la SE, en serie,
    con la misma corriente) y la verificación del total contra el admisible.
    El total suma la caída previa hasta el punto de diseño, si la concesionaria la exige
    (criterio de Electrocentro visto en las tesis).
    """
    s = potencia_base_kva(proyecto)
    cos_phi = proyecto.cuadro_de_cargas.cos_phi
    previo = proyecto.sitio.dv_previo_punto_diseno_pct
    admisible = proyecto.sitio.dv_admisible_pct
    resultados = []
    for v in tensiones_de_calculo(proyecto):
        i = corriente_nominal(s, v)
        total_v = 0.0
        for tramo in proyecto.tramos:
            c = buscar_conductor(tramo.conductor)
            dv = caida_tension_v(i, tramo.longitud_m / 1000, c.r_ohm_km, c.x_ohm_km, cos_phi)
            total_v += dv
            resultados.append(ResultadoCalculo(
                nombre=f"Caída de tensión tramo '{tramo.nombre}' a {v:g} kV",
                valor=dv,
                unidad="V",
                formula=(f"ΔV = √3 × {i:.2f} × {tramo.longitud_m / 1000:g} × "
                         f"({c.r_ohm_km} × {cos_phi} + {c.x_ohm_km} × sen φ)"),
            ))
        total_pct = caida_tension_pct(total_v, v) + previo
        formula = "ΔV% = Σ ΔV tramos / V × 100"
        if previo:
            formula += f" + {previo:g} % previo al punto de diseño"
        resultados.append(ResultadoCalculo(
            nombre=f"Caída de tensión total a {v:g} kV",
            valor=total_pct,
            unidad="%",
            formula=formula,
            limite=admisible,
            cumple=total_pct <= admisible,
        ))
    return resultados
