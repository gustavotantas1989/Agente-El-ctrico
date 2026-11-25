"""
Catálogo interno de conductores (decisión 2 de la Fase 0).

El proyectista solo escribe el CÓDIGO del cable (por ejemplo "NA2XSY-120").
Los datos eléctricos (r, x, ampacidad, constante k de Ikm) salen de aquí,
no de lo que escriba cada expediente.

Versión 2 (24/11/2026): los cables subterráneos usan valores OFICIALES de ficha
de fabricante, con su fuente en la columna "fuente":
  - NA2XSY 18/30 kV (aluminio): ficha Indeco/Nexans incluida en el anexo de
    catálogos del Exp. Redondos (OV-2330301); coincide con la ficha publicada
    por Nexans Perú.
  - N2XSY 18/30 kV (cobre): ficha CELSA incluida en el Exp. Minera Vicus (OV-2300525).

Condiciones base de las ampacidades (NTP-IEC 60502-2, Anexo B):
  conductor 90 °C · terreno 20 °C · profundidad 0.8 m · resistividad térmica
  del suelo 1.5 K·m/W · aire 30 °C · pantallas a tierra en ambos extremos.

Los cables AÉREOS (AAAC y autoportante) siguen PRELIMINARES: falta su ficha.
"""

from dataclasses import dataclass

# Condiciones base de las fichas (para normalizar los factores de corrección)
BASE_T_TERRENO_C = 20.0
BASE_PROFUNDIDAD_M = 0.8
BASE_RESISTIVIDAD_KMW = 1.5


@dataclass(frozen=True)
class Conductor:
    codigo: str               # nombre corto que usa el proyectista
    tipo: str                 # "subterraneo" o "aereo"
    material: str             # "Cu", "Al" o "AAAC"
    seccion_mm2: float
    r_ohm_km: float           # resistencia en CA a temperatura de operación (90 °C en XLPE)
    x_trebol_ohm_km: float    # reactancia, 3 unipolares en trébol (triángulo)
    x_plano_ohm_km: float     # reactancia, 3 unipolares en plano
    icat_trebol_a: float      # ampacidad enterrado en condiciones base, trébol (0 = sin dato)
    icat_plano_a: float       # ampacidad enterrado en condiciones base, plano (0 = sin dato)
    fuente: str               # de dónde salió el dato
    aislado: bool = True      # False solo para aéreo desnudo (AAAC)

    def reactancia(self, disposicion: str = "trebol") -> float:
        """Reactancia según cómo van los 3 cables: 'trebol' o 'plano'."""
        return self.x_plano_ohm_km if disposicion == "plano" else self.x_trebol_ohm_km

    def ampacidad_base(self, disposicion: str = "trebol") -> float:
        """Ampacidad de catálogo (enterrado, condiciones base) según la disposición."""
        return self.icat_plano_a if disposicion == "plano" else self.icat_trebol_a


# Constante k de la corriente de cortocircuito admisible: Ikm = k * S / raiz(t)
# (S en mm2, t en s, Ikm en kA). Depende SOLO del material del conductor.
# Verificado contra IEC 60949 para Cu y Al con XLPE (90 → 250 °C).
K_IKM = {
    "Cu": 0.143,     # cobre con aislamiento XLPE
    "Al": 0.0945,    # aluminio con aislamiento XLPE
    "AAAC": 0.0884,  # aleación de aluminio desnudo (POR VERIFICAR)
}

_INDECO = "Ficha Indeco NA2XSY 18/30 kV (anexo Exp. Redondos OV-2330301)"
_CELSA = "Ficha CELSA N2XSY 18/30 kV (anexo Exp. Minera Vicus OV-2300525)"

CATALOGO = {
    c.codigo: c
    for c in [
        # --- Subterráneos, aluminio (Indeco) ---------------------------------
        #          código        tipo         mat  S    R90    X trébol X plano Itr  Ipl
        Conductor("NA2XSY-50", "subterraneo", "Al", 50, 0.822, 0.167, 0.236, 152, 157, _INDECO),
        Conductor("NA2XSY-70", "subterraneo", "Al", 70, 0.568, 0.156, 0.226, 186, 192, _INDECO),
        Conductor("NA2XSY-95", "subterraneo", "Al", 95, 0.411, 0.148, 0.218, 221, 229, _INDECO),
        Conductor("NA2XSY-120", "subterraneo", "Al", 120, 0.325, 0.143, 0.213, 252, 260, _INDECO),
        Conductor("NA2XSY-185", "subterraneo", "Al", 185, 0.211, 0.134, 0.204, 317, 324, _INDECO),
        Conductor("NA2XSY-240", "subterraneo", "Al", 240, 0.162, 0.129, 0.198, 367, 373, _INDECO),
        # --- Subterráneos, cobre (CELSA) -------------------------------------
        Conductor("N2XSY-50", "subterraneo", "Cu", 50, 0.494, 0.179, 0.249, 196, 203, _CELSA),
        Conductor("N2XSY-70", "subterraneo", "Cu", 70, 0.342, 0.170, 0.240, 239, 246, _CELSA),
        Conductor("N2XSY-120", "subterraneo", "Cu", 120, 0.196, 0.156, 0.225, 323, 332, _CELSA),
        # --- Aéreos: PRELIMINARES (falta ficha) ------------------------------
        Conductor("AAAC-70", "aereo", "AAAC", 70, 0.482, 0.43, 0.43, 0, 0,
                  "Exp. ASR (r); x típica; Icat POR COMPLETAR", aislado=False),
        Conductor("AAAC-120", "aereo", "AAAC", 120, 0.2877, 0.43, 0.43, 0, 0,
                  "Exp. Redondos (r); x típica; Icat POR COMPLETAR", aislado=False),
        Conductor("NA2XSA2Y-S-35", "aereo", "Al", 35, 0.904, 0.44, 0.44, 0, 0,
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
