"""
Pruebas del motor de cálculo (Fase 2).

Los valores esperados están RECALCULADOS, no copiados del expediente,
porque varios expedientes traen errores (regla R6 del Revisor).
"""

import pytest

from motor_su.calculos import (
    calcular_corrientes,
    corriente_diseno,
    corriente_nominal,
    potencia_base_kva,
)
from motor_su.modelos import ProyectoSU
from tests.test_modelos import datos_sol_de_olmos


# --- Sesión 1: corriente nominal y de diseño --------------------------------

def test_corriente_nominal_sol_de_olmos():
    """Sol de Olmos: trafo de 630 kVA, doble tensión 20 / 10 kV."""
    assert corriente_nominal(630, 20) == pytest.approx(18.19, abs=0.01)
    assert corriente_nominal(630, 10) == pytest.approx(36.37, abs=0.01)


def test_corriente_nominal_poder_judicial():
    """Poder Judicial Huaura: trafo seco de 800 kVA a 20 kV."""
    assert corriente_nominal(800, 20) == pytest.approx(23.09, abs=0.01)


def test_corriente_nominal_bravo():
    """Tesis Bravo (SEAL): 1,000 kVA a 22.9 kV."""
    assert corriente_nominal(1000, 22.9) == pytest.approx(25.21, abs=0.01)


def test_corriente_diseno_es_125_por_ciento():
    assert corriente_diseno(630, 10) == pytest.approx(1.25 * 36.37, abs=0.01)


def test_rechaza_tension_cero():
    with pytest.raises(ValueError, match="tensión"):
        corriente_nominal(630, 0)


def test_rechaza_potencia_negativa():
    with pytest.raises(ValueError, match="potencia"):
        corriente_nominal(-630, 20)


def test_base_por_defecto_es_potencia_instalada():
    p = ProyectoSU(**datos_sol_de_olmos())
    assert potencia_base_kva(p) == 630


def test_base_maxima_demanda():
    """Opción alternativa (caso Fruit Farm): S = MD / cos φ = 500 / 0.85."""
    d = datos_sol_de_olmos()
    d["sitio"]["base_corriente"] = "maxima_demanda"
    p = ProyectoSU(**d)
    assert potencia_base_kva(p) == pytest.approx(588.24, abs=0.01)


def test_proyecto_completo_calcula_en_las_dos_tensiones():
    """Sol de Olmos tiene doble tensión: deben salir 4 resultados (In e Idis × 2)."""
    p = ProyectoSU(**datos_sol_de_olmos())
    resultados = calcular_corrientes(p)
    assert len(resultados) == 4
    valores = {r.nombre: r.valor for r in resultados}
    assert valores["Corriente nominal a 20 kV"] == pytest.approx(18.19, abs=0.01)
    assert valores["Corriente nominal a 10 kV"] == pytest.approx(36.37, abs=0.01)
    assert valores["Corriente de diseño a 10 kV"] == pytest.approx(45.47, abs=0.01)


def test_resultado_se_imprime_legible():
    p = ProyectoSU(**datos_sol_de_olmos())
    texto = str(calcular_corrientes(p)[0])
    assert texto == "Corriente nominal a 20 kV: 18.19 A"


# --- Sesión 2: cortocircuito e Ikm ------------------------------------------

from motor_su.calculos import calcular_cortocircuito, corriente_cortocircuito, ikm_admisible


