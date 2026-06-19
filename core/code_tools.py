"""Capacidades de codigo de Green Tail: leer, entender, analizar, corregir y
generar codigo. Sin dependencias externas.

- Para Python se hace analisis profundo con el modulo `ast` (estructura,
  metricas, complejidad y deteccion de problemas con reglas).
- Para otros lenguajes se hace un analisis heuristico (balance de llaves,
  lineas largas, TODOs, etc.).
- La generacion usa un catalogo de plantillas para funciones comunes; es
  honesta cuando una peticion esta fuera de su repertorio (no es un modelo
  generativo neuronal).
"""
import ast
import os
import re

# Extension -> lenguaje
_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".java": "java", ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".h": "c",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".sql": "sql", ".sh": "bash", ".html": "html",
    ".css": "css", ".json": "json", ".kt": "kotlin", ".swift": "swift",
}


def detect_language(code, filename=None):
    """Detecta el lenguaje por extension o por heuristica del contenido."""
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in _EXT_LANG:
            return _EXT_LANG[ext]
    c = code
    # Marcadores fuertes de Python: aunque no parsee (tendra un error de
    # sintaxis que el analizador reportara), es Python.
    py_markers = (
        re.search(r"^\s*def\s+\w+\s*\(", c, re.M),
        re.search(r"^\s*(from\s+\w|import\s+\w)", c, re.M),
        re.search(r"^\s*class\s+\w+.*:", c, re.M),
        re.search(r"\bprint\s*\(", c) and ":" in c,
        re.search(r"^\s*(elif|def|class)\b", c, re.M),
    )
    # Descarta lenguajes con llaves/punto y coma claramente no-Python
    looks_braced = re.search(r"\b(function|const|let|=>)\b", c) and "{" in c
    if any(py_markers) and not looks_braced:
        return "python"
    if re.search(r"\b(function|const|let|var)\b", c) and (";" in c or "=>" in c):
        return "javascript"
    if re.search(r"#include\s*<", c):
        return "cpp" if re.search(r"\b(std::|cout|cin|class)\b", c) else "c"
    if re.search(r"\bpublic\s+(static\s+)?(class|void|int)\b", c):
        return "java"
    if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE)\b", c, re.I):
        return "sql"
    # Fallback: intenta Python
    try:
        ast.parse(c)
        return "python"
    except SyntaxError:
        return "desconocido"


# ──────────────────────────────────────────────────────────────────────────
#  DETECCION DE INTENCION DE CODIGO EN EL CHAT
# ──────────────────────────────────────────────────────────────────────────

_CODE_NOUNS = ("codigo", "código", "funcion", "función", "programa", "script",
               "clase", "metodo", "método", "algoritmo", "code", "function",
               "program", "class", "method", "algorithm", "snippet")
_GEN_VERBS = ("escribe", "escribeme", "escríbeme", "crea", "creame", "créame",
              "genera", "generame", "genérame", "hazme", "haz", "implementa",
              "programame", "prográmame", "dame", "necesito", "quiero",
              "write", "create", "generate", "make", "implement", "build", "give me")
_ANALYZE_TRIGGERS = ("analiza", "analizame", "revisa", "revisame", "corrige",
                     "corrigeme", "corrígeme", "depura", "que esta mal",
                     "qué está mal", "que tiene de malo", "encuentra el error",
                     "encuentra errores", "mejora este", "optimiza este",
                     "review", "debug", "fix this", "check this", "what's wrong")


def looks_like_code(text):
    """Heuristica: ¿el texto es (contiene) codigo fuente?"""
    patterns = [
        r"\bdef\s+\w+\s*\(", r"^\s*import\s+\w", r"^\s*from\s+\w+\s+import",
        r"\bclass\s+\w+", r"\bfunction\b", r"=>", r"console\.log",
        r"\bprint\s*\(", r"[{};]\s*$", r"^\s*(if|for|while)\b.*[:{]",
        r"\breturn\b", r"#include", r"\bpublic\s+(static|class|void)",
    ]
    hits = sum(1 for p in patterns if re.search(p, text, re.M))
    multiline = "\n" in text.strip()
    return hits >= 2 and (multiline or len(text) > 60)


