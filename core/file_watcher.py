"""Monitor de imports/: detecta archivos nuevos y los procesa automáticamente.

Flujo por archivo:
  1. Detectar archivo nuevo en imports/
  2. Extraer texto (PDF/DOCX/XLSX/PPTX/ODT/RTF/CSV/TXT/HTML/MD)
  3. Limpiar con document_cleaner
  4. Clasificar dominio → crear carpeta en knowledge/ si no existe
  5. Copiar original a documents/<categoria>/
  6. Escribir MD con metadatos por fragmento en knowledge/<categoria>/
  7. Reconstruir índice BM25 inmediatamente
"""

import os
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime

from core.nlu import BASE_DIR
from core.document_importer import DocumentImporter
from core.document_classifier import DocumentClassifier

IMPORTS_DIR   = os.path.join(BASE_DIR, "imports")
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
DOCUMENTS_DIR = os.path.join(BASE_DIR, "documents")


class FileWatcher:
    """Monitor de archivos en imports/."""

    def __init__(self, kb=None, check_interval=10):
        self.kb             = kb
        self.check_interval = check_interval
        self.imports_dir    = Path(IMPORTS_DIR)
        self.file_mtimes    = {}
        self.running        = False
        self.thread         = None
        self.importer       = DocumentImporter()
        self.classifier     = DocumentClassifier()
        os.makedirs(IMPORTS_DIR,   exist_ok=True)
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        self._initial_scan()

    # ------------------------------------------------------------------
    # Escaneo inicial
    # ------------------------------------------------------------------

    def _initial_scan(self):
        """Registra los archivos que ya estaban en imports/ al arrancar."""
        for file_path in self.imports_dir.rglob("*"):
            if file_path.is_file():
                try:
                    self.file_mtimes[str(file_path)] = os.path.getmtime(file_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Detección de cambios
    # ------------------------------------------------------------------

    def _check_changes(self) -> dict:
        changes = {"new": [], "modified": []}
        if not self.imports_dir.exists():
            return changes

        for file_path in self.imports_dir.rglob("*"):
            if not file_path.is_file():
                continue
            path_str = str(file_path)
            try:
                mtime = os.path.getmtime(file_path)
                if path_str not in self.file_mtimes:
                    changes["new"].append(path_str)
                    self.file_mtimes[path_str] = mtime
                elif self.file_mtimes[path_str] != mtime:
                    changes["modified"].append(path_str)
                    self.file_mtimes[path_str] = mtime
            except OSError:
                pass

        return changes

    # ------------------------------------------------------------------
    # Procesamiento de un archivo
    # ------------------------------------------------------------------

    def _process_file(self, file_path: str) -> dict:
        """Extrae, clasifica, copia a documents/ y escribe MD en knowledge/."""
        try:
            # 1. Extraer + limpiar + fragmentar
            result = self.importer.import_file(
                file_path,
                document_classifier=self.classifier,
            )

            if not result:
                return {"file": Path(file_path).name, "status": "unsupported_format"}
            if result.get("status") in ("already_imported", "empty_or_unreadable", "error"):
                return result

            filename    = result["filename"]
            chunks      = result.get("chunks", [])
            chunk_pages = result.get("chunk_pages", []) or [None] * len(chunks)
            if not chunks:
                return {"file": filename, "status": "no_chunks"}

            # 2. Determinar categoría. import_file ya clasificó con
            # classify_with_new sobre el texto completo (mejor señal); la
            # reusamos para no clasificar dos veces ni desincronizar.
            category = result.get("category")
            if not category or category == "general":
                category = self.classifier.classify_with_new(
                    " ".join(chunks[:3]), filename=filename)

            # 3. Copiar original a documents/<categoria>/
            doc_dir  = os.path.join(DOCUMENTS_DIR, category)
            os.makedirs(doc_dir, exist_ok=True)
            dest_original = os.path.join(doc_dir, filename)
            if not os.path.exists(dest_original):
                try:
                    shutil.copy2(file_path, dest_original)
                except OSError:
                    pass  # si no se puede copiar, continúa igualmente

            # 4. Escribir MD con metadatos por fragmento en knowledge/<categoria>/
            knowledge_dir = os.path.join(KNOWLEDGE_DIR, category)
            os.makedirs(knowledge_dir, exist_ok=True)

            md_filename = Path(file_path).stem + ".md"
            md_path     = os.path.join(knowledge_dir, md_filename)

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(self._build_markdown(
                    filename    = filename,
                    source_path = file_path,
                    dest_path   = dest_original,
                    category    = category,
                    imported_at = result.get("imported_at", datetime.now().isoformat()),
                    chunks      = chunks,
                    chunk_pages = chunk_pages,
                    cleaning    = result.get("cleaning", {}),
                ))

            result.update({
                "status":           "success",
                "category":         category,
                "destination_md":   md_path,
                "destination_orig": dest_original,
            })

            # 5. Reconstruir índice BM25
            self._rebuild_index()

            return result

        except Exception as e:
            return {"file": Path(file_path).name, "status": "error", "error": str(e)}

    # ------------------------------------------------------------------
    # Formato Markdown con metadatos por fragmento
    # ------------------------------------------------------------------

    def _build_markdown(self, filename, source_path, dest_path,
                         category, imported_at, chunks, cleaning, chunk_pages=None):
        """Genera el MD con cabecera de documento y metadatos inline por chunk.

        El comentario de metadatos va PEGADO al texto del fragmento (sin línea
        en blanco entre medias) para que el indexador (_passages_from_file) los
        lea como un solo bloque y pueda asociar la página al pasaje.
        """
        n_chunks = len(chunks)
        if not chunk_pages or len(chunk_pages) != n_chunks:
            chunk_pages = [None] * n_chunks

        pages_present = [p for p in chunk_pages if p is not None]
        page_range = ""
        if pages_present:
            page_range = f" (páginas {min(pages_present)}–{max(pages_present)})"

        lines = [
            f"# {Path(filename).stem}",
            "",
            "## Metadatos del documento",
            "",
            f"- **Archivo original:** {filename}",
            f"- **Ruta de origen:** {source_path}",
            f"- **Copia en documents/:** {dest_path}",
            f"- **Categoría:** {category}",
            f"- **Importado:** {imported_at}",
            f"- **Fragmentos:** {n_chunks}{page_range}",
        ]

        if cleaning:
            reduction = cleaning.get("reduction_pct", 0)
            removed   = cleaning.get("removed_words", 0)
            if reduction > 0:
                lines.append(
                    f"- **Limpieza:** {reduction}% de ruido eliminado ({removed} palabras)"
                )

        lines += ["", "---", ""]

        for i, chunk in enumerate(chunks, 1):
            page = chunk_pages[i - 1]
            page_tag   = f" | pag:{page}" if page is not None else ""
            page_label = f" — página {page}" if page is not None else ""
            comment = (f"<!-- fuente:{filename} | categoria:{category} | "
                       f"frag:{i}/{n_chunks}{page_tag} -->")
            lines += [
                f"## Fragmento {i} / {n_chunks}{page_label}",
                "",
                # comentario + chunk SIN línea en blanco → un solo bloque
                comment,
                chunk,
                "",
            ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Reconstrucción de índice
    # ------------------------------------------------------------------

    def _rebuild_index(self):
        if self.kb:
            try:
                self.kb.rebuild()
            except Exception as e:
                print(f"[FileWatcher] Error reconstruyendo índice: {e}")

    # ------------------------------------------------------------------
    # Loop de monitoreo
    # ------------------------------------------------------------------

    def run(self):
        self.running = True
        print("[FileWatcher] Iniciado. Vigilando imports/...")

        while self.running:
            try:
                changes = self._check_changes()
                for file_path in changes.get("new", []) + changes.get("modified", []):
                    result    = self._process_file(file_path)
                    ts        = datetime.now().strftime("%H:%M:%S")
                    status    = result.get("status", "?")
                    cat       = result.get("category", "")
                    fname     = result.get("filename") or Path(file_path).name
                    cat_info  = f" → knowledge/{cat}" if cat and status == "success" else ""
                    print(f"[FileWatcher {ts}] {fname}: {status}{cat_info}")
            except Exception as e:
                print(f"[FileWatcher] Error: {e}")

            time.sleep(self.check_interval)

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        return {
            "running":        self.running,
            "files_watched":  len(self.file_mtimes),
            "check_interval": self.check_interval,
            "imports_dir":    str(self.imports_dir),
        }

    def process_directory(self) -> list:
        """Procesa en batch todos los archivos actualmente en imports/."""
        results = []
        for file_path in sorted(self.imports_dir.rglob("*")):
            if file_path.is_file():
                results.append(self._process_file(str(file_path)))
        return results
