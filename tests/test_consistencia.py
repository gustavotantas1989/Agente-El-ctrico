"""Pruebas del Revisor v1 — sesión 2: consistencia entre capítulos (R1–R5)."""

import pytest

from motor_su.consistencia import (Mencion, leer_conductor, leer_longitud_m, leer_numero,
                                   revisar_consistencia)
from motor_su.ejemplos import caracoto, menciones_caracoto, menciones_sol_de_olmos, sol_de_olmos
from motor_su.modelos import ProyectoSU


def _revisar(datos, menciones):
    hallazgos = revisar_consistencia(ProyectoSU(**datos), [Mencion(**m) for m in menciones])
    return {(h.regla, h.titulo): h for h in hallazgos}


def _por_regla(hallazgos, regla):
    return [h for (r, _), h in hallazgos.items() if r == regla]


# --- Lectura de textos -------------------------------------------------------

def test_lee_numeros_con_coma_o_punto():
    assert leer_numero("0,85") == 0.85
    assert leer_numero("37.30 kW") == 37.3


def test_lee_longitud_en_km():
    assert leer_longitud_m("L = 0.14313 km") == pytest.approx(143.13)
    assert leer_longitud_m("143.13 m") == 143.13


@pytest.mark.parametrize("texto, familia, seccion, clase", [
    ("3-1x120mm2 NA2XSA2Y 18/30kV", "NA2XSA2Y", 120, "18/30"),
    ("NA2XSA2Y de 3-1x120 mm2, 18/30 kV", "NA2XSA2Y", 120, "18/30"),
    ("N2XSY 1x35mm², 8,7/15 kV", "N2XSY", 35, "8.7/15"),
    ("120 mm² - AAAC", "AAAC", 120, None),
    ("NA2XSY 18/30 kV 3-1x120 mm²", "NA2XSY", 120, "18/30"),
])
def test_lee_designaciones_de_cable(texto, familia, seccion, clase):
    c = leer_conductor(texto)
    assert (c["familia"], c["seccion"], c["clase"]) == (familia, seccion, clase)


# --- Caracoto (expediente aprobado) -----------------------------------------

def test_caracoto_r1_detecta_conductor_con_varias_designaciones():
    h = _por_regla(_revisar(caracoto(), menciones_caracoto()), "R1")[0]
    assert not h.consistente
    texto = " ".join(h.detalle)
    assert "AAAC" in texto and "N2XSY" in texto and "120 mm²" in texto


def test_caracoto_r4_detecta_md_distinta():
    h = _por_regla(_revisar(caracoto(), menciones_caracoto()), "R4")[0]
    assert not h.consistente
    assert "35.22" in h.mensaje and "37.3" in h.mensaje


def test_caracoto_lo_demas_es_consistente():
    hs = _revisar(caracoto(), menciones_caracoto())
    for regla in ("R2", "R3", "R5"):
        assert all(h.consistente for h in _por_regla(hs, regla)), regla


# --- Sol de Olmos ------------------------------------------------------------

def test_sol_de_olmos_r1_cable_aereo_en_tramo_subterraneo():
    h = _por_regla(_revisar(sol_de_olmos(), menciones_sol_de_olmos()), "R1")[0]
    assert not h.consistente
    assert any("cable aéreo y el tramo es subterráneo" in d for d in h.detalle)
    assert any("12/20, 18/30" in d for d in h.detalle)   # dos clases de tensión


def test_sol_de_olmos_longitud_en_km_es_consistente():
    h = _por_regla(_revisar(sol_de_olmos(), menciones_sol_de_olmos()), "R2")[0]
    assert h.consistente


# --- Casos sueltos -----------------------------------------------------------

def test_r3_detecta_dos_cos_phi():
    hs = _revisar(sol_de_olmos(), [
        {"campo": "cos_phi", "valor": "0.85", "referencia": "Memoria"},
        {"campo": "cos_phi", "valor": "0.9", "referencia": "Cálculos"},
    ])
    h = _por_regla(hs, "R3")[0]
    assert not h.consistente and "0.9" in h.detalle[0]


def test_r5_detecta_pcc_distinta_a_la_carta():
    hs = _revisar(sol_de_olmos(), [{"campo": "pcc_mva", "valor": "250 MVA", "referencia": "Cálculos"}])
    assert not _por_regla(hs, "R5")[0].consistente


def test_r5_carta_se_compara_sin_importar_el_formato():
    hs = _revisar(caracoto(), [{"campo": "carta", "valor": "Carta Nº 071-2021-ELPU/GT-P FP"}])
    assert _por_regla(hs, "R5")[0].consistente


def test_sin_menciones_no_hay_hallazgos():
    assert revisar_consistencia(ProyectoSU(**caracoto()), []) == []
