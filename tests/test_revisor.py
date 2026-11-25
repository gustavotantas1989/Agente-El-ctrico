"""Pruebas del Revisor v1 — sesión 1: comparador de resultados (regla R6)."""

import pytest

from motor_su.calculos import calcular_proyecto
from motor_su.ejemplos import declarados_sol_de_olmos, sol_de_olmos
from motor_su.modelos import ProyectoSU
from motor_su.revisor import (Estado, ValorDeclarado, comparar, convertir,
                              diferencia_porcentual, informe_revision, resumen)


def _revisar_sol_de_olmos(declarados=None):
    resultados = calcular_proyecto(ProyectoSU(**sol_de_olmos()))
    decl = [ValorDeclarado(**d) for d in (declarados or declarados_sol_de_olmos())]
    return {c.clave: c for c in comparar(resultados, decl)}


def test_convierte_unidades():
    assert convertir(3.75, "kA", "A") == pytest.approx(3750)
    assert convertir(500, "kVA", "MVA") == pytest.approx(0.5)
    assert convertir(10, None, "A") == 10


def test_unidades_incompatibles_dan_error():
    with pytest.raises(ValueError, match="incompatibles"):
        convertir(3.75, "kV", "A")


def test_diferencia_porcentual_con_signo():
    assert diferencia_porcentual(214.27, 143.8) == pytest.approx(49.0, abs=0.1)
    assert diferencia_porcentual(57.57, 59.85) == pytest.approx(-3.81, abs=0.01)


def test_sol_de_olmos_lo_que_coincide():
    c = _revisar_sol_de_olmos()
    for clave in ["idis_10kv", "dv_t1_10kv", "dv_total_10kv", "icc_20kv",
                  "ikm_NA2XSY-120_10kv", "pcc_barras_10kv", "pcc_barras_20kv",
                  "icc_barras_10kv", "fusible_se1_tr1_10kv"]:
        assert c[clave].estado == Estado.COINCIDE, clave


def test_sol_de_olmos_detecta_ampacidad_inflada():
    """Declara 214.27 A; con ficha oficial y factores normalizados son 143.8 A (+49 %)."""
    c = _revisar_sol_de_olmos()["ampacidad_t1"]
    assert c.estado == Estado.DIFIERE
    assert c.diferencia_pct == pytest.approx(49.0, abs=0.5)
    assert "por encima" in c.mensaje


def test_sol_de_olmos_detecta_puesta_a_tierra_y_fusible_20kv():
    c = _revisar_sol_de_olmos()
    assert c["r_pat"].estado == Estado.DIFIERE            # 57.57 vs 59.85 Ω (−3.8 %)
    assert c["fusible_se1_tr1_20kv"].estado == Estado.DIFIERE  # 40 A vs 31.5 A sugerido


def test_kiloamperios_se_comparan_bien_con_amperios():
    """Icc declarada 2.89 kA vs 2887 A calculados: coincide (no es un error de 1000 veces)."""
    c = _revisar_sol_de_olmos()["icc_10kv"]
    assert c.estado == Estado.COINCIDE
    assert c.declarado == pytest.approx(2.89)  # el motor calcula Icc en kA


def test_verificacion_no_presentada_sale_como_no_declarado():
    decl = [d for d in declarados_sol_de_olmos() if d["clave"] != "r_pat"]
    c = _revisar_sol_de_olmos(decl)
    assert c["r_pat"].estado == Estado.NO_DECLARADO


def test_dato_no_presentado_no_genera_observacion():
    """La corriente nominal es un dato, no una verificación: si falta, no se observa."""
    c = _revisar_sol_de_olmos()
    assert "in_20kv" not in c


def test_resultado_en_imagen_es_no_verificable():
    decl = declarados_sol_de_olmos() + [{"clave": "icc_barras_20kv", "no_verificable": True,
                                         "referencia": "Anexo DIgSILENT"}]
    c = _revisar_sol_de_olmos(decl)
    assert c["icc_barras_20kv"].estado == Estado.NO_VERIFICABLE


def test_clave_mal_escrita():
    decl = [{"clave": "icc_30kv", "valor": 3.0, "unidad": "kA"}]
    c = _revisar_sol_de_olmos(decl)
    assert c["icc_30kv"].estado == Estado.CLAVE_DESCONOCIDA


def test_resumen_e_informe():
    comps = list(_revisar_sol_de_olmos().values())
    conteo = resumen(comps)
    assert conteo["difiere"] == 3          # ampacidad, PAT, fusible 20 kV
    assert conteo["coincide"] == 14
    texto = informe_revision(comps)
    assert "Observaciones: 3" in texto
    assert "Ampacidad corregida" in texto
