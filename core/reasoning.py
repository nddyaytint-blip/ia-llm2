"""Capa de razonamiento sobre la base de conocimiento.

Convierte una busqueda en una respuesta fundamentada, detallada y
multi-materia, con nivel de confianza, fuentes y conexiones, capaz de:
- recordar el contexto de los ultimos N turnos para respuestas coherentes,
- combinar pasajes de distintos dominios con transiciones naturales,
- defender su postura cuando la evidencia la sostiene, o
- ceder y marcar el tema para ampliarlo cuando la evidencia es debil.
"""
import re
from collections import deque

from core import storage
from core.nlu import tokenize

ANSWER_THRESHOLD = 0.06
DEFEND_THRESHOLD = 0.18
HIGH_LEVEL  = 0.25
MEDIUM_LEVEL = 0.12
# Una seccion secundaria de otra materia solo se incluye si su relevancia
# (relativa al mejor pasaje) supera este umbral; evita conexiones forzadas.
SECONDARY_THRESHOLD = 0.32

# Ambiguedad: una consulta sin enmarcar (palabra suelta abstracta) cuyos
# mejores pasajes se reparten entre VARIOS dominios distintos con puntuacion
# BM25 cercana indica varios sentidos posibles -> pedir clarificacion.
AMBIGUITY_RATIO = 0.78   # un dominio rival cuenta si su raw_score >= 78% del top
AMBIGUITY_MIN_DOMAINS = 2  # nº de dominios distintos compitiendo para ser ambiguo

_MAX_SECTIONS = {"short": 1, "normal": 2, "detailed": 2}

# Máximo de palabras por pasaje en la respuesta (evita volcar PDFs enteros)
_MAX_PASSAGE_WORDS = 120


_RE_INDEX_ENTRY = re.compile(
    r"[A-Za-záéíóúñüÁÉÍÓÚÑÜ][A-Za-záéíóúñüÁÉÍÓÚÑÜ\s\-]{2,}\s+\d[\d,\s]+",
    re.UNICODE,
)
_RE_FIGURE_LABEL = re.compile(
    r"\b(FIGURA|FIGURE|CUADRO|TABLA|FCG|ECG|NEUMO|INSP|ESP|ACG|FEM|REG)\b",
    re.IGNORECASE,
)


def _prose_quality(text: str) -> float:
    """Puntaje 0-1 de calidad de prosa."""
    words = text.split()
    if len(words) < 5:
        return 0.0

    numeric_tokens = sum(1 for w in words if re.fullmatch(r"[\d,\.\-]+", w))
    long_words     = sum(1 for w in words if len(re.sub(r"\W", "", w)) >= 5)
    short_tokens   = sum(1 for w in words if len(re.sub(r"\W", "", w)) <= 2)

    long_ratio    = long_words / len(words)
    numeric_ratio = numeric_tokens / len(words)
    short_ratio   = short_tokens / len(words)

    if numeric_ratio > 0.20:
        return max(0.0, 0.10 - numeric_ratio)

    # Índice de libro: alta densidad de comas (>1 coma cada 3 palabras = índice)
    comma_ratio = text.count(",") / max(len(words), 1)
    if comma_ratio > 0.30:
        return 0.03

    figure_hits    = len(_RE_FIGURE_LABEL.findall(text))
    figure_penalty = min(figure_hits / max(len(words), 1) * 4, 0.35)

    score = long_ratio - short_ratio * 0.4 - figure_penalty
    return max(0.0, min(score, 1.0))


# Señales de basura OCR dentro de una oración
_RE_INSTRUMENT_LABEL = re.compile(
    r"(?:FONOMECANOCARDIOGRAMA|FONOMECANO|APEXCARDIOGRAMA|NEUMOGRAMA|FCG|ACG|"
    r"[a-z]{0,8}FIGURA\s+\d+|CUADRO\s+\d+|REG\.\s+\d+|FEM\.\s+\d+)",
    re.IGNORECASE,
)
# Etiquetas de figura incrustadas en prosa (ej: "comunicaFIGURA 1 Registro…")
_RE_FIGURA_INLINE = re.compile(
    r"[a-záéíóúñü]{0,8}(?:FIGURA|CUADRO|TABLA|FIGURE)\s+\d+[^\n.]*",
    re.IGNORECASE,
)
# Palabras autónomas que no deben fusionarse con un fragmento adyacente
_COL_STOPWORDS = frozenset({
    # artículos y preposiciones españolas
    "el", "la", "lo", "le", "de", "del", "en", "al", "a",
    "se", "es", "ha", "su", "me", "te", "si",
    # pronombres/conjunciones
    "que", "con", "por", "las", "los", "una", "uno",
    "son", "han", "hay", "sin", "sus", "nos", "les",
    "muy", "mas", "fue", "ser", "era", "tan", "vez",
    "dos", "tres", "bien", "como",
    # inglés
    "the", "and", "for", "are", "not", "but",
})
_COL_STANDALONE = frozenset({
    "fase", "tipo", "caso", "alto", "alta", "bajo", "baja", "gran", "grado",
    "nivel", "tasa", "valor", "forma", "zona", "parte", "cada", "entre",
    "sobre", "hacia", "desde", "antes", "hasta", "puede", "tiene", "hace",
    "toda", "todo", "otra", "otro", "mismo", "misma", "dicho", "dicha",
    "grave", "larga", "largo", "corto", "corta", "imagen",
    "carga", "efecto", "tiempo", "datos", "signo", "ritmo",
    "pulso", "dolor", "fiebre", "aguda", "agudo",
    # Merges OCR frecuentes (artículo/preposición pegada) → no fusionar más
    "enla", "enlos", "enlas", "enlo", "enun", "enuna",
    "dela", "delos", "delas", "delo", "deun",
    "ala", "alos", "alas",
    "conla", "conlos", "conel", "conun",
    "esde", "esla", "esel", "esun",
    "porla", "porlos", "porel",
    "enel", "porlo",
})
_COL_ALPHA_RE = re.compile(r'[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]')
# Oración que empieza con numerales romanos sueltos (lista OCR)
_RE_ROMAN_START    = re.compile(r"^\s*(?:II|III|IV|VI|VII|VIII|IX|XI|XII)\b")
_RE_NUMBERED_LIST  = re.compile(r"^\s*\d+[\.\)]\s")
_RE_EMBEDDED_LIST  = re.compile(r"\.\s+\d+[\.\)]")    # ". 2." inside a sentence


def _sentence_quality(sent: str) -> float:
    """Calidad de prosa: ratio de palabras reales (>=5 chars alfanuméricos)."""
    words = sent.split()
    if not words:
        return 0.0
    real = sum(1 for w in words if len(re.sub(r"\W", "", w)) >= 5)
    return real / len(words)


