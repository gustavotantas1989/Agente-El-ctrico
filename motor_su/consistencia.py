"""
Revisor v1 — Sesión 2: reglas de consistencia entre capítulos (R1 a R5).

Un expediente repite los mismos datos en varios capítulos (memoria, cálculos,
especificaciones, metrado, planos). Si no coinciden, al menos uno está mal.
Estas reglas NO recalculan nada: revisan que el expediente sea coherente consigo
mismo y con la carta de punto de diseño.

  R1  El conductor (tipo, sección y clase de tensión) es el mismo en todos los capítulos.
  R2  La longitud de cada tramo coincide entre capítulos.
  R3  Se usa un solo cos φ.
  R4  MD declarada = MD usada en los cálculos = potencia de la carta.
  R5  Tensión, Pcc, tiempo de apertura y N° de carta coinciden con la carta.

Cada dato que aparece en el expediente se ingresa como una "Mencion"
(dato + valor tal como está escrito + dónde aparece).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from .conductores import buscar_conductor
from .modelos import ProyectoSU

Campo = Literal["conductor", "longitud_m", "cos_phi", "md_kw",
                "tension_kv", "pcc_mva", "t_apertura_s", "carta"]

# Nombre legible de cada campo (para la página web y los mensajes)
CAMPOS = {
    "conductor": "Conductor (designación)",
    "longitud_m": "Longitud del tramo (m)",
    "cos_phi": "Factor de potencia (cos φ)",
    "md_kw": "Máxima demanda (kW)",
    "tension_kv": "Tensión del punto de diseño (kV)",
    "pcc_mva": "Pcc del punto de diseño (MVA)",
    "t_apertura_s": "Tiempo de apertura (s)",
    "carta": "N° de carta de punto de diseño",
}


class Mencion(BaseModel):
    """Un dato tal como aparece escrito en un capítulo del expediente."""
    campo: Campo
    valor: str = Field(description="Tal como está escrito, ej. '0,85' o '3-1x120mm2 NA2XSA2Y 18/30kV'")
    referencia: str = Field("", description="Capítulo / página donde aparece")
    tramo: int = Field(1, ge=1, description="Para conductor y longitud: N° de tramo")


@dataclass
class Hallazgo:
    regla: str            # "R1" … "R5"
    titulo: str
    consistente: bool
    mensaje: str
    detalle: list[str] = field(default_factory=list)  # cada mención con su referencia

    @property
    def es_observacion(self) -> bool:
        return not self.consistente


# ---------------------------------------------------------------------------
# Lectura de textos del expediente
# ---------------------------------------------------------------------------

# Familias de cable que reconoce el Revisor, de la más larga a la más corta
# (para que "NA2XSA2Y" no se confunda con "NA2XSY").
_FAMILIAS = ["NA2XSA2Y", "NA2XSEY", "N2XSEY", "NA2XSY", "N2XSY", "AAAC", "AAC", "CAAI", "NYY"]
_FAMILIA_TIPO = {"NA2XSA2Y": "aereo", "AAAC": "aereo", "AAC": "aereo", "CAAI": "aereo"}


def leer_numero(texto: str) -> float:
    """'0,85' → 0.85 ; '143.13 m' → 143.13 ; '37.30 kW' → 37.3."""
    m = re.search(r"-?\d+(?:[.,]\d+)?", texto.replace(" ", ""))
    if not m:
        raise ValueError(f"No se encontró un número en '{texto}'")
    return float(m.group().replace(",", "."))


def leer_conductor(texto: str) -> dict:
    """
    Extrae familia, sección y clase de tensión de una designación libre.
    '3-1x120mm2 NA2XSA2Y 18/30kV' → {'familia': 'NA2XSA2Y', 'seccion': 120, 'clase': '18/30'}
    """
    t = texto.upper().replace(" ", "").replace("²", "2")
    familia = next((f for f in _FAMILIAS if f in t), None)
    m_sec = (re.search(r"(\d+(?:[.,]\d+)?)MM2?", t)
             or re.search(r"\dX(\d+(?:[.,]\d+)?)", t))
    seccion = float(m_sec.group(1).replace(",", ".")) if m_sec else None
    con_espacios = texto.upper()
    m_clase = re.search(r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s*/\s*(\d{2})\s*KV", con_espacios)
    clase = f"{m_clase.group(1).replace(',', '.')}/{m_clase.group(2)}" if m_clase else None
    return {"familia": familia, "seccion": seccion, "clase": clase}


def _familia_del_catalogo(codigo: str) -> tuple[str, float]:
    """'NA2XSA2Y-S-35' → ('NA2XSA2Y', 35.0); 'NA2XSY-120' → ('NA2XSY', 120.0)."""
    base, seccion = codigo.rsplit("-", 1)
    familia = next((f for f in _FAMILIAS if base.startswith(f)), base)
    return familia, float(seccion)


def _normalizar_carta(texto: str) -> str:
    """'CARTA N° 071-2021-ELPU/GT-P FP' y '071-2021-ELPU/GT-P FP' quedan iguales."""
    t = texto.upper()
    for palabra in ("CARTA", "N°", "Nº", "NRO.", "NRO", "DOCUMENTO"):
        t = t.replace(palabra, "")
    return re.sub(r"[^A-Z0-9]", "", t)


def leer_longitud_m(texto: str) -> float:
    """'143.13 m' → 143.13 ; 'L = 0.14313 km' → 143.13."""
    v = leer_numero(texto)
    return v * 1000 if re.search(r"\d\s*KM\b", texto.upper()) else v


def _lista(menciones: list[Mencion]) -> list[str]:
    return [f"'{m.valor}'" + (f" ({m.referencia})" if m.referencia else "") for m in menciones]


# ---------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------

def regla_r1_conductor(proyecto: ProyectoSU, menciones: list[Mencion]) -> list[Hallazgo]:
    hallazgos = []
    for n, tramo in enumerate(proyecto.tramos, start=1):
        ms = [m for m in menciones if m.campo == "conductor" and m.tramo == n]
        if not ms:
            continue
        fam_ok, sec_ok = _familia_del_catalogo(tramo.conductor)
        tipo = buscar_conductor(tramo.conductor).tipo
        problemas = []
        for m in ms:
            c = leer_conductor(m.valor)
            ref = f" ({m.referencia})" if m.referencia else ""
            if c["familia"] is None:
                problemas.append(f"'{m.valor}'{ref}: no se reconoce el tipo de cable")
            elif c["familia"] != fam_ok:
                tipo_m = _FAMILIA_TIPO.get(c["familia"], "subterraneo")
                nombre_tipo = {"aereo": "aéreo", "subterraneo": "subterráneo"}
                extra = (f" — {c['familia']} es un cable {nombre_tipo[tipo_m]}"
                         f" y el tramo es {nombre_tipo[tipo]}") if tipo_m != tipo else ""
                problemas.append(f"'{m.valor}'{ref}: tipo {c['familia']}, el proyecto usa {fam_ok}{extra}")
            if c["seccion"] is not None and c["seccion"] != sec_ok:
                problemas.append(f"'{m.valor}'{ref}: sección {c['seccion']:g} mm², el proyecto usa {sec_ok:g} mm²")
        clases = {leer_conductor(m.valor)["clase"] for m in ms} - {None}
        if len(clases) > 1:
            problemas.append(f"Clases de tensión distintas entre capítulos: {', '.join(sorted(clases))} kV")
        hallazgos.append(Hallazgo(
            "R1", f"Conductor del tramo '{tramo.nombre}'", not problemas,
            ("El conductor se describe igual en todos los capítulos." if not problemas else
             f"El conductor no se describe igual en todos los capítulos ({len(problemas)} diferencia(s))."),
            problemas or _lista(ms)))
    return hallazgos


def _regla_numerica(regla: str, titulo: str, ms: list[Mencion], referencia: float,
                    nombre_ref: str, unidad: str, tolerancia_rel: float,
                    lector=leer_numero) -> Hallazgo:
    """Compara cada mención con un valor de referencia, con tolerancia relativa."""
    problemas = []
    for m in ms:
        ref = f" ({m.referencia})" if m.referencia else ""
        try:
            v = lector(m.valor)
        except ValueError:
            problemas.append(f"'{m.valor}'{ref}: no es un número")
            continue
        if abs(v - referencia) > tolerancia_rel * abs(referencia):
            problemas.append(f"{v:g} {unidad}{ref} ≠ {referencia:g} {unidad} ({nombre_ref})")
    valores = sorted({lector(m.valor) for m in ms if re.search(r"\d", m.valor)})
    if problemas:
        msg = (f"Se encontraron {len(valores)} valor(es) distinto(s): "
               f"{', '.join(f'{v:g}' for v in valores)} {unidad}. Referencia: {referencia:g} {unidad} ({nombre_ref}).")
    else:
        msg = f"Todas las menciones coinciden con {referencia:g} {unidad} ({nombre_ref})."
    return Hallazgo(regla, titulo, not problemas, msg, problemas or _lista(ms))


def regla_r2_longitudes(proyecto: ProyectoSU, menciones: list[Mencion]) -> list[Hallazgo]:
    hallazgos = []
    for n, tramo in enumerate(proyecto.tramos, start=1):
        ms = [m for m in menciones if m.campo == "longitud_m" and m.tramo == n]
        if ms:
            hallazgos.append(_regla_numerica(
                "R2", f"Longitud del tramo '{tramo.nombre}'", ms, tramo.longitud_m,
                "longitud usada en los cálculos", "m", 0.01, lector=leer_longitud_m))
    return hallazgos


def regla_r3_cos_phi(proyecto: ProyectoSU, menciones: list[Mencion]) -> list[Hallazgo]:
    ms = [m for m in menciones if m.campo == "cos_phi"]
    if not ms:
        return []
    return [_regla_numerica("R3", "Factor de potencia único", ms, proyecto.cuadro_de_cargas.cos_phi,
                            "cos φ usado en los cálculos", "", 0.005)]


def regla_r4_maxima_demanda(proyecto: ProyectoSU, menciones: list[Mencion]) -> list[Hallazgo]:
    ms = [m for m in menciones if m.campo == "md_kw"]
    if not ms:
        return []
    carta = proyecto.punto_de_diseno.potencia_contratada_kw
    return [_regla_numerica("R4", "Máxima demanda = potencia de la carta", ms, carta,
                            "potencia de la carta", "kW", 0.01)]


def regla_r5_punto_de_diseno(proyecto: ProyectoSU, menciones: list[Mencion]) -> list[Hallazgo]:
    pdd = proyecto.punto_de_diseno
    hallazgos = []
    numericos = [("tension_kv", "Tensión del punto de diseño", pdd.tension_nominal_kv, "kV"),
                 ("pcc_mva", "Pcc del punto de diseño", pdd.pcc_3f_mva, "MVA"),
                 ("t_apertura_s", "Tiempo de apertura", pdd.t_apertura_s, "s")]
    for campo, titulo, valor, unidad in numericos:
        ms = [m for m in menciones if m.campo == campo]
        if ms:
            hallazgos.append(_regla_numerica("R5", titulo, ms, valor, "carta de punto de diseño",
                                             unidad, 0.01))
    ms = [m for m in menciones if m.campo == "carta"]
    if ms:
        ok = _normalizar_carta(pdd.carta)
        malas = [f"'{m.valor}'" + (f" ({m.referencia})" if m.referencia else "")
                 for m in ms if _normalizar_carta(m.valor) != ok]
        hallazgos.append(Hallazgo(
            "R5", "N° de carta de punto de diseño", not malas,
            (f"Todas las menciones citan la carta {pdd.carta}." if not malas else
             f"Hay menciones que no citan la carta {pdd.carta}."),
            malas or _lista(ms)))
    return hallazgos


def revisar_consistencia(proyecto: ProyectoSU, menciones: list[Mencion]) -> list[Hallazgo]:
    """Aplica R1 a R5. Solo evalúa los datos que tienen al menos una mención."""
    return (regla_r1_conductor(proyecto, menciones)
            + regla_r2_longitudes(proyecto, menciones)
            + regla_r3_cos_phi(proyecto, menciones)
            + regla_r4_maxima_demanda(proyecto, menciones)
            + regla_r5_punto_de_diseno(proyecto, menciones))


def informe_consistencia(hallazgos: list[Hallazgo]) -> str:
    obs = [h for h in hallazgos if h.es_observacion]
    lineas = ["CONSISTENCIA ENTRE CAPÍTULOS (Revisor v1, reglas R1–R5)", "",
              f"Observaciones: {len(obs)}"]
    for n, h in enumerate(obs, start=1):
        lineas.append(f"  {n}. [{h.regla}] {h.titulo}: {h.mensaje}")
        lineas += [f"       - {d}" for d in h.detalle]
    ok = [h for h in hallazgos if h.consistente]
    lineas += ["", f"Consistentes: {len(ok)}"]
    lineas += [f"  - [{h.regla}] {h.titulo}" for h in ok]
    return "\n".join(lineas)
