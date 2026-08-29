"""
==========================================================================
🤖 ASISTENTE IA · NORMATIVAS TÉCNICAS
==========================================================================

Proyecto que procesa PDFs de normativas (CNE, IEEE, IEC, manuales técnicos)
y responde consultas citando documento y página exacta.

Arquitectura RAG con caché de embeddings:

    PDFs en disco
        ↓
    Chunking por párrafos (máx ~500 palabras)
        ↓
    Embeddings EN LOTES con caché en disco (gemini-embedding-001)
        ↓
    Consulta del usuario → embed → top-K chunks por similitud
        ↓
    Prompt enriquecido + Gemini 2.5 Flash → Respuesta citada

MODOS DE CONSULTA:
    - Respuesta directa:        escribe tu pregunta normalmente
    - Razonamiento profundo:    escribe ** al inicio de tu pregunta
                                (usa chain-of-thought con 2 llamadas a Gemini)

CAMBIOS EN ESTA VERSIÓN (lista para Streamlit / nube):
    1. EMBEDDINGS EN LOTES: se agrupan TAM_LOTE textos por request.
    2. BÚSQUEDA VECTORIZADA: similitud coseno con una operación matricial.
    3. CHUNKS EN EL CACHÉ: el .npz ahora guarda también los chunks, para que
       en la nube (sin carpeta documentos/) la app funcione solo con el .npz.
    4. API KEY DUAL: lee de Streamlit Secrets (nube) o de .env (local).

REQUISITOS:
    pip install google-genai numpy python-dotenv pypdf
==========================================================================
"""

import os
import re
import time
import hashlib
from pathlib import Path

import numpy as np
from google import genai
from dotenv import load_dotenv
from pypdf import PdfReader


# ============================================================
# CONFIGURACIÓN
# ============================================================

def obtener_api_key() -> str:
    """Obtiene la API key desde Streamlit Secrets (nube) o .env (local).
    Intenta primero Streamlit; si no está disponible, cae al entorno/.env."""
    # 1) Streamlit Secrets (cuando corre en la nube)
    try:
        import streamlit as st
        if "GOOGLE_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        pass
    # 2) .env local
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
    return os.environ.get("GOOGLE_API_KEY")


api_key = obtener_api_key()
if not api_key:
    raise RuntimeError(
        "❌ No se encontró GOOGLE_API_KEY.\n"
        "   Local: crea un archivo .env con GOOGLE_API_KEY=tu_api_key\n"
        "   Nube:  configúrala en los Secrets de Streamlit."
    )

client = genai.Client(api_key=api_key)

MODELO_GEN = "gemini-2.5-flash"
MODELO_EMB = "gemini-embedding-001"

# Carpetas
SCRIPT_DIR = Path(__file__).parent
DOCS_DIR = SCRIPT_DIR / "documentos"
CACHE_FILE = SCRIPT_DIR / "cache_embeddings.npz"

# Parámetros de chunking
MAX_PALABRAS_POR_CHUNK = 500
TOP_K = 6  # cuántos chunks pasarle a Gemini como contexto

# Parámetros de embeddings en lotes
TAM_LOTE = 20   # cuántos textos mandar por request. Si da error de tamaño,
                 # baja a 50 o 32 (sigue siendo ~40 requests en vez de 2000).
MAX_REINTENTOS = 5


# ============================================================
# FASE 1 · INGESTA DE PDFs
# ============================================================

def leer_pdf(ruta_pdf: Path) -> list[dict]:
    """Lee un PDF y devuelve una lista de chunks con metadatos.
    Cada chunk tiene: texto, archivo, página."""
    chunks = []
    reader = PdfReader(str(ruta_pdf))
    nombre_archivo = ruta_pdf.name

    for num_pagina, pagina in enumerate(reader.pages, start=1):
        texto = pagina.extract_text() or ""
        texto = re.sub(r"\s+", " ", texto).strip()
        if len(texto) < 50:
            continue

        palabras = texto.split()
        for i in range(0, len(palabras), MAX_PALABRAS_POR_CHUNK):
            fragmento = " ".join(palabras[i:i + MAX_PALABRAS_POR_CHUNK])
            chunks.append({
                "texto": fragmento,
                "archivo": nombre_archivo,
                "pagina": num_pagina,
            })

    return chunks


