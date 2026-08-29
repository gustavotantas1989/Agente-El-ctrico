"""
==========================================================================
🤖 CONSULTOR DE NORMAS ELÉCTRICAS · Interfaz web (Streamlit)
==========================================================================

Envuelve la lógica de 'consultor de normas electricas.py' en una interfaz
de chat web. Reutiliza tus funciones sin modificarlas: importa chunks,
embeddings, buscar() y asistente() del módulo original.

CÓMO CORRER LOCAL:
    streamlit run app.py

CÓMO DESPLEGAR (link público):
    1. Sube este repo a GitHub (incluyendo cache_embeddings.npz)
    2. Ve a share.streamlit.io → New app → elige tu repo
    3. Archivo principal: app.py
    4. En Advanced settings → Secrets, pega:
           GOOGLE_API_KEY = "tu-clave-real"
    5. Deploy → sale tu link público
==========================================================================
"""

import importlib.util
from pathlib import Path

import streamlit as st


# ============================================================
# Importar tu módulo (el nombre tiene espacios, así que lo
# cargamos por ruta en vez de un import normal)
# ============================================================

@st.cache_resource(show_spinner="Cargando la base de conocimiento...")
def cargar_backend():
    """Carga el módulo del consultor + los chunks + embeddings UNA sola vez.
    @st.cache_resource garantiza que esto corre una vez por sesión de la app,
    no en cada mensaje del usuario."""
    ruta = Path(__file__).parent / "consultor de normas electricas.py"
    spec = importlib.util.spec_from_file_location("consultor", ruta)
    consultor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consultor)

    # Carga chunks (de los PDFs) y embeddings (del caché .npz)
    chunks = consultor.cargar_todos_los_documentos()
    embeddings = consultor.obtener_embeddings(chunks)
    return consultor, chunks, embeddings


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="Consultor de Normas Eléctricas",
    page_icon="⚡",
    layout="centered",
)

st.title("⚡ Consultor de Normas Eléctricas")
st.caption("Asistente sobre normativa peruana del sector eléctrico (CNE, LCE, RLCE y otras)")

# Barra lateral
with st.sidebar:
    st.header("Opciones")
    modo_profundo = st.checkbox(
        "🧠 Razonamiento profundo",
        value=False,
        help="Usa chain-of-thought (2 llamadas a Gemini). Más lento pero más detallado.",
    )
    st.divider()
    st.caption(
        "Cada consulta usa la API de Gemini. Si varias personas preguntan "
        "a la vez, puede agotarse la cuota diaria del plan gratuito."
    )

# Cargar backend (cacheado)
try:
    consultor, chunks, embeddings = cargar_backend()
    n_docs = len(set(c["archivo"] for c in chunks))
    st.sidebar.success(f"✓ {len(chunks)} chunks de {n_docs} documento(s)")
except Exception as e:
    st.error(
        f"No se pudo cargar la base de conocimiento.\n\n"
        f"Verifica que 'cache_embeddings.npz' esté en el repo y que "
        f"GOOGLE_API_KEY esté configurada en los Secrets.\n\nDetalle: {e}"
    )
    st.stop()


# ============================================================
# Historial de chat
# ============================================================

if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

# Mostrar historial previo
for msg in st.session_state.mensajes:
    with st.chat_message(msg["rol"]):
        st.markdown(msg["contenido"])
        if msg.get("fuentes"):
            with st.expander("📖 Fuentes consultadas"):
                for f in msg["fuentes"]:
                    st.markdown(f"- {f['archivo']} (página {f['pagina']})")


# ============================================================
# Entrada del usuario
# ============================================================

pregunta = st.chat_input("Escribe tu consulta sobre normativa eléctrica...")

if pregunta:
    # Soporta también el ** al inicio como en la versión de terminal
    modo_cot = modo_profundo or pregunta.startswith("**")
    if pregunta.startswith("**"):
        pregunta = pregunta[2:].strip()

    # Mostrar la pregunta del usuario
    st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    # Generar respuesta
    with st.chat_message("assistant"):
        spinner_txt = (
            "🧠 Razonando en profundidad (2 pasos)..."
            if modo_cot else "🔍 Buscando en las normativas..."
        )
        with st.spinner(spinner_txt):
            try:
                resultado = consultor.asistente(
                    pregunta, chunks, embeddings, modo_cot=modo_cot
                )
                st.markdown(resultado["respuesta"])
                with st.expander("📖 Fuentes consultadas"):
                    for f in resultado["fuentes"]:
                        st.markdown(f"- {f['archivo']} (página {f['pagina']})")

                st.session_state.mensajes.append({
                    "rol": "assistant",
                    "contenido": resultado["respuesta"],
                    "fuentes": resultado["fuentes"],
                })
            except Exception as e:
                st.error(f"Ocurrió un error al procesar la consulta: {e}")
