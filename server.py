import json
import os
import sys
import argparse
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from core.engine import Engine
from core import code_tools

APP_NAME = "Green Tail"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

engine = Engine()
# BackgroundIndexer ya está inicializado en Engine.__init__()

# Tracking de sesiones (user -> session token)
SESSIONS = {}


class Handler(BaseHTTPRequestHandler):
    def _get_current_user(self):
        """Extrae el usuario de la sesión actual (Authorization header)."""
        auth = self.headers.get("Authorization", "").strip()
        if auth.startswith("Bearer "):
            token = auth[7:]
            # Busca el usuario por token
            for user, stored_token in SESSIONS.items():
                if stored_token == token:
                    return user
        return None

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send(404, {"error": "archivo no encontrado"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/ui", "/index.html"):
            self._send_file(os.path.join(WEB_DIR, "index.html"), "text/html; charset=utf-8")
        elif path == "/status":
            s = engine.status()
            s["app_name"] = APP_NAME
            self._send(200, s)
        elif path == "/suggestions":
            self._send(200, {"suggestions": engine.suggestions()})
        elif path == "/hardware":
            self._send(200, {"hardware": engine.hardware_needs()})
        elif path == "/knowledge":
            self._send(200, engine.knowledge_stats())
        elif path == "/connections":
            topic = (parse_qs(parsed.query).get("topic") or [""])[0].strip()
            if not topic:
                self._send(400, {"error": "parametro 'topic' requerido"})
            else:
                self._send(200, engine.connections(topic))
        elif path == "/memory":
            self._send(200, {"memory": engine.reasoner.memory_summary()})
        elif path == "/files":
            self._send(200, {"files": engine.kb.list_files()})
        elif path == "/health":
            self._send(200, {"ok": True, "service": APP_NAME})
        elif path == "/analysis":
            self._send(200, engine.analysis_report())
        elif path == "/user/profile":
            username = self._get_current_user()
            if not username:
                self._send(401, {"error": "no autenticado"})
                return
            from core import user_manager as um
            self._send(200, {
                "username":  username,
                "folder":    str(engine.get_user_folder(username)),
                "is_master": um.is_master(username),
            })
        else:
            self._send(404, {"error": "ruta no encontrada"})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, UnicodeDecodeError):
            return None, "JSON invalido"

    def do_POST(self):
        data, err = self._read_json()
        if err:
            self._send(400, {"error": err})
            return

        # ── Endpoints de autenticación ──────────────────────────────────
        if self.path == "/register":
            username = (data.get("username") or "").strip()
            password = (data.get("password") or "").strip()
            if not username or not password:
                self._send(400, {"error": "se requieren 'username' y 'password'"})
                return
            result = engine.register_user(username, password)
            self._send(200, result)

        elif self.path == "/login":
            username = (data.get("username") or "").strip()
            password = (data.get("password") or "").strip()
            if not username or not password:
                self._send(400, {"error": "se requieren 'username' y 'password'"})
                return
            auth_result = engine.login_user(username, password)
            if auth_result.get("success"):
                # Genera un token simple (en producción, usar JWT)
                import uuid
                token = str(uuid.uuid4())
                SESSIONS[username] = token
                auth_result["token"] = token
            self._send(200, auth_result)

        elif self.path == "/logout":
            username = self._get_current_user()
            if not username:
                self._send(401, {"error": "no autenticado"})
                return
            if username in SESSIONS:
                del SESSIONS[username]
            self._send(200, {"success": True, "message": f"Logout exitoso"})

        elif self.path == "/users":
            # Solo el maestro puede ver todos los usuarios
            current = self._get_current_user()
            from core import user_manager as um
            if current and um.is_master(current):
                users = engine.list_users()
            else:
                users = []
            self._send(200, {"users": users})

        elif self.path == "/user/profile":
            username = self._get_current_user()
            if not username:
                self._send(401, {"error": "no autenticado"})
                return
            from core import user_manager as um
            user_folder = engine.get_user_folder(username)
            self._send(200, {
                "username":  username,
                "folder":    str(user_folder) if user_folder else None,
                "is_master": um.is_master(username),
            })

        elif self.path == "/user/delete":
            # Eliminar usuario: el maestro puede borrar cualquiera
            current = self._get_current_user()
            if not current:
                self._send(401, {"error": "no autenticado"})
                return
            target   = (data.get("username") or "").strip()
            password = (data.get("password") or "").strip()
            if not target or not password:
                self._send(400, {"error": "se requieren 'username' y 'password'"})
                return
            result = engine.delete_user(target, password)
            self._send(200, result)

        # ── Endpoints de chat y conocimiento ──────────────────────
        elif self.path in ("/chat", "/ask"):
            text = (data.get("text") or "").strip()
            if not text:
                self._send(400, {"error": "campo 'text' requerido"})
                return
            # Usar el usuario autenticado como session_id para memoria persistente
            current_user = self._get_current_user() or "default"
            engine.reasoner.set_session(current_user)
            self._send(200, engine.handle(text))

        elif self.path == "/classify":
            # Clasifica texto en un dominio existente sin guardarlo
            text = (data.get("text") or "").strip()
            if not text:
                self._send(400, {"error": "campo 'text' requerido"})
                return
            self._send(200, engine.kb.classify_domain(text))

        elif self.path == "/learn":
            # Guarda nuevo conocimiento, auto-clasifica dominio
            text   = (data.get("text")   or "").strip()
            title  = (data.get("title")  or "").strip() or None
            domain = (data.get("domain") or "").strip() or None
            force_new = bool(data.get("force_new_domain", False))
            if not text:
                self._send(400, {"error": "campo 'text' requerido"})
                return
            result = engine.kb.ingest(text, title=title, domain=domain,
                                      force_new_domain=force_new)
            self._send(200, result)

        elif self.path == "/code/analyze":
            code = data.get("code") or ""
            filename = (data.get("filename") or "").strip() or None
            if not code.strip():
                self._send(400, {"error": "campo 'code' requerido"})
                return
            self._send(200, engine.analyze_code(code, filename=filename))

        elif self.path == "/code/generate":
            req = (data.get("request") or data.get("text") or "").strip()
            if not req:
                self._send(400, {"error": "campo 'request' requerido"})
                return
            self._send(200, engine.generate_code(req, lang="es"))

        elif self.path == "/code/save":
            code = data.get("code") or ""
            filename = (data.get("filename") or "").strip()
            directory = (data.get("directory") or "").strip() or None
            if not code.strip() or not filename:
                self._send(400, {"error": "se requieren 'code' y 'filename'"})
                return
            self._send(200, engine.save_code(code, filename, directory=directory))

        elif self.path == "/upload":
            # Subida de archivo (texto/codigo) en base64 o texto plano.
            # Si el usuario está autenticado, guarda en su carpeta.
            content = data.get("content") or ""
            filename = (data.get("filename") or "archivo.txt").strip()
            save_to_knowledge = bool(data.get("save_to_knowledge", False))

            if data.get("base64"):
                import base64
                try:
                    content = base64.b64decode(content).decode("utf-8", "replace")
                except Exception:
                    self._send(400, {"error": "contenido base64 invalido"})
                    return
            if not content.strip():
                self._send(400, {"error": "archivo vacio"})
                return

            # Si parece codigo -> analizar; si no, ofrecer aprenderlo como conocimiento
            if code_tools.looks_like_code(content) or filename.lower().endswith(
                    (".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".rb", ".cs", ".php", ".sql")):
                result = engine.analyze_code(content, filename=filename)
                result["kind"] = "code"
            else:
                result = {"kind": "text", "filename": filename,
                          "chars": len(content),
                          "message": "Documento de texto recibido. Puedo aprenderlo "
                                     "como conocimiento (usa 'Enseñar') o respondo "
                                     "preguntas sobre él si me las haces."}

            # Si se solicita guardar como conocimiento
            if save_to_knowledge:
                title = (data.get("title") or "").strip() or None
                domain = (data.get("domain") or "").strip() or None
                current_user = self._get_current_user()

                # Si hay usuario autenticado, guarda en su carpeta
                if current_user:
                    user_folder = engine.get_user_folder(current_user)
                    if user_folder:
                        # Guarda el archivo en knowledge/users/{username}/
                        # Esto se indexará automáticamente por el background indexer
                        learn_result = engine.kb.ingest(content, title=title, domain=domain)
                        result["learn_result"] = learn_result
                else:
                    # Usuario no autenticado, guarda en general
                    learn_result = engine.kb.ingest(content, title=title, domain=domain)
                    result["learn_result"] = learn_result

            self._send(200, result)


        elif self.path == "/enrich":
            # Enriquece un archivo existente con contenido adicional
            source  = (data.get("source")        or "").strip()
            query   = (data.get("query")         or "").strip()
            content = (data.get("text")          or "").strip()
            section = (data.get("section_title") or "").strip() or None
            if not content:
                self._send(400, {"error": "campo 'text' requerido"})
                return
            if source:
                result = engine.kb.enrich_file(source, content, section)
            elif query:
                result = engine.kb.enrich_by_query(query, content, section)
            else:
                self._send(400, {"error": "se requiere 'source' o 'query'"})
                return
            self._send(200, result)

        elif self.path == "/analysis/run":
            # Fuerza un ciclo de análisis inmediato (requiere autenticación)
            current = self._get_current_user()
            if not current:
                self._send(401, {"error": "no autenticado"})
                return
            result = engine.run_analysis_now()
            self._send(200, result)

        else:
            self._send(404, {"error": "ruta no encontrada"})


def main():
    parser = argparse.ArgumentParser(description=f"Servicio {APP_NAME}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    s = engine.status()
    url = f"http://{args.host}:{args.port}"
    print(f"  {APP_NAME}  —  {url}/")
    print(f"  Perfil: {s['tier']}  |  {s['cpu_cores']} nucleos  |  {s['ram_total_mb']}MB RAM")
    kb = engine.knowledge_stats()
    print(f"  Conocimiento: {kb['passages']} pasajes en {len(kb['domains'])} materias")
    print(f"  POST /ask  |  GET /status /knowledge /connections?topic=... /memory")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nDeteniendo {APP_NAME}...")
        engine.indexer.stop()
        engine.analyst.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