def extract_code(text):
    """Extrae el codigo de un mensaje: bloque entre ``` ```, todo el texto si ya
    es codigo, o lo que sigue a un prefijo en lenguaje natural + dos puntos."""
    fence = re.search(r"```[a-zA-Z0-9_+-]*\s*\n?(.*?)```", text, re.S)
    if fence:
        return fence.group(1).strip()
    stripped = text.strip()
    # Si el mensaje completo (o desde su primera linea) ya es codigo, devolverlo
    # tal cual: no hay prefijo en lenguaje natural que recortar.
    first_line = stripped.splitlines()[0] if stripped else ""
    if looks_like_code(stripped) and (
            re.match(r"^\s*(def |class |import |from |#|@|\w+\s*=)", first_line)
            or re.search(r"\b(function|const|let|var|public|#include)\b", first_line)):
        return stripped
    # Prefijo en lenguaje natural seguido de ':' y luego el codigo en otra linea.
    m = re.search(r"^[^\n:]{0,80}:\s*\n(.+)$", text, re.S)
    if m and looks_like_code(m.group(1)):
        return m.group(1).strip()
    return stripped


def classify_code_request(text):
    """Decide si el mensaje es una peticion de codigo.

    Devuelve (accion, payload):
      - ('generate', descripcion)  -> escribir codigo nuevo
      - ('analyze',  codigo)       -> leer/analizar/corregir codigo
      - (None, None)               -> no es sobre codigo
    """
    low = " " + text.lower() + " "
    has_code_noun = any(n in low for n in _CODE_NOUNS)
    has_gen_verb = any(f" {v} " in low for v in _GEN_VERBS)
    has_analyze = any(t in low for t in _ANALYZE_TRIGGERS)
    fenced = bool(re.search(r"```", text))
    code_present = looks_like_code(text) or fenced

    # Analizar: hay codigo presente y/o se pide revision explicita
    if has_analyze and (code_present or has_code_noun):
        return "analyze", extract_code(text)
    if code_present and not has_gen_verb:
        # El usuario pego codigo sin pedir explicitamente otra cosa -> analizar
        return "analyze", extract_code(text)

    # Generar: verbo de creacion + sustantivo de codigo, y NO hay codigo pegado
    if has_gen_verb and has_code_noun and not code_present:
        return "generate", text

    return None, None


# ──────────────────────────────────────────────────────────────────────────
#  ANALISIS DE PYTHON (ast)
# ──────────────────────────────────────────────────────────────────────────

def _node_lines(node):
    if hasattr(node, "end_lineno") and node.end_lineno:
        return node.end_lineno - node.lineno + 1
    return 1


def _complexity(node):
    """Complejidad ciclomatica aproximada: ramas de decision + 1."""
    score = 1
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                          ast.With, ast.Assert)):
            score += 1
        elif isinstance(n, ast.BoolOp):
            score += len(n.values) - 1
        elif isinstance(n, ast.comprehension):
            score += 1 + len(n.ifs)
    return score


