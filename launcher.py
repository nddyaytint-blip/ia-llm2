"""Punto de entrada para la distribución .exe de Green Tail (versión LLM).

Inicia el servidor HTTP y abre el navegador. Si Ollama no está corriendo,
muestra un aviso pero sigue funcionando en modo BM25 de respaldo.
"""

import os
import sys
import threading
import time
import webbrowser
import urllib.request

PORT = 8000

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

for folder in ("knowledge", "data", "imports", "documents", "logs"):
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)


def _seed_bundled_resources():
    """Copia los recursos de solo lectura (data/, web/) del bundle de
    PyInstaller (_internal/) junto al exe, si faltan. Sin esto el motor no
    encuentra intents.json, stopwords ni index.html (BASE_DIR = dir del exe,
    pero PyInstaller empaqueta en _internal/)."""
    if not getattr(sys, "frozen", False):
        return
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return
    import shutil
    for resource in ("data", "web"):
        src = os.path.join(bundle, resource)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(BASE_DIR, resource)
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            s, d = os.path.join(src, name), os.path.join(dst, name)
            if os.path.isfile(s) and not os.path.exists(d):
                try:
                    shutil.copy2(s, d)
                except OSError:
                    pass


_seed_bundled_resources()


def _check_ollama() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434", timeout=2):
            return True
    except Exception:
        return False


def _open_browser():
    time.sleep(2)
    webbrowser.open(f"http://localhost:{PORT}")


def main():
    ollama_ok = _check_ollama()

    print("=" * 55)
    print("   Green Tail — Asistente de Conocimiento (LLM)")
    print("=" * 55)
    print(f"  Directorio: {BASE_DIR}")
    print(f"  Puerto    : {PORT}")
    print(f"  Navegador : http://localhost:{PORT}")
    print()
    if ollama_ok:
        print("  [OK] Ollama detectado — modo LLM activo")
    else:
        print("  [!] Ollama no detectado — modo BM25 de respaldo activo")
        print("      Para activar el LLM instala Ollama desde ollama.com")
        print("      y ejecuta: ollama pull qwen2.5:1.5b")
    print()
    print("  Coloca documentos en 'imports/' para indexarlos.")
    print("  Cierra esta ventana para detener el servidor.")
    print("=" * 55)

    threading.Thread(target=_open_browser, daemon=True).start()

    import server as _server_module  # noqa: F401

    from http.server import ThreadingHTTPServer
    from server import Handler

    httpd = ThreadingHTTPServer(("", PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Green Tail] Servidor detenido.")


if __name__ == "__main__":
    main()