def _is_bad_sentence(s: str) -> bool:
    """True si la oración es un artefacto OCR, caption o lista."""
    words = s.split()
    if len(words) < 5:
        return True
    if _RE_INSTRUMENT_LABEL.search(s):
        return True
    if _RE_ROMAN_START.match(s):
        return True
    if _RE_NUMBERED_LIST.match(s):
        return True
    if _RE_EMBEDDED_LIST.search(s):
        return True
    # Alta densidad de tokens numéricos → tabla o índice estadístico
    numeric = sum(1 for w in words if re.search(r"\d", w))
    if numeric / len(words) > 0.30:
        return True
    # Demasiadas palabras con mayúscula → tabla de contenidos / lista de encabezados
    if len(words) >= 7:
        caps = sum(1 for w in words if w and w[0].isupper())
        if caps / len(words) > 0.45:
            return True
    if _sentence_quality(s) < 0.30:
        return True
    return False


def _fix_breaks(text: str) -> str:
    """Une fragmentos de columna OCR: 'flu jo'→'flujo', '(mio cardio)'→'(miocardio)'."""
    def _ok(a, b):
        a_c = _COL_ALPHA_RE.sub("", a)
        b_c = _COL_ALPHA_RE.sub("", b)
        if not a_c or not b_c:
            return False
        if a_c.lower() in _COL_STOPWORDS or b_c.lower() in _COL_STOPWORDS:
            return False
        if a_c.lower() in _COL_STANDALONE or b_c.lower() in _COL_STANDALONE:
            return False
        if not (2 <= len(a_c) <= 7 and 2 <= len(b_c) <= 7):
            return False
        # Ambos largos → probablemente dos palabras reales, no quiebre de columna
        if len(a_c) >= 6 and len(b_c) >= 5:
            return False
        return a_c[0].islower() and b_c[0].islower()

    words = text.split()
    out, i = [], 0
    while i < len(words):
        if i + 1 < len(words) and _ok(words[i], words[i + 1]):
            a_pre  = re.match(r'^[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]*', words[i]).group()
            a_body = re.sub(r'^[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+', '', words[i])
            b_body = re.sub(r'[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+$', '', words[i + 1])
            b_suf  = re.search(r'[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]*$', words[i + 1]).group()
            out.append(a_pre + a_body + b_body + b_suf)
            i += 2
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def _clean_passage(text: str, max_words: int = _MAX_PASSAGE_WORDS) -> str:
    """Filtra oraciones basura y trunca el pasaje.
    Devuelve '' si el resultado no contiene prosa real suficiente."""
    # Aplanar saltos de línea del PDF (columnas rotas)
    flat = " ".join(text.split())
    # Eliminar etiquetas FIGURA/CUADRO incrustadas en prosa
    flat = _RE_FIGURA_INLINE.sub("", flat)
    # Unir fragmentos de columna OCR
    flat = _fix_breaks(flat)

    # Segmentar por oraciones
    raw_sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚ])", flat)
    good = [s.strip() for s in raw_sents if not _is_bad_sentence(s.strip())]

    if not good:
        return ""

    cleaned = " ".join(good)
    words = cleaned.split()
    if len(words) < 15:
        return ""
    if len(words) > max_words:
        fragment = " ".join(words[:max_words])
        dot = max(fragment.rfind(". "), fragment.rfind("? "))
        if dot > len(fragment) // 2:
            cleaned = fragment[: dot + 1]
        else:
            cleaned = fragment + "…"
    return cleaned.strip()
MEMORY_TURNS = 10  # turnos de contexto que se conservan

_DOMAIN_NAMES = {
    "es": {
        "historia": "la Historia", "quimica": "la Química",
        "fisica": "la Física", "matematicas": "las Matemáticas",
        "geografia": "la Geografía", "geologia": "la Geología",
        "botanica": "la Botánica", "biologia": "la Biología",
        "genetica": "la Genética", "microbiologia": "la Microbiología",
        "biologia_molecular": "la Biología Molecular",
        "psicologia": "la Psicología", "filosofia": "la Filosofía",
        "epistemologia": "la Epistemología", "ontologia": "la Ontología",
        "economia": "la Economía", "sociologia": "la Sociología",
        "general": "el conocimiento general",
    },
    "en": {
        "historia": "History", "quimica": "Chemistry",
        "fisica": "Physics", "matematicas": "Mathematics",
        "geografia": "Geography", "geologia": "Geology",
        "botanica": "Botany", "biologia": "Biology",
        "genetica": "Genetics", "microbiologia": "Microbiology",
        "biologia_molecular": "Molecular Biology",
        "psicologia": "Psychology", "filosofia": "Philosophy",
        "epistemologia": "Epistemology", "ontologia": "Ontology",
        "economia": "Economics", "sociologia": "Sociology",
        "general": "General Knowledge",
    },
}

_TRANSITIONS = {
    "es": [
        "Desde {domain}, se añade que",
        "La perspectiva de {domain} complementa esto:",
        "En el campo de {domain} se explica además que",
        "Relacionado con lo anterior, {domain} aporta:",
        "Desde {domain} puede verse también que",
        "Ampliando con {domain}:",
        "Cabe añadir que {domain} señala:",
    ],
    "en": [
        "From the perspective of {domain},",
        "{domain} adds to this:",
        "In the field of {domain},",
        "Related to the above, {domain} contributes:",
        "Looking at this from {domain},",
        "Expanding with {domain}:",
        "It is worth noting that {domain} points out:",
    ],
}

_QUESTION_STARTS = {
    "que", "como", "cuando", "donde", "quien", "cual", "cuanto", "porque",
    "what", "how", "when", "where", "who", "which", "whom", "whose", "why",
    "define", "explica", "explain", "dime", "cuentame", "habla", "describe",
    "definir", "compara", "relaciona", "en", "por",
}
_CHALLENGE = (
    "estas mal", "estas equivocado", "te equivocas", "eso es falso", "es falso",
    "incorrecto", "no es correcto", "no es asi", "no es verdad", "mientes",
    "youre wrong", "you are wrong", "that is wrong", "thats wrong",
    "that is false", "thats false", "not true", "you are mistaken",
)
# Marcadores que indican que la consulta depende del turno anterior. Se
# mantienen especificos: nada de "y"/"and"/"mas" que aparecen en frases normales.
_FOLLOWUP_MARKERS = (
    "eso", "esto", "ello", "aquello", "anterior", "amplialo", "amplia eso",
    "continua", "sigue con", "y eso", "y aquello", "lo anterior",
    "that", "previous", "expand", "go on", "continue",
)

