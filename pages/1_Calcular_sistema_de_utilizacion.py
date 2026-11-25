"""
Página "Calcular sistema de utilización" del Agente Eléctrico.

Streamlit la agrega sola al menú lateral porque está dentro de la carpeta pages/.
No toca app.py (el Consultor sigue igual).

Flujo (como un tablero):
    formulario (entradas)  ->  ProyectoSU (valida)  ->  calcular_proyecto (motor)  ->  tabla + informe
"""

from datetime import date

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from motor_su.calculos import calcular_proyecto, imprimir_informe
from motor_su.conductores import CATALOGO
from motor_su.ejemplos import DECLARADOS, EJEMPLOS, MENCIONES
from motor_su.consistencia import CAMPOS, Mencion, informe_consistencia, revisar_consistencia
from motor_su.factores import INSTALACIONES
from motor_su.revisor import ValorDeclarado, comparar, informe_revision, resumen
from motor_su.modelos import (
    TAMANOS_COMERCIALES_KVA, Aislamiento, BaseCorriente, Concesionaria,
    ProyectoSU, TipoRed, TipoSubestacion, TipoTramite,
)

st.set_page_config(page_title="Calcular sistema de utilización", page_icon="⚡", layout="wide")

st.title("⚡ Calcular y revisar sistema de utilización")
st.caption(
    "Versión preliminar del motor de cálculo (Fase 2). Calcula corrientes, cortocircuito, "
    "ampacidad corregida, caída de tensión, Pcc en barras, fusible sugerido y puesta a tierra. "
    "Cables subterráneos con datos oficiales de ficha (Indeco / CELSA); cables aéreos aún preliminares."
)

# ---------------------------------------------------------------------------
# Cargar un ejemplo o empezar en blanco
# ---------------------------------------------------------------------------
eleccion = st.selectbox("Empezar desde", list(EJEMPLOS.keys()))
datos = EJEMPLOS[eleccion]()
k = eleccion  # prefijo de las claves: al cambiar de ejemplo, el formulario se recarga

pd_ = datos["punto_de_diseno"]
cc = datos["cuadro_de_cargas"]
se = datos["subestaciones"][0]
tr = se["transformadores"][0]
si = datos["sitio"]


def _fecha(texto):
    return date.fromisoformat(texto) if texto else date.today()


# ---------------------------------------------------------------------------
# 1. Datos generales y trámite
# ---------------------------------------------------------------------------
st.header("1. Datos generales")
c1, c2, c3 = st.columns(3)
nombre = c1.text_input("Nombre del proyecto", datos["nombre"], key=f"{k}nombre")
tipos_red = [t.value for t in TipoRed if t != TipoRed.MIXTA_RAMIFICADA]
tipo_red = c2.selectbox("Tipo de red (punto de diseño → SE)", tipos_red,
                        index=tipos_red.index(datos["tipo_red"]), key=f"{k}tipo_red",
                        help="La red ramificada (varias SE) llega en la Fase 8.")
tipos_tram = [t.value for t in TipoTramite]
tipo_tramite = c3.selectbox("Trámite", tipos_tram,
                            index=tipos_tram.index(datos["tramite"]["tipo"]), key=f"{k}tramite")
potencia_anterior = None
if tipo_tramite == "incremento":
    potencia_anterior = c3.number_input("Potencia anterior (kW)", min_value=0.1, value=50.0,
                                        key=f"{k}pant")

# ---------------------------------------------------------------------------
# 2. Punto de diseño (carta de la concesionaria)
# ---------------------------------------------------------------------------
st.header("2. Punto de diseño")
c1, c2, c3 = st.columns(3)
carta = c1.text_input("N° de carta", pd_["carta"], key=f"{k}carta")
fecha_carta = c1.date_input("Fecha de la carta", _fecha(pd_["fecha_carta"]), key=f"{k}fcarta")
potencia_contratada = c1.number_input("Potencia contratada (kW)", min_value=0.1,
                                      value=float(pd_["potencia_contratada_kw"]), key=f"{k}pc")