def analyze_python(code):
    issues = []        # problemas/errores (con linea, severidad, mensaje, sugerencia)
    suggestions = []   # recomendaciones de estilo/diseño
    metrics = {}

    # 1. Sintaxis
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {
            "language": "python",
            "ok": False,
            "syntax_error": {
                "line": e.lineno, "offset": e.offset, "message": e.msg,
                "text": (e.text or "").strip(),
            },
            "issues": [{
                "line": e.lineno or 0, "severity": "error",
                "message": f"Error de sintaxis: {e.msg}",
                "suggestion": "Revisa la línea indicada: paréntesis, dos puntos, indentación o comillas sin cerrar.",
            }],
            "suggestions": [],
            "metrics": {},
            "summary": f"El código tiene un error de sintaxis en la línea {e.lineno}: {e.msg}.",
        }

    funcs, classes, imports_nodes = [], [], []
    imported_names = {}      # nombre -> linea
    used_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            funcs.append(node)
        elif isinstance(node, ast.ClassDef):
            classes.append(node)
        elif isinstance(node, ast.Import):
            imports_nodes.append(node)
            for a in node.names:
                imported_names[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            imports_nodes.append(node)
            for a in node.names:
                if a.name != "*":
                    imported_names[a.asname or a.name] = node.lineno
        elif isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass

    # 2. Reglas de deteccion de problemas
    for node in ast.walk(tree):
        # except desnudo
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({
                "line": node.lineno, "severity": "warning",
                "message": "Cláusula 'except:' sin tipo de excepción.",
                "suggestion": "Captura excepciones específicas (p.ej. 'except ValueError:') para no ocultar errores inesperados como KeyboardInterrupt.",
            })
        # except: pass (silencioso)
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                issues.append({
                    "line": node.lineno, "severity": "warning",
                    "message": "Excepción capturada y silenciada con 'pass'.",
                    "suggestion": "Registra el error (logging) o coméntalo; silenciar excepciones oculta fallos reales.",
                })
        # argumentos mutables por defecto
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({
                        "line": node.lineno, "severity": "error",
                        "message": f"Argumento mutable por defecto en la función '{node.name}'.",
                        "suggestion": "Usa None como valor por defecto y crea la lista/dict dentro de la función. El valor por defecto se comparte entre llamadas (bug clásico de Python).",
                    })
        # comparacion con None usando == / !=
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    issues.append({
                        "line": node.lineno, "severity": "info",
                        "message": "Comparación con None usando == o !=.",
                        "suggestion": "Usa 'is None' / 'is not None' (comparación de identidad, más correcta y rápida).",
                    })
        # eval / exec
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            issues.append({
                "line": node.lineno, "severity": "warning",
                "message": f"Uso de '{node.func.id}()'.",
                "suggestion": "eval/exec ejecutan código arbitrario y son un riesgo de seguridad. Busca una alternativa (ast.literal_eval, dict de funciones, etc.).",
            })
        # lambda asignada a variable
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda):
            issues.append({
                "line": node.lineno, "severity": "info",
                "message": "Lambda asignada a una variable.",
                "suggestion": "Define una función con 'def' en vez de asignar una lambda; es más legible y depurable (PEP 8).",
            })

    # 3. Funciones: docstring, tamaño, nº de argumentos, complejidad
    for fn in funcs:
        if not ast.get_docstring(fn):
            suggestions.append({
                "line": fn.lineno,
                "message": f"La función '{fn.name}' no tiene docstring.",
                "suggestion": "Añade una cadena de documentación que explique qué hace, sus parámetros y qué devuelve.",
            })
        n_args = len(fn.args.args) + len(fn.args.kwonlyargs)
        if n_args > 5:
            suggestions.append({
                "line": fn.lineno,
                "message": f"La función '{fn.name}' tiene {n_args} parámetros.",
                "suggestion": "Considera agrupar parámetros relacionados en un objeto/dataclass; más de 5 argumentos dificulta el uso.",
            })
        length = _node_lines(fn)
        if length > 50:
            suggestions.append({
                "line": fn.lineno,
                "message": f"La función '{fn.name}' tiene ~{length} líneas.",
                "suggestion": "Divídela en funciones más pequeñas con una sola responsabilidad cada una.",
            })
        cx = _complexity(fn)
        if cx > 10:
            suggestions.append({
                "line": fn.lineno,
                "message": f"La función '{fn.name}' tiene complejidad ciclomática {cx} (alta).",
                "suggestion": "Demasiadas ramas de decisión. Simplifica con early-returns, diccionarios de despacho o subfunciones.",
            })

    # 4. Clases sin docstring
    for cl in classes:
        if not ast.get_docstring(cl):
            suggestions.append({
                "line": cl.lineno,
                "message": f"La clase '{cl.name}' no tiene docstring.",
                "suggestion": "Documenta el propósito de la clase y su responsabilidad.",
            })

    # 5. Imports sin usar (heuristico)
    for name, line in imported_names.items():
        if name not in used_names and name != "*":
            suggestions.append({
                "line": line,
                "message": f"El import '{name}' no parece usarse.",
                "suggestion": "Elimina los imports no utilizados para mantener el código limpio.",
            })

    # 6. Metricas
    lines = code.splitlines()
    metrics = {
        "lineas_totales": len(lines),
        "lineas_codigo": sum(1 for l in lines if l.strip() and not l.strip().startswith("#")),
        "lineas_comentario": sum(1 for l in lines if l.strip().startswith("#")),
        "lineas_vacias": sum(1 for l in lines if not l.strip()),
        "funciones": len(funcs),
        "clases": len(classes),
        "imports": len(imports_nodes),
        "complejidad_max": max((_complexity(f) for f in funcs), default=1),
    }

    # 7. Lineas largas (estilo PEP 8: 79/99)
    for i, line in enumerate(lines, 1):
        if len(line) > 99:
            suggestions.append({
                "line": i,
                "message": f"Línea {i} muy larga ({len(line)} caracteres).",
                "suggestion": "Divide la línea; el límite recomendado por PEP 8 es 79-99 caracteres.",
            })
            break  # solo reporta la primera para no saturar

    n_err = sum(1 for x in issues if x["severity"] == "error")
    n_warn = sum(1 for x in issues if x["severity"] == "warning")
    summary = _python_summary(metrics, n_err, n_warn, len(suggestions))

    return {
        "language": "python", "ok": True,
        "issues": issues, "suggestions": suggestions, "metrics": metrics,
        "structure": {
            "funciones": [f.name for f in funcs],
            "clases": [c.name for c in classes],
            "imports": sorted(imported_names.keys()),
        },
        "summary": summary,
    }