def cargar_todos_los_documentos() -> list[dict]:
    """Lee todos los PDFs de la carpeta documentos/.
    En la nube esta carpeta no existe: devuelve [] y los chunks se toman
    del caché .npz (ver obtener_embeddings)."""
    if not DOCS_DIR.exists():
        # En la nube no hay carpeta documentos/. No es un error:
        # los chunks vendrán del caché junto con los embeddings.
        return []

    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        return []

    print(f"📚 Encontrados {len(pdfs)} PDF(s) en documentos/")
    todos_chunks = []
    pdfs_vacios = []
    for pdf in pdfs:
        print(f"   📄 Leyendo {pdf.name}...")
        chunks = leer_pdf(pdf)
        todos_chunks.extend(chunks)
        print(f"      → {len(chunks)} chunks extraídos")
        if len(chunks) == 0:
            pdfs_vacios.append(pdf.name)

    print(f"✓ Total: {len(todos_chunks)} chunks de texto\n")

    if pdfs_vacios:
        print(f"⚠️  {len(pdfs_vacios)} PDF(s) no aportaron texto (probablemente escaneados):")
        for n in pdfs_vacios:
            print(f"      • {n}")
        print(f"   Estos NO están en el índice. Requieren OCR para incluirlos.\n")

    return todos_chunks


# ============================================================
# FASE 2 · EMBEDDINGS CON CACHÉ (EN LOTES)
# ============================================================

def hash_chunks(chunks: list[dict]) -> str:
    """Genera un hash del contenido para detectar cambios en los PDFs."""
    contenido = "".join(c["texto"] for c in chunks)
    return hashlib.md5(contenido.encode()).hexdigest()


def embed_lote(textos: list[str], max_reintentos: int = MAX_REINTENTOS) -> list[np.ndarray]:
    """Convierte una LISTA de textos en vectores en UNA sola llamada.
    Si encuentra rate limit (429), espera y reintenta automáticamente."""
    for intento in range(max_reintentos):
        try:
            r = client.models.embed_content(model=MODELO_EMB, contents=textos)
            return [np.array(e.values, dtype=np.float32) for e in r.embeddings]
        except Exception as e:
            mensaje_error = str(e)
            print(f"\n   🔍 ERROR COMPLETO: {mensaje_error}\n")   # ← línea de diagnóstico
            if "429" in mensaje_error or "RESOURCE_EXHAUSTED" in mensaje_error:
                espera = 30 * (intento + 1)
                print(f"   ⏳ Esperando {espera}s antes de reintentar...")
                time.sleep(espera)
            else:
                raise
    raise RuntimeError("Excedido el número máximo de reintentos para embed_lote()")


def embed(texto: str) -> np.ndarray:
    """Embebe UN solo texto (para la consulta del usuario en buscar())."""
    return embed_lote([texto])[0]


CACHE_PARCIAL = SCRIPT_DIR / "cache_parcial.npy"


def obtener_embeddings(chunks: list[dict]) -> np.ndarray:
    """Genera embeddings EN LOTES con caché. En la nube, si chunks viene vacío,
    reconstruye chunks Y embeddings desde el .npz (que ahora guarda ambos)."""

    # --- CASO NUBE: no hay PDFs, cargar todo del caché ---
    if not chunks:
        if CACHE_FILE.exists():
            data = np.load(CACHE_FILE, allow_pickle=True)
            if "chunks" in data:
                # Reponer los chunks en la lista que la app usará
                chunks.extend(list(data["chunks"]))
                print(f"💾 Chunks y embeddings cargados desde caché ({CACHE_FILE.name})")
                return data["embeddings"]
            else:
                raise RuntimeError(
                    "El caché no contiene chunks. Regenéralo en local con esta "
                    "versión del script (que guarda chunks dentro del .npz)."
                )
        else:
            raise RuntimeError(
                "No hay carpeta documentos/ ni cache_embeddings.npz. "
                "En la nube debes subir el .npz al repo."
            )

    # --- CASO LOCAL: hay chunks desde los PDFs ---
    hash_actual = hash_chunks(chunks)

    if CACHE_FILE.exists():
        try:
            data = np.load(CACHE_FILE, allow_pickle=True)
            if str(data["hash"]) == hash_actual:
                print(f"💾 Embeddings cargados desde caché ({CACHE_FILE.name})")
                return data["embeddings"]
            else:
                print(f"🔄 Los PDFs cambiaron, regenerando embeddings...")
        except Exception as e:
            print(f"⚠️  Caché corrupto, regenerando: {e}")

    embeddings_previos = []
    if CACHE_PARCIAL.exists():
        try:
            embeddings_previos = list(np.load(CACHE_PARCIAL, allow_pickle=True))
            if len(embeddings_previos) < len(chunks):
                print(f"♻️  Continuando desde el chunk {len(embeddings_previos) + 1}/{len(chunks)}")
            else:
                embeddings_previos = []
        except Exception:
            embeddings_previos = []

    inicio = len(embeddings_previos)
    total = len(chunks)
    print(f"🔢 Generando embeddings de {total - inicio} chunks restantes (lotes de {TAM_LOTE})...")
    print(f"   ⏱  Con lotes esto son ~{(total - inicio + TAM_LOTE - 1) // TAM_LOTE} requests en total.\n")

    embeddings = embeddings_previos

    for i in range(inicio, total, TAM_LOTE):
        bloque = [c["texto"] for c in chunks[i:i + TAM_LOTE]]
        try:
            vectores = embed_lote(bloque)
            embeddings.extend(vectores)
        except Exception as e:
            print(f"\n❌ Error en el lote que empieza en el chunk {i+1}: {e}")
            print(f"   Guardando progreso parcial ({len(embeddings)} embeddings)...")
            np.save(CACHE_PARCIAL, np.array(embeddings))
            print(f"   Vuelve a ejecutar el script para continuar desde aquí.")
            raise

        np.save(CACHE_PARCIAL, np.array(embeddings))
        procesados = min(i + TAM_LOTE, total)
        porcentaje = (procesados / total) * 100
        print(f"   Procesado: {procesados}/{total} ({porcentaje:.1f}%)")

    embeddings_final = np.array(embeddings)

    # Guardar embeddings + hash + CHUNKS (para que la nube no necesite PDFs)
    np.savez(
        CACHE_FILE,
        embeddings=embeddings_final,
        hash=hash_actual,
        chunks=np.array(chunks, dtype=object),
    )

    if CACHE_PARCIAL.exists():
        CACHE_PARCIAL.unlink()

    print(f"\n✓ Embeddings generados y guardados en {CACHE_FILE.name}\n")
    return embeddings_final