# Verbos de acción que necesitan un sujeto del turno anterior para tener sentido.
# Si la única "palabra de contenido" de la consulta es uno de estos verbos,
# la consulta es un seguimiento aunque no use pronombres explícitos.
# Ej: "como se corrige", "como se trata", "qué causa", "cómo se previene"
_ACTION_VERBS = {
    # tratamiento / corrección
    "corrige", "corrije", "corriges", "corregir", "corrijo",
    "trata", "tratas", "tratar", "tratamiento", "tratamientos",
    "cura", "curan", "curar", "curación",
    "maneja", "manejar", "manejo",
    "controla", "controlar", "control",
    "resuelve", "resolver", "resolución",
    # prevención / diagnóstico
    "previene", "prevenir", "prevención", "prevencion",
    "diagnostica", "diagnosticar", "diagnóstico", "diagnostico",
    "detecta", "detectar", "detección",
    "identifica", "identificar", "identificación",
    # mecanismo / causa
    "causa", "causan", "causas", "causante", "causar",
    "provoca", "provocan", "provocar",
    "origina", "originan", "originar",
    "produce", "producen", "producir",
    "ocurre", "ocurren", "ocurrir",
    "pasa", "pasan", "pasar",
    "afecta", "afectan", "afectar",
    "genera", "generan", "generar",
    # funcionalidad
    "funciona", "funcionan", "funcionar", "funcionamiento",
    "sirve", "sirven",
    "permite", "permiten",
    # inglés
    "treat", "treats", "treatment",
    "cure", "cures",
    "prevent", "prevents", "prevention",
    "diagnose", "diagnoses", "diagnosis",
    "cause", "causes",
    "produce", "produces",
    "affect", "affects",
    "correct", "corrects", "correction",
    "fix", "fixes",
    "solve", "solves", "solution",
    "occur", "occurs",
    "work", "works",
}

# Sinonimos de búsqueda para verbos de acción sin sujeto.
# Cuando el usuario pregunta "como se corrige", añadir estos términos
# amplía el recall de BM25 hacia el contenido clínico/educativo correcto.
_ACTION_SYNONYMS: dict = {
    "corrige":      ["corrección", "tratamiento", "manejo", "terapia"],
    "corrije":      ["corrección", "tratamiento", "manejo"],
    "corregir":     ["corrección", "tratamiento", "manejo"],
    "trata":        ["tratamiento", "terapia", "manejo", "intervención"],
    "tratar":       ["tratamiento", "terapia", "manejo"],
    "tratamiento":  ["terapia", "manejo", "intervención"],
    "cura":         ["tratamiento", "curación", "terapia"],
    "curar":        ["curación", "tratamiento", "terapia"],
    "previene":     ["prevención", "profilaxis", "medidas preventivas"],
    "prevenir":     ["prevención", "profilaxis"],
    "prevención":   ["profilaxis", "medidas preventivas"],
    "diagnostica":  ["diagnóstico", "detección", "criterios diagnósticos"],
    "diagnosticar": ["diagnóstico", "detección"],
    "causa":        ["causas", "etiología", "origen", "mecanismo"],
    "causar":       ["etiología", "mecanismo"],
    "provoca":      ["causas", "etiología", "mecanismo fisiopatológico"],
    "produce":      ["mecanismo", "fisiopatología", "efecto"],
    "ocurre":       ["mecanismo", "fisiopatología", "proceso"],
    "funciona":     ["mecanismo", "funcionamiento", "proceso"],
    "funcionar":    ["mecanismo", "funcionamiento"],
    "sirve":        ["función", "utilidad", "propósito"],
    "afecta":       ["efecto", "impacto", "consecuencias"],
    "treat":        ["treatment", "therapy", "management"],
    "treats":       ["treatment", "therapy"],
    "cure":         ["treatment", "cure", "therapy"],
    "prevent":      ["prevention", "prophylaxis"],
    "prevents":     ["prevention", "prophylaxis"],
    "diagnose":     ["diagnosis", "diagnostic criteria"],
    "diagnoses":    ["diagnosis", "diagnostic criteria"],
    "cause":        ["cause", "etiology", "mechanism"],
    "causes":       ["etiology", "mechanism", "pathophysiology"],
    "correct":      ["correction", "treatment", "management"],
    "corrects":     ["correction", "treatment"],
    "fix":          ["correction", "treatment", "solution"],
    "fixes":        ["correction", "treatment"],
    "solve":        ["solution", "treatment", "management"],
    "occurs":       ["mechanism", "physiopathology", "process"],
    "work":         ["mechanism", "function", "process"],
    "works":        ["mechanism", "function"],
}
_EXPLAIN = (
    "por que dices", "en que te basas", "como lo sabes", "como sabes",
    "de donde sacas", "justifica", "demuestra", "pruebalo",
    "tus fuentes", "tu fuente", "cual es tu fuente", "cuales son tus fuentes",
    "explica tu respuesta", "explica eso", "amplia tu respuesta", "amplia eso",
    "why do you say", "your source", "your sources",
    "how do you know", "justify", "prove it", "explain your answer",
    "explain that", "back that up",
)

# Preguntas sobre el propio funcionamiento de Green Tail (auto-introspeccion).
# Requieren auto-referencia (verbo en 2a persona, "tu/your", o "green tail")
# para no confundirse con "como funciona la celula" (3a persona).
_SELF_MARKERS = (
    # funcionamiento general (2a persona)
    "como funcionas", "como funciona green tail", "como funciona greentail",
    "como trabajas", "como operas", "como funcionas tu", "como te funciona",
    # capacidades especificas (2a persona)
    "como aprendes", "como buscas", "como respondes", "como razonas",
    "como piensas", "como guardas", "como almacenas", "como clasificas",
    "como detectas el idioma", "como sabes el idioma", "como decides",
    "como te actualizas", "como te entrenas", "como procesas",
    # tecnologia / algoritmo
    "que algoritmo usas", "que algoritmo utilizas", "que algoritmo empleas",
    "que tecnologia usas", "que tecnologia utilizas", "con que estas hecha",
    "con que estas hecho", "de que estas hecha", "de que estas hecho",
    "como estas hecha", "como estas hecho", "como estas programada",
    # identidad
    "que eres", "quien eres", "que eres tu", "quien eres tu",
    "eres una ia", "eres inteligencia artificial", "eres un chatbot",
    "usas gpt", "usas chatgpt", "usas un modelo", "eres un llm",
    # creacion / arquitectura
    "como te crearon", "como fuiste creada", "como fuiste creado",
    "como te hicieron", "tu arquitectura", "tu codigo", "tu sistema",
    "tu funcionamiento", "tu memoria", "tus modulos", "tus componentes",
    "como te disenaron", "como estas construida",
    # hardware propio / recursos / dispositivos
    "necesitas gpu", "necesitas una gpu", "necesitas tarjeta grafica",
    "requieres gpu", "usas gpu", "necesitas una tarjeta", "ocupas gpu",
    "necesitas mas ram", "necesitas mucha ram", "necesitas mucha memoria",
    "cuanta ram necesitas", "cuanta memoria necesitas", "necesitas mucho",
    "que hardware necesitas", "que recursos necesitas", "que necesitas para funcionar",
    "puedes correr en", "puedes funcionar en", "funcionas en dispositivos",
    "corres en", "necesitas un buen equipo", "necesitas mucha potencia",
    "que requisitos", "requisitos tienes", "que te falta para",
    "need a gpu", "do you need gpu", "need gpu", "require gpu", "use gpu",
    "how much ram", "do you need much", "can you run on", "low end device",
    "what hardware", "system requirements",
    # internet / privacidad
    "usas internet", "necesitas internet", "te conectas a internet",
    "guardas mis datos", "envias mis datos", "eres privada", "eres offline",
    "explicate", "explica como funcionas", "explicame como funcionas",
    "describe tu funcionamiento", "habla de ti", "preséntate", "presentate",
    # ingles
    "how do you work", "how do you function", "how you work",
    "how do you learn", "how do you search", "how do you answer",
    "how do you think", "how do you store", "how do you classify",
    "how do you detect", "how do you decide", "how do you respond",
    "what algorithm", "what technology do you use", "what are you made of",
    "what are you", "who are you", "are you an ai", "are you a chatbot",
    "do you use gpt", "do you use a model", "are you an llm",
    "how were you made", "how were you created", "how are you made",
    "your architecture", "your code", "your system", "your memory",
    "do you use internet", "do you need internet", "are you offline",
    "explain yourself", "explain how you work", "describe yourself",
    "tell me about yourself", "introduce yourself",
)

