"""Clasificador de documentos: asigna categorías automáticamente basado en contenido.

Analiza palabras clave y estructura para detectar el dominio más probable.
Si la categoría no existe como carpeta en knowledge/, la crea automáticamente.
"""

import os
import re
import unicodedata
from pathlib import Path

from core.nlu import tokenize, BASE_DIR

KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")

# Mínimo de coincidencias para asignar una categoría (evita falsos positivos)
MIN_SCORE_THRESHOLD = 2

DOMAIN_KEYWORDS = {
    "biologia": [
        "célula", "celula", "organismo", "especie", "evolución", "evolucion",
        "gen", "proteína", "proteina", "metabolismo", "mitocondria", "nucleo",
        "cell", "organism", "species", "evolution", "gene", "protein", "metabolism",
    ],
    "biologia_molecular": [
        "adn", "arn", "proteína", "enzima", "gen", "cromatina", "transcripcion",
        "traduccion", "ribosoma", "plasmido", "secuenciacion",
        "dna", "rna", "protein", "enzyme", "chromatin", "ribosome", "plasmid",
    ],
    "genetica": [
        "gen", "herencia", "fenotipo", "genotipo", "alelo", "mutación", "mutacion",
        "cromosoma", "haploide", "diploide", "meiosis",
        "gene", "inheritance", "phenotype", "genotype", "allele", "mutation",
        "chromosome", "haploid", "diploid",
    ],
    "microbiologia": [
        "bacteria", "virus", "hongo", "microorganismo", "patógeno", "patogeno",
        "antibiotico", "infección", "infeccion", "cepa", "cultivo",
        "bacterium", "fungus", "microorganism", "pathogen", "antibiotic",
        "infection", "strain", "culture",
    ],
    "medicina": [
        "paciente", "diagnóstico", "diagnostico", "enfermedad", "síntoma", "sintoma",
        "tratamiento", "médico", "medico", "hospital", "clinica", "cirugía", "cirugia",
        "salud", "patología", "patologia",
        "patient", "diagnosis", "disease", "symptom", "treatment", "physician",
        "hospital", "surgery", "health", "pathology",
    ],
    "farmacologia": [
        "fármaco", "farmaco", "medicamento", "droga", "dosis", "farmacocinética",
        "farmacocinetica", "receptor", "biodisponibilidad", "metabolismo",
        "drug", "medication", "dose", "pharmacokinetics", "receptor",
        "bioavailability",
    ],
    "fisiologia": [
        "órgano", "organo", "sistema", "fisiológico", "fisiologico",
        "cardiovascular", "nervioso", "respiratorio", "digestivo", "renal",
        "organ", "system", "cardiovascular", "nervous", "respiratory", "digestive",
        "renal", "physiological",
    ],
    "endocrinologia": [
        "hormona", "glándula", "glandula", "endocrino", "insulina", "tiroides",
        "páncreas", "pancreas", "cortisol", "testosterona", "estrógeno", "estrogeno",
        "hipófisis", "hipofisis", "hipotálamo", "hipotalamo",
        "hormone", "gland", "endocrine", "insulin", "thyroid", "pancreas",
        "cortisol", "testosterone", "estrogen", "pituitary", "hypothalamus",
    ],
    "botanica": [
        "planta", "flor", "hoja", "raíz", "raiz", "fotosíntesis", "fotosintesis",
        "cloroplasto", "semilla", "tallo", "xilema", "floema",
        "plant", "flower", "leaf", "root", "photosynthesis", "chloroplast",
        "seed", "stem", "xylem", "phloem",
    ],
    "fisica": [
        "energía", "energia", "fuerza", "movimiento", "onda", "partícula", "particula",
        "campo", "velocidad", "aceleración", "aceleracion", "masa", "gravedad",
        "energy", "force", "motion", "wave", "particle", "field", "velocity",
        "acceleration", "mass", "gravity",
    ],
    "quimica": [
        "átomo", "atomo", "molécula", "molecula", "reacción", "reaccion",
        "elemento", "compuesto", "enlace", "oxidación", "oxidacion", "ion",
        "atom", "molecule", "reaction", "element", "compound", "bond",
        "oxidation", "ion",
    ],
    "matematicas": [
        "número", "numero", "ecuación", "ecuacion", "función", "funcion",
        "variable", "teorema", "integral", "derivada", "matriz", "vector",
        "number", "equation", "function", "variable", "theorem", "integral",
        "derivative", "matrix", "vector",
    ],
    "economia": [
        "mercado", "precio", "demanda", "oferta", "capital", "dinero",
        "inflación", "inflacion", "pib", "producto", "comercio", "banco",
        "market", "price", "demand", "supply", "capital", "money",
        "inflation", "gdp", "trade", "bank",
    ],
    "sociologia": [
        "sociedad", "cultura", "grupo", "comunidad", "clase social", "institución",
        "institucion", "desigualdad", "norma", "rol",
        "society", "culture", "group", "community", "institution",
        "inequality", "norm", "role",
    ],
    "psicologia": [
        "mente", "comportamiento", "cognición", "cognicion", "emoción", "emocion",
        "personalidad", "conducta", "psique", "terapia",
        "mind", "behavior", "cognition", "emotion", "personality",
        "conduct", "psyche", "therapy",
    ],
    "filosofia": [
        "ser", "verdad", "conocimiento", "moral", "ética", "etica",
        "metafísica", "metafisica", "razón", "razon", "lógica", "logica",
        "being", "truth", "knowledge", "moral", "ethics", "metaphysics",
        "reason", "logic",
    ],
    "epistemologia": [
        "conocimiento", "verdad", "evidencia", "teoría", "teoria",
        "justificación", "justificacion", "ciencia", "método", "metodo",
        "knowledge", "truth", "evidence", "theory", "justification",
        "science", "method",
    ],
    "ontologia": [
        "ser", "existencia", "sustancia", "propiedad", "realidad",
        "being", "existence", "substance", "property", "reality",
    ],
    "historia": [
        "período", "periodo", "edad", "época", "epaca", "civilización",
        "civilizacion", "guerra", "revolución", "revolucion", "siglo",
        "period", "age", "era", "civilization", "war", "revolution", "century",
    ],
    "geografia": [
        "territorio", "región", "region", "clima", "océano", "oceano",
        "continente", "frontera", "mapa", "altitud", "latitud",
        "territory", "region", "climate", "ocean", "continent", "border",
        "map", "altitude", "latitude",
    ],
    "geologia": [
        "roca", "mineral", "tierra", "placa", "magma", "sedimento",
        "volcán", "volcan", "erosión", "erosion", "fósil", "fosil",
        "rock", "mineral", "earth", "plate", "magma", "sediment",
        "volcano", "erosion", "fossil",
    ],
    "programacion": [
        "código", "codigo", "función", "funcion", "variable", "algoritmo",
        "programa", "datos", "clase", "objeto", "método", "metodo",
        "code", "function", "variable", "algorithm", "program", "data",
        "class", "object", "method",
    ],
    "nutricion": [
        "nutriente", "vitamina", "mineral", "proteína", "proteina", "carbohidrato",
        "grasa", "caloría", "caloria", "dieta", "alimentación", "alimentacion",
        "nutrient", "vitamin", "mineral", "protein", "carbohydrate",
        "fat", "calorie", "diet", "nutrition",
    ],
    "astronomia": [
        "estrella", "planeta", "galaxia", "universo", "orbita", "telescopio",
        "cometa", "asteroide", "nebulosa", "agujero negro",
        "star", "planet", "galaxy", "universe", "orbit", "telescope",
        "comet", "asteroid", "nebula", "black hole",
    ],
    "arquitectura": [
        "edificio", "estructura", "diseño", "plano", "construcción", "construccion",
        "material", "cimiento", "viga", "arco",
        "building", "structure", "design", "blueprint", "construction",
        "material", "foundation", "beam", "arch",
    ],
    "derecho": [
        "ley", "norma", "código", "codigo", "jurídico", "juridico", "tribunal",
        "sentencia", "delito", "contrato", "constitución", "constitucion",
        "law", "norm", "code", "legal", "court", "sentence", "crime",
        "contract", "constitution",
    ],
}

