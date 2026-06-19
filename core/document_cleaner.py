"""Limpieza de texto extraído de documentos.

Se aplica después de la extracción (PDF/DOCX/HTML/TXT) y antes del chunking.
No requiere dependencias externas — solo stdlib.

Orden de operaciones:
  1. Decodificación / normalización Unicode
  2. Artefactos de PDF (guiones partidos, ligaduras, números de página)
  3. Entidades HTML residuales
  4. Caracteres de control y basura binaria
  5. Espacios y saltos de línea
  6. Líneas cortas que son ruido (encabezados, pies de página repetidos)
  7. Párrafos duplicados
  8. Puntuación y tipografía
"""

import re
import unicodedata
from collections import Counter


# ---------------------------------------------------------------------------
# 1. Unicode
# ---------------------------------------------------------------------------

def _normalize_unicode(text: str) -> str:
    """NFC para compatibilidad, reemplaza sustitutos y caracteres nulos."""
    text = text.replace("\x00", "")
    text = text.encode("utf-8", "replace").decode("utf-8", "replace")
    return unicodedata.normalize("NFC", text)


# ---------------------------------------------------------------------------
# 2. Artefactos de PDF
# ---------------------------------------------------------------------------

# Ligaduras tipográficas que pdfplumber a veces no descompone
_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "st", "ﬆ": "st",
}

# Patrones de encabezado/pie de página de PDF (se detectan como líneas repetidas)
_PAGE_NUMBER_RE = re.compile(
    r"^\s*"
    r"("
    r"p[aá]g(ina)?\.?\s*\d+"           # "página 3", "pag. 3"
    r"|page\s*\d+"                       # "page 3"
    r"|\d+\s*/\s*\d+"                   # "3 / 47"
    r"|\[\s*\d+\s*\]"                   # "[ 3 ]"
    r"|[-–—]\s*\d+\s*[-–—]"            # "— 3 —"
    r"|\d+"                              # línea que solo tiene un número
    r")"
    r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Guión de partición de palabra al final de línea: "trans-\nporte" → "transporte"
_HYPHEN_BREAK_RE = re.compile(r"-\n(\w)")


def _fix_pdf_artifacts(text: str) -> str:
    for lig, repl in _LIGATURES.items():
        text = text.replace(lig, repl)
    # Guiones de partición
    text = _HYPHEN_BREAK_RE.sub(r"\1", text)
    # Números de página aislados
    text = _PAGE_NUMBER_RE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# 3. Entidades HTML residuales
# ---------------------------------------------------------------------------

_HTML_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&apos;": "'", "&nbsp;": " ",
    "&ndash;": "–", "&mdash;": "—", "&hellip;": "…",
    "&laquo;": "«", "&raquo;": "»",
    "&aacute;": "á", "&eacute;": "é", "&iacute;": "í",
    "&oacute;": "ó", "&uacute;": "ú", "&ntilde;": "ñ",
    "&Aacute;": "Á", "&Eacute;": "É", "&Iacute;": "Í",
    "&Oacute;": "Ó", "&Uacute;": "Ú", "&Ntilde;": "Ñ",
    "&uuml;": "ü", "&Uuml;": "Ü",
}
_HTML_ENTITY_RE = re.compile(r"&#?\w+;")


def _strip_html_entities(text: str) -> str:
    for ent, repl in _HTML_ENTITIES.items():
        text = text.replace(ent, repl)
    # Entidades numéricas y desconocidas restantes
    text = _HTML_ENTITY_RE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# 4. Caracteres de control y basura binaria
# ---------------------------------------------------------------------------

# Mantener: imprimibles + saltos de línea + tabulador
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Caracteres de uso privado Unicode (a menudo basura de PDF)
_PRIVATE_USE_RE = re.compile(r"[-]")


def _strip_control_chars(text: str) -> str:
    text = _CONTROL_RE.sub("", text)
    text = _PRIVATE_USE_RE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# 5. Espacios y saltos de línea
# ---------------------------------------------------------------------------

def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    # Espacios múltiples en una misma línea
    text = re.sub(r" {2,}", " ", text)
    # Líneas con solo espacios → línea vacía
    text = re.sub(r"^ +$", "", text, flags=re.MULTILINE)
    # Más de 2 líneas vacías consecutivas → 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 6. Líneas cortas que son ruido
# ---------------------------------------------------------------------------

# Palabras que solas en una línea son probablemente ruido de encabezado
_NOISE_WORDS = {
    "confidencial", "confidential", "copyright", "reserved", "rights",
    "version", "versión", "draft", "borrador", "chapter", "capítulo",
    "section", "sección", "contents", "índice", "index", "tabla",
    "figura", "figure", "table", "anexo", "annex", "appendix",
}