def datos_caracoto() -> dict:
    """Expediente APROBADO I.E.S. 02 de Mayo, Caracoto (Electro Puno, 2021): 10 kV, 3,825 msnm."""
    return {
        "nombre": "I.E.S. 02 de Mayo Caracoto",
        "tipo_red": "aerea",
        "punto_de_diseno": {
            "carta": "071-2021-ELPU/GT-P FP",
            "fecha_carta": "2021-03-16",
            "potencia_contratada_kw": 37.30,
            "tension_nominal_kv": 10,
            "pcc_3f_mva": 250,
            "t_apertura_s": 0.02,
        },
        "tramite": {"tipo": "nuevo"},
        "cuadro_de_cargas": {
            "items": [{"descripcion": "Cuadro de cargas (agregado)", "cantidad": 1,
                       "potencia_unitaria": 37.30}],
            "fs": 1.0,
            "cos_phi": 0.9,
        },
        "tramos": [{"nombre": "PD - SE", "conductor": "NA2XSA2Y-S-35", "longitud_m": 20.19}],
        "subestaciones": [{
            "nombre": "SE monoposte",
            "tipo": "monoposte",
            "transformadores": [{"kva": 50, "tension_primaria_kv": 10,
                                 "tension_secundaria_v": 380, "aislamiento": "aceite"}],
        }],
        # ρ = 100 Ω·m es PROVISIONAL: la medición del expediente viene como imagen y no se pudo leer
        "sitio": {"concesionaria": "Otra", "altitud_msnm": 3825, "resistividad_ohm_m": 100},
    }


def test_icc_sol_de_olmos():
    assert corriente_cortocircuito(130, 20) == pytest.approx(3.75, abs=0.01)
    assert corriente_cortocircuito(50, 10) == pytest.approx(2.89, abs=0.01)


def test_icc_poder_judicial_y_bravo():
    assert corriente_cortocircuito(213, 20) == pytest.approx(6.15, abs=0.01)
    assert corriente_cortocircuito(250, 22.9) == pytest.approx(6.30, abs=0.01)


def test_ikm_aluminio_120():
    """NA2XSY 120 mm² (aluminio), 0.02 s: coincide con el valor del exp. Redondos (80.19 kA)."""
    assert ikm_admisible("Al", 120, 0.02) == pytest.approx(80.19, abs=0.01)


def test_ikm_usa_k_segun_material():
    """Regla R7: el mismo calibre en cobre soporta más que en aluminio."""
    assert ikm_admisible("Cu", 120, 0.02) > ikm_admisible("Al", 120, 0.02)


def test_ikm_rechaza_material_desconocido():
    with pytest.raises(ValueError, match="sin constante k"):
        ikm_admisible("Oro", 120, 0.02)


def test_cortocircuito_sol_de_olmos_cumple_en_ambas_tensiones():
    p = ProyectoSU(**datos_sol_de_olmos())
    resultados = calcular_cortocircuito(p)
    assert len(resultados) == 4  # (Icc + Ikm) × 2 tensiones
    verificaciones = [r for r in resultados if r.cumple is not None]
    assert all(r.cumple for r in verificaciones)


def test_caracoto_aprobado_cumple():
    """Icc 14.43 kA contra Ikm 23.39 kA del NA2XSA2Y-S 35 mm²."""
    p = ProyectoSU(**datos_caracoto())
    icc, ikm = calcular_cortocircuito(p)
    assert icc.valor == pytest.approx(14.43, abs=0.01)
    assert ikm.valor == pytest.approx(23.39, abs=0.01)
    assert ikm.cumple


def test_caracoto_corriente_nominal():
    p = ProyectoSU(**datos_caracoto())
    assert calcular_corrientes(p)[0].valor == pytest.approx(2.89, abs=0.01)


def test_detecta_cable_que_no_soporta_el_cortocircuito():
    """Si la Pcc fuera 1,000 MVA a 10 kV (57.7 kA), el cable de 35 mm² no alcanza."""
    d = datos_caracoto()
    d["punto_de_diseno"]["pcc_3f_mva"] = 1000
    icc, ikm = calcular_cortocircuito(ProyectoSU(**d))
    assert not ikm.cumple
    assert "NO CUMPLE" in str(ikm)


# --- Sesión 3: caída de tensión ---------------------------------------------

from motor_su.calculos import caida_tension_pct, caida_tension_v, calcular_caida_tension


def test_caida_tension_sol_de_olmos_10kv():
    """Sol de Olmos: 36.37 A, 143.13 m, NA2XSY 120 (R 0.324, X 0.149), cos 0.85 → 3.19 V."""
    dv = caida_tension_v(36.37, 0.14313, 0.324, 0.149, 0.85)
    assert dv == pytest.approx(3.19, abs=0.01)