tensiones = [10.0, 20.0, 22.9]
v_nom = c2.selectbox("Tensión nominal (kV)", tensiones,
                     index=tensiones.index(float(pd_["tension_nominal_kv"])), key=f"{k}vnom")
pcc = c2.number_input("Pcc trifásica (MVA)", min_value=0.0,
                      value=float(pd_["pcc_3f_mva"]), key=f"{k}pcc")
t_apertura = c2.number_input("Tiempo de apertura (s)", min_value=0.001, max_value=1.0,
                             value=float(pd_["t_apertura_s"]), step=0.01, format="%.3f",
                             key=f"{k}tap")
doble = c3.checkbox("Doble tensión (opera al inicio en otra tensión)",
                    value=pd_.get("tension_operacion_inicial_kv") is not None, key=f"{k}doble")
v_op, pcc_op = None, None
if doble:
    v_op = c3.selectbox("Tensión de operación inicial (kV)", tensiones,
                        index=tensiones.index(float(pd_.get("tension_operacion_inicial_kv") or 10)),
                        key=f"{k}vop")
    pcc_op = c3.number_input("Pcc trifásica a la tensión inicial (MVA)", min_value=0.0,
                             value=float(pd_.get("pcc_3f_operacion_inicial_mva") or 50),
                             key=f"{k}pccop")

# ---------------------------------------------------------------------------
# 3. Cuadro de cargas
# ---------------------------------------------------------------------------
st.header("3. Cuadro de cargas")
st.caption("Agrega filas con el botón ➕ al pie de la tabla. Unidad: kW o HP.")
cargas = st.data_editor(
    pd.DataFrame(cc["items"]),
    num_rows="dynamic", width="stretch", key=f"{k}cargas",
    column_config={
        "descripcion": st.column_config.TextColumn("Descripción"),
        "cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1),
        "potencia_unitaria": st.column_config.NumberColumn("Potencia unitaria", min_value=0.0),
        "unidad": st.column_config.SelectboxColumn("Unidad", options=["kW", "HP"]),
        "fd": st.column_config.NumberColumn("Factor de demanda", min_value=0.01, max_value=1.0),
    },
)
c1, c2 = st.columns(2)
fs = c1.number_input("Factor de simultaneidad", min_value=0.01, max_value=1.0,
                     value=float(cc["fs"]), key=f"{k}fs")
cos_phi = c2.number_input("cos φ", min_value=0.7, max_value=1.0, value=float(cc["cos_phi"]),
                          key=f"{k}cos")

# ---------------------------------------------------------------------------
# 4. Red y subestación
# ---------------------------------------------------------------------------
st.header("4. Red y subestación")
st.caption("Tramos en orden, desde el punto de diseño hasta la SE. Conductor: del catálogo interno.")
st.caption("Condiciones de instalación (solo tramos subterráneos): sirven para la ampacidad "
           "corregida. Resistividad térmica en K·m/W (1.5 = 150 °C·cm/W). "
           "Agrupamiento: 1.0 si va una sola terna en la zanja.")
_por_defecto = {"disposicion": "trebol", "profundidad_m": 1.0, "temperatura_terreno_c": 25.0,
                "resistividad_termica_kmw": 1.5, "instalacion": "directo",
                "factor_agrupamiento": 1.0}
_df_tramos = pd.DataFrame(datos["tramos"])
for _col, _val in _por_defecto.items():
    if _col not in _df_tramos:
        _df_tramos[_col] = _val
    _df_tramos[_col] = _df_tramos[_col].fillna(_val)
