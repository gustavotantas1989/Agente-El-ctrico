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
    assert len(at.dataframe) == 4  # cargas, tramos, resultados y valores declarados
    assert len(at.dataframe[2].value) == 20          # los 20 resultados del motor
    assert "Resistencia de puesta a tierra" in at.error[0].value  # 59.85 Ω no cumple


def test_pagina_calcula_caracoto():
    at = _calcular("Ejemplo: Caracoto (aérea, monoposte, 10 kV)")
    assert not at.exception
    assert len(at.dataframe) == 4  # cargas, tramos, resultados y valores declarados


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
    assert "3 observación" in at.error[-1].value
    contraste = at.dataframe[-1].value
    assert (contraste["Estado"] == "❌ difiere").sum() == 3