# ============================================================
# FASE 3 · BÚSQUEDA SEMÁNTICA (VECTORIZADA)
# ============================================================

def buscar(pregunta: str, embeddings: np.ndarray, k: int = TOP_K) -> list[int]:
    """Devuelve los índices de los k chunks más similares a la pregunta.
    Vectorizado: un único producto matricial en vez de un bucle Python."""
    v = embed(pregunta).astype(np.float32)
    v = v / (np.linalg.norm(v) + 1e-10)

    M = np.asarray(embeddings, dtype=np.float32)
    normas = np.linalg.norm(M, axis=1, keepdims=True) + 1e-10
    M_norm = M / normas

    similitudes = M_norm @ v
    return np.argsort(similitudes)[::-1][:k].tolist()


# ============================================================
# FASE 4 · CONSTRUCCIÓN DEL PROMPT
# ============================================================

def construir_prompt_razonamiento(pregunta: str, chunks: list[dict], indices: list[int]) -> str:
    contexto = ""
    for i, idx in enumerate(indices, start=1):
        c = chunks[idx]
        contexto += f"\n[Fuente {i}: {c['archivo']}, página {c['pagina']}]\n"
        contexto += f"{c['texto']}\n"

    return f"""Eres un abogado-ingeniero eléctrico experto en normativas peruanas del sector eléctrico (LCE, CNE, RLCE y demás normas técnicas).

Se te entrega una pregunta de casuística y fragmentos de normativas relevantes.
Tu tarea es RAZONAR paso a paso antes de responder:

PASO 1 — IDENTIFICAR: ¿Qué artículos o conceptos de los fragmentos se relacionan con la pregunta, aunque sea indirectamente?
PASO 2 — INTERPRETAR: ¿Qué implican esos artículos para el caso planteado? Razona como un experto jurídico-técnico.
PASO 3 — CONCLUIR: ¿A qué conclusión llegas sobre la situación del caso?

PREGUNTA:
{pregunta}

FRAGMENTOS DE LAS NORMATIVAS:
{contexto}

Desarrolla los 3 pasos con detalle. Cita cada fuente (archivo y página) cuando la uses."""


def construir_prompt_respuesta_final(pregunta: str, razonamiento: str) -> str:
    return f"""Eres un asistente experto en normativas eléctricas peruanas.

Basándote en el siguiente razonamiento jurídico-técnico, redacta una respuesta
clara, estructurada y profesional para el usuario.

PREGUNTA ORIGINAL:
{pregunta}

RAZONAMIENTO PREVIO:
{razonamiento}

INSTRUCCIONES:
- Presenta la respuesta directamente, sin mencionar que hubo un razonamiento previo.
- Mantén las citas de fuentes (archivo y página).
- Usa viñetas o numeración si la respuesta tiene varios puntos.
- Tono profesional, como un informe técnico-legal."""


