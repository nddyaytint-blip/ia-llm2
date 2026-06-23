"""Prueba end-to-end de la cita por número de página.

Genera un PDF multipágina real (sin dependencias), lo procesa con el
DocumentImporter, lo indexa con KnowledgeBase y verifica que un dato que
está en la página 3 se recupere CON su número de página — el caso de uso
comercial: "la evidencia está en la página X".

Ejecutar:  py tests/test_page_numbers.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  OK   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}  {detail}")


# ---------------------------------------------------------------------------
# Generador de PDF mínimo en crudo (stdlib pura)
# ---------------------------------------------------------------------------

def _esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(pages_lines):
    """pages_lines: lista de páginas, cada una lista de líneas de texto."""
    objects = []  # lista de bytes por objeto (1-indexado al ensamblar)

    def content_stream(lines):
        body = "BT /F1 12 Tf 14 TL 72 720 Td\n"
        for ln in lines:
            body += f"({_esc(ln)}) Tj T*\n"
        body += "ET"
        return body.encode("latin-1")

    n_pages = len(pages_lines)
    font_obj_num = 2 + 2 * n_pages + 1   # catalog=1, pages=2, luego pares page/content

    # obj 1: catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # obj 2: pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    # páginas + contenidos
    for i, lines in enumerate(pages_lines):
        page_num   = 3 + 2 * i
        cont_num   = page_num + 1
        page = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {cont_num} 0 R "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> >>")
        objects.append(page.encode())
        stream = content_stream(lines)
        cont = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        objects.append(cont)
    # font
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Ensamblar con xref
    out = b"%PDF-1.4\n"
    offsets = []
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    n_obj = len(objects)
    out += f"xref\n0 {n_obj + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {n_obj + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    return out


# ---------------------------------------------------------------------------
# Construir el PDF de prueba: encabezado corrido + dato único en página 3
# ---------------------------------------------------------------------------

HEADER = "MANUAL CLINICO IMSS CONFIDENCIAL"
MARKER = "El expediente registra una dosis de cuarenta miligramos administrada por error."

pages = []
for n in range(1, 5):
    body = [
        HEADER,                                   # encabezado corrido (en todas)
        f"Pagina {n} contenido general del documento clinico.",
        "Texto de relleno con suficientes palabras para formar un fragmento valido "
        "que el motor pueda indexar correctamente sin descartarlo por ser muy corto.",
    ]
    if n == 3:
        body.append(MARKER)   # el dato clave, solo en la página 3
        body.append("Detalle adicional de la negligencia documentada en este expediente medico.")
    pages.append(body)

pdf_bytes = make_pdf(pages)

# Verificar que pdfplumber puede leerlo (sanity del generador)
import pdfplumber
import io
with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
    check("generador PDF: pdfplumber lee 4 páginas", len(pdf.pages) == 4,
          f"leyó {len(pdf.pages)}")
    p3 = pdf.pages[2].extract_text() or ""
    check("generador PDF: marcador en página 3", "cuarenta miligramos" in p3, repr(p3[:80]))

# ---------------------------------------------------------------------------
# Procesar con DocumentImporter
# ---------------------------------------------------------------------------

from core.document_importer import DocumentImporter, _strip_running_headers, _extract_pdf_pages

with tempfile.TemporaryDirectory() as tmp:
    pdf_path = os.path.join(tmp, "expediente.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Extracción por página
    raw_pages = _extract_pdf_pages(pdf_path)
    check("extracción por página: 4 páginas", len(raw_pages) == 4)

    # Encabezado corrido se elimina
    stripped = _strip_running_headers(raw_pages)
    joined = "\n".join(t for _, t in stripped)
    check("encabezado corrido eliminado", HEADER not in joined, "header sigue presente")
    check("contenido real conservado", "cuarenta miligramos" in joined)

    # import_file completo
    imp = DocumentImporter()
    # forzar registro limpio para no chocar con hash previo
    imp.registry = {}
    result = imp.import_file(pdf_path, target_category="medicina")

    chunks      = result.get("chunks", [])
    chunk_pages = result.get("chunk_pages", [])
    check("import_file: chunks generados", len(chunks) > 0)
    check("import_file: chunk_pages paralelo a chunks", len(chunk_pages) == len(chunks),
          f"{len(chunk_pages)} vs {len(chunks)}")

    # El chunk que contiene el marcador debe estar mapeado a la página 3
    marker_pages = [chunk_pages[i] for i, c in enumerate(chunks)
                    if "cuarenta miligramos" in c]
    check("marcador mapeado a página 3", marker_pages == [3] or 3 in marker_pages,
          f"páginas del marcador: {marker_pages}")

    # -----------------------------------------------------------------
    # Cadena completa: MD → KnowledgeBase → búsqueda expone la página
    # -----------------------------------------------------------------
    import core.knowledge as kb_mod
    from core.file_watcher import FileWatcher

    kdir = os.path.join(tmp, "knowledge")
    os.makedirs(os.path.join(kdir, "medicina"), exist_ok=True)

    fw = FileWatcher(kb=None)
    md = fw._build_markdown(
        filename="expediente.pdf", source_path=pdf_path, dest_path=pdf_path,
        category="medicina", imported_at="2026-06-22", chunks=chunks,
        cleaning=result.get("cleaning", {}), chunk_pages=chunk_pages,
    )
    with open(os.path.join(kdir, "medicina", "expediente.md"), "w", encoding="utf-8") as f:
        f.write(md)

    # Apuntar KnowledgeBase al directorio temporal y construir
    orig_kdir = kb_mod.KNOWLEDGE_DIR
    kb_mod.KNOWLEDGE_DIR = kdir
    try:
        kb = kb_mod.KnowledgeBase(tier="high")
        kb.build()   # build() evita la caché
        hits = kb.search("cuarenta miligramos dosis error")
        check("búsqueda: recupera el pasaje", bool(hits), "sin hits")
        if hits:
            top = hits[0]
            check("búsqueda: el hit expone página 3",
                  top.get("page") == 3, f"page={top.get('page')}")
        # El comentario de metadato NO debe indexarse como pasaje basura
        comment_hit = any("fuente:expediente" in h["text"] for h in hits)
        check("búsqueda: comentario no indexado como basura", not comment_hit)
    finally:
        kb_mod.KNOWLEDGE_DIR = orig_kdir

print(f"\n{'='*52}")
print(f"  PASARON: {_passed}   FALLARON: {_failed}")
print(f"{'='*52}")
sys.exit(1 if _failed else 0)
