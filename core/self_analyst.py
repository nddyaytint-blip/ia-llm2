"""Analizador autónomo de Green Tail.

Corre en segundo plano de forma continua y realiza tres tareas:

1. DOCUMENTOS: Escanea knowledge/ (general y de usuarios), detecta archivos
   delgados, temas sin cobertura, duplicados; crea carpetas y stubs nuevos.

2. CÓDIGO: Revisa core/*.py con AST, detecta problemas comunes y aplica
   correcciones seguras (con copia de respaldo antes de modificar).

3. INFORME: Escribe data/self_analysis.json con el estado actual y los
   cambios realizados; accesible por el motor para responder preguntas.
"""

import ast
import json
import os
import re
import shutil
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from core.nlu import BASE_DIR, DATA_DIR

ANALYSIS_LOG = Path(DATA_DIR) / "self_analysis.json"
CORE_DIR     = Path(BASE_DIR) / "core"
KNOWLEDGE_DIR = Path(BASE_DIR) / "knowledge"
BACKUP_DIR   = Path(DATA_DIR) / "code_backups"

# Extensiones de texto reconocidas como pasajes
TEXT_EXTS = {".md", ".txt", ".markdown"}

# Dominios base que siempre deben existir (no se borran)
BASE_DOMAINS = {
    "biologia", "quimica", "fisica", "matematicas", "historia",
    "geografia", "geologia", "botanica", "biologia_molecular", "genetica",
    "psicologia", "filosofia", "epistemologia", "ontologia",
    "economia", "sociologia", "programacion", "green_tail",
}

# Ficheros de código que el analista puede intentar reparar
CORE_FILES = [
    "engine.py", "knowledge.py", "reasoning.py", "responder.py",
    "nlu.py", "storage.py", "resources.py", "self_improve.py",
    "code_tools.py", "background_indexer.py", "user_manager.py",
]


# ── Utilidades ────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _load_report() -> dict:
    if ANALYSIS_LOG.exists():
        try:
            return json.loads(ANALYSIS_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"runs": 0, "last_run": None, "knowledge": {}, "code": {}, "actions": []}


def _save_report(report: dict):
    ANALYSIS_LOG.parent.mkdir(parents=True, exist_ok=True)
    ANALYSIS_LOG.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Análisis de conocimiento ──────────────────────────────────────────────

def _scan_knowledge(kb=None) -> dict:
    """Escanea knowledge/ y devuelve métricas + lista de acciones sugeridas."""
    result = {
        "domains_found":    [],
        "thin_files":       [],   # archivos con < 80 palabras
        "empty_files":      [],   # archivos vacíos o casi vacíos
        "user_folders":     [],   # carpetas de usuarios
        "new_domains_created": [],
        "stubs_created":    [],
        "actions_taken":    [],
    }

    if not KNOWLEDGE_DIR.exists():
        return result

    # Escanea dominios existentes
    for folder in sorted(KNOWLEDGE_DIR.iterdir()):
        if not folder.is_dir():
            continue

        domain = folder.name

        if domain == "users":
            # Escanea carpetas de usuario
            for user_folder in folder.iterdir():
                if user_folder.is_dir():
                    result["user_folders"].append(user_folder.name)
            continue

        result["domains_found"].append(domain)

        for md_file in folder.rglob("*"):
            if md_file.suffix.lower() not in TEXT_EXTS:
                continue
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
                wc = _word_count(text)
                rel = str(md_file.relative_to(KNOWLEDGE_DIR))
                if wc == 0:
                    result["empty_files"].append(rel)
                elif wc < 80:
                    result["thin_files"].append({"file": rel, "words": wc})
            except Exception:
                pass

    # Detecta dominios base faltantes y crea stubs
    for base_domain in BASE_DOMAINS:
        domain_dir = KNOWLEDGE_DIR / base_domain
        if not domain_dir.exists():
            domain_dir.mkdir(parents=True, exist_ok=True)
            stub = domain_dir / "00-introduccion.md"
            stub.write_text(
                f"# {base_domain.replace('_', ' ').title()}\n\n"
                f"Carpeta de conocimiento para '{base_domain}'. "
                f"Añade documentos .md aquí para ampliar este dominio.\n",
                encoding="utf-8",
            )
            result["stubs_created"].append(str(stub))
            result["actions_taken"].append(
                f"Creada carpeta base faltante: knowledge/{base_domain}/"
            )

    # Si hay KB, usa clasificación para sugerir nuevos dominios con el contenido huérfano
    # (archivos en knowledge/ raíz, no en subcarpeta)
    orphan_files = [
        f for f in KNOWLEDGE_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in TEXT_EXTS
    ]
    for orphan in orphan_files:
        if kb is None:
            break
        try:
            text = orphan.read_text(encoding="utf-8", errors="replace")
            if _word_count(text) < 30:
                continue
            cls = kb.classify_domain(text[:2000])
            domain = cls.get("domain") or orphan.stem.lower().replace(" ", "_")[:30]
            domain_dir = KNOWLEDGE_DIR / domain
            domain_dir.mkdir(parents=True, exist_ok=True)
            dest = domain_dir / orphan.name
            shutil.move(str(orphan), str(dest))
            result["actions_taken"].append(
                f"Archivo huérfano '{orphan.name}' movido a knowledge/{domain}/"
            )
        except Exception as e:
            result["actions_taken"].append(f"Error procesando '{orphan.name}': {e}")

    return result


