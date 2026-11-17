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
    assert totales[1].valor == pytest.approx(0.0319, abs=0.0001)  # 3.19 V / 10 kV


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
