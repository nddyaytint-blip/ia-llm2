"""
Módulo opcional: reformula respuestas usando Ollama local.
Si Ollama no está disponible, devuelve el texto original sin errores.

No requiere dependencias externas — usa únicamente urllib de la stdlib.
"""

import json
import urllib.request
import urllib.error

OLLAMA_BASE  = "http://localhost:11434"
OLLAMA_URL   = f"{OLLAMA_BASE}/api/generate"
MODELO       = "qwen2.5:1.5b"
TIMEOUT      = 30  # segundos máximo de espera

PERFILES = {
    "basico": (
        "Eres un asistente que habla de forma muy sencilla y amigable. "
        "Usa palabras del día a día. Si hay términos difíciles, explícalos "
        "con ejemplos simples de la vida cotidiana. Responde en el mismo "
        "idioma en que está escrito el texto."
    ),
    "intermedio": (
        "Eres un asistente claro y directo. Usa lenguaje accesible. "
        "Puedes mencionar términos técnicos si los explicas brevemente. "
        "Responde en el mismo idioma en que está escrito el texto."
    ),
    "avanzado": (
        "Eres un asistente técnico y preciso. El usuario tiene conocimientos "
        "del área. Sé directo, completo y usa terminología apropiada. "
        "Responde en el mismo idioma en que está escrito el texto."
    ),
}

# Caché en memoria para no consultar Ollama en cada llamada
_disponible_cache: bool | None = None
_modelo_ok_cache:  bool | None = None


def _ollama_disponible() -> bool:
    """Verifica rápido si Ollama está corriendo."""
    global _disponible_cache
    if _disponible_cache is not None:
        return _disponible_cache
    try:
        req = urllib.request.Request(OLLAMA_BASE, method="GET")
        with urllib.request.urlopen(req, timeout=2):
            _disponible_cache = True
            return True
    except Exception:
        _disponible_cache = False
        return False


def _modelo_disponible() -> bool:
    """Verifica que el modelo configurado esté descargado en Ollama."""
    global _modelo_ok_cache
    if _modelo_ok_cache is not None:
        return _modelo_ok_cache
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        nombres = [m.get("name", "") for m in data.get("models", [])]
        # Comparación flexible: "qwen2.5:1.5b" ↔ "qwen2.5:1.5b" o "qwen2.5"
        modelo_base = MODELO.split(":")[0]
        _modelo_ok_cache = any(
            m == MODELO or m.startswith(modelo_base + ":")
            for m in nombres
        )
        return _modelo_ok_cache
    except Exception:
        _modelo_ok_cache = False
        return False


def invalidar_cache():
    """Reinicia la caché de disponibilidad (útil si Ollama se reinicia)."""
    global _disponible_cache, _modelo_ok_cache
    _disponible_cache = None
    _modelo_ok_cache  = None


def reformular(texto: str, nivel: str = "intermedio") -> str:
    """
    Reformula un texto para sonar más natural y adaptado al nivel del usuario.

    Parámetros:
        texto  : el texto generado por el motor de razonamiento
        nivel  : "basico", "intermedio" o "avanzado"

    Retorna el texto reformulado, o el texto original si Ollama no está disponible.
    """
    if not texto or not texto.strip():
        return texto

    if not _ollama_disponible():
        return texto

    if not _modelo_disponible():
        return texto  # modelo no descargado — fallo silencioso

    perfil = PERFILES.get(nivel, PERFILES["intermedio"])
    prompt = (
        f"{perfil}\n\n"
        f"Reformula este texto de forma natural y fluida, "
        f"sin inventar información nueva, solo mejora cómo está dicho:\n\n"
        f"{texto}"
    )

    payload = json.dumps({
        "model":  MODELO,
        "prompt": prompt,
        "stream": False,
    }).encode()

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
        return data.get("response", texto).strip() or texto
    except urllib.error.URLError:
        invalidar_cache()  # Ollama puede haberse detenido
    except TimeoutError:
        pass
    except Exception:
        pass

    return texto  # siempre hay fallback


def estado() -> dict:
    """Devuelve el estado actual del reformulador (útil para diagnóstico)."""
    ollama_ok = _ollama_disponible()
    modelo_ok = _modelo_disponible() if ollama_ok else False
    return {
        "ollama_disponible": ollama_ok,
        "modelo":            MODELO,
        "modelo_descargado": modelo_ok,
        "activo":            ollama_ok and modelo_ok,
        "instruccion":       f"ollama pull {MODELO}" if ollama_ok and not modelo_ok else None,
    }