def test_caida_tension_palomino():
    """Tesis Palomino (Luz del Sur): 10.08 A, 355 m, N2XSY 50, cos 0.85 → 3.14 V."""
    dv = caida_tension_v(10.08, 0.355, 0.4937, 0.1657, 0.85)
    assert dv == pytest.approx(3.14, abs=0.01)
    assert caida_tension_pct(dv, 22.9) == pytest.approx(0.0137, abs=0.0001)


def test_caida_tension_rechaza_cos_phi_invalido():
    with pytest.raises(ValueError, match="cos φ"):
        caida_tension_v(10, 0.1, 0.3, 0.1, 1.5)


def test_proyecto_sol_de_olmos_cumple_en_ambas_tensiones():
    resultados = calcular_caida_tension(ProyectoSU(**datos_sol_de_olmos()))
    totales = [r for r in resultados if r.cumple is not None]
    assert len(totales) == 2
    assert all(r.cumple for r in totales)
    # 3.17 V / 10 kV con la X oficial en trébol (0.143); el expediente declaró 3.19 V (0.6 %: dentro de ±2 %)
    assert totales[1].valor == pytest.approx(0.0317, abs=0.0001)


def test_caracoto_caida_minima():
    """20 m de cable con 2.89 A: ~0.10 V."""
    tramo, total = calcular_caida_tension(ProyectoSU(**datos_caracoto()))
    assert tramo.valor == pytest.approx(0.10, abs=0.01)
    assert total.cumple


def test_red_mixta_suma_los_tramos():
    """Aéreo + subterráneo en serie: la caída total es la suma de ambos tramos."""
    d = datos_sol_de_olmos()
    d["tipo_red"] = "mixta_lineal"
    d["tramos"] = [
        {"nombre": "Aéreo", "conductor": "AAAC-70", "longitud_m": 18},
        {"nombre": "Subterráneo", "conductor": "NA2XSY-120", "longitud_m": 350},
    ]
    resultados = calcular_caida_tension(ProyectoSU(**d))
    aereo, subt, total = resultados[0], resultados[1], resultados[2]
    assert total.valor == pytest.approx((aereo.valor + subt.valor) / 20000 * 100, abs=1e-6)


def test_caida_previa_puede_hacer_que_no_cumpla():
    """Criterio Electrocentro: si ya cae 4.99 % hasta el punto de diseño, no queda margen."""
    d = datos_sol_de_olmos()
    d["sitio"]["dv_previo_punto_diseno_pct"] = 4.99
    total_20kv, total_10kv = [r for r in calcular_caida_tension(ProyectoSU(**d))
                              if r.cumple is not None]
    assert total_20kv.cumple          # 4.99 + 0.008 = 4.998 % ≤ 5 %
    assert not total_10kv.cumple      # 4.99 + 0.032 = 5.022 % > 5 %
    assert "previo" in total_10kv.formula


# --- Sesión 5: Pcc en barras y fusible --------------------------------------

from motor_su.calculos import (
    FUSIBLES_HH, FUSIBLES_K, calcular_fusibles, calcular_pcc_barras,
    calcular_proyecto, calcular_puesta_tierra, fusible_minimo, imprimir_informe,
    pcc_en_barras, resistencia_varilla,
)


def test_pcc_barras_palomino():
    """Tesis Palomino: 230 MVA a 22.9 kV + N2XSY 50 de 355 m → 223.6 MVA."""
    pcc = pcc_en_barras(230, 22.9, 0.4937 * 0.355, 0.1657 * 0.355)
    assert pcc == pytest.approx(223.6, abs=0.1)


def test_pcc_barras_sol_de_olmos_coincide_con_expediente():
    """El expediente reporta 129 MVA (20 kV) y 49.5 MVA (10 kV)."""
    resultados = calcular_pcc_barras(ProyectoSU(**datos_sol_de_olmos()))
    pcc = {r.nombre: r.valor for r in resultados if r.unidad == "MVA"}
    assert pcc["Pcc en barras de la SE a 20 kV"] == pytest.approx(129.1, abs=0.1)
    assert pcc["Pcc en barras de la SE a 10 kV"] == pytest.approx(49.46, abs=0.05)


def test_fusible_k_bravo():
    """Tesis Bravo: In 25.21 A × 1.5 = 37.8 A → 40 A."""
    assert fusible_minimo(25.21, FUSIBLES_K) == 40


