"""
Limpiador de base de conocimiento OCR.

Lee todos los .md en knowledge/, elimina párrafos basura (índices, pies de
figura, listas de autores, artefactos OCR) y reescribe solo el texto con
calidad de prosa real. Hace backup antes de modificar cualquier archivo.

Uso:
    python tools/clean_knowledge.py [--dry-run] [--folder cardiologia]
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
BACKUP_DIR   = BASE_DIR / "data" / "knowledge_backups"

# Carpetas de dominio base (generadas por nosotros, no por OCR) — se omiten
SKIP_FOLDERS = {
    "biologia", "quimica", "fisica", "matematicas", "historia",
    "geografia", "geologia", "botanica", "biologia_molecular", "genetica",
    "psicologia", "filosofia", "epistemologia", "ontologia",
    "economia", "sociologia", "programacion", "green_tail",
}


# ── Expresiones de detección ───────────────────────────────────────────────────

_RE_FIGURE_LABEL = re.compile(
    r"\b(FIGURA|FIGURE|CUADRO|TABLA|FCG|ECG|NEUMO|INSP|ESP|ACG|FEM|REG)\b",
    re.IGNORECASE,
)
_RE_INSTRUMENT = re.compile(
    r"\b(FONOMECANOCARDIOGRAMA|FONOMECANO|APEXCARDIOGRAMA|NEUMOGRAMA|"
    r"FIGURA\s+\d+|CUADRO\s+\d+|REG\.\s+\d+|FEM\.\s+\d+)\b",
    re.IGNORECASE,
)
_RE_ROMAN_START   = re.compile(r"^\s*(?:II|III|IV|VI|VII|VIII|IX|XI|XII)\b")
_RE_NUMBERED_LIST = re.compile(r"^\s*\d+[\.\)]\s")
_RE_EMBEDDED_LIST = re.compile(r"\.\s+\d+[\.\)]")
_RE_HEADING       = re.compile(r"^\s*#{1,6}\s+")
_RE_AUTHOR_LINE = re.compile(
    r"^(DR\.|DRA\.|DR\s|DRA\s|PROF\.|LIC\.|ING\.)\s+[A-Z]", re.IGNORECASE
)


# ── Métricas de calidad ────────────────────────────────────────────────────────

def _prose_quality(text: str) -> float:
    """Puntaje 0-1: ratio de palabras largas penalizado por tokens numéricos."""
    words = text.split()
    if len(words) < 5:
        return 0.0
    numeric   = sum(1 for w in words if re.fullmatch(r"[\d,\.\-/]+", w))
    long_w    = sum(1 for w in words if len(re.sub(r"\W", "", w)) >= 5)
    short_tok = sum(1 for w in words if len(re.sub(r"\W", "", w)) <= 2)

    if numeric / len(words) > 0.20:     # >20% números → índice
        return 0.02
    alpha = sum(c.isalpha() for c in text)
    if alpha / max(len(text), 1) < 0.35:  # demasiados símbolos
        return 0.02
    # Alta densidad de comas → índice de libro (ej: "Edema, células, hiponatremia,...")
    if text.count(",") / max(len(words), 1) > 0.30:
        return 0.03

    figure_density = len(_RE_FIGURE_LABEL.findall(text)) / max(len(words), 1)
    score = long_w / len(words) - short_tok * 0.4 / len(words) - figure_density * 3
    return max(0.0, min(score, 1.0))


def _sentence_quality(sent: str) -> float:
    words = sent.split()
    if not words:
        return 0.0
    real = sum(1 for w in words if len(re.sub(r"\W", "", w)) >= 5)
    return real / len(words)


def _is_bad_sentence(s: str) -> bool:
    words = s.split()
    if len(words) < 4:
        return True
    if _RE_INSTRUMENT.search(s):
        return True
    if _RE_ROMAN_START.match(s):
        return True
    if _RE_NUMBERED_LIST.match(s):
        return True
    if _RE_EMBEDDED_LIST.search(s):
        return True
    if _RE_AUTHOR_LINE.match(s):
        return True
    # Alta densidad de tokens numéricos → tabla estadística
    numeric = sum(1 for w in words if re.search(r"\d", w))
    if numeric / len(words) > 0.30:
        return True
    # Demasiadas palabras con mayúscula → tabla de contenidos / lista
    if len(words) >= 7:
        caps = sum(1 for w in words if w and w[0].isupper())
        if caps / len(words) > 0.45:
            return True
    if _sentence_quality(s) < 0.28:
        return True
    return False


def _fix_column_breaks(text: str) -> str:
    """Une palabras partidas por columnas OCR del PDF.

    Patrones: "flu jo"→"flujo", "inhala ción"→"inhalación", "mio cardio"→"miocardio".
    Ambas partes deben ser cortas (2-7 chars), todo minúsculas alfabéticas, y
    ninguna debe ser una palabra castellana autónoma común.
    """
    STOPWORDS = {
        # artículos y preposiciones españolas (los más frecuentes)
        "el", "la", "lo", "le", "de", "del", "en", "al", "a",
        "se", "es", "ha", "su", "me", "te", "si",
        # pronombres/conjunciones
        "que", "con", "por", "las", "los", "una", "uno",
        "son", "han", "hay", "sin", "sus", "nos", "les",
        "muy", "mas", "fue", "ser", "era", "tan", "vez",
        "dos", "tres", "bien", "como",
        # inglés
        "the", "and", "for", "are", "not", "but",
    }
    # Palabras autónomas frecuentes que NO deben fusionarse con el fragmento adyacente
    # NOTA: "ciencia" no está aquí para permitir "insufi"+"ciencia" → "insuficiencia"
    STANDALONE = {"fase", "tipo", "caso", "alto", "alta", "bajo", "baja",
                  "gran", "grado", "nivel", "tasa", "valor", "forma", "zona",
                  "parte", "cada", "entre", "sobre", "hacia", "desde", "antes",
                  "hasta", "puede", "tiene", "hace", "toda", "todo", "otra",
                  "otro", "mismo", "misma", "dicho", "dicha", "grave", "larga",
                  "largo", "corto", "corta", "imagen", "carga", "efecto",
                  "tiempo", "datos", "signo", "ritmo", "pulso", "dolor",
                  "fiebre", "aguda", "agudo",
                  # Merges OCR frecuentes — no fusionar más
                  "enla", "enlos", "enlas", "enlo", "enun", "enuna",
                  "dela", "delos", "delas", "delo", "deun",
                  "ala", "alos", "alas",
                  "conla", "conlos", "conel", "conun",
                  "esde", "esla", "esel", "esun",
                  "porla", "porlos", "porel", "enel", "porlo"}

    _ALPHA_RE = re.compile(r'[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]')

    def _should_join(a: str, b: str) -> bool:
        # Extraer solo la parte alfabética (ignorar puntuación adjunta)
        a_c = _ALPHA_RE.sub("", a)
        b_c = _ALPHA_RE.sub("", b)
        if not a_c or not b_c:
            return False
        if a_c.lower() in STOPWORDS or b_c.lower() in STOPWORDS:
            return False
        if a_c.lower() in STANDALONE or b_c.lower() in STANDALONE:
            return False
        if not (2 <= len(a_c) <= 7 and 2 <= len(b_c) <= 7):
            return False
        # Si ambos fragmentos son "largos" (>=6 y >=5 chars), probablemente
        # son dos palabras reales, no un quiebre de columna: no unir.
        # Esto evita "ciencia"+"mitral" → "cienciamitral".
        if len(a_c) >= 6 and len(b_c) >= 5:
            return False
        # Ambos deben empezar en minúscula (no inicio de oración)
        if not (a_c[0].islower() and b_c[0].islower()):
            return False
        return True

    words = text.split()
    result = []
    i = 0
    while i < len(words):
        if i + 1 < len(words) and _should_join(words[i], words[i + 1]):
            # Une: conserva prefijo de puntuación de `a` + ambas partes alfa + sufijo de `b`
            a_pre  = re.match(r'^[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]*', words[i]).group()
            a_body = re.sub(r'^[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+', '', words[i])
            b_body = re.sub(r'[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+$', '', words[i + 1])
            b_suf  = re.search(r'[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]*$', words[i + 1]).group()
            result.append(a_pre + a_body + b_body + b_suf)
            i += 2
        else:
            result.append(words[i])
            i += 1
    return " ".join(result)


_RE_FIGURA_INLINE = re.compile(
    r"[a-záéíóúñü]{0,8}(?:FIGURA|CUADRO|TABLA|FIGURE)\s+\d+[^\n.]*",
    re.IGNORECASE,
)


def _clean_block(text: str, min_words: int = 20) -> str:
    """Limpia un bloque de texto: une columnas rotas, elimina oraciones basura."""
    flat = " ".join(text.split())
    # Elimina etiquetas de figura/tabla incrustadas en prosa (ej: "comunicaFIGURA 1 …")
    flat = _RE_FIGURA_INLINE.sub("", flat)
    flat = _fix_column_breaks(flat)
    sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚ])", flat)
    good  = [s.strip() for s in sents if not _is_bad_sentence(s.strip())]
    result = " ".join(good)
    words  = result.split()
    if len(words) < min_words:
        return ""
    return result


# ── Procesador de archivos ─────────────────────────────────────────────────────

def process_file(path: Path, dry_run: bool = False) -> dict:
    """Limpia un .md. Devuelve estadísticas."""
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"path": str(path), "error": str(e)}

    lines_in = original.splitlines()
    blocks   = original.split("\n\n")
    kept     = []
    removed  = 0

    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue

        # Encabezados Markdown siempre se conservan
        if _RE_HEADING.match(stripped):
            kept.append(stripped)
            continue

        # Bloque muy corto (< 5 palabras) sin encabezado → descartar
        if len(stripped.split()) < 5:
            removed += 1
            continue

        # Calidad global del bloque
        if _prose_quality(stripped) < 0.15:
            removed += 1
            continue

        # Limpiar oración por oración
        cleaned = _clean_block(stripped)
        if cleaned:
            kept.append(cleaned)
        else:
            removed += 1

    new_content = "\n\n".join(kept) + "\n"

    # Si nada cambió, no tocar el archivo
    if new_content.strip() == original.strip():
        return {"path": str(path), "changed": False, "removed": 0}

    # Estadísticas
    words_before = len(original.split())
    words_after  = len(new_content.split())
    reduction    = round((1 - words_after / max(words_before, 1)) * 100, 1)

    if not dry_run:
        # Backup
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak  = BACKUP_DIR / f"{path.stem}_{ts}.md.bak"
        shutil.copy2(path, bak)
        path.write_text(new_content, encoding="utf-8")

    return {
        "path":         str(path.relative_to(BASE_DIR)),
        "changed":      True,
        "removed_blocks": removed,
        "words_before": words_before,
        "words_after":  words_after,
        "reduction_pct": reduction,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Limpiador de conocimiento OCR")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo simula, no escribe nada")
    parser.add_argument("--folder", default=None,
                        help="Procesa solo esta subcarpeta (ej: cardiologia)")
    parser.add_argument("--min-quality", type=float, default=0.15,
                        help="Umbral mínimo de calidad de bloque (0-1, default 0.15)")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN — no se escribirá nada]\n")

    files = sorted(KNOWLEDGE_DIR.rglob("*.md"))
    if args.folder:
        files = [f for f in files if args.folder in str(f)]

    # Filtra carpetas base (son limpias, no vienen de OCR)
    def _should_skip(f: Path) -> bool:
        parts = f.relative_to(KNOWLEDGE_DIR).parts
        return parts[0] in SKIP_FOLDERS

    to_process = [f for f in files if not _should_skip(f)]
    skipped    = len(files) - len(to_process)

    print(f"Archivos a procesar: {len(to_process)}  |  omitidos (base): {skipped}")
    if not to_process:
        print("Nada que limpiar.")
        return

    total_changed  = 0
    total_removed  = 0
    words_saved    = 0

    for f in to_process:
        result = process_file(f, dry_run=args.dry_run)
        if result.get("error"):
            print(f"  ERROR {result['path']}: {result['error']}")
        elif result.get("changed"):
            total_changed += 1
            total_removed += result.get("removed_blocks", 0)
            words_saved   += result["words_before"] - result["words_after"]
            print(f"  OK {result['path']}  "
                  f"-{result['reduction_pct']}%  "
                  f"({result['words_before']}->{result['words_after']} palabras)")

    print(f"\nResumen:")
    print(f"  Archivos modificados : {total_changed}")
    print(f"  Bloques eliminados   : {total_removed}")
    print(f"  Palabras eliminadas  : {words_saved:,}")
    if not args.dry_run and total_changed > 0:
        print(f"  Backups en          : {BACKUP_DIR}/")
        print("\nReconstruyendo índice BM25...")
        sys.path.insert(0, str(BASE_DIR))
        from core import knowledge
        kb = knowledge.KnowledgeBase()
        kb.ensure(force=True)
        st = kb.stats()
        print(f"  Nuevo índice: {st['passages']} pasajes en {len(st['domains'])} materias")


if __name__ == "__main__":
    main()