tramos = st.data_editor(
    _df_tramos,
    num_rows="dynamic", width="stretch", key=f"{k}tramos",
    column_config={
        "nombre": st.column_config.TextColumn("Tramo"),
        "conductor": st.column_config.SelectboxColumn("Conductor", options=list(CATALOGO.keys())),
        "longitud_m": st.column_config.NumberColumn("Longitud (m)", min_value=0.0),
        "disposicion": st.column_config.SelectboxColumn("Disposición", options=["trebol", "plano"]),
        "profundidad_m": st.column_config.NumberColumn("Profundidad (m)", min_value=0.5, max_value=1.5),
        "temperatura_terreno_c": st.column_config.NumberColumn("T terreno (°C)", min_value=10, max_value=50),
        "resistividad_termica_kmw": st.column_config.NumberColumn("ρ térmica (K·m/W)", min_value=0.5, max_value=3.0),
        "instalacion": st.column_config.SelectboxColumn("Instalación", options=INSTALACIONES),
        "factor_agrupamiento": st.column_config.NumberColumn("F. agrupamiento", min_value=0.1, max_value=1.0),
    },
)
c1, c2, c3 = st.columns(3)
se_nombre = c1.text_input("Nombre de la SE", se["nombre"], key=f"{k}senom")
tipos_se = [t.value for t in TipoSubestacion]
se_tipo = c1.selectbox("Tipo de SE", tipos_se, index=tipos_se.index(se["tipo"]), key=f"{k}setipo")
kva = c2.selectbox("Transformador (kVA)", TAMANOS_COMERCIALES_KVA,
                   index=TAMANOS_COMERCIALES_KVA.index(tr["kva"]), key=f"{k}kva")
v_prim = c2.selectbox("Tensión primaria (kV)", tensiones,
                      index=tensiones.index(float(tr["tension_primaria_kv"])), key=f"{k}vprim")
v_sec = c3.number_input("Tensión secundaria (V)", min_value=1.0, max_value=1000.0,
                        value=float(tr["tension_secundaria_v"]), key=f"{k}vsec")
aisl = [a.value for a in Aislamiento]
aislamiento = c3.selectbox("Aislamiento", aisl, index=aisl.index(tr["aislamiento"]), key=f"{k}aisl")

# ---------------------------------------------------------------------------
# 5. Sitio y criterios
# ---------------------------------------------------------------------------
st.header("5. Sitio y criterios")
c1, c2, c3 = st.columns(3)
conces = [c.value for c in Concesionaria]
concesionaria = c1.selectbox("Concesionaria", conces, index=conces.index(si["concesionaria"]),
                             key=f"{k}conc")
altitud = c1.number_input("Altitud (msnm)", min_value=0.0, max_value=5000.0,
                          value=float(si["altitud_msnm"]), key=f"{k}alt")
rho = c2.number_input("Resistividad del terreno (Ω·m)", min_value=0.1,
                      value=float(si["resistividad_ohm_m"]), key=f"{k}rho")
medida = c2.checkbox("La resistividad fue medida (tiene fecha)", value=False, key=f"{k}medida")
fecha_rho = c2.date_input("Fecha de medición", date.today(), key=f"{k}frho") if medida else None
dv_adm = c3.number_input("ΔV admisible (%)", min_value=0.1, max_value=10.0, value=5.0, key=f"{k}dv")
dv_prev = c3.number_input("ΔV previa hasta el punto de diseño (%)", min_value=0.0, max_value=5.0,
                          value=0.0, key=f"{k}dvp")

with st.expander("Criterios avanzados (puesta a tierra, reserva, base de corriente)"):
    c1, c2, c3 = st.columns(3)
    bases = [b.value for b in BaseCorriente]
    base = c1.selectbox("Base de corriente", bases, key=f"{k}base",
                        help="Por defecto, la potencia instalada de los transformadores (decisión Fase 0).")
    reserva = c1.number_input("Factor de reserva", min_value=1.0, max_value=1.5, value=1.0, key=f"{k}res")
    l_var = c2.number_input("Longitud de varilla (m)", min_value=0.1, max_value=10.0, value=2.4, key=f"{k}lvar")
    d_var = c2.number_input("Diámetro de varilla (mm)", min_value=1.0, max_value=50.0, value=15.88, key=f"{k}dvar")
    f_trat = c3.number_input("Factor de tratamiento del terreno", min_value=0.01, max_value=1.0,
                             value=1.0, key=f"{k}ftrat", help="1.0 = sin tratamiento")
    r_max = c3.number_input("R de puesta a tierra máxima (Ω)", min_value=0.1, value=25.0, key=f"{k}rmax")


