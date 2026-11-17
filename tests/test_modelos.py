"""
Pruebas de los modelos con datos reales (Fase 1).

Se ejecutan con:   pytest -v
Cada función test_... es un "ensayo": si el modelo se comporta como esperamos, pasa.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from motor_su.modelos import ProyectoSU


def datos_sol_de_olmos() -> dict:
    """Expediente OV-2168507 (Sol de Olmos, Barranca, 2023): red subterránea + caseta."""
    return {
        "nombre": "Agropecuaria Sol de Olmos",
        "tipo_red": "subterranea",
        "punto_de_diseno": {
            "carta": "SGGC-SCE-41754362-2021",
            "fecha_carta": "2021-01-01",  # fecha exacta por completar
            "potencia_contratada_kw": 500,
            "tension_nominal_kv": 20,
            "tension_operacion_inicial_kv": 10,
            "pcc_3f_mva": 130,
            "pcc_3f_operacion_inicial_mva": 50,
            "t_apertura_s": 0.02,
        },
        "tramite": {"tipo": "nuevo"},
        "cuadro_de_cargas": {
            # El expediente trae 10 ítems; aquí van agregados en uno (625 kW instalados)
            "items": [{"descripcion": "Cargas del cuadro (10 ítems)", "cantidad": 1,
                       "potencia_unitaria": 625, "fd": 1.0}],
            "fs": 0.80,
            "cos_phi": 0.85,
        },
        "tramos": [{"nombre": "PMI - SE", "conductor": "NA2XSY-120", "longitud_m": 143.13}],
        "subestaciones": [{
            "nombre": "SE caseta",
            "tipo": "caseta",
            "transformadores": [{"kva": 630, "tension_primaria_kv": 20,
                                 "tension_secundaria_v": 230, "aislamiento": "aceite"}],
        }],
        "sitio": {"concesionaria": "PLUZ", "altitud_msnm": 50, "resistividad_ohm_m": 148},
    }


# --- Casos que deben pasar --------------------------------------------------

def test_sol_de_olmos_se_carga():
    p = ProyectoSU(**datos_sol_de_olmos())
    assert p.cuadro_de_cargas.potencia_instalada_kw == 625
    assert p.cuadro_de_cargas.maxima_demanda_kw == pytest.approx(500)
    assert p.potencia_instalada_kva == 630


def test_sol_de_olmos_avisa_resistividad_sin_medicion():
    p = ProyectoSU(**datos_sol_de_olmos())
    assert any("R10" in a for a in p.advertencias())


def test_cargas_en_hp_se_convierten():
    d = datos_sol_de_olmos()
    d["cuadro_de_cargas"]["items"] = [
        {"descripcion": "Bomba", "cantidad": 2, "potencia_unitaria": 100, "unidad": "HP"},
    ]
    d["cuadro_de_cargas"]["fs"] = 1.0
    d["punto_de_diseno"]["potencia_contratada_kw"] = 149.2
    p = ProyectoSU(**d)
    assert p.cuadro_de_cargas.potencia_instalada_kw == pytest.approx(149.2)


# --- Casos que deben ser RECHAZADOS (errores reales encontrados) ------------

def test_rechaza_pcc_con_error_de_unidades():
    """Tesis de Huanta: Pcc = 0.2749 MVA (debía ser 274.9 MVA)."""
    d = datos_sol_de_olmos()
    d["punto_de_diseno"]["pcc_3f_mva"] = 0.2749
    with pytest.raises(ValidationError, match="fuera de rango"):
        ProyectoSU(**d)


def test_rechaza_conductor_fuera_de_catalogo():
    d = datos_sol_de_olmos()
    d["tramos"][0]["conductor"] = "NA2XSY-95"
    with pytest.raises(ValidationError, match="no está en el catálogo"):
        ProyectoSU(**d)


def test_rechaza_tramo_aereo_en_red_subterranea():
    d = datos_sol_de_olmos()
    d["tramos"].append({"nombre": "Acometida", "conductor": "AAAC-70", "longitud_m": 20})
    with pytest.raises(ValidationError, match="Red subterránea con tramos aéreos"):
        ProyectoSU(**d)


def test_rechaza_trafo_insuficiente():
    """Agromar: 1,640 kVA instalados para 1,882 kVA requeridos."""
    d = datos_sol_de_olmos()
    d["subestaciones"][0]["transformadores"][0]["kva"] = 500
    with pytest.raises(ValidationError, match="no cubren"):
        ProyectoSU(**d)


def test_rechaza_incremento_sin_potencia_anterior():
    d = datos_sol_de_olmos()
    d["tramite"] = {"tipo": "incremento"}
    with pytest.raises(ValidationError, match="potencia anterior"):
        ProyectoSU(**d)


def test_rechaza_doble_tension_sin_su_pcc():
    d = datos_sol_de_olmos()
    del d["punto_de_diseno"]["pcc_3f_operacion_inicial_mva"]
    with pytest.raises(ValidationError, match="falta su Pcc"):
        ProyectoSU(**d)


# --- Advertencias (no bloquean, pero el Revisor las reporta) ----------------

def test_avisa_md_distinta_a_la_carta():
    """ISM / Redondos: la MD usada no coincide con la de la carta."""
    d = datos_sol_de_olmos()
    d["punto_de_diseno"]["potencia_contratada_kw"] = 600
    p = ProyectoSU(**d)
    assert any("R4" in a for a in p.advertencias())


def test_avisa_trafo_en_aceite_dentro_de_edificio():
    d = datos_sol_de_olmos()
    d["subestaciones"][0]["tipo"] = "interior_edificio"
    p = ProyectoSU(**d)
    assert any("edificio" in a for a in p.advertencias())


def test_sin_aviso_r10_si_hay_medicion_reciente():
    d = datos_sol_de_olmos()
    d["sitio"]["fecha_medicion_resistividad"] = date.today().isoformat()
    p = ProyectoSU(**d)
    assert not any("R10" in a for a in p.advertencias())


# --- Tipo de red y tipo de subestación son ejes independientes --------------

def test_acepta_red_mixta_lineal_hacia_caseta():
    """Caso tipo ISM parcela A23 / Agromar / Bravo: aéreo corto + bajada + subterráneo."""
    d = datos_sol_de_olmos()
    d["tipo_red"] = "mixta_lineal"
    d["tramos"] = [
        {"nombre": "PMI - poste de transición", "conductor": "AAAC-70", "longitud_m": 18},
        {"nombre": "Poste - SE", "conductor": "NA2XSY-120", "longitud_m": 350},
    ]
    p = ProyectoSU(**d)
    assert [t.tipo for t in p.tramos] == ["aereo", "subterraneo"]


def test_acepta_red_subterranea_hacia_biposte():
    """Caso tipo Palomino: cable subterráneo que llega a una SE biposte."""
    d = datos_sol_de_olmos()
    d["subestaciones"][0]["tipo"] = "biposte"
    p = ProyectoSU(**d)
    assert p.subestaciones[0].tipo == "biposte"


def test_rechaza_mixta_lineal_sin_tramo_aereo():
    d = datos_sol_de_olmos()
    d["tipo_red"] = "mixta_lineal"
    with pytest.raises(ValidationError, match="al menos un tramo aéreo y uno subterráneo"):
        ProyectoSU(**d)


def test_rechaza_red_aerea_con_tramo_subterraneo():
    d = datos_sol_de_olmos()
    d["tipo_red"] = "aerea"
    with pytest.raises(ValidationError, match="Red aérea con tramos subterráneos"):
        ProyectoSU(**d)


def test_red_ramificada_queda_para_fase_8():
    d = datos_sol_de_olmos()
    d["tipo_red"] = "mixta_ramificada"
    with pytest.raises(ValidationError, match="Fase 8"):
        ProyectoSU(**d)


def test_rechaza_varias_se_sin_red_ramificada():
    d = datos_sol_de_olmos()
    d["subestaciones"].append(dict(d["subestaciones"][0], nombre="SE 2"))
    with pytest.raises(ValidationError, match="mixta_ramificada"):
        ProyectoSU(**d)