def _python_summary(m, n_err, n_warn, n_sug):
    parts = [
        f"Código Python con {m['lineas_codigo']} líneas de código, "
        f"{m['funciones']} función(es) y {m['clases']} clase(s)."
    ]
    if n_err:
        parts.append(f"Detecté {n_err} problema(s) importante(s) que conviene corregir.")
    if n_warn:
        parts.append(f"{n_warn} advertencia(s).")
    if n_sug:
        parts.append(f"{n_sug} sugerencia(s) de mejora de estilo/diseño.")
    if not (n_err or n_warn or n_sug):
        parts.append("No detecté problemas; el código se ve limpio.")
    if m["complejidad_max"] > 10:
        parts.append(f"La complejidad máxima ({m['complejidad_max']}) es alta.")
    return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────────
#  ANALISIS GENERICO (otros lenguajes)
# ──────────────────────────────────────────────────────────────────────────

def analyze_generic(code, language):
    issues = []
    suggestions = []
    lines = code.splitlines()

    # Balance de llaves/paréntesis/corchetes
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    balanced = True
    for ch in code:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                balanced = False
                break
            stack.pop()
    if stack or not balanced:
        issues.append({
            "line": 0, "severity": "error",
            "message": "Paréntesis, corchetes o llaves desbalanceados.",
            "suggestion": "Revisa que cada '(', '[' y '{' tenga su cierre correspondiente.",
        })

    # TODO/FIXME
    for i, line in enumerate(lines, 1):
        if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line):
            suggestions.append({
                "line": i, "message": f"Marca pendiente en la línea {i}: {line.strip()[:60]}",
                "suggestion": "Hay trabajo pendiente marcado; resuélvelo o crea un issue.",
            })
        if len(line) > 120:
            suggestions.append({
                "line": i, "message": f"Línea {i} muy larga ({len(line)} caracteres).",
                "suggestion": "Considera dividir la línea para mejorar la legibilidad.",
            })

    # Mezcla de tabs y espacios para indentar
    has_tab = any(l.startswith("\t") for l in lines)
    has_space = any(l.startswith("  ") for l in lines)
    if has_tab and has_space:
        suggestions.append({
            "line": 0, "message": "Mezcla de tabulaciones y espacios para indentar.",
            "suggestion": "Usa un solo estilo de indentación de forma consistente.",
        })

    metrics = {
        "lineas_totales": len(lines),
        "lineas_no_vacias": sum(1 for l in lines if l.strip()),
        "lineas_vacias": sum(1 for l in lines if not l.strip()),
    }
    summary = (
        f"Código en {language} con {metrics['lineas_no_vacias']} líneas no vacías. "
        + ("Detecté un desbalance de paréntesis/llaves. "
           if any(i['severity']=='error' for i in issues) else "Estructura de bloques balanceada. ")
        + (f"{len(suggestions)} observación(es)." if suggestions else "Sin observaciones notables.")
        + " (Análisis heurístico: para revisión profunda envíame código Python.)"
    )
    return {
        "language": language, "ok": not any(i["severity"] == "error" for i in issues),
        "issues": issues, "suggestions": suggestions, "metrics": metrics,
        "structure": {}, "summary": summary,
    }