def _remove_short_noise_lines(text: str, min_words: int = 3) -> str:
    """Elimina líneas que son demasiado cortas para ser contenido real.

    Conserva líneas cortas que son encabezados Markdown (# Título) o
    que forman parte de listas (- item).
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Siempre conservar vacías (separan párrafos)
        if not stripped:
            cleaned.append(line)
            continue
        # Conservar encabezados Markdown
        if stripped.startswith("#"):
            cleaned.append(line)
            continue
        # Conservar ítems de lista
        if re.match(r"^[-*•·]\s", stripped) or re.match(r"^\d+[.)]\s", stripped):
            cleaned.append(line)
            continue
        words = stripped.split()
        # Descartar si es muy corta Y parece ruido
        if len(words) < min_words:
            # Solo descartar si no parece texto normal (ej: terminación de oración)
            if not stripped.endswith((".", ":", "?", "!")):
                if stripped.lower() in _NOISE_WORDS or len(stripped) < 4:
                    continue  # descartar
        cleaned.append(line)
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# 7. Párrafos duplicados
# ---------------------------------------------------------------------------

def _remove_duplicate_paragraphs(text: str, min_words: int = 6) -> str:
    """Elimina párrafos exactamente duplicados (encabezados/pies repetidos en PDF)."""
    paragraphs = re.split(r"\n{2,}", text)
    seen: set = set()
    unique = []
    for para in paragraphs:
        key = re.sub(r"\s+", " ", para.strip().lower())
        words = key.split()
        if len(words) >= min_words:
            if key in seen:
                continue
            seen.add(key)
        unique.append(para)
    return "\n\n".join(unique)


# ---------------------------------------------------------------------------
# 8. Puntuación y tipografía
# ---------------------------------------------------------------------------

# Comillas tipográficas → neutras (más seguras para BM25)
_QUOTE_MAP = str.maketrans({
    "‘": "'", "’": "'",   # ' '
    "“": '"', "”": '"',   # " "
    "«": '"', "»": '"',   # « »
    "‹": "'", "›": "'",   # ‹ ›
})

# Guiones tipográficos → guión estándar donde tiene sentido
_DASHES_RE = re.compile(r"(?<!\s)[–—](?!\s)")  # pegados a texto → guión
_ELLIPSIS_RE = re.compile(r"\.{3,}")            # ... → …


def _normalize_punctuation(text: str) -> str:
    text = text.translate(_QUOTE_MAP)
    text = _DASHES_RE.sub("-", text)
    text = _ELLIPSIS_RE.sub("...", text)
    # Espacios antes de signo de puntuación (artefacto de PDF)
    text = re.sub(r" ([.,;:!?])", r"\1", text)
    # Punto doble
    text = re.sub(r"\.{2}(?!\.)", ".", text)
    return text


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def clean(text: str, *, aggressive: bool = False) -> str:
    """Limpia texto extraído de un documento.

    Args:
        text: texto crudo de extractor (PDF/DOCX/HTML/TXT).
        aggressive: si True, aplica eliminación de líneas cortas más estricta
                    (útil para PDFs con muchos artefactos).

    Returns:
        Texto limpio listo para chunking e indexación.
    """
    if not text:
        return ""

    text = _normalize_unicode(text)
    text = _fix_pdf_artifacts(text)
    text = _strip_html_entities(text)
    text = _strip_control_chars(text)
    text = _normalize_whitespace(text)
    text = _remove_short_noise_lines(text, min_words=2 if not aggressive else 4)
    text = _remove_duplicate_paragraphs(text)
    text = _normalize_punctuation(text)
    # Segunda pasada de espacios (la normalización de puntuación puede generar dobles)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_stats(original: str, cleaned: str) -> dict:
    """Devuelve estadísticas de cuánto se limpió."""
    orig_lines  = original.count("\n") + 1
    clean_lines = cleaned.count("\n") + 1
    orig_words  = len(original.split())
    clean_words = len(cleaned.split())
    return {
        "original_chars":  len(original),
        "cleaned_chars":   len(cleaned),
        "removed_chars":   len(original) - len(cleaned),
        "original_words":  orig_words,
        "cleaned_words":   clean_words,
        "removed_words":   orig_words - clean_words,
        "original_lines":  orig_lines,
        "cleaned_lines":   clean_lines,
        "reduction_pct":   round((1 - len(cleaned) / max(len(original), 1)) * 100, 1),
    }
