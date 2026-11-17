"""
Catálogo interno de conductores (decisión 2 de la Fase 0).

El proyectista solo escribe el CÓDIGO del cable (por ejemplo "NA2XSY-120").
Los datos eléctricos (r, x, ampacidad, constante k de Ikm) salen de aquí,
no de lo que escriba cada expediente.

IMPORTANTE: estos valores son PRELIMINARES. Se tomaron de los expedientes
revisados en la Fase 0 (columna "fuente") y deben reemplazarse por los valores
oficiales de los catálogos de Indeco y Nexans antes de usar el motor en producción.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Conductor:
    codigo: str          # nombre corto que usa el proyectista
    tipo: str            # "subterraneo" o "aereo"
    material: str        # "Cu", "Al" o "AAAC"
    seccion_mm2: float
    r_ohm_km: float      # resistencia a temperatura de operación
    x_ohm_km: float      # reactancia (depende de la disposición; aquí, la típica)
    icat_a: float        # ampacidad de catálogo en condiciones base
    fuente: str          # de dónde salió el dato (para reemplazarlo luego)
    aislado: bool = True # False solo para aéreo desnudo (AAAC); el autoportante NA2XSA2Y-S es aéreo aislado


# Constante k de la corriente de cortocircuito admisible: Ikm = k * S / raiz(t)
# (S en mm2, t en s, Ikm en kA). Depende SOLO del material del conductor.
# Así se evita el error R7 (usar 0.143 de cobre en un cable de aluminio).
K_IKM = {
    "Cu": 0.143,     # cobre con aislamiento XLPE
    "Al": 0.0945,    # aluminio con aislamiento XLPE
    "AAAC": 0.0884,  # aleación de aluminio desnudo
}


CATALOGO = {
    c.codigo: c
    for c in [
        Conductor("NA2XSY-70", "subterraneo", "Al", 70, 0.443, 0.157, 186,
                  "Exp. Poder Judicial Huaura (OV-2206490)"),
        Conductor("NA2XSY-120", "subterraneo", "Al", 120, 0.324, 0.149, 300,
                  "Exp. Sol de Olmos (OV-2168507)"),
        Conductor("N2XSY-50", "subterraneo", "Cu", 50, 0.4937, 0.1657, 250,
                  "Tesis Palomino 2021 (r, x) y Aliaga 2022 (Icat)"),
        Conductor("AAAC-70", "aereo", "AAAC", 70, 0.482, 0.43, 0,
                  "Exp. ASR (r); x típica; Icat POR COMPLETAR", aislado=False),
        Conductor("AAAC-120", "aereo", "AAAC", 120, 0.2877, 0.43, 0,
                  "Exp. Redondos (r); x típica; Icat POR COMPLETAR", aislado=False),
        Conductor("NA2XSA2Y-S-35", "aereo", "Al", 35, 0.904, 0.44, 0,
                  "Exp. aprobado Caracoto, Electro Puno (r a 40 °C, x); Icat POR COMPLETAR"),
    ]
}


def buscar_conductor(codigo: str) -> Conductor:
    """Devuelve el conductor del catálogo o da un error claro si no existe."""
    if codigo not in CATALOGO:
        disponibles = ", ".join(sorted(CATALOGO))
        raise ValueError(
            f"Conductor '{codigo}' no está en el catálogo. Disponibles: {disponibles}"
        )
    return CATALOGO[codigo]