# ---------------------------------------------------------------------------
# Armar el proyecto con lo que se llenó
# ---------------------------------------------------------------------------
def _filas(df: pd.DataFrame) -> list[dict]:
    """Convierte la tabla editada en una lista de diccionarios, sin filas vacías."""
    df = df.dropna(how="all")
    return [{c: v for c, v in fila.items() if pd.notna(v)} for fila in df.to_dict("records")]


def armar_datos() -> dict:
    items = _filas(cargas)
    for it in items:
        it.setdefault("descripcion", "")
        it["cantidad"] = int(it.get("cantidad", 1))
    return {
        "nombre": nombre or "Proyecto sin nombre",
        "tipo_red": tipo_red,
        "punto_de_diseno": {
            "carta": carta, "fecha_carta": fecha_carta,
            "potencia_contratada_kw": potencia_contratada,
            "tension_nominal_kv": v_nom, "pcc_3f_mva": pcc, "t_apertura_s": t_apertura,
            "tension_operacion_inicial_kv": v_op, "pcc_3f_operacion_inicial_mva": pcc_op,
        },
        "tramite": {"tipo": tipo_tramite, "potencia_anterior_kw": potencia_anterior},
        "cuadro_de_cargas": {"items": items, "fs": fs, "cos_phi": cos_phi},
        "tramos": _filas(tramos),
        "subestaciones": [{
            "nombre": se_nombre, "tipo": se_tipo,
            "transformadores": [{"kva": kva, "tension_primaria_kv": v_prim,
                                 "tension_secundaria_v": v_sec, "aislamiento": aislamiento}],
        }],
        "sitio": {
            "concesionaria": concesionaria, "altitud_msnm": altitud, "resistividad_ohm_m": rho,
            "fecha_medicion_resistividad": fecha_rho,
            "dv_admisible_pct": dv_adm, "dv_previo_punto_diseno_pct": dv_prev,
            "factor_reserva": reserva, "base_corriente": base,
            "varilla_longitud_m": l_var, "varilla_diametro_mm": d_var,
            "factor_tratamiento_pat": f_trat, "r_pat_max_ohm": r_max,
        },
    }


def explicar_errores(err: ValidationError) -> list[str]:
    """Traduce los errores de Pydantic a mensajes cortos."""
    mensajes = []
    for e in err.errors():
        lugar = " → ".join(str(p) for p in e["loc"])
        texto = e["msg"].replace("Value error, ", "")
        mensajes.append(f"**{lugar}**: {texto}" if lugar else texto)
    return mensajes


# ---------------------------------------------------------------------------
# Botón Calcular y resultados
# ---------------------------------------------------------------------------
st.divider()
_clave_calc = f"{k}proyecto_calculado"
if st.button("⚡ Calcular", type="primary", width="stretch"):
    try:
        st.session_state[_clave_calc] = ProyectoSU(**armar_datos())
    except ValidationError as err:
        st.session_state.pop(_clave_calc, None)
        st.error("Hay datos que revisar antes de calcular:")
        for m in explicar_errores(err):
            st.markdown(f"- {m}")
        st.stop()

