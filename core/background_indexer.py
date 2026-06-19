"""Monitor de fondo: detecta cambios en knowledge/ y reconstruye el índice.

Corre en un hilo separado constantemente vigilando archivos .md nuevos,
modificados o eliminados. Cuando detecta cambios, reconstruye los pasajes
y actualiza el índice BM25 automáticamente.
"""

import os
import threading
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from core.nlu import BASE_DIR


class BackgroundIndexer:
    """Monitor de archivos y re-indexador."""

    def __init__(self, kb=None, check_interval=30):
        """
        Args:
            kb: instancia de KnowledgeBase
            check_interval: segundos entre verificaciones (default 30)
        """
        self.kb = kb
        self.check_interval = check_interval
        self.knowledge_dir = Path(BASE_DIR) / "knowledge"
        self.file_mtimes = {}  # archivo -> última modificación conocida
        self.running = False
        self.thread = None
        self._initial_scan()

    def _initial_scan(self):
        """Escanea inicial de archivos."""
        for md_file in self.knowledge_dir.rglob("*.md"):
            try:
                self.file_mtimes[str(md_file)] = os.path.getmtime(md_file)
            except OSError:
                pass

    def _check_changes(self):
        """Detecta archivos nuevos, modificados o eliminados."""
        changes = {"new": [], "modified": [], "deleted": []}
        current_files = set()

        # Archivos actuales
        for md_file in self.knowledge_dir.rglob("*.md"):
            try:
                path_str = str(md_file)
                current_files.add(path_str)
                mtime = os.path.getmtime(md_file)

                if path_str not in self.file_mtimes:
                    changes["new"].append(path_str)
                    self.file_mtimes[path_str] = mtime
                elif self.file_mtimes[path_str] != mtime:
                    changes["modified"].append(path_str)
                    self.file_mtimes[path_str] = mtime
            except OSError:
                pass

        # Archivos eliminados
        for path_str in list(self.file_mtimes.keys()):
            if path_str not in current_files:
                changes["deleted"].append(path_str)
                del self.file_mtimes[path_str]

        return changes

    def _rebuild_index(self, changes):
        """Reconstruye el índice si hay cambios."""
        if not self.kb:
            return

        has_changes = any(changes.values())
        if not has_changes:
            return

        # Reconstruye el índice completo (es rápido con caché)
        try:
            self.kb.rebuild()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stats = f"new={len(changes['new'])}, modified={len(changes['modified'])}, deleted={len(changes['deleted'])}"
            print(
                f"[{timestamp}] Índice reconstruido: {stats} | Total pasajes: {self.kb.total_passages()}"
            )
        except Exception as e:
            print(f"Error reconstruyendo índice: {e}")

    def run(self):
        """Corre el monitor de fondo (debe llamarse en un thread)."""
        self.running = True
        print("Background indexer iniciado. Vigilando knowledge/...")

        while self.running:
            try:
                changes = self._check_changes()
                self._rebuild_index(changes)
            except Exception as e:
                print(f"Error en background indexer: {e}")

            time.sleep(self.check_interval)

    def start(self):
        """Inicia el monitor en un thread de fondo."""
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        """Detiene el monitor."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def get_stats(self):
        """Devuelve estadísticas de monitoreo."""
        return {
            "running": self.running,
            "files_watched": len(self.file_mtimes),
            "check_interval": self.check_interval,
        }