# Mapea palabras clave de la pregunta a terminos ancla que ayudan a BM25 a
# recuperar el documento de green_tail correcto.
_SELF_ANCHORS = (
    (("aprend", "learn", "guard", "store", "clasific", "classif", "enseñ", "ensen",
      "editas", "actualiz", "crece", "nuevo", "carpeta", "dominio", "domain"),
     "aprendo clasifico dominio enseñar ingest enriquecer índice nuevo carpeta discernir"),
    (("busc", "search", "respond", "answer", "algoritmo", "algorithm", "bm25",
      "rankea", "relevan", "indice", "index", "tf"),
     "BM25 índice invertido búsqueda ranking relevancia sinónimos confianza pasajes"),
    (("idioma", "language", "bilingue", "ingles", "español", "espanol",
      "memoria", "memory", "contexto", "context", "debat", "razon", "reason"),
     "idioma bilingüe detección memoria conversación contexto debate autocrítica"),
    (("gpu", "tarjeta", "grafica", "ram", "hardware", "recurso", "resource",
      "dispositivo", "device", "potencia", "requisito", "requirement",
      "correr", "ejecutar", "bajos recursos", "low end", "modesto", "ligera"),
     "GPU tarjeta gráfica RAM CPU BM25 bajos recursos dispositivos modestos "
     "eficiente sin GPU redes neuronales perfil bajo Python puro ligera"),
    (("internet", "offline", "privac", "privado", "datos", "data", "nube", "cloud",
      "gpt", "modelo", "model", "llm", "arquitectura", "modulo", "componente"),
     "internet offline privacidad arquitectura recursos módulos sin nube"),
)

_PHRASES = {
    "es": {
        "unknown": "No tengo información suficiente sobre eso en mi base de conocimiento actual. "
                   "Puedes agregar documentos en la carpeta knowledge/ y los incorporaré automáticamente.",
        "caveat": "No tengo certeza plena, pero según los datos que manejo:",
        "no_prev": "No tengo una afirmación previa con evidencia que defender.",
        "defend": "He re-verificado mi respuesta y mantengo mi posición (confianza {pct}%). "
                  "La evidencia en mi base de conocimiento la sostiene:",
        "defend_cite": "Según {src}: «{frag}»",
        "defend_tail": "Si tienes una fuente concreta que contradiga esto, agrégala a knowledge/ "
                       "y lo reconsideraré con esa evidencia.",
        "defend_counter": "Antes de ceder, revisé mi base de conocimiento nuevamente buscando "
                          "posibles errores en mi respuesta anterior. No encontré contradicciones. "
                          "¿Puedes indicarme qué parte específicamente crees que es incorrecta?",
        "concede_verified": "Revisé nuevamente y tienes razón: mi respuesta anterior tenía un error. "
                            "Lo corrijo: {correction}",
        "concede": "Puede que tengas razón. Mi evidencia sobre esto es débil (confianza {pct}%), "
                   "así que no la defiendo con seguridad. He marcado el tema para ampliar mi conocimiento.",
        "connect_tail": "Este tema conecta además con: {domains}.",
        "explain": "Me baso exclusivamente en lo que tengo indexado, sin internet. "
                   "Para tu consulta recuperé los siguientes pasajes por similitud de términos:",
        "explain_none": "Aún no he dado una respuesta fundamentada que explicar.",
        "context_note": "Basándome también en lo que mencionaste antes:",
        "clarify_ambiguous": "Tu pregunta podría ir por varios caminos y quiero darte la "
                             "respuesta correcta. ¿A cuál de estos te refieres?",
        "clarify_vague": "Tu pregunta es un poco amplia o breve y quiero entenderte bien "
                         "antes de responder. ¿Podrías concretar un poco más? Por ejemplo:",
        "clarify_tail": "También puedes reformularla con más detalle y la respondo.",
        "interpreted": "Entiendo que preguntas por {topic}. Esto es lo que sé:",
        "history_context": "Contexto de nuestra conversación ({n} turnos previos): {topics}",
    },
    "en": {
        "unknown": "I don't have enough information about that in my knowledge base. "
                   "Add documents to the knowledge/ folder and I'll incorporate them automatically.",
        "caveat": "I'm not fully certain, but based on the data I have:",
        "no_prev": "I don't have a previous evidence-backed claim to defend.",
        "defend": "I've re-verified my answer and I stand by my position (confidence {pct}%). "
                  "The evidence in my knowledge base supports it:",
        "defend_cite": 'According to {src}: "{frag}"',
        "defend_tail": "If you have a specific source that contradicts this, add it to knowledge/ "
                       "and I'll reconsider with that evidence.",
        "defend_counter": "Before conceding, I re-checked my knowledge base for errors in my "
                          "previous answer. I found no contradictions. "
                          "Can you tell me which specific part you think is incorrect?",
        "concede_verified": "I re-checked and you're right: my previous answer had an error. "
                            "Corrected: {correction}",
        "concede": "You may be right. My evidence on this is weak (confidence {pct}%), "
                   "so I won't defend it with certainty. I've flagged this topic to expand my knowledge.",
        "connect_tail": "This topic also connects with: {domains}.",
        "explain": "I rely solely on what I have indexed, with no internet access. "
                   "For your query I retrieved these passages by term similarity:",
        "explain_none": "I haven't given an evidence-backed answer to explain yet.",
        "context_note": "Drawing also on what you mentioned earlier:",
        "clarify_ambiguous": "Your question could go in several directions and I want to give "
                             "you the right answer. Which of these do you mean?",
        "clarify_vague": "Your question is a bit broad or short and I want to understand you "
                         "well before answering. Could you be more specific? For example:",
        "clarify_tail": "You can also rephrase it with more detail and I'll answer.",
        "interpreted": "I understand you're asking about {topic}. Here's what I know:",
        "history_context": "Context from our conversation ({n} previous turns): {topics}",
    },
}