# Los resultados se guardan en la sesión para que no se borren al usar el Revisor.
proyecto = st.session_state.get(_clave_calc)
if proyecto is not None:
    resultados = calcular_proyecto(proyecto)
    ok = sum(r.cumple is True for r in resultados)
    fallas = [r for r in resultados if r.cumple is False]

    st.header(f"Resultados — {proyecto.nombre}")
    st.caption("Si cambias datos del formulario, vuelve a presionar ⚡ Calcular.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Máxima demanda", f"{proyecto.cuadro_de_cargas.maxima_demanda_kw:.1f} kW")
    m2.metric("Transformación instalada", f"{proyecto.potencia_instalada_kva:g} kVA")
    m3.metric("Verificaciones que cumplen", ok)
    m4.metric("No cumplen", len(fallas))

    if fallas:
        st.error("NO CUMPLE: " + "; ".join(r.nombre for r in fallas))
    else:
        st.success("Todas las verificaciones cumplen.")

    def _estado(r):
        if r.cumple is None:
            return "— dato"
        return "✅ cumple" if r.cumple else "❌ no cumple"

    tabla = pd.DataFrame([{
        "Cálculo": r.nombre,
        "Valor": f"{r.valor:.4g}",
        "Unidad": r.unidad,
        "Límite": "" if r.limite is None else f"{r.limite:.4g}",
        "Resultado": _estado(r),
        "Fórmula": r.formula,
    } for r in resultados])
    st.dataframe(tabla, width="stretch", hide_index=True)

    avisos = proyecto.advertencias()
    if avisos:
        st.subheader("Advertencias")
        for a in avisos:
            st.warning(a)

    st.caption("El fusible es una PROPUESTA (1.5·In → calibre comercial siguiente) "
               "hasta tener la tabla de fusibles por potencia de la concesionaria.")
    st.download_button("📄 Descargar informe de cálculo (.txt)", imprimir_informe(proyecto),
                       file_name=f"informe_{proyecto.nombre.replace(' ', '_')}.txt")

    # -----------------------------------------------------------------------
    # 6. Revisor v1: contraste contra lo que declara el expediente
    # -----------------------------------------------------------------------
    st.divider()
    st.header("6. Revisar el expediente")
    st.subheader("Resultados declarados (R6)")
    st.caption(
        "Escribe en la columna **Valor declarado** lo que presenta el proyectista. "
        "Deja vacío lo que el expediente no presenta. Marca **Imagen** si el resultado "
        "viene como pantallazo (p. ej. DIgSILENT). Tolerancia: ±2 %."
    )
    previos = {d["clave"]: d for d in DECLARADOS.get(eleccion, lambda: [])()}
    filas = []
    for r in resultados:
        d = previos.get(r.clave, {})
        filas.append({
            "clave": r.clave,
            "Cálculo": r.nombre,
            "Recalculado": round(r.valor, 4),
            "Unidad motor": r.unidad,
            "Valor declarado": d.get("valor"),
            "Unidad declarada": d.get("unidad", r.unidad),
            "Referencia": d.get("referencia", ""),
            "Imagen": bool(d.get("no_verificable", False)),
        })
    declarados_df = st.data_editor(
        pd.DataFrame(filas), hide_index=True, width="stretch", key=f"{k}declarados",
        disabled=["clave", "Cálculo", "Recalculado", "Unidad motor"],
        column_config={
            "clave": None,  # oculta: solo sirve para emparejar
            "Valor declarado": st.column_config.NumberColumn("Valor declarado", format="%.4g"),
            "Unidad declarada": st.column_config.SelectboxColumn(
                "Unidad declarada", options=["A", "kA", "V", "kV", "%", "MVA", "kVA", "Ω"]),
            "Referencia": st.column_config.TextColumn("Referencia (cap./pág.)"),
            "Imagen": st.column_config.CheckboxColumn("Imagen"),
        },
    )

    st.subheader("Consistencia entre capítulos (R1–R5)")
    st.caption(
        "Copia cada dato **tal como aparece escrito** en cada capítulo (memoria, cálculos, "
        "especificaciones, metrado, planos). Agrega filas con ➕. El Revisor verifica que "
        "coincidan entre sí y con la carta de punto de diseño."
    )
    _etiqueta = {v: k for k, v in CAMPOS.items()}  # "Máxima demanda (kW)" → "md_kw"
    _menc = [{"Dato": CAMPOS[m["campo"]], "Valor tal como está escrito": m["valor"],
              "Referencia": m.get("referencia", ""), "Tramo": m.get("tramo", 1)}
             for m in MENCIONES.get(eleccion, lambda: [])()]
    menciones_df = st.data_editor(
        pd.DataFrame(_menc, columns=["Dato", "Valor tal como está escrito", "Referencia", "Tramo"]),
        num_rows="dynamic", hide_index=True, width="stretch", key=f"{k}menciones",
        column_config={
            "Dato": st.column_config.SelectboxColumn("Dato", options=list(CAMPOS.values()), required=True),
            "Valor tal como está escrito": st.column_config.TextColumn("Valor tal como está escrito"),
            "Referencia": st.column_config.TextColumn("Referencia (cap./pág.)"),
            "Tramo": st.column_config.NumberColumn("Tramo", min_value=1, step=1, default=1,
                                                   help="Solo para conductor y longitud"),
        },
    )

    if st.button("🔍 Revisar", type="primary", width="stretch"):
        declarados = []
        for fila in declarados_df.to_dict("records"):
            valor = fila["Valor declarado"]
            hay_valor = valor is not None and not pd.isna(valor)
            if hay_valor or fila["Imagen"]:
                declarados.append(ValorDeclarado(
                    clave=fila["clave"],
                    valor=float(valor) if hay_valor else None,
                    unidad=fila["Unidad declarada"] or None,
                    referencia=fila["Referencia"] or "",
                    no_verificable=bool(fila["Imagen"]),
                ))
        comparaciones = comparar(resultados, declarados)
        conteo = resumen(comparaciones)
        observaciones = [c for c in comparaciones if c.es_observacion]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✅ Coinciden", conteo["coincide"])
        c2.metric("❌ Difieren", conteo["difiere"])
        c3.metric("⚪ No declarados", conteo["no declarado"])
        c4.metric("🖼️ No verificables", conteo["no verificable"])

        if observaciones:
            st.error(f"{len(observaciones)} observación(es) para el proyectista")
        else:
            st.success("Todo lo declarado coincide con el recálculo.")

        iconos = {"coincide": "✅", "difiere": "❌", "no declarado": "⚪",
                  "no verificable": "🖼️", "clave desconocida": "❓"}
        orden = sorted(comparaciones, key=lambda c: not c.es_observacion)
        st.dataframe(pd.DataFrame([{
            "Estado": f"{iconos[c.estado.value]} {c.estado.value}",
            "Cálculo": c.nombre,
            "Declarado": "" if c.declarado is None else f"{c.declarado:.4g}",
            "Recalculado": "" if c.calculado is None else f"{c.calculado:.4g}",
            "Unidad": c.unidad,
            "Diferencia": "" if c.diferencia_pct is None else f"{c.diferencia_pct:+.1f} %",
            "Referencia": c.referencia,
            "Observación": c.mensaje,
        } for c in orden]), width="stretch", hide_index=True)

        # --- Consistencia R1–R5 ---
        menciones = []
        for fila in menciones_df.to_dict("records"):
            dato, valor = fila.get("Dato"), fila.get("Valor tal como está escrito")
            if dato and isinstance(valor, str) and valor.strip():
                tramo = fila.get("Tramo")
                menciones.append(Mencion(
                    campo=_etiqueta[dato], valor=valor.strip(),
                    referencia=fila.get("Referencia") or "",
                    tramo=int(tramo) if tramo is not None and not pd.isna(tramo) else 1))
        hallazgos = revisar_consistencia(proyecto, menciones)

        st.subheader("Consistencia entre capítulos")
        if not hallazgos:
            st.info("No se ingresaron datos por capítulo; no se evaluaron R1–R5.")
        else:
            obs_c = [h for h in hallazgos if h.es_observacion]
            if obs_c:
                st.error(f"{len(obs_c)} inconsistencia(s) entre capítulos")
            else:
                st.success("Los datos coinciden en todos los capítulos ingresados.")
            for h in sorted(hallazgos, key=lambda h: h.consistente):
                icono = "✅" if h.consistente else "❌"
                with st.expander(f"{icono} [{h.regla}] {h.titulo}", expanded=not h.consistente):
                    st.markdown(h.mensaje)
                    for d in h.detalle:
                        st.markdown(f"- {d}")

        texto = informe_revision(comparaciones) + "\n\n" + informe_consistencia(hallazgos)
        st.download_button("📄 Descargar revisión completa (.txt)", texto,
                           file_name=f"revision_{proyecto.nombre.replace(' ', '_')}.txt")
