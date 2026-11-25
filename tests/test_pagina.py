"""Pruebas de la página de Streamlit "Calcular sistema de utilización" (sin abrir el navegador)."""

from streamlit.testing.v1 import AppTest

from motor_su.ejemplos import EJEMPLOS
from motor_su.modelos import ProyectoSU

PAGINA = "../pages/1_Calcular_sistema_de_utilizacion.py"


def test_los_ejemplos_son_proyectos_validos():
    for nombre, fabrica in EJEMPLOS.items():
        if fabrica().get("nombre"):  # el formulario en blanco no tiene fecha de carta
            ProyectoSU(**fabrica())


def _calcular(ejemplo: str) -> AppTest:
    at = AppTest.from_file(PAGINA, default_timeout=30)
    at.run()
    at.selectbox[0].set_value(ejemplo).run()
    at.button[0].click().run()
    return at


def test_pagina_calcula_sol_de_olmos():
    at = _calcular("Ejemplo: Sol de Olmos (subterránea, caseta, 20/10 kV)")
    assert not at.exception
    assert len(at.dataframe) == 5  # cargas, tramos, resultados, declarados y menciones
    assert len(at.dataframe[2].value) == 20          # los 20 resultados del motor
    assert "Resistencia de puesta a tierra" in at.error[0].value  # 59.85 Ω no cumple


def test_pagina_calcula_caracoto():
    at = _calcular("Ejemplo: Caracoto (aérea, monoposte, 10 kV)")
    assert not at.exception
    assert len(at.dataframe) == 5  # cargas, tramos, resultados, declarados y menciones


def test_pagina_muestra_errores_de_datos():
    at = AppTest.from_file(PAGINA, default_timeout=30)
    at.run()
    at.selectbox[0].set_value("Ejemplo: Caracoto (aérea, monoposte, 10 kV)").run()
    at.number_input(key="Ejemplo: Caracoto (aérea, monoposte, 10 kV)pcc").set_value(0.27).run()
    at.button[0].click().run()
    assert not at.exception
    assert "revisar" in at.error[0].value
    assert any("Pcc" in m.value for m in at.markdown)


def test_pagina_revisa_sol_de_olmos():
    """Calcular y luego Revisar: con lo declarado por Sol de Olmos salen 3 observaciones."""
    at = _calcular("Ejemplo: Sol de Olmos (subterránea, caseta, 20/10 kV)")
    revisar = [b for b in at.button if "Revisar" in b.label][0]
    revisar.click().run()
    assert not at.exception
    assert any("3 observación" in e.value for e in at.error)
    contraste = at.dataframe[-1].value
    assert (contraste["Estado"] == "❌ difiere").sum() == 3


def test_pagina_revisa_consistencia_caracoto():
    """Caracoto: la consistencia detecta el conductor (R1) y la MD (R4)."""
    at = _calcular("Ejemplo: Caracoto (aérea, monoposte, 10 kV)")
    [b for b in at.button if "Revisar" in b.label][0].click().run()
    assert not at.exception
    assert any("2 inconsistencia" in e.value for e in at.error)
    titulos = [e.label for e in at.expander]
    assert any("[R1]" in t and "❌" in t for t in titulos)
    assert any("[R4]" in t and "❌" in t for t in titulos)
