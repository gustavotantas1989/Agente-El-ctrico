"""
Motor de cálculo del Agente Eléctrico — Fase 2.

Funciones Python puras: sin inteligencia artificial, sin internet.
Reciben números y devuelven números, siempre los mismos para los mismos datos.

Cada verificación devuelve un ResultadoCalculo: una fila del "protocolo de pruebas"
con el valor, su unidad, el límite contra el que se compara y si cumple.

Sesión 1: corriente nominal y corriente de diseño.
Sesión 2: corriente de cortocircuito y cortocircuito admisible del cable (Ikm).
Sesión 3: caída de tensión (incluida la caída previa hasta el punto de diseño).
Sesión 5: Pcc en barras de la subestación y fusible mínimo sugerido.
Sesión 6: resistencia de puesta a tierra (Dwight, IEEE 80 / IEEE 142).
Sesión 7: calcular_proyecto, el informe completo.
(La sesión 4, ampacidad corregida, espera las tablas de factores de Indeco.)
"""

import math
from dataclasses import dataclass
from typing import Optional

from .conductores import K_IKM, buscar_conductor
from . import factores
from .modelos import BaseCorriente, ProyectoSU, TipoSubestacion


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
    clave: Optional[str] = None      # identificador fijo para el Revisor, ej. "icc_20kv"

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
            clave=f"in_{v:g}kv",
            nombre=f"Corriente nominal a {v:g} kV",
            valor=corriente_nominal(s, v),
            unidad="A",
            formula=f"In = S / (√3 × V) = {s:g} / (√3 × {v:g})",
        ))
        resultados.append(ResultadoCalculo(
            clave=f"idis_{v:g}kv",
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
            clave=f"icc_{v:g}kv",
            nombre=f"Corriente de cortocircuito a {v:g} kV",
            valor=icc,
            unidad="kA",
            formula=f"Icc = Pcc / (√3 × V) = {pcc:g} / (√3 × {v:g})",
        ))
        for codigo in conductores:
            c = buscar_conductor(codigo)
            ikm = ikm_admisible(c.material, c.seccion_mm2, t)
            resultados.append(ResultadoCalculo(
                clave=f"ikm_{codigo}_{v:g}kv",
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
        for n, tramo in enumerate(proyecto.tramos, start=1):
            c = buscar_conductor(tramo.conductor)
            x = c.reactancia(tramo.disposicion)
            dv = caida_tension_v(i, tramo.longitud_m / 1000, c.r_ohm_km, x, cos_phi)
            total_v += dv
            resultados.append(ResultadoCalculo(
                clave=f"dv_t{n}_{v:g}kv",
                nombre=f"Caída de tensión tramo '{tramo.nombre}' a {v:g} kV",
                valor=dv,
                unidad="V",
                formula=(f"ΔV = √3 × {i:.2f} × {tramo.longitud_m / 1000:g} × "
                         f"({c.r_ohm_km} × {cos_phi} + {x} × sen φ)"),
            ))
        total_pct = caida_tension_pct(total_v, v) + previo
        formula = "ΔV% = Σ ΔV tramos / V × 100"
        if previo:
            formula += f" + {previo:g} % previo al punto de diseño"
        resultados.append(ResultadoCalculo(
            clave=f"dv_total_{v:g}kv",
            nombre=f"Caída de tensión total a {v:g} kV",
            valor=total_pct,
            unidad="%",
            formula=formula,
            limite=admisible,
            cumple=total_pct <= admisible,
        ))
    return resultados


# ---------------------------------------------------------------------------
# Sesión 4: ampacidad corregida (capacidad de corriente del cable subterráneo)
# ---------------------------------------------------------------------------

def ampacidad_corregida(tramo) -> tuple[float, dict]:
    """
    I admisible = Icat × Ft × Fr × Fp × Fd × Fa, con cada factor normalizado a las
    condiciones base del catálogo (ver motor_su/factores.py).
    Devuelve (ampacidad en A, diccionario con cada factor) para mostrarlo en el informe.
    """
    c = buscar_conductor(tramo.conductor)
    icat = c.ampacidad_base(tramo.disposicion)
    if icat <= 0:
        raise ValueError(f"El conductor {c.codigo} no tiene ampacidad de catálogo cargada")
    f = {
        "Icat": icat,
        "Ft": factores.factor_temperatura_terreno(tramo.temperatura_terreno_c),
        "Fr": factores.factor_resistividad_termica(tramo.resistividad_termica_kmw),
        "Fp": factores.factor_profundidad(tramo.profundidad_m, c.seccion_mm2),
        "Fd": factores.factor_ducto(tramo.instalacion, c.seccion_mm2),
        "Fa": tramo.factor_agrupamiento,
    }
    valor = icat * f["Ft"] * f["Fr"] * f["Fp"] * f["Fd"] * f["Fa"]
    return valor, f


def calcular_ampacidad(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """
    Para cada tramo SUBTERRÁNEO: I admisible ≥ I de diseño.
    Se compara con la mayor corriente de diseño (la de la tensión más baja, si hay doble tensión).
    Los tramos aéreos se omiten hasta tener la ficha de esos conductores.
    """
    s = potencia_base_kva(proyecto)
    tensiones = tensiones_de_calculo(proyecto)
    v_min = min(tensiones)
    i_dis = corriente_diseno(s, v_min)
    resultados = []
    for n, tramo in enumerate(proyecto.tramos, start=1):
        if tramo.tipo != "subterraneo":
            continue
        valor, f = ampacidad_corregida(tramo)
        resultados.append(ResultadoCalculo(
            clave=f"ampacidad_t{n}",
            nombre=f"Ampacidad corregida tramo '{tramo.nombre}' ({tramo.conductor}, {tramo.disposicion})",
            valor=valor,
            unidad="A",
            formula=(f"I = {f['Icat']:g} × Ft {f['Ft']:.3f} × Fr {f['Fr']:.3f} × Fp {f['Fp']:.3f}"
                     f" × Fd {f['Fd']:.2f} × Fa {f['Fa']:.2f}  ≥  Idis a {v_min:g} kV"),
            limite=i_dis,
            cumple=valor >= i_dis,
            norma="Ficha Indeco/CELSA (IEC 60502-2) + CNE Distribución 2011, Tablas 2-XXXII, 2-XXXV, 2-XXXVI",
        ))
    return resultados


# ---------------------------------------------------------------------------
# Sesión 5: Pcc en barras de la subestación
# ---------------------------------------------------------------------------

def pcc_en_barras(pcc_mva: float, v_kv: float, r_ohm: float, x_ohm: float) -> float:
    """
    Pcc al final del cable, en barras de la SE.
    Z sistema = V² / Pcc (se toma como reactancia pura), Z cable = R + jX.
    Pcc barras = V² / |Z sistema + Z cable|.  (MVA, con V en kV y Z en ohmios)
    """
    if pcc_mva <= 0:
        raise ValueError(f"La Pcc debe ser positiva (llegó {pcc_mva} MVA)")
    z_sistema = v_kv ** 2 / pcc_mva            # ohmios
    z_total = abs(complex(r_ohm, z_sistema + x_ohm))
    return v_kv ** 2 / z_total


def calcular_pcc_barras(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """Pcc e Icc en barras de la SE, sumando la impedancia de todos los tramos."""
    r_total = x_total = 0.0
    for tramo in proyecto.tramos:
        c = buscar_conductor(tramo.conductor)
        r_total += c.r_ohm_km * tramo.longitud_m / 1000
        x_total += c.reactancia(tramo.disposicion) * tramo.longitud_m / 1000
    resultados = []
    for v, pcc in pcc_por_tension(proyecto).items():
        pcc_b = pcc_en_barras(pcc, v, r_total, x_total)
        resultados.append(ResultadoCalculo(
            clave=f"pcc_barras_{v:g}kv",
            nombre=f"Pcc en barras de la SE a {v:g} kV",
            valor=pcc_b,
            unidad="MVA",
            formula=f"Pcc = V² / |j·V²/{pcc:g} + ({r_total:.4f} + j{x_total:.4f})|",
        ))
        resultados.append(ResultadoCalculo(
            clave=f"icc_barras_{v:g}kv",
            nombre=f"Icc en barras de la SE a {v:g} kV",
            valor=corriente_cortocircuito(pcc_b, v),
            unidad="kA",
            formula="Icc = Pcc barras / (√3 × V)",
        ))
    return resultados


# ---------------------------------------------------------------------------
# Sesión 5: fusible mínimo sugerido
# ---------------------------------------------------------------------------

# Calibres comerciales. Tipo K (cut-out, SE aéreas): ANSI C37.42.
# Tipo HH (celdas, SE caseta o interior): IEC 60282-1.
FUSIBLES_K = [1, 2, 3, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 65, 80, 100, 140, 200]
FUSIBLES_HH = [6.3, 10, 16, 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200]
FACTOR_FUSIBLE = 1.5  # criterio CNE: 1.5 × In y el calibre comercial siguiente

SE_CON_CELDAS = {TipoSubestacion.CASETA, TipoSubestacion.INTERIOR_EDIFICIO,
                 TipoSubestacion.COMPACTA}


def fusible_minimo(in_a: float, serie: list[float], factor: float = FACTOR_FUSIBLE) -> float:
    """Primer calibre comercial ≥ factor × In."""
    requerido = factor * in_a
    for calibre in serie:
        if calibre >= requerido:
            return calibre
    raise ValueError(f"No hay fusible comercial ≥ {requerido:.1f} A en la serie")


def calcular_fusibles(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """
    Fusible mínimo sugerido para cada transformador y tensión.
    Es una PROPUESTA (cumple = None): los trafos pequeños suelen llevar fusibles
    de ~1.0-1.1 × In por tabla del fabricante (caso Caracoto, 3K para 2.89 A).
    La tabla de fusibles por potencia y tensión queda como afinamiento (regla R11).
    """
    resultados = []
    for i, se in enumerate(proyecto.subestaciones, start=1):
        con_celdas = se.tipo in SE_CON_CELDAS
        serie, tipo = (FUSIBLES_HH, "HH") if con_celdas else (FUSIBLES_K, "K")
        for j, trafo in enumerate(se.transformadores, start=1):
            for v in tensiones_de_calculo(proyecto):
                in_a = corriente_nominal(trafo.kva, v)
                resultados.append(ResultadoCalculo(
                    clave=f"fusible_se{i}_tr{j}_{v:g}kv",
                    nombre=f"Fusible {tipo} sugerido, trafo {trafo.kva:g} kVA a {v:g} kV",
                    valor=fusible_minimo(in_a, serie),
                    unidad="A",
                    formula=f"Calibre comercial ≥ {FACTOR_FUSIBLE} × In = {FACTOR_FUSIBLE} × {in_a:.2f} A",
                ))
    return resultados


# ---------------------------------------------------------------------------
# Sesión 6: puesta a tierra
# ---------------------------------------------------------------------------

def resistencia_varilla(rho_ohm_m: float, l_m: float, d_m: float) -> float:
    """
    Resistencia de una varilla vertical (H. B. Dwight, 1936; IEEE 80 e IEEE 142):
        R = ρ / (2πL) × (ln(4L / a) − 1),   con a = RADIO = d / 2.
    Ojo: varios expedientes ponen el diámetro donde va el radio y subestiman R ~11 %.
    """
    if rho_ohm_m <= 0 or l_m <= 0 or d_m <= 0:
        raise ValueError("Resistividad, longitud y diámetro deben ser positivos")
    a = d_m / 2
    return rho_ohm_m / (2 * math.pi * l_m) * (math.log(4 * l_m / a) - 1)


def calcular_puesta_tierra(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    sitio = proyecto.sitio
    r = resistencia_varilla(sitio.resistividad_ohm_m, sitio.varilla_longitud_m,
                            sitio.varilla_diametro_mm / 1000)
    r_final = r * sitio.factor_tratamiento_pat
    formula = (f"R = {sitio.resistividad_ohm_m:g} / (2π × {sitio.varilla_longitud_m:g}) × "
               f"(ln(4 × {sitio.varilla_longitud_m:g} / {sitio.varilla_diametro_mm / 2000:g}) − 1)")
    if sitio.factor_tratamiento_pat < 1:
        formula += f" × {sitio.factor_tratamiento_pat:g} (tratamiento)"
    return [ResultadoCalculo(
        clave="r_pat",
        nombre="Resistencia de puesta a tierra (una varilla)",
        valor=r_final,
        unidad="Ω",
        formula=formula,
        limite=sitio.r_pat_max_ohm,
        cumple=r_final <= sitio.r_pat_max_ohm,
    )]


# ---------------------------------------------------------------------------
# Sesión 7: el informe completo
# ---------------------------------------------------------------------------

def calcular_proyecto(proyecto: ProyectoSU) -> list[ResultadoCalculo]:
    """Corre toda la cadena de cálculo, en orden, y devuelve el informe completo."""
    return (calcular_corrientes(proyecto)
            + calcular_ampacidad(proyecto)
            + calcular_cortocircuito(proyecto)
            + calcular_caida_tension(proyecto)
            + calcular_pcc_barras(proyecto)
            + calcular_fusibles(proyecto)
            + calcular_puesta_tierra(proyecto))


def imprimir_informe(proyecto: ProyectoSU) -> str:
    """Informe en texto: resultados, observaciones y advertencias."""
    resultados = calcular_proyecto(proyecto)
    lineas = [f"INFORME DE CÁLCULO — {proyecto.nombre}", ""]
    lineas += [f"  {r}" for r in resultados]
    fallas = [r for r in resultados if r.cumple is False]
    ok = sum(r.cumple is True for r in resultados)
    lineas += ["", f"Verificaciones: {ok} cumple{'n' if ok != 1 else ''}, "
                   f"{len(fallas)} no cumple{'n' if len(fallas) != 1 else ''}"]
    for r in fallas:
        lineas.append(f"  NO CUMPLE: {r.nombre}")
    avisos = proyecto.advertencias()
    if avisos:
        lineas += ["", "Advertencias:"] + [f"  - {a}" for a in avisos]
    return "\n".join(lineas)