def test_fusible_hh_sol_de_olmos_10kv_coincide():
    """Sol de Olmos usa 63 A a 10 kV: 1.5 × 36.37 = 54.6 A → 63 A (serie HH)."""
    assert fusible_minimo(36.37, FUSIBLES_HH) == 63


def test_fusible_usa_serie_segun_tipo_de_se():
    caseta = calcular_fusibles(ProyectoSU(**datos_sol_de_olmos()))
    monoposte = calcular_fusibles(ProyectoSU(**datos_caracoto()))
    assert all("HH" in r.nombre for r in caseta)
    assert all(" K " in r.nombre for r in monoposte)
    assert all(r.cumple is None for r in caseta + monoposte)  # son propuestas


# --- Sesión 6: puesta a tierra ----------------------------------------------

def test_pat_palomino_con_radio_ieee():
    """ρ 46 Ω·m, varilla 2.4 m × 15.88 mm: 18.60 Ω con el RADIO (IEEE 80/142).
    El expediente, con el diámetro, reporta 16.49 Ω (11 % menos)."""
    assert resistencia_varilla(46, 2.4, 0.01588) == pytest.approx(18.60, abs=0.01)


def test_pat_varilla_mas_larga_baja_la_resistencia():
    assert resistencia_varilla(100, 3.0, 0.01588) < resistencia_varilla(100, 2.4, 0.01588)


def test_pat_sol_de_olmos_sin_tratamiento_no_cumple():
    """ρ 148 Ω·m con una varilla da ~60 Ω > 25 Ω: el expediente también pide tratamiento."""
    (r,) = calcular_puesta_tierra(ProyectoSU(**datos_sol_de_olmos()))
    assert r.valor == pytest.approx(59.85, abs=0.05)
    assert not r.cumple


def test_pat_con_tratamiento_cumple():
    d = datos_sol_de_olmos()
    d["sitio"]["factor_tratamiento_pat"] = 0.35
    (r,) = calcular_puesta_tierra(ProyectoSU(**d))
    assert r.valor == pytest.approx(59.85 * 0.35, abs=0.05)
    assert r.cumple
    assert "tratamiento" in r.formula


def test_pat_rechaza_resistividad_cero():
    with pytest.raises(ValueError):
        resistencia_varilla(0, 2.4, 0.01588)


# --- Sesión 7: informe completo ---------------------------------------------

def test_calcular_proyecto_junta_toda_la_cadena():
    resultados = calcular_proyecto(ProyectoSU(**datos_sol_de_olmos()))
    # 4 corrientes + 4 cortocircuito + 4 caída + 4 Pcc barras + 2 fusibles + 1 PAT
    assert len(resultados) == 20  # 19 anteriores + ampacidad del tramo


def test_informe_lista_lo_que_no_cumple():
    texto = imprimir_informe(ProyectoSU(**datos_sol_de_olmos()))
    assert "INFORME DE CÁLCULO — Agropecuaria Sol de Olmos" in texto
    assert "NO CUMPLE: Resistencia de puesta a tierra" in texto
    assert "R10" in texto  # advertencia: resistividad sin fecha de medición


# ---------------------------------------------------------------------------
# Sesión 4: ampacidad corregida
# ---------------------------------------------------------------------------
from motor_su import factores
from motor_su.calculos import ampacidad_corregida, calcular_ampacidad
from motor_su.conductores import buscar_conductor
from motor_su.modelos import Tramo


def test_catalogo_usa_valores_oficiales_indeco():
    """NA2XSY 120 mm² 18/30 kV: R 0.325, X trébol 0.143 / plano 0.213, I enterrado 252 / 260 A."""
    c = buscar_conductor("NA2XSY-120")
    assert c.r_ohm_km == 0.325
    assert c.reactancia("trebol") == 0.143 and c.reactancia("plano") == 0.213
    assert c.ampacidad_base("trebol") == 252 and c.ampacidad_base("plano") == 260