def construir_prompt_directo(pregunta: str, chunks: list[dict], indices: list[int]) -> str:
    contexto = ""
    for i, idx in enumerate(indices, start=1):
        c = chunks[idx]
        contexto += f"\n[Fuente {i}: {c['archivo']}, página {c['pagina']}]\n"
        contexto += f"{c['texto']}\n"

    return f"""Eres un abogado-ingeniero eléctrico experto en normativas peruanas del sector eléctrico (LCE, CNE, RLCE y demás normas técnicas).

PREGUNTA DEL USUARIO:
{pregunta}

FRAGMENTOS RELEVANTES DE LAS NORMATIVAS:
{contexto}

INSTRUCCIONES PARA RESPONDER:
- Analiza los fragmentos como lo haría un experto: razona, interpreta y extrae consecuencias jurídicas aunque la norma no lo diga textualmente.
- Si los fragmentos mencionan obligaciones, derechos o procedimientos relacionados con la pregunta, úsalos para construir una respuesta fundamentada.
- Cita siempre la fuente (archivo y página) entre paréntesis al mencionar cada artículo.
- Si genuinamente no hay información relacionada en los fragmentos, dilo — pero solo si no hay NINGUNA relación posible.
- Usa viñetas o numeración si la respuesta tiene varios puntos.
- Tono profesional, como un informe técnico-legal."""


# ============================================================
# FASE 5 · GENERACIÓN DE RESPUESTA
# ============================================================

def responder(prompt: str) -> str:
    r = client.models.generate_content(model=MODELO_GEN, contents=prompt)
    return r.text


# ============================================================
# FASE 6 · PIPELINE COMPLETO
# ============================================================

def asistente(pregunta: str, chunks: list[dict], embeddings: np.ndarray,
              modo_cot: bool = False) -> dict:
    indices = buscar(pregunta, embeddings, k=TOP_K)

    if modo_cot:
        prompt_razonamiento = construir_prompt_razonamiento(pregunta, chunks, indices)
        razonamiento = responder(prompt_razonamiento)
        prompt_final = construir_prompt_respuesta_final(pregunta, razonamiento)
        respuesta = responder(prompt_final)
    else:
        prompt = construir_prompt_directo(pregunta, chunks, indices)
        respuesta = responder(prompt)

    return {
        "respuesta": respuesta,
        "fuentes": [
            {"archivo": chunks[i]["archivo"], "pagina": chunks[i]["pagina"]}
            for i in indices
        ],
    }


# ============================================================
# FASE 7 · INTERFAZ INTERACTIVA (solo para uso en terminal)
# ============================================================

def modo_interactivo(chunks: list[dict], embeddings: np.ndarray):
    print("=" * 70)
    print("  🤖  ASISTENTE DE NORMATIVAS TÉCNICAS")
    print("=" * 70)
    print(f"\n📚 Base cargada: {len(chunks)} chunks de {len(set(c['archivo'] for c in chunks))} documento(s)")
    print(f"💡 Escribe 'salir' para terminar.")
    print(f"🧠 Prefijo ** activa razonamiento profundo. Ej: ** ¿Qué pasa si...?\n")

    while True:
        try:
            pregunta = input("👤  Tu consulta: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋  Hasta luego.")
            break

        if not pregunta:
            continue
        if pregunta.lower() in ("salir", "exit", "quit", "q"):
            print("👋  Hasta luego.")
            break

        modo_cot = pregunta.startswith("**")
        if modo_cot:
            pregunta = pregunta[2:].strip()
            print(f"\n🧠  Modo razonamiento profundo activado (2 llamadas a Gemini)...")
        else:
            print(f"\n🔍  Buscando en las normativas...")

        resultado = asistente(pregunta, chunks, embeddings, modo_cot=modo_cot)

        print(f"\n🤖  RESPUESTA:")
        print(f"{resultado['respuesta']}\n")

        print(f"📖  Fuentes consultadas:")
        for f in resultado["fuentes"]:
            print(f"    • {f['archivo']} (página {f['pagina']})")
        print("─" * 70 + "\n")


# ============================================================
# PUNTO DE ENTRADA (terminal)
# ============================================================

if __name__ == "__main__":
    chunks = cargar_todos_los_documentos()
    if not chunks:
        exit(0)
    embeddings = obtener_embeddings(chunks)
    modo_interactivo(chunks, embeddings)