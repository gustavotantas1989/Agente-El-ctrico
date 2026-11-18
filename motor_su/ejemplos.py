"""
Proyectos de ejemplo para la página "Calcular sistema de utilización".

Son los mismos casos de prueba del motor (tests/), listos para cargar
en el formulario con un clic y ver cómo funciona el cálculo.
"""


def sol_de_olmos() -> dict:
    """Expediente OV-2168507 (Sol de Olmos, Barranca): red subterránea + caseta, doble tensión."""
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
            "items": [{"descripcion": "Cargas del cuadro (10 ítems)", "cantidad": 1,
                       "potencia_unitaria": 625, "unidad": "kW", "fd": 1.0}],
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


def caracoto() -> dict:
    """Expediente APROBADO I.E.S. 02 de Mayo, Caracoto (Electro Puno): aérea, 10 kV, 3,825 msnm."""
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
                       "potencia_unitaria": 37.30, "unidad": "kW", "fd": 1.0}],
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
        # ρ = 100 Ω·m es PROVISIONAL: la medición del expediente viene como imagen
        "sitio": {"concesionaria": "Otra", "altitud_msnm": 3825, "resistividad_ohm_m": 100},
    }


def en_blanco() -> dict:
    """Formulario con valores típicos para empezar un proyecto nuevo."""
    return {
        "nombre": "",
        "tipo_red": "subterranea",
        "punto_de_diseno": {
            "carta": "",
            "fecha_carta": None,
            "potencia_contratada_kw": 100.0,
            "tension_nominal_kv": 20,
            "pcc_3f_mva": 250,
            "t_apertura_s": 0.02,
        },
        "tramite": {"tipo": "nuevo"},
        "cuadro_de_cargas": {
            "items": [{"descripcion": "", "cantidad": 1, "potencia_unitaria": 100.0,
                       "unidad": "kW", "fd": 1.0}],
            "fs": 1.0,
            "cos_phi": 0.9,
        },
        "tramos": [{"nombre": "PD - SE", "conductor": "NA2XSY-70", "longitud_m": 50.0}],
        "subestaciones": [{
            "nombre": "SE",
            "tipo": "caseta",
            "transformadores": [{"kva": 160, "tension_primaria_kv": 20,
                                 "tension_secundaria_v": 380, "aislamiento": "aceite"}],
        }],
        "sitio": {"concesionaria": "PLUZ", "altitud_msnm": 0, "resistividad_ohm_m": 100},
    }


EJEMPLOS = {
    "Proyecto nuevo (en blanco)": en_blanco,
    "Ejemplo: Sol de Olmos (subterránea, caseta, 20/10 kV)": sol_de_olmos,
    "Ejemplo: Caracoto (aérea, monoposte, 10 kV)": caracoto,
}