# Reformulacion: frases de pregunta que apuntan al mismo nucleo semantico.
# Distintos fraseos -> mismos terminos de busqueda. Esto permite entender
# "de que esta hecho el agua" y "cual es la composicion del agua" como lo mismo.
_INTENT_REWRITES = (
    # (patrones que aparecen en la consulta, terminos canonicos a anadir)
    (("de que esta hecho", "de que esta hecha", "de que se compone", "que compone",
      "cual es la composicion", "de que esta formado", "de que esta formada",
      "que contiene", "cuales son los componentes", "made of", "composed of",
      "what makes up", "composition of"),
     "composición estructura componentes elementos"),
    (("para que sirve", "cual es la funcion", "que funcion", "que utilidad",
      "para que se usa", "para que sirven", "what is the function", "what is it for",
      "what is used for", "purpose of"),
     "función utilidad uso propósito papel"),
    (("por que", "cual es la causa", "que causa", "que provoca", "a que se debe",
      "que origina", "por que ocurre", "por que pasa", "why does", "what causes",
      "cause of", "reason for"),
     "causa razón origen motivo mecanismo"),
    (("como se hace", "como se forma", "como se produce", "como se genera",
      "cual es el proceso", "como ocurre", "como sucede", "como se realiza",
      "how is", "how does", "how do", "process of", "how is it made", "how is it formed"),
     "proceso formación mecanismo etapas cómo"),
    (("que diferencia", "en que se diferencian", "cual es la diferencia",
      "diferencias entre", "compara", "comparar", "versus", "difference between",
      "compare", "vs"),
     "diferencia comparación contraste distinción"),
    (("que tipos", "cuales tipos", "que clases", "clasificacion de", "tipos de",
      "types of", "kinds of", "classification of"),
     "tipos clases categorías clasificación"),
    (("que importancia", "por que es importante", "que relevancia",
      "importance of", "why is important"),
     "importancia relevancia impacto consecuencias"),
    (("que es", "que son", "define", "definicion de", "que significa",
      "what is", "what are", "definition of", "meaning of", "que quiere decir"),
     "definición concepto significado"),
    (("ejemplo de", "ejemplos de", "dame un ejemplo", "example of", "examples of"),
     "ejemplo caso"),
)

# Muletillas y rellenos conversacionales que se eliminan para llegar al nucleo.
# Las frases mas largas van primero (la limpieza es secuencial). Incluye
# introductores coloquiales de tema ("eso de los…" = "el asunto de…") que NO
# son pronombres de seguimiento.
_FILLERS = (
    "eso de los", "eso de las", "eso de la", "eso de el", "esto de los",
    "esto de las", "esto de la", "lo de los", "lo de las", "lo de la",
    "eso de", "esto de", "lo de", "aquello de",
    "oye", "hola", "mira", "una pregunta", "tengo una pregunta", "queria saber",
    "quería saber", "quiero saber", "me gustaria saber", "me gustaría saber",
    "me podrias decir", "me podrías decir", "podrias decirme", "podrías decirme",
    "puedes decirme", "dime", "explicame", "explícame", "cuentame", "cuéntame",
    "necesito saber", "tengo duda", "tengo una duda", "una duda", "sabes",
    "por favor", "porfa", "ayudame", "ayúdame", "me explicas", "explicame por favor",
    "i want to know", "i would like to know", "can you tell me", "could you tell me",
    "tell me", "please", "i have a question", "a question", "do you know",
    "i need to know", "help me", "explain to me",
)


def _norm(text):
    return " ".join(tokenize(text))