# ── Análisis de código ────────────────────────────────────────────────────

def _parse_issues(filepath: Path) -> list:
    """Analiza un archivo Python con AST y devuelve lista de problemas."""
    issues = []
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return [{"line": 0, "type": "read_error", "msg": str(e), "fixable": False}]

    # Verificar que compila
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        return [{"line": e.lineno, "type": "syntax_error", "msg": str(e), "fixable": False}]

    for node in ast.walk(tree):
        # == None / != None en lugar de is None / is not None
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(comp, ast.Constant) and comp.value is None:
                    if isinstance(op, (ast.Eq, ast.NotEq)):
                        op_str = "==" if isinstance(op, ast.Eq) else "!="
                        issues.append({
                            "line": node.lineno,
                            "type": "none_comparison",
                            "msg": f"Usar '{op_str} None' en vez de 'is [not] None'",
                            "fixable": True,
                        })

        # Bare except (except sin especificar excepción)
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({
                "line": node.lineno,
                "type": "bare_except",
                "msg": "Bare 'except:' — especificar excepción (e.g. except Exception)",
                "fixable": True,
            })

        # Argumentos mutables como default ([], {})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({
                        "line": node.lineno,
                        "type": "mutable_default",
                        "msg": f"Argumento mutable como default en '{node.name}'",
                        "fixable": False,
                    })

        # eval() / exec() — peligrosos
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                issues.append({
                    "line": node.lineno,
                    "type": "dangerous_call",
                    "msg": f"Uso de {node.func.id}() — revisar si es necesario",
                    "fixable": False,
                })

    return issues


def _apply_safe_fixes(filepath: Path, issues: list) -> list:
    """Aplica correcciones seguras al archivo. Hace backup antes de modificar."""
    fixable = [i for i in issues if i.get("fixable")]
    if not fixable:
        return []

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return []

    original = source
    changes = []

    # Fix: == None → is None, != None → is not None
    none_cmp_issues = [i for i in fixable if i["type"] == "none_comparison"]
    if none_cmp_issues:
        new_source = re.sub(r"\b==\s*None\b", "is None", source)
        new_source = re.sub(r"\b!=\s*None\b", "is not None", new_source)
        if new_source != source:
            source = new_source
            changes.append("== None → is None / != None → is not None")

    # Fix: bare except: → except Exception:
    bare_except_issues = [i for i in fixable if i["type"] == "bare_except"]
    if bare_except_issues:
        new_source = re.sub(r"\bexcept\s*:", "except Exception:", source)
        if new_source != source:
            source = new_source
            changes.append("bare except: → except Exception:")

    if source == original or not changes:
        return []

    # Hacer backup antes de sobrescribir
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"{filepath.stem}_{timestamp}.py.bak"
    shutil.copy2(str(filepath), str(backup))

    try:
        filepath.write_text(source, encoding="utf-8")
        return changes
    except Exception as e:
        # Restaurar backup si falla la escritura
        shutil.copy2(str(backup), str(filepath))
        return []