def test_factores_valen_1_en_condiciones_base_del_catalogo():
    """En las condiciones base de Indeco (20 °C, 1.5 K·m/W, 0.8 m) todo factor es 1."""
    assert factores.factor_temperatura_terreno(20) == pytest.approx(1.0)
    assert factores.factor_resistividad_termica(1.5) == pytest.approx(1.0)
    assert factores.factor_profundidad(0.8, 120) == pytest.approx(1.0)
    assert factores.factor_ducto("directo", 120) == 1.0


def test_resistividad_se_normaliza_a_la_base_del_catalogo():
    """CNE 2-XXXII: 2.5 K·m/W → 0.65 y base 1.5 K·m/W → 0.83 ⇒ factor real 0.65/0.83 = 0.783."""
    assert factores.factor_resistividad_termica(2.5) == pytest.approx(0.65 / 0.83, abs=1e-4)
    # Terreno mejor que el de catálogo (1.0 K·m/W) da factor > 1
    assert factores.factor_resistividad_termica(1.0) == pytest.approx(1.0 / 0.83, abs=1e-4)


def test_profundidad_se_normaliza_y_se_interpola():
    assert factores.factor_profundidad(1.0, 120) == pytest.approx(0.96 / 0.98, abs=1e-4)
    assert factores.factor_profundidad(0.9, 120) == pytest.approx(0.97 / 0.98, abs=1e-4)


def test_ducto_depende_de_la_seccion():
    assert factores.factor_ducto("un_ducto", 50) == 0.81
    assert factores.factor_ducto("un_ducto", 120) == 0.79
    assert factores.factor_ducto("tres_ductos_trebol", 240) == 0.78


def test_factor_fuera_de_tabla_da_error():
    with pytest.raises(ValueError, match="fuera de la tabla"):
        factores.factor_temperatura_terreno(60)


def test_ampacidad_sol_de_olmos_con_sus_condiciones():
    """
    Condiciones que declara el expediente: terreno 30 °C, 2.5 K·m/W, 1.0 m, factor de
    proximidad 0.80. Con la ampacidad oficial (252 A trébol) y factores normalizados:
    252 × 0.93 × 0.783 × 0.980 × 1 × 0.80 = 143.8 A.
    El expediente declaró 214.27 A (usó Icat 300 A y Fr = 1.00): ~49 % de más.
    """
    tramo = Tramo(nombre="PMI - SE", conductor="NA2XSY-120", longitud_m=143.13,
                  temperatura_terreno_c=30, resistividad_termica_kmw=2.5,
                  profundidad_m=1.0, factor_agrupamiento=0.80)
    valor, f = ampacidad_corregida(tramo)
    assert valor == pytest.approx(143.8, abs=0.2)
    assert f["Icat"] == 252


def test_plano_tiene_mas_ampacidad_y_mas_reactancia():
    trebol = Tramo(nombre="t", conductor="NA2XSY-120", longitud_m=100)
    plano = Tramo(nombre="p", conductor="NA2XSY-120", longitud_m=100, disposicion="plano")
    assert ampacidad_corregida(plano)[0] > ampacidad_corregida(trebol)[0]


def test_calcular_ampacidad_verifica_contra_corriente_de_diseno():
    """Sol de Olmos: se compara con Idis a 10 kV (45.47 A), la mayor de las dos tensiones."""
    r = calcular_ampacidad(ProyectoSU(**datos_sol_de_olmos()))
    assert len(r) == 1
    assert r[0].limite == pytest.approx(45.47, abs=0.01)
    assert r[0].cumple


def test_ampacidad_detecta_cable_insuficiente():
    d = datos_sol_de_olmos()
    d["tramos"][0].update(conductor="NA2XSY-50", instalacion="un_ducto",
                          temperatura_terreno_c=40, resistividad_termica_kmw=3.0,
                          factor_agrupamiento=0.5)
    d["subestaciones"][0]["transformadores"][0]["kva"] = 2500
    r = calcular_ampacidad(ProyectoSU(**d))
    assert r[0].cumple is False


def test_tramo_aereo_no_se_verifica_por_ampacidad_aun():
    """Caracoto es aéreo: falta la ficha del autoportante, así que no hay verificación."""
    assert calcular_ampacidad(ProyectoSU(**datos_caracoto())) == []