# Patrones regex de mayor especificidad (peso doble)
DOMAIN_PATTERNS = {
    "medicina": r"(medicin|diagnóst|diagnost|paciente|síntom|sintom|terapia|tratamiento|médico|hospital|cirugía|cirugia|vaccine|surgical|diagnosis|patient|symptom|therapy|treatment|physician)",
    "farmacologia": r"(fármac|farmac|medicament|farmacocinét|farmacocinet|biodisponibil|drug|medication|pharmacokinetic|bioavailability)",
    "fisiologia": r"(fisiológ|fisiolog|cardiovascular|sistema nervioso|respiratorio|digestivo|renal|physiolog|cardiovascular|nervous system|respiratory|digestive|renal)",
    "endocrinologia": r"(hormon|glándula|glandula|endocrin|insulina|tiroides|páncreas|pancreas|cortisol|testosteron|estrógeno|estrogen|hipófisis|hipofisis|hipotálamo|hipotalamo|pituitar|hypothalamus)",
    "nutricion": r"(nutrición|nutricion|vitamina|suplemento|dietética|dietetica|macronutriente|micronutriente|nutrition|supplement|dietary|macronutrient|micronutrient)",
    "astronomia": r"(astronomía|astronomia|astrofísica|astrofisica|cosmología|cosmologia|astronomy|astrophysics|cosmology|stellar|galactic)",
    "derecho": r"(derecho|jurídico|juridico|legal|legislación|legislacion|jurisprudencia|tribunal|constitucional|law|legal|legislation|jurisprudence|court|constitutional)",
}