def _scan_code() -> dict:
    """Analiza todos los archivos de core/ y aplica correcciones seguras."""
    result = {
        "files_scanned":  [],
        "files_with_issues": [],
        "fixes_applied": [],
        "syntax_errors": [],
    }

    for filename in CORE_FILES:
        filepath = CORE_DIR / filename
        if not filepath.exists():
            continue

        issues = _parse_issues(filepath)
        result["files_scanned"].append(filename)

        syntax_errs = [i for i in issues if i["type"] == "syntax_error"]
        if syntax_errs:
            result["syntax_errors"].append({
                "file": filename,
                "errors": syntax_errs,
            })
            continue

        if not issues:
            continue

        result["files_with_issues"].append({
            "file": filename,
            "issues": issues,
        })

        applied = _apply_safe_fixes(filepath, issues)
        if applied:
            result["fixes_applied"].append({
                "file": filename,
                "fixes": applied,
                "timestamp": _now(),
            })

    return result


# ── Clase principal ───────────────────────────────────────────────────────

class SelfAnalyst:
    """Analizador autónomo de documentos y código en segundo plano."""

    def __init__(self, kb=None, check_interval: int = 300):
        """
        Args:
            kb: instancia de KnowledgeBase (para clasificación automática)
            check_interval: segundos entre ciclos completos (default 5 min)
        """
        self.kb = kb
        self.check_interval = check_interval
        self.running = False
        self.thread: threading.Thread | None = None
        self._report = _load_report()

    # ── API pública ───────────────────────────────────────────────────────

    def start(self):
        """Inicia el analizador en un hilo de fondo."""
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="SelfAnalyst")
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def run_now(self) -> dict:
        """Ejecuta un ciclo de análisis completo de forma síncrona y devuelve el informe."""
        return self._run_cycle()

    def get_report(self) -> dict:
        """Devuelve el último informe generado."""
        return dict(self._report)

    # ── Bucle de fondo ────────────────────────────────────────────────────

    def _run_loop(self):
        self.running = True
        print(f"[SelfAnalyst] Iniciado — ciclos cada {self.check_interval}s")
        while self.running:
            try:
                self._run_cycle()
            except Exception as e:
                print(f"[SelfAnalyst] Error en ciclo: {e}")
            time.sleep(self.check_interval)

    def _run_cycle(self) -> dict:
        ts = _now()
        print(f"[SelfAnalyst] Ciclo iniciado {ts}")

        know = _scan_knowledge(self.kb)
        code = _scan_code()

        report = _load_report()
        report["runs"] = report.get("runs", 0) + 1
        report["last_run"] = ts
        report["knowledge"] = {
            "domains":         know["domains_found"],
            "user_folders":    know["user_folders"],
            "thin_files":      len(know["thin_files"]),
            "empty_files":     len(know["empty_files"]),
            "stubs_created":   know["stubs_created"],
        }
        report["code"] = {
            "files_scanned":     code["files_scanned"],
            "files_with_issues": len(code["files_with_issues"]),
            "syntax_errors":     code["syntax_errors"],
            "fixes_applied":     code["fixes_applied"],
        }

        # Añade acciones al log (máx 200 entradas)
        new_actions = (
            [{"ts": ts, "area": "knowledge", "action": a} for a in know["actions_taken"]]
            + [{"ts": ts, "area": "code", "file": f["file"], "fixes": f["fixes"]}
               for f in code["fixes_applied"]]
        )
        report["actions"] = (report.get("actions", []) + new_actions)[-200:]

        _save_report(report)
        self._report = report

        # Resumen en consola
        k = report["knowledge"]
        c = report["code"]
        print(
            f"[SelfAnalyst] Conocimiento: {len(k['domains'])} dominios, "
            f"{k['thin_files']} archivos delgados | "
            f"Código: {len(c['files_scanned'])} archivos, "
            f"{c['files_with_issues']} con problemas, "
            f"{len(c['fixes_applied'])} reparados"
        )
        return report