def _token_overlap(a, b):
    ta = set(tokenize(a))
    tb = set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class Reasoner:
    def __init__(self, kb, session_id="default"):
        self.kb = kb
        self.last = None
        self.session_id = session_id
        # Memoria conversacional: deque de {query, reply, lang, domains, confidence}
        self._memory: deque = deque(maxlen=MEMORY_TURNS)
        self._load_persistent_memory()

    def _load_persistent_memory(self):
        """Carga el historial de conversación persistente desde disco."""
        from core import storage
        turns = storage.load_conversation(self.session_id)
        for turn in turns[-MEMORY_TURNS:]:
            self._memory.append(turn)

    def _save_persistent_memory(self):
        """Guarda el historial de conversación a disco."""
        from core import storage
        storage.save_conversation(self.session_id, list(self._memory))

    def set_session(self, session_id):
        """Cambia la sesión activa y carga su historial."""
        if session_id != self.session_id:
            self.session_id = session_id
            self._memory.clear()
            self._load_persistent_memory()

    # -- memoria conversacional -----------------------------------------------
    def _is_followup(self, text):
        """Detecta si la consulta depende del contexto anterior.

        Es seguimiento cuando:
        1. Contiene un pronombre/marcador explícito ("eso", "esto", etc.)
        2. No tiene palabras de contenido propias (frase muy corta)
        3. Solo tiene verbos de acción sin sujeto ("como se corrige",
           "como se trata", "como se previene") — necesitan el tema previo.
        """
        n = _norm(text)
        toks = n.split()
        words = set(toks)

        # 1. Marcadores explícitos de seguimiento
        for marker in _FOLLOWUP_MARKERS:
            if " " in marker:
                if marker in n:
                    return True
            elif marker in words:
                return True

        # Palabras de contenido: no son marcadores de pregunta ni demasiado cortas
        content = [t for t in toks if t not in _QUESTION_STARTS and len(t) > 3]

        # 2. Sin palabras de contenido propias
        if len(content) == 0:
            return True

        # 3. Todas las palabras de contenido son verbos de acción sin sujeto
        if self._memory and all(c in _ACTION_VERBS for c in content):
            return True

        return False

    def _context_query(self, text):
        """Enriquece la consulta si es seguimiento del turno anterior.

        Para verbos de acción sin sujeto ("como se corrige"), la búsqueda
        se construye poniendo el TEMA PREVIO primero (mayor peso BM25)
        y añadiendo sinónimos del verbo para recuperar el contenido correcto.
        """
        if not self._memory or not self._is_followup(text):
            return text
        prev = self._memory[-1]

        # Términos del tema anterior (palabras de contenido de la pregunta previa)
        topic_terms = [t for t in tokenize(prev["query"])
                       if len(t) > 3 and t not in _QUESTION_STARTS][:6]

        # Para verbos de acción, expandir con sinónimos de dominio
        n = _norm(text)
        content_words = [t for t in n.split()
                         if t not in _QUESTION_STARTS and len(t) > 3]
        action_expansion = []
        for v in content_words:
            if v in _ACTION_VERBS:
                action_expansion.extend(_ACTION_SYNONYMS.get(v, []))

        # Construir: tema + sinonimos de la acción + texto original
        parts = []
        if topic_terms:
            parts.extend(topic_terms)
        if action_expansion:
            parts.extend(action_expansion[:4])
        if not parts:
            return text
        return " ".join(parts) + " " + text

    # -- comprension y reformulacion de la consulta --------------------------
    def _clean_query(self, text):
        """Elimina muletillas y rellenos conversacionales para llegar al nucleo."""
        n = " " + _norm(text) + " "
        for filler in _FILLERS:
            n = n.replace(" " + filler + " ", " ")
        return n.strip()

    def _reformulate(self, text):
        """Reescribe la consulta a su nucleo semantico. BM25 ya es robusto al
        fraseo (empareja por palabras de contenido), asi que el trabajo aqui es
        limpiar muletillas y detectar el TIPO de pregunta (definición, causa,
        proceso…) para mostrar que razono el sentido real.

        Devuelve (consulta_limpia, intent_label)."""
        n = _norm(text)
        intent_label = None
        for patterns, canon in _INTENT_REWRITES:
            if any(p in n for p in patterns):
                intent_label = canon.split()[0]
                break
        cleaned = self._clean_query(text)
        return cleaned, intent_label

    def _core_topic(self, text):
        """Extrae el tema central: palabras de contenido reales, filtrando
        muletillas, palabras de pregunta y stopwords del idioma."""
        cleaned = self._clean_query(text)
        sw = getattr(self.kb, "stopwords", set())
        # frases de intencion cuyos verbos no son el tema
        intent_words = {"hecho", "hecha", "compone", "composicion", "sirve",
                        "sirven", "debe", "funcion", "ocurre", "pasa", "llama",
                        "formado", "formada", "contiene", "provoca", "origina",
                        "activan", "desactivan", "made", "function", "called"}
        core = [t for t in tokenize(cleaned)
                if len(t) > 2 and t not in _QUESTION_STARTS
                and t not in sw and t not in intent_words]
        if not core:  # fallback: cualquier palabra de contenido
            core = [t for t in tokenize(cleaned) if len(t) > 2 and t not in _QUESTION_STARTS and t not in sw]
        return " ".join(core[:5])

    def _assess(self, text, hits):
        """Evalua la recuperacion para decidir como responder.

        Devuelve 'ok', 'ambiguous' o 'empty'.
        - empty:     sin resultados.
        - ambiguous: la consulta NO esta enmarcada como pregunta concreta
                     (es una palabra/termino suelto) y sus mejores pasajes se
                     reparten entre varios dominios distintos con puntuacion
                     parecida -> varios sentidos posibles, pedir clarificacion.
        - ok:        hay un sentido dominante -> responder.
        """
        if not hits:
            return "empty", None

        sw = getattr(self.kb, "stopwords", set())
        content = [t for t in tokenize(text)
                   if len(t) > 2 and t not in _QUESTION_STARTS and t not in sw]

        # Una pregunta bien enmarcada ("¿qué es X?", "¿para qué sirve X?") con
        # al menos un termino propio se responde directamente, sin nitpicking.
        framed = self.is_question(text) and len(content) >= 1
        if framed:
            return "ok", None

        # Solo una palabra suelta y abstracta (sin enmarcar) merece clarificacion;
        # una frase de 2+ terminos ya aporta contexto suficiente para responder.
        if len(content) > 1:
            return "ok", None

        # Consulta suelta: ¿compiten varios dominios de cerca?
        top_raw = hits[0]["raw_score"]
        if top_raw <= 0:
            return "ok", None
        competing = []
        for h in hits:
            if h["raw_score"] / top_raw >= AMBIGUITY_RATIO and h["domain"] not in competing:
                competing.append(h["domain"])
        if len(competing) >= AMBIGUITY_MIN_DOMAINS:
            return "ambiguous", None
        return "ok", None

    def _clarify_options(self, text, hits, lang):
        """Construye opciones de clarificacion a partir de los dominios candidatos."""
        core = self._core_topic(text)
        seen = []
        options = []
        for h in hits:
            d = h["domain"]
            if d in seen:
                continue
            seen.append(d)
            domain_name = _DOMAIN_NAMES[lang].get(d, d)
            # Sugerencia de consulta refinada que el usuario puede pulsar
            if lang == "es":
                label = f"{core} — en {domain_name}" if core else domain_name
                refined = f"{core} {d}".strip()
            else:
                label = f"{core} — in {domain_name}" if core else domain_name
                refined = f"{core} {d}".strip()
            options.append({"label": label, "query": refined, "domain": d})
            if len(options) >= 4:
                break
        return options

    def _store_turn(self, query, reply, lang, domains, confidence=0.0):
        self._memory.append({
            "query": query,
            "reply": reply[:200],
            "lang": lang,
            "domains": domains,
            "confidence": confidence,
        })
        self._save_persistent_memory()

    def memory_summary(self):
        return list(self._memory)

    def _build_context_prefix(self, lang):
        """Genera un resumen del contexto previo para incluir en respuestas de seguimiento."""
        if len(self._memory) < 2:
            return ""
        ph = _PHRASES.get(lang, _PHRASES["es"])
        prev = self._memory[-1]
        topic = " ".join(t for t in tokenize(prev["query"]) if len(t) > 3)[:60]
        if not topic:
            return ""
        return ph.get("context_note", "") + f" ({topic})"

    # -- deteccion de tipo de entrada ----------------------------------------
    def is_question(self, text):
        if "?" in text or "¿" in text:
            return True
        toks = tokenize(text)
        if toks and toks[0] in _QUESTION_STARTS:
            return True
        # Fraseos interrogativos que no empiezan con palabra de pregunta clasica
        # ("para que sirve…", "de que esta hecho…", "a que se debe…").
        n = _norm(text)
        for patterns, _canon in _INTENT_REWRITES:
            if any(p in n for p in patterns):
                return True
        return False

    def is_challenge(self, text):
        n = _norm(text)
        return any(p in n for p in _CHALLENGE)

    def is_explain_request(self, text):
        n = _norm(text)
        return any(p in n for p in _EXPLAIN)

    def is_self_question(self, text):
        """Pregunta sobre el propio funcionamiento de Green Tail."""
        n = _norm(text)
        return any(p in n for p in _SELF_MARKERS)

    def self_explain(self, text, lang, facts=None):
        """Responde una pregunta sobre el propio funcionamiento combinando los
        documentos indexados de green_tail con datos en vivo del sistema."""
        n = _norm(text)
        # Anclas segun el aspecto preguntado para que BM25 recupere el doc correcto
        anchors = ["green tail funcionamiento"]
        for keywords, anchor in _SELF_ANCHORS:
            if any(k in n for k in keywords):
                anchors.append(anchor)
        enriched = text + " " + " ".join(anchors)

        hits = self.kb.search(enriched, top_k=8, include_meta=True)
        # Prioriza pasajes del propio dominio green_tail
        self_hits = [h for h in hits if h["domain"] == "green_tail"]
        chosen = self_hits or hits

        if not chosen:
            # Sin documentos: responde con datos en vivo minimos
            reply = self._live_facts_text(lang, facts)
            self.last = {"query": text, "hits": [], "confidence": 0.4, "lang": lang}
            return {"mode": "self", "reply": reply, "score": 0.4,
                    "confidence": self._level(0.4, lang), "sources": [],
                    "connections": ["green_tail"]}

        # Compone 1-2 secciones de green_tail sin transiciones de dominio
        parts = []
        seen = set()
        for h in chosen[:2]:
            if h["source"] in seen:
                continue
            seen.add(h["source"])
            body = _clean_passage(h["text"])
            if body:
                parts.append(body)

        # Adjunta una linea de datos en vivo del sistema actual
        live = self._live_facts_text(lang, facts)
        if live:
            parts.append(live)

        reply = "\n\n".join(parts)
        conf = chosen[0]["score"]
        self.last = {"query": text, "hits": chosen, "confidence": conf, "lang": lang}
        self._store_turn(text, reply, lang, ["green_tail"])
        return {
            "mode": "self",
            "reply": reply,
            "score": round(conf, 3),
            "confidence": self._level(max(conf, 0.25), lang),
            "sources": self._sources(chosen),
            "connections": ["green_tail"],
        }

    def _live_facts_text(self, lang, facts):
        """Genera una linea con datos reales del estado actual del sistema."""
        if not facts:
            return ""
        if lang == "es":
            return (
                f"En este momento concreto: tengo {facts.get('passages', 0)} pasajes "
                f"indexados en {facts.get('domains', 0)} materias, funcionando en perfil "
                f"'{facts.get('tier', '?')}' sobre {facts.get('cores', '?')} núcleos de CPU "
                f"y {facts.get('ram_mb', '?')} MB de RAM. Uso BM25 (k1={facts.get('k1', 1.5)}, "
                f"b={facts.get('b', 0.75)}) para rankear los pasajes, todo localmente y sin internet."
            )
        return (
            f"Right now specifically: I have {facts.get('passages', 0)} passages indexed "
            f"across {facts.get('domains', 0)} subjects, running on the "
            f"'{facts.get('tier', '?')}' profile with {facts.get('cores', '?')} CPU cores "
            f"and {facts.get('ram_mb', '?')} MB of RAM. I use BM25 (k1={facts.get('k1', 1.5)}, "
            f"b={facts.get('b', 0.75)}) to rank passages, all locally and offline."
        )

    # -- utilidades ----------------------------------------------------------
    def _level(self, score, lang):
        if score >= HIGH_LEVEL:
            return "alta" if lang == "es" else "high"
        if score >= MEDIUM_LEVEL:
            return "media" if lang == "es" else "medium"
        return "baja" if lang == "es" else "low"

    def _sources(self, hits):
        return [f"{h['source']} (score {h['score']})" for h in hits[:5]]

    def _connections(self, related):
        return sorted(related.get("domains", []))

    # -- seleccion de secciones ----------------------------------------------
    def _select_sections(self, hits, max_sections):
        # Re-rankea combinando BM25 con calidad de prosa (0-1).
        # Un índice con BM25 alto pero prosa basura queda por debajo de
        # un pasaje real con BM25 moderado.
        ranked = sorted(
            hits,
            key=lambda h: h["score"] * max(_prose_quality(h["text"]), 0.05),
            reverse=True,
        )

        seen_sources = set()
        selected = []
        for h in ranked:
            threshold = ANSWER_THRESHOLD if not selected else SECONDARY_THRESHOLD
            if h["score"] < threshold:
                continue
            if h["source"] in seen_sources:
                continue
            if any(_token_overlap(h["text"], p["text"]) > 0.55 for p in selected):
                continue
            cleaned = _clean_passage(h["text"])
            if not cleaned:
                continue
            seen_sources.add(h["source"])
            # Guardamos el texto limpio para no re-limpiar en _compose_answer
            h = dict(h)
            h["_cleaned"] = cleaned
            selected.append(h)
            if len(selected) >= max_sections:
                break
        return selected

    # -- composicion de respuesta --------------------------------------------
    def _compose_answer(self, sections, related, lang, conf):
        ph = _PHRASES[lang]
        trans = _TRANSITIONS[lang]
        parts = []

        for i, h in enumerate(sections):
            body = h.get("_cleaned") or _clean_passage(h["text"])
            if not body:
                continue
            if i == 0:
                parts.append(body if conf >= MEDIUM_LEVEL
                              else f"{ph['caveat']}\n{body}")
            else:
                domain_name = _DOMAIN_NAMES[lang].get(h["domain"], h["domain"])
                t = trans[(i - 1) % len(trans)].format(domain=domain_name)
                parts.append(f"{t} {body}")

        conn_domains = related.get("domains", [])
        main_domain = sections[0]["domain"] if sections else ""
        other = [_DOMAIN_NAMES[lang].get(d, d)
                 for d in conn_domains if d != main_domain][:4]
        if other:
            parts.append(ph["connect_tail"].format(domains=", ".join(other)))

        return "\n\n".join(parts)

    # -- respuesta fundamentada con comprension de la consulta ---------------
    def answer(self, text, lang, verbosity="normal"):
        max_sections = _MAX_SECTIONS.get(verbosity, 3)
        ph = _PHRASES[lang]

        # 1. Comprender: reformular fraseos distintos al mismo nucleo y, si es
        #    seguimiento, enriquecer con el contexto previo.
        reformulated, intent_label = self._reformulate(text)
        query = self._context_query(reformulated)

        # 2. Recuperar
        hits = self.kb.search(query)

        # 3. Evaluar la calidad de la recuperacion
        quality, _ = self._assess(text, hits)

        # 3a. Nada relevante -> reconocer honestamente
        if quality == "empty":
            self.last = {"query": text, "hits": hits, "confidence": 0.0, "lang": lang}
            return {"mode": "knowledge", "reply": ph["unknown"], "score": 0.0,
                    "confidence": self._level(0.0, lang), "sources": [], "connections": []}

        # 3b. Ambigua -> pedir clarificacion ofreciendo interpretaciones
        if quality == "ambiguous":
            options = self._clarify_options(text, hits, lang)
            core = self._core_topic(text)
            head = ph["clarify_vague"] if len(core.split()) <= 1 else ph["clarify_ambiguous"]
            opt_lines = "\n".join(f"  • {o['label']}" for o in options)
            reply = f"{head}\n\n{opt_lines}\n\n{ph['clarify_tail']}"
            self.last = {"query": text, "hits": hits,
                         "confidence": hits[0]["score"], "lang": lang}
            return {
                "mode": "clarify",
                "reply": reply,
                "score": round(hits[0]["score"], 3),
                "confidence": self._level(hits[0]["score"], lang),
                "sources": [],
                "connections": sorted({o["domain"] for o in options}),
                "options": options,
            }

        # 4. Hay un ganador (ok) o algo flojo (weak): componer respuesta
        conf = hits[0]["score"]
        self.last = {"query": text, "hits": hits, "confidence": conf, "lang": lang}

        sections = self._select_sections(hits, max_sections)
        related = self.kb.related(reformulated)
        reply = self._compose_answer(sections, related, lang, conf)

        # Si la pregunta venia muy reformulada (fraseo indirecto), antepone una
        # linea de interpretacion para mostrar que razono el sentido real.
        if intent_label and quality == "ok":
            core = self._core_topic(text)
            if core:
                reply = ph["interpreted"].format(topic=core) + "\n\n" + reply

        domains = self._connections(related)
        self._store_turn(text, reply, lang, domains, confidence=conf)
        # Guardar también en last con reply para que debate() pueda comparar
        self.last["reply"] = reply[:200]

        return {
            "mode": "knowledge",
            "reply": reply,
            "score": round(conf, 3),
            "confidence": self._level(conf, lang),
            "sources": self._sources(hits),
            "connections": domains,
        }

    # -- debate / autocritica -----------------------------------------------
    def debate(self, text, lang):
        """Maneja una objeción del usuario.

        Flujo de decisión:
        1. Re-busca la query anterior en BM25 para re-verificar la evidencia.
        2. Si la evidencia re-verificada es fuerte → defiende con cita.
        3. Si la re-búsqueda encuentra información contradictoria con la respuesta
           previa → reconoce el error y corrige.
        4. Si la evidencia es débil → cede y marca el tema para expansión.
        """
        ph = _PHRASES[lang]
        if not self.last or self.last["confidence"] <= 0.0:
            return {"mode": "debate", "reply": ph["no_prev"], "score": 0.0,
                    "confidence": self._level(0.0, lang), "sources": [], "connections": []}

        prev_query = self.last["query"]
        prev_conf  = self.last["confidence"]
        pct        = round(prev_conf * 100)

        # --- Paso 1: re-verificar buscando de nuevo la query anterior ----------
        fresh_hits = self.kb.search(prev_query)
        fresh_quality, _ = self._assess(prev_query, fresh_hits)

        # --- Paso 2: buscar si el usuario está dando una contra-afirmación ----
        # Extraemos palabras de contenido del texto de objeción para buscarlas
        challenge_terms = [t for t in tokenize(text)
                           if len(t) > 3 and t not in _QUESTION_STARTS]
        counter_hits = []
        if challenge_terms:
            counter_query = " ".join(challenge_terms[:8])
            counter_hits  = self.kb.search(counter_query)

        # Mejor fragmento de soporte fresco
        supporting_fresh = [h for h in fresh_hits if h["score"] >= MEDIUM_LEVEL]
        # Mejor fragmento que apoye la CONTRA-afirmación del usuario
        counter_support  = [h for h in counter_hits if h["score"] >= MEDIUM_LEVEL]

        # --- Decisión ----------------------------------------------------------
        if fresh_quality in ("ok",) and supporting_fresh and prev_conf >= DEFEND_THRESHOLD:
            # Hay evidencia fuerte que respalda lo que dijimos: defender
            top  = supporting_fresh[0]
            frag = top["text"][:240].rstrip()
            if len(top["text"]) > 240:
                frag += "..."

            # Verificar si la contra-evidencia del usuario es más fuerte
            if counter_support and counter_support[0]["score"] > top["score"] * 1.15:
                # La evidencia del usuario (deducida de su texto) supera la nuestra: corregir
                correction_frag = counter_support[0]["text"][:200].rstrip()
                storage.append_knowledge_gap(prev_query,
                                             "evidencia de usuario supera la nuestra; se corrigió")
                storage.append_improvement(
                    f"Auto-corrección tras objeción: '{prev_query}' — "
                    f"evidencia contraria score {counter_support[0]['score']:.2f} "
                    f"vs nuestra {top['score']:.2f}"
                )
                reply = ph.get("concede_verified", ph["concede"].format(pct=pct)).format(
                    correction=correction_frag[:160])
                return {"mode": "debate", "stance": "corrige", "reply": reply,
                        "score": round(counter_support[0]["score"], 3),
                        "confidence": self._level(counter_support[0]["score"], lang),
                        "sources": self._sources(counter_hits), "connections": []}

            # Defender: evidencia nuestra es más fuerte o no hay contra-evidencia clara
            reply = "\n\n".join([
                ph["defend"].format(pct=pct),
                ph["defend_cite"].format(src=top["source"], frag=frag),
                ph["defend_tail"],
            ])
            return {"mode": "debate", "stance": "defiende", "reply": reply,
                    "score": round(prev_conf, 3), "confidence": self._level(prev_conf, lang),
                    "sources": self._sources(fresh_hits), "connections": []}

        # Evidencia débil o inexistente: ceder y registrar gap
        storage.append_knowledge_gap(prev_query,
                                     f"objecion del usuario; confianza previa {pct}%")
        storage.append_improvement(
            f"Tema marcado para ampliar conocimiento: '{prev_query}' "
            f"(cedido tras objecion, confianza {pct}%)."
        )
        return {"mode": "debate", "stance": "cede", "reply": ph["concede"].format(pct=pct),
                "score": round(prev_conf, 3), "confidence": self._level(prev_conf, lang),
                "sources": self._sources(fresh_hits), "connections": []}

    def explain(self, text, lang):
        ph = _PHRASES[lang]
        if not self.last or not self.last["hits"]:
            return {"mode": "explain", "reply": ph["explain_none"], "score": 0.0,
                    "confidence": self._level(0.0, lang), "sources": [], "connections": []}
        conf = self.last["confidence"]
        return {"mode": "explain", "reply": ph["explain"], "score": round(conf, 3),
                "confidence": self._level(conf, lang),
                "sources": self._sources(self.last["hits"]), "connections": []}
