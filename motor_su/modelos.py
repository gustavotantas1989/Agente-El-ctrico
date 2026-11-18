"""
Modelos de datos del Agente Eléctrico — Fase 1.

Dos ejes independientes describen el proyecto (revisión de 14 casos):
    - tipo de red: cómo va el cable del punto de diseño a la SE
    - tipo de subestación: caseta, interior, biposte, monoposte o compacta

Analogía: cada clase es una "placa de características" normalizada.
Define qué campos debe tener un dato y rechaza valores incoherentes
ANTES de que lleguen al motor de cálculo.

Los 5 bloques de entrada del contrato de datos (Fase 0):
    1. PuntoDeDiseno       -> lo que dice la carta de la concesionaria
    2. Tramite             -> nuevo suministro, incremento o replanteo
    3. CuadroDeCargas      -> cargas del cliente y máxima demanda
    4. Red + Subestacion   -> tipo de red, tramos de cable y transformadores
    5. SitioYCriterios     -> concesionaria, terreno y criterios de diseño
y el modelo que los reúne: ProyectoSU.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .conductores import buscar_conductor


# ---------------------------------------------------------------------------
# Listas cerradas (Enum): solo se aceptan estos valores
# ---------------------------------------------------------------------------

class TipoTramite(str, Enum):
    NUEVO = "nuevo"
    INCREMENTO = "incremento"
    REPLANTEO = "replanteo"


class TipoRed(str, Enum):
    """Cómo va el cable desde el punto de diseño hasta la subestación."""
    SUBTERRANEA = "subterranea"            # solo cable subterráneo (5 de 14 casos)
    AEREA = "aerea"                        # solo conductor aéreo (2 de 14)
    MIXTA_LINEAL = "mixta_lineal"          # aéreo + subterráneo, una sola SE (3 de 14)
    MIXTA_RAMIFICADA = "mixta_ramificada"  # troncal con derivaciones a varias SE (Fase 8)


class Concesionaria(str, Enum):
    PLUZ = "PLUZ"
    LUZ_DEL_SUR = "Luz del Sur"
    SEAL = "SEAL"
    ELECTROCENTRO = "Electrocentro"
    OTRA = "Otra"


class BaseCorriente(str, Enum):
    POTENCIA_INSTALADA = "potencia_instalada"  # decisión 1 de la Fase 0
    MAXIMA_DEMANDA = "maxima_demanda"


class UnidadPotencia(str, Enum):
    KW = "kW"
    HP = "HP"


class Aislamiento(str, Enum):
    ACEITE = "aceite"
    SECO = "seco"


class TipoSubestacion(str, Enum):
    """Tipo de subestación del cliente (eje independiente del tipo de red)."""
    CASETA = "caseta"                        # caseta de material noble con celdas
    INTERIOR_EDIFICIO = "interior_edificio"  # sótano o ambiente dentro de una edificación
    BIPOSTE = "biposte"
    MONOPOSTE = "monoposte"
    COMPACTA = "compacta"


TAMANOS_COMERCIALES_KVA = [
    25, 37.5, 50, 75, 100, 160, 200, 250, 315, 400, 500, 630,
    800, 1000, 1250, 1600, 2000, 2500, 3150,
]


# ---------------------------------------------------------------------------
# Bloque 1: Punto de diseño (carta de la concesionaria)
# ---------------------------------------------------------------------------

class PuntoDeDiseno(BaseModel):
    carta: str = Field(min_length=3, description="Número de la carta de punto de diseño")
    fecha_carta: date
    potencia_contratada_kw: float = Field(gt=0)
    tension_nominal_kv: float
    tension_operacion_inicial_kv: Optional[float] = None  # ej. 10 kV en doble tensión
    pcc_3f_mva: float = Field(description="Pcc trifásica a la tensión nominal")
    pcc_3f_operacion_inicial_mva: Optional[float] = None
    pcc_1f_mva: Optional[float] = None
    t_apertura_s: float = Field(gt=0, le=1.0)

    @field_validator("tension_nominal_kv", "tension_operacion_inicial_kv")
    @classmethod
    def tension_normalizada(cls, v):
        if v is not None and v not in (10.0, 20.0, 22.9):
            raise ValueError(f"Tensión {v} kV no normalizada (se espera 10, 20 o 22.9 kV)")
        return v

    @field_validator("pcc_3f_mva", "pcc_3f_operacion_inicial_mva", "pcc_1f_mva")
    @classmethod
    def pcc_en_rango(cls, v):
        # En los expedientes y tesis revisados, la Pcc va de 20 a 250 MVA.
        # Un valor como 0.2749 MVA (error de unidades de la tesis de Huanta) se rechaza.
        if v is not None and not (5 <= v <= 1000):
            raise ValueError(
                f"Pcc = {v} MVA fuera de rango (5-1000 MVA). ¿Error de unidades?"
            )
        return v

    @model_validator(mode="after")
    def doble_tension_completa(self):
        if self.tension_operacion_inicial_kv and self.pcc_3f_operacion_inicial_mva is None:
            raise ValueError(
                "Hay tensión de operación inicial, pero falta su Pcc trifásica"
            )
        return self


# ---------------------------------------------------------------------------
# Bloque 2: Trámite
# ---------------------------------------------------------------------------

class Tramite(BaseModel):
    tipo: TipoTramite
    potencia_anterior_kw: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def incremento_requiere_anterior(self):
        if self.tipo == TipoTramite.INCREMENTO and self.potencia_anterior_kw is None:
            raise ValueError("Un incremento de carga requiere la potencia anterior")
        return self


# ---------------------------------------------------------------------------
# Bloque 3: Cuadro de cargas y máxima demanda
# ---------------------------------------------------------------------------

class CargaItem(BaseModel):
    descripcion: str
    cantidad: int = Field(ge=1)
    potencia_unitaria: float = Field(gt=0)
    unidad: UnidadPotencia = UnidadPotencia.KW
    fd: float = Field(default=1.0, gt=0, le=1.0, description="Factor de demanda")

    @property
    def potencia_instalada_kw(self) -> float:
        p = self.potencia_unitaria * (0.746 if self.unidad == UnidadPotencia.HP else 1.0)
        return p * self.cantidad

    @property
    def demanda_kw(self) -> float:
        return self.potencia_instalada_kw * self.fd


class CuadroDeCargas(BaseModel):
    items: list[CargaItem] = Field(min_length=1)
    fs: float = Field(default=1.0, gt=0, le=1.0, description="Factor de simultaneidad")
    cos_phi: float = Field(ge=0.7, le=1.0, description="Un solo cos φ para todo el expediente")

    @property
    def potencia_instalada_kw(self) -> float:
        return sum(i.potencia_instalada_kw for i in self.items)

    @property
    def maxima_demanda_kw(self) -> float:
        return sum(i.demanda_kw for i in self.items) * self.fs


# ---------------------------------------------------------------------------
# Bloque 4: Red y subestación
# ---------------------------------------------------------------------------

class Tramo(BaseModel):
    nombre: str
    conductor: str = Field(description="Código del catálogo, ej. 'NA2XSY-120'")
    longitud_m: float = Field(gt=0)

    @field_validator("conductor")
    @classmethod
    def conductor_existe(cls, v):
        buscar_conductor(v)  # da error si el código no está en el catálogo
        return v

    @property
    def tipo(self) -> str:
        return buscar_conductor(self.conductor).tipo


class Transformador(BaseModel):
    kva: float
    tension_primaria_kv: float
    tension_secundaria_v: float = Field(gt=0, le=1000)
    aislamiento: Aislamiento
    grupo_conexion: str = "Dyn5"

    @field_validator("kva")
    @classmethod
    def tamano_comercial(cls, v):
        if v not in TAMANOS_COMERCIALES_KVA:
            raise ValueError(f"{v} kVA no es un tamaño comercial")
        return v


class Subestacion(BaseModel):
    nombre: str
    tipo: TipoSubestacion
    transformadores: list[Transformador] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Bloque 5: Sitio y criterios
# ---------------------------------------------------------------------------

class SitioYCriterios(BaseModel):
    concesionaria: Concesionaria
    altitud_msnm: float = Field(ge=0, le=5000)
    resistividad_ohm_m: float = Field(gt=0)
    fecha_medicion_resistividad: Optional[date] = None  # None = valor asumido
    dv_admisible_pct: float = Field(default=5.0, gt=0, le=10)
    dv_previo_punto_diseno_pct: float = Field(default=0.0, ge=0, le=5)
    factor_reserva: float = Field(default=1.0, ge=1.0, le=1.5)
    base_corriente: BaseCorriente = BaseCorriente.POTENCIA_INSTALADA
    # Puesta a tierra (sesión 6). Por defecto: varilla de cobre 2.4 m × 5/8" (15.88 mm)
    varilla_longitud_m: float = Field(default=2.4, gt=0, le=10)
    varilla_diametro_mm: float = Field(default=15.88, gt=0, le=50)
    factor_tratamiento_pat: float = Field(
        default=1.0, gt=0, le=1.0,
        description="Multiplica la R calculada si hay tratamiento del terreno (1.0 = sin tratamiento)")
    r_pat_max_ohm: float = Field(default=25.0, gt=0, description="Límite de la concesionaria o del CNE")


# ---------------------------------------------------------------------------
# El proyecto completo
# ---------------------------------------------------------------------------

class ProyectoSU(BaseModel):
    nombre: str
    tipo_red: TipoRed
    punto_de_diseno: PuntoDeDiseno
    tramite: Tramite
    cuadro_de_cargas: CuadroDeCargas
    tramos: list[Tramo] = Field(min_length=1)
    subestaciones: list[Subestacion] = Field(min_length=1)
    sitio: SitioYCriterios

    @property
    def potencia_instalada_kva(self) -> float:
        return sum(t.kva for s in self.subestaciones for t in s.transformadores)

    @model_validator(mode="after")
    def coherencia_tipo_red(self):
        """Los tramos (ordenados del punto de diseño a la SE) deben calzar con el tipo de red."""
        tipos = {t.tipo for t in self.tramos}
        if self.tipo_red == TipoRed.MIXTA_RAMIFICADA:
            raise ValueError("La red ramificada (varias SE) se implementa en la Fase 8")
        if self.tipo_red == TipoRed.SUBTERRANEA and tipos != {"subterraneo"}:
            aereos = [t.nombre for t in self.tramos if t.tipo == "aereo"]
            raise ValueError(f"Red subterránea con tramos aéreos: {aereos}")
        if self.tipo_red == TipoRed.AEREA and tipos != {"aereo"}:
            subt = [t.nombre for t in self.tramos if t.tipo == "subterraneo"]
            raise ValueError(f"Red aérea con tramos subterráneos: {subt}")
        if self.tipo_red == TipoRed.MIXTA_LINEAL and tipos != {"aereo", "subterraneo"}:
            raise ValueError("Una red mixta necesita al menos un tramo aéreo y uno subterráneo")
        if self.tipo_red != TipoRed.MIXTA_RAMIFICADA and len(self.subestaciones) > 1:
            raise ValueError("Con varias subestaciones, el tipo de red debe ser mixta_ramificada")
        return self

    @model_validator(mode="after")
    def trafo_cubre_demanda(self):
        s_requerida = (self.cuadro_de_cargas.maxima_demanda_kw
                       / self.cuadro_de_cargas.cos_phi * self.sitio.factor_reserva)
        if self.potencia_instalada_kva < s_requerida:
            raise ValueError(
                f"Transformadores ({self.potencia_instalada_kva} kVA) no cubren "
                f"la demanda ({s_requerida:.1f} kVA)"
            )
        return self

    def advertencias(self) -> list[str]:
        """Observaciones que no bloquean el cálculo, pero que el Revisor debe reportar."""
        avisos = []
        md = self.cuadro_de_cargas.maxima_demanda_kw
        pc = self.punto_de_diseno.potencia_contratada_kw
        if abs(md - pc) / pc > 0.05:
            avisos.append(f"R4: MD calculada ({md:.1f} kW) difiere de la carta ({pc} kW) en más de 5 %")
        if self.sitio.fecha_medicion_resistividad is None:
            avisos.append("R10: la resistividad no tiene fecha de medición (valor asumido)")
        elif (date.today() - self.sitio.fecha_medicion_resistividad).days > 365 * 3:
            avisos.append("R10: la medición de resistividad tiene más de 3 años")
        for s in self.subestaciones:
            for t in s.transformadores:
                if s.tipo == TipoSubestacion.INTERIOR_EDIFICIO and t.aislamiento == Aislamiento.ACEITE:
                    avisos.append(f"{s.nombre}: trafo en aceite dentro de edificio (CNE-S exige seco)")
        carga_pct = (md / self.cuadro_de_cargas.cos_phi) / self.potencia_instalada_kva * 100
        if carga_pct > 90:
            avisos.append(f"Transformadores al {carga_pct:.0f} % de carga (> 90 %)")
        return avisos
