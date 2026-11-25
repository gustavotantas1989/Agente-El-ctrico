"""
Revisor v1 — Sesión 1: comparador de resultados (regla R6).

Principio (Fase 0): el Revisor compara RESULTADOS, no fórmulas.
  1. El motor recalcula el proyecto con los datos que declara el expediente.
  2. Se ingresan los valores que el proyectista DECLARA en su expediente.
  3. Se comparan uno a uno, con tolerancia de ±2 %.

Analogía: es el contraste de un medidor. El motor es el instrumento patrón;
el expediente es el medidor bajo prueba; si el error pasa la tolerancia, se observa.

Estados posibles de cada comparación:
  COINCIDE        |diferencia| ≤ tolerancia
  DIFIERE         |diferencia| > tolerancia  → observación
  NO_DECLARADO    el motor verifica algo que el expediente no presenta → observación
  NO_VERIFICABLE  el expediente lo presenta como imagen (p. ej. pantallazo de DIgSILENT)
  CLAVE_DESCONOCIDA  se declaró algo que el motor no calcula (revisar la clave)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .calculos import ResultadoCalculo

TOLERANCIA_PCT = 2.0

# Unidades aceptadas y su conversión a la unidad base que usa el motor.
# Así "3.75 kA" declarado se compara bien con 3753 A, y un error de unidades
# (como el de la tesis Aliaga: Pcc en MVA escrita como si fueran kVA) sale como DIFIERE.
_UNIDADES = {
    "A": ("A", 1.0), "kA": ("A", 1000.0),
    "V": ("V", 1.0), "kV": ("V", 1000.0),
    "MVA": ("MVA", 1.0), "kVA": ("MVA", 0.001),
    "Ω": ("Ω", 1.0), "ohm": ("Ω", 1.0), "Ohm": ("Ω", 1.0),
    "%": ("%", 1.0),
}


class Estado(str, Enum):
    COINCIDE = "coincide"
    DIFIERE = "difiere"
    NO_DECLARADO = "no declarado"
    NO_VERIFICABLE = "no verificable"
    CLAVE_DESCONOCIDA = "clave desconocida"


class ValorDeclarado(BaseModel):
    """Un valor tal como aparece en el expediente."""
    clave: str = Field(description="Clave del resultado del motor, ej. 'icc_20kv'")
    valor: Optional[float] = Field(None, description="Vacío si viene como imagen")
    unidad: Optional[str] = Field(None, description="Si se omite, se asume la del motor")
    referencia: str = Field("", description="Dónde aparece: capítulo, página")
    no_verificable: bool = Field(False, description="True si el resultado viene como imagen")


@dataclass
class Comparacion:
    clave: str
    nombre: str
    calculado: Optional[float]
    declarado: Optional[float]   # ya convertido a la unidad del motor
    unidad: str
    diferencia_pct: Optional[float]
    estado: Estado
    referencia: str = ""
    mensaje: str = ""

    @property
    def es_observacion(self) -> bool:
        return self.estado in (Estado.DIFIERE, Estado.NO_DECLARADO,
                               Estado.NO_VERIFICABLE, Estado.CLAVE_DESCONOCIDA)


def convertir(valor: float, unidad_declarada: Optional[str], unidad_motor: str) -> float:
    """Convierte el valor declarado a la unidad del motor (kA → A, kV → V, kVA → MVA…)."""
    if not unidad_declarada or unidad_declarada == unidad_motor:
        return valor
    if unidad_declarada not in _UNIDADES or unidad_motor not in _UNIDADES:
        raise ValueError(f"Unidad no reconocida: '{unidad_declarada}' o '{unidad_motor}'")
    base_d, factor_d = _UNIDADES[unidad_declarada]
    base_m, factor_m = _UNIDADES[unidad_motor]
    if base_d != base_m:
        raise ValueError(f"Unidades incompatibles: declarado en {unidad_declarada}, "
                         f"el motor calcula en {unidad_motor}")
    return valor * factor_d / factor_m


def diferencia_porcentual(declarado: float, calculado: float) -> float:
    """(declarado − calculado) / calculado × 100. Positivo = el expediente declara de más."""
    if calculado == 0:
        return 0.0 if declarado == 0 else float("inf")
    return (declarado - calculado) / abs(calculado) * 100


def comparar(resultados: list[ResultadoCalculo], declarados: list[ValorDeclarado],
             tolerancia_pct: float = TOLERANCIA_PCT) -> list[Comparacion]:
    """
    Compara lo calculado por el motor con lo declarado en el expediente.
    Devuelve una Comparacion por cada valor declarado, más una NO_DECLARADO por cada
    VERIFICACIÓN del motor (las que tienen cumple / no cumple) que el expediente no presenta.
    """
    por_clave = {r.clave: r for r in resultados if r.clave}
    comparaciones = []
    vistas = set()

    for d in declarados:
        r = por_clave.get(d.clave)
        if r is None:
            comparaciones.append(Comparacion(
                d.clave, d.clave, None, d.valor, d.unidad or "", None,
                Estado.CLAVE_DESCONOCIDA, d.referencia,
                "El motor no calcula un resultado con esta clave; revisar la clave."))
            continue
        vistas.add(d.clave)

        if d.no_verificable or d.valor is None:
            comparaciones.append(Comparacion(
                d.clave, r.nombre, r.valor, None, r.unidad, None,
                Estado.NO_VERIFICABLE, d.referencia,
                "El expediente presenta el resultado como imagen o sin valor numérico; "
                "no se puede verificar."))
            continue

        try:
            declarado = convertir(d.valor, d.unidad, r.unidad)
        except ValueError as e:
            comparaciones.append(Comparacion(
                d.clave, r.nombre, r.valor, d.valor, d.unidad or "", None,
                Estado.DIFIERE, d.referencia, str(e)))
            continue

        dif = diferencia_porcentual(declarado, r.valor)
        if abs(dif) <= tolerancia_pct:
            estado, msg = Estado.COINCIDE, ""
        else:
            sentido = "por encima" if dif > 0 else "por debajo"
            estado = Estado.DIFIERE
            msg = (f"El valor declarado ({declarado:.4g} {r.unidad}) está {abs(dif):.1f} % "
                   f"{sentido} del recalculado ({r.valor:.4g} {r.unidad}).")
        comparaciones.append(Comparacion(
            d.clave, r.nombre, r.valor, declarado, r.unidad, dif, estado, d.referencia, msg))

    for r in resultados:
        if r.clave and r.clave not in vistas and r.cumple is not None:
            comparaciones.append(Comparacion(
                r.clave, r.nombre, r.valor, None, r.unidad, None, Estado.NO_DECLARADO, "",
                "El expediente no presenta esta verificación."))
    return comparaciones


def resumen(comparaciones: list[Comparacion]) -> dict[str, int]:
    """Cuenta cuántas comparaciones hay en cada estado."""
    conteo = {e.value: 0 for e in Estado}
    for c in comparaciones:
        conteo[c.estado.value] += 1
    return conteo


def informe_revision(comparaciones: list[Comparacion]) -> str:
    """Texto del contraste: primero las observaciones, luego lo que coincide."""
    obs = [c for c in comparaciones if c.es_observacion]
    ok = [c for c in comparaciones if c.estado == Estado.COINCIDE]
    lineas = ["CONTRASTE DE RESULTADOS (Revisor v1, regla R6)",
              f"Tolerancia: ±{TOLERANCIA_PCT:g} %", ""]
    lineas.append(f"Observaciones: {len(obs)}")
    for n, c in enumerate(obs, start=1):
        ref = f" [{c.referencia}]" if c.referencia else ""
        lineas.append(f"  {n}. {c.nombre} — {c.estado.value.upper()}{ref}: {c.mensaje}")
    lineas += ["", f"Coinciden: {len(ok)}"]
    for c in ok:
        lineas.append(f"  - {c.nombre}: declarado {c.declarado:.4g}, "
                      f"recalculado {c.calculado:.4g} {c.unidad} ({c.diferencia_pct:+.1f} %)")
    return "\n".join(lineas)