def _slugify(text: str) -> str:
    """Convierte texto a slug válido para nombre de carpeta."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:50]


class DocumentClassifier:
    """Clasificador automático de documentos basado en palabras clave.

    A diferencia de la versión anterior, evalúa TODOS los dominios conocidos
    (no solo los que ya tienen carpeta) y crea la carpeta automáticamente
    cuando detecta una categoría nueva con suficiente confianza.
    """

    def __init__(self):
        self._refresh_domains()

    def _refresh_domains(self):
        """Escanea las carpetas de knowledge/ para detectar dominios existentes."""
        self.existing_domains = set()
        if os.path.isdir(KNOWLEDGE_DIR):
            for item in os.listdir(KNOWLEDGE_DIR):
                if os.path.isdir(os.path.join(KNOWLEDGE_DIR, item)):
                    self.existing_domains.add(item)

    def _score_all(self, text: str) -> dict:
        """Puntúa todos los dominios conocidos, existan o no como carpeta."""
        text_lower = text.lower()
        tokens = set(tokenize(text))
        scores = {}

        for domain, keywords in DOMAIN_KEYWORDS.items():
            matches = sum(
                1 for kw in keywords
                if kw in text_lower or any(kw in t for t in tokens)
            )
            if matches > 0:
                scores[domain] = matches

        for domain, pattern in DOMAIN_PATTERNS.items():
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
            if matches > 0:
                scores[domain] = scores.get(domain, 0) + matches * 2

        return scores

    def _ensure_category_folder(self, category: str) -> str:
        """Crea la carpeta en knowledge/ si no existe. Devuelve la ruta."""
        folder = os.path.join(KNOWLEDGE_DIR, category)
        os.makedirs(folder, exist_ok=True)
        self.existing_domains.add(category)
        return folder

    def classify(self, text: str) -> str:
        """Devuelve la categoría más probable y crea su carpeta si no existe.

        Si ningún dominio conocido alcanza el umbral mínimo, intenta derivar
        una categoría del contenido (palabras más frecuentes) antes de caer
        en 'general'.
        """
        scores = self._score_all(text)

        if not scores:
            return "general"

        best, best_score = max(scores.items(), key=lambda x: x[1])

        if best_score < MIN_SCORE_THRESHOLD:
            return "general"

        # Crear carpeta si la categoría no existía antes
        self._ensure_category_folder(best)
        return best

    def classify_with_new(self, text: str, filename: str = "") -> str:
        """Como classify(), pero si no hay coincidencia intenta derivar una
        categoría nueva del nombre del archivo o del contenido más frecuente.

        Úsalo desde FileWatcher para garantizar que siempre haya una carpeta
        semántica en lugar de caer en 'general'.
        """
        scores = self._score_all(text)

        if scores:
            best, best_score = max(scores.items(), key=lambda x: x[1])
            if best_score >= MIN_SCORE_THRESHOLD:
                self._ensure_category_folder(best)
                return best

        # Intentar derivar categoría del nombre del archivo
        if filename:
            slug = _slugify(Path(filename).stem)
            if slug and slug not in ("general", "untitled", "documento", "document"):
                self._ensure_category_folder(slug)
                return slug

        return "general"

    def suggest_categories(self, text: str, top_k: int = 3) -> list:
        """Devuelve las top-k categorías más probables con puntuaciones."""
        scores = self._score_all(text)
        if not scores:
            return [("general", 0)]
        sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_domains[:top_k]

    def auto_create_category(self, text: str, suggested_name: str = None) -> str:
        """Crea una categoría explícita (o infiere una) y devuelve su nombre."""
        if suggested_name:
            slug = _slugify(suggested_name)
            self._ensure_category_folder(slug)
            return slug
        return self.classify_with_new(text)

    def list_domains(self) -> list:
        """Lista todos los dominios disponibles (carpetas en knowledge/)."""
        self._refresh_domains()
        return sorted(self.existing_domains)