def analyze(code, filename=None, language=None):
    """Punto de entrada: detecta lenguaje y delega al analizador adecuado."""
    if not code or not code.strip():
        return {"ok": False, "language": "?", "issues": [],
                "suggestions": [], "metrics": {}, "summary": "No recibí código que analizar."}
    lang = language or detect_language(code, filename)
    if lang == "python":
        return analyze_python(code)
    return analyze_generic(code, lang)


# ──────────────────────────────────────────────────────────────────────────
#  GENERACION DE CODIGO (catalogo de plantillas)
# ──────────────────────────────────────────────────────────────────────────

# Cada entrada: keywords que disparan la plantilla -> (titulo, codigo, explicacion)
_SNIPPETS = [
    (("factorial",),
     "Factorial",
     "def factorial(n):\n"
     "    \"\"\"Devuelve el factorial de n (n!). Usa iteración para evitar\n"
     "    límites de recursión con valores grandes.\"\"\"\n"
     "    if n < 0:\n"
     "        raise ValueError(\"n debe ser >= 0\")\n"
     "    resultado = 1\n"
     "    for i in range(2, n + 1):\n"
     "        resultado *= i\n"
     "    return resultado",
     "Calcula n! de forma iterativa, validando que n no sea negativo."),

    (("fibonacci",),
     "Fibonacci",
     "def fibonacci(n):\n"
     "    \"\"\"Devuelve una lista con los primeros n números de Fibonacci.\"\"\"\n"
     "    secuencia = []\n"
     "    a, b = 0, 1\n"
     "    for _ in range(n):\n"
     "        secuencia.append(a)\n"
     "        a, b = b, a + b\n"
     "    return secuencia",
     "Genera la sucesión de Fibonacci iterativamente en O(n)."),

    (("primo", "prime", "es primo"),
     "Comprobar número primo",
     "def es_primo(n):\n"
     "    \"\"\"Devuelve True si n es primo.\"\"\"\n"
     "    if n < 2:\n"
     "        return False\n"
     "    if n % 2 == 0:\n"
     "        return n == 2\n"
     "    i = 3\n"
     "    while i * i <= n:\n"
     "        if n % i == 0:\n"
     "            return False\n"
     "        i += 2\n"
     "    return True",
     "Comprueba primalidad probando divisores impares hasta la raíz cuadrada: O(√n)."),

    (("palindromo", "palindrome", "capicua"),
     "Detectar palíndromo",
     "def es_palindromo(texto):\n"
     "    \"\"\"True si 'texto' se lee igual al derecho y al revés,\n"
     "    ignorando mayúsculas y espacios.\"\"\"\n"
     "    limpio = ''.join(c.lower() for c in texto if c.isalnum())\n"
     "    return limpio == limpio[::-1]",
     "Normaliza el texto (sin espacios ni mayúsculas) y lo compara con su inverso."),

    (("invertir", "reverse", "reversa", "revertir"),
     "Invertir cadena",
     "def invertir(texto):\n"
     "    \"\"\"Devuelve la cadena al revés.\"\"\"\n"
     "    return texto[::-1]",
     "Usa slicing [::-1], la forma idiomática en Python."),

    (("ordenar", "sort", "burbuja", "bubble"),
     "Ordenamiento (burbuja didáctico + recomendación)",
     "def ordenar_burbuja(lista):\n"
     "    \"\"\"Ordena una copia de la lista con el método de burbuja (didáctico).\"\"\"\n"
     "    datos = list(lista)\n"
     "    n = len(datos)\n"
     "    for i in range(n):\n"
     "        for j in range(0, n - i - 1):\n"
     "            if datos[j] > datos[j + 1]:\n"
     "                datos[j], datos[j + 1] = datos[j + 1], datos[j]\n"
     "    return datos\n\n"
     "# En la práctica usa sorted(lista): es O(n log n) y está optimizado en C.",
     "Burbuja es O(n²), solo didáctico. Para producción usa sorted()/list.sort()."),

    (("busqueda binaria", "binary search", "binaria"),
     "Búsqueda binaria",
     "def busqueda_binaria(lista_ordenada, objetivo):\n"
     "    \"\"\"Devuelve el índice de 'objetivo' en una lista YA ordenada, o -1.\"\"\"\n"
     "    izq, der = 0, len(lista_ordenada) - 1\n"
     "    while izq <= der:\n"
     "        medio = (izq + der) // 2\n"
     "        if lista_ordenada[medio] == objetivo:\n"
     "            return medio\n"
     "        if lista_ordenada[medio] < objetivo:\n"
     "            izq = medio + 1\n"
     "        else:\n"
     "            der = medio - 1\n"
     "    return -1",
     "Busca en O(log n) dividiendo el rango a la mitad; requiere lista ordenada."),

    (("leer archivo", "read file", "abrir archivo", "leer fichero"),
     "Leer un archivo de texto",
     "def leer_archivo(ruta):\n"
     "    \"\"\"Lee un archivo de texto y devuelve su contenido.\"\"\"\n"
     "    with open(ruta, encoding='utf-8') as f:\n"
     "        return f.read()",
     "Usa 'with' para cerrar el archivo automáticamente y encoding utf-8."),

    (("escribir archivo", "write file", "guardar archivo", "guardar texto"),
     "Escribir un archivo de texto",
     "def escribir_archivo(ruta, contenido):\n"
     "    \"\"\"Escribe 'contenido' en un archivo de texto (lo sobrescribe).\"\"\"\n"
     "    with open(ruta, 'w', encoding='utf-8') as f:\n"
     "        f.write(contenido)",
     "Abre en modo 'w' (sobrescribe) con 'with' y utf-8."),

    (("leer json", "read json", "cargar json", "parse json"),
     "Leer un archivo JSON",
     "import json\n\n"
     "def leer_json(ruta):\n"
     "    \"\"\"Carga un archivo JSON y devuelve el objeto Python.\"\"\"\n"
     "    with open(ruta, encoding='utf-8') as f:\n"
     "        return json.load(f)",
     "json.load convierte el JSON en dicts/listas de Python."),

    (("leer csv", "read csv", "csv"),
     "Leer un archivo CSV",
     "import csv\n\n"
     "def leer_csv(ruta):\n"
     "    \"\"\"Lee un CSV y devuelve una lista de diccionarios (una por fila).\"\"\"\n"
     "    with open(ruta, newline='', encoding='utf-8') as f:\n"
     "        return list(csv.DictReader(f))",
     "csv.DictReader usa la primera fila como nombres de columna."),

    (("contar palabras", "word count", "frecuencia"),
     "Contar frecuencia de palabras",
     "from collections import Counter\n\n"
     "def contar_palabras(texto):\n"
     "    \"\"\"Devuelve un Counter con la frecuencia de cada palabra.\"\"\"\n"
     "    palabras = texto.lower().split()\n"
     "    return Counter(palabras)",
     "Counter cuenta apariciones; .most_common(n) da las más frecuentes."),

    (("clase", "class", "objeto", "constructor"),
     "Esqueleto de clase",
     "class MiClase:\n"
     "    \"\"\"Describe aquí la responsabilidad de la clase.\"\"\"\n\n"
     "    def __init__(self, nombre):\n"
     "        self.nombre = nombre\n\n"
     "    def __repr__(self):\n"
     "        return f\"MiClase(nombre={self.nombre!r})\"\n\n"
     "    def saludar(self):\n"
     "        return f\"Hola, soy {self.nombre}\"",
     "Plantilla con __init__, __repr__ y un método de ejemplo."),

    (("fizzbuzz", "fizz buzz"),
     "FizzBuzz",
     "def fizzbuzz(n):\n"
     "    \"\"\"Imprime 1..n: 'Fizz' si múltiplo de 3, 'Buzz' de 5, 'FizzBuzz' de ambos.\"\"\"\n"
     "    for i in range(1, n + 1):\n"
     "        if i % 15 == 0:\n"
     "            print('FizzBuzz')\n"
     "        elif i % 3 == 0:\n"
     "            print('Fizz')\n"
     "        elif i % 5 == 0:\n"
     "            print('Buzz')\n"
     "        else:\n"
     "            print(i)",
     "El clásico ejercicio; comprueba el múltiplo de 15 primero."),

    (("peticion http", "http request", "descargar url", "api", "request"),
     "Petición HTTP (solo stdlib)",
     "import urllib.request\n"
     "import json\n\n"
     "def get_json(url):\n"
     "    \"\"\"Hace una petición GET y devuelve el JSON de respuesta.\"\"\"\n"
     "    with urllib.request.urlopen(url, timeout=10) as r:\n"
     "        return json.loads(r.read().decode('utf-8'))",
     "Usa urllib (biblioteca estándar), sin necesidad de instalar requests."),
]


