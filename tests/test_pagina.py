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
    assert len(at.dataframe) == 3  # cargas, tramos y resultados
    assert len(at.dataframe[-1].value) == 19          # los 19 resultados del motor
    assert "Resistencia de puesta a tierra" in at.error[0].value  # 59.85 Ω no cumple


def test_pagina_calcula_caracoto():
    at = _calcular("Ejemplo: Caracoto (aérea, monoposte, 10 kV)")
    assert not at.exception
    assert len(at.dataframe) == 3  # cargas, tramos y resultados


def test_pagina_muestra_errores_de_datos():
    at = AppTest.from_file(PAGINA, default_timeout=30)
    at.run()
    at.selectbox[0].set_value("Ejemplo: Caracoto (aérea, monoposte, 10 kV)").run()
    at.number_input(key="Ejemplo: Caracoto (aérea, monoposte, 10 kV)pcc").set_value(0.27).run()
    at.button[0].click().run()
    assert not at.exception
    assert "revisar" in at.error[0].value
    assert any("Pcc" in m.value for m in at.markdown)