def generate(request, lang="es"):
    """Genera codigo a partir de una peticion en lenguaje natural, usando un
    catalogo de plantillas. Devuelve dict con codigo, titulo, explicacion y
    una marca de si fue una coincidencia o un fallback honesto."""
    req = request.lower()
    # Puntua cada snippet por nº de keywords presentes
    best = None
    best_score = 0
    for keywords, title, code, explanation in _SNIPPETS:
        score = sum(1 for k in keywords if k in req)
        # bonus si el keyword aparece como palabra completa
        if score > best_score:
            best_score = score
            best = (title, code, explanation)

    if best and best_score > 0:
        title, code, explanation = best
        return {
            "found": True,
            "title": title,
            "code": code,
            "language": "python",
            "explanation": explanation,
        }

    # Fallback honesto: lista lo que SÍ puede generar
    catalogo = ", ".join(sorted({s[1] for s in _SNIPPETS}))
    msg_es = (
        "No tengo una plantilla exacta para esa petición. No soy un modelo "
        "generativo: genero código a partir de un catálogo de patrones comunes. "
        "Puedo escribir, por ejemplo: " + catalogo + ". "
        "Si me describes tu problema en términos de uno de estos, lo genero. "
        "También puedo analizar y corregir cualquier código que me envíes."
    )
    msg_en = (
        "I don't have an exact template for that request. I'm not a generative "
        "model: I produce code from a catalog of common patterns. "
        "I can write, for example: " + catalogo + ". "
        "I can also analyze and fix any code you send me."
    )
    return {
        "found": False,
        "title": "Sin plantilla",
        "code": "",
        "language": "python",
        "explanation": msg_es if lang == "es" else msg_en,
    }


# ──────────────────────────────────────────────────────────────────────────
#  GUARDADO EN UBICACION EXTERNA
# ──────────────────────────────────────────────────────────────────────────

# Carpeta por defecto para el codigo generado/guardado (dentro del proyecto).
from core.nlu import BASE_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_code")


def save_code(code, filename, directory=None):
    """Guarda codigo en un archivo. Por seguridad, si no se da una ruta
    absoluta, escribe dentro de generated_code/ del proyecto."""
    if not filename:
        return {"saved": False, "message": "Falta el nombre de archivo."}
    filename = os.path.basename(filename)  # evita traspaso de rutas en el nombre
    if directory and os.path.isabs(directory):
        target_dir = directory
    else:
        target_dir = OUTPUT_DIR
    try:
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return {"saved": True, "path": path,
                "message": f"Código guardado en: {path}"}
    except OSError as e:
        return {"saved": False, "message": f"No pude guardar el archivo: {e}"}
