"""Base de conocimiento local: ingiere documentos, los indexa (BM25) y
permite buscar pasajes relevantes y encontrar conexiones entre conceptos.

Sin dependencias externas y sin internet. El indice se reconstruye solo
cuando cambian los archivos de knowledge/ y limita su tamano segun el
perfil de recursos (low/medium/high).
"""
import json
import math
import os
import re
import threading
import time
from collections import defaultdict

from core.nlu import tokenize, BASE_DIR, DATA_DIR

KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
INDEX_CACHE = os.path.join(DATA_DIR, "knowledge_index.json")
TEXT_EXTS = (".md", ".markdown", ".txt")
INDEX_VERSION = 3  # BM25 + sinonimos

# Dominios "meta": describen el propio sistema (auto-introspeccion). Se excluyen
# de las busquedas de conocimiento general; solo aparecen cuando se pregunta
# explicitamente por el funcionamiento de Green Tail (search include_meta=True).
META_DOMAINS = {"green_tail"}

TIER_LIMITS = {
    "low":     {"max_passages": 600,   "max_postings_per_term": 40,  "top_k": 3},
    "medium":  {"max_passages": 4000,  "max_postings_per_term": 120, "top_k": 5},
    "high":    {"max_passages": 20000, "max_postings_per_term": 400, "top_k": 10},
    "unknown": {"max_passages": 2000,  "max_postings_per_term": 80,  "top_k": 5},
}

# BM25 parametros
BM25_K1 = 1.5
BM25_B  = 0.75

# Sinonimos y puentes ES<->EN (termino canonico -> lista de variantes).
# Si CUALQUIER variante (o el canonico) aparece en la consulta, se anaden
# todos los demas. Esto permite que una pregunta en ingles recupere
# contenido escrito en espanol y viceversa.
SYNONYMS: dict[str, list[str]] = {
    # Biologia / genetica / molecular
    "adn":        ["ácido desoxirribonucleico", "deoxyribonucleic acid", "dna"],
    "arn":        ["ácido ribonucleico", "rna", "ribonucleic acid"],
    "atp":        ["adenosin trifosfato", "adenosine triphosphate"],
    "gen":        ["genes", "gene", "locus", "genetico", "genetic"],
    "celula":     ["células", "cell", "cells", "celular", "cellular"],
    "proteina":   ["proteínas", "protein", "proteins", "polipeptido"],
    "enzima":     ["enzimas", "enzyme", "enzymes", "catalizador biologico"],
    "evolucion":  ["evolution", "seleccion natural", "natural selection",
                   "darwinismo", "darwin", "neodarwinismo", "filogenia"],
    "ecosistema": ["ecosystem", "bioma", "biome", "biocenosis", "habitat"],
    "neurona":    ["neuronas", "neuron", "neurons", "celula nerviosa"],
    "sinapsis":   ["sinapticas", "synapse", "neurotransmisor", "neurotransmitter"],
    "mitosis":    ["division celular", "cell division", "meiosis", "ciclo celular"],
    "fotosintesis":["photosynthesis", "clorofila", "chlorophyll", "cloroplasto"],
    "metilacion": ["metilación", "methylation", "epigenetica", "epigenetics",
                   "histona", "histone", "cromatina"],
    "inmunidad":  ["immunity", "immune", "sistema inmune", "immune system",
                   "anticuerpo", "antibody", "linfocito"],
    "microbioma": ["microbiome", "microbiota", "flora intestinal", "gut"],
    "crispr":     ["edicion genomica", "gene editing", "cas9", "ingenieria genetica"],
    # Quimica / fisica
    "entropia":   ["entropía", "entropy", "segunda ley", "desorden termodinamico"],
    "energia":    ["energía", "energy", "trabajo", "work", "calor", "heat", "joule"],
    "fuerza":     ["force", "newton", "dinamica", "mecanica", "inercia", "inertia"],
    "cuantica":   ["cuántica", "quantum", "mecanica cuantica", "quantum mechanics"],
    "atomo":      ["átomo", "atom", "atoms", "atomico", "electron", "neutron"],
    "reaccion":   ["reaction", "reacción", "reactivo", "reactant", "producto quimico"],
    # Economia
    "pib":        ["producto interior bruto", "producto interno bruto", "gdp",
                   "gross domestic product"],
    "inflacion":  ["inflación", "inflation", "deflacion", "deflation", "ipc",
                   "precios", "prices"],
    "mercado":    ["market", "oferta", "supply", "demanda", "demand",
                   "precio de equilibrio", "microeconomia"],
    "desempleo":  ["unemployment", "paro", "empleo", "employment"],
    "ventaja comparativa": ["comparative advantage", "comercio internacional",
                            "international trade", "ricardo"],
    "capitalismo":["capitalism", "libre mercado", "free market", "neoliberalismo"],
    "socialismo": ["socialism", "marxismo", "marxism", "comunismo", "economia planificada"],
    # Sociologia / filosofia / politica
    "sociedad":   ["society", "social", "sociologia", "sociology"],
    "clase social":["social class", "estratificacion", "stratification",
                    "movilidad social", "burguesia", "proletariado"],
    "democracia": ["democracy", "republica", "parlamentarismo", "sufragio",
                   "estado de derecho"],
    "etica":      ["ética", "ethics", "moral", "morality", "virtud", "virtue"],
    "conciencia": ["consciencia", "consciousness", "qualia", "mente", "mind"],
    "conocimiento":["knowledge", "epistemologia", "epistemology", "verdad", "truth"],
    "ser":        ["being", "ontologia", "ontology", "existencia", "existence",
                   "metafisica", "metaphysics"],
    # Geologia / geografia
    "tectonica":  ["tectonics", "placas", "plates", "deriva continental", "sismo",
                   "earthquake", "terremoto"],
    "clima":      ["climate", "cambio climatico", "climate change", "calentamiento global",
                   "global warming", "bioma"],
}

# Dominio canonico -> variantes de nombre de carpeta
DOMAIN_ALIASES = {
    "economia": ["economia", "economía", "economics", "economy"],
    "sociologia": ["sociologia", "sociología", "sociology"],
}


def _load_stopwords():
    words = set()
    for lang in ("es", "en"):
        path = os.path.join(DATA_DIR, f"stopwords_{lang}.txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                words.update(f.read().split())
    return words


def _stem(word):
    if len(word) > 5 and word.endswith("es"):
        return word[:-2]
    if len(word) > 4 and word.endswith("s"):
        return word[:-1]
    if len(word) > 6 and word.endswith("cion"):
        return word[:-4]
    return word


def _content_tokens(text, stopwords):
    return [_stem(t) for t in tokenize(text)
            if len(t) > 2 and t not in stopwords]


def _expand_query(text, stopwords):
    """Expande la consulta con sinonimos canonicos."""
    base = _content_tokens(text, stopwords)
    extra = set()
    low = text.lower()
    for canon, variants in SYNONYMS.items():
        canon_stem = _stem(canon.replace(" ", ""))
        if canon_stem in base or any(v in low for v in variants):
            extra.update(_content_tokens(canon, stopwords))
            for v in variants:
                extra.update(_content_tokens(v, stopwords))
    combined = base + [t for t in extra if t not in base]
    return combined


class KnowledgeBase:
    def __init__(self, tier="unknown"):
        self.tier = tier
        self.limits = TIER_LIMITS.get(tier, TIER_LIMITS["unknown"])
        self.stopwords = _load_stopwords()
        self.passages = []
        self.postings = {}      # term -> [[passage_id, bm25_weight], ...]
        self.idf = {}
        self.avgdl = 1.0
        self.domains = {}
        self.signature = {}
        self.built = False
        self._watch_thread = None
        self._watch_stop = threading.Event()

    def _scan(self):
        files = []
        if not os.path.isdir(KNOWLEDGE_DIR):
            return files
        for root, _dirs, names in os.walk(KNOWLEDGE_DIR):
            for name in names:
                if name.lower().endswith(TEXT_EXTS):
                    files.append(os.path.join(root, name))
        return sorted(files)

    def _signature(self, files):
        sig = {}
        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue
            rel = os.path.relpath(path, KNOWLEDGE_DIR).replace("\\", "/")
            sig[rel] = [int(st.st_mtime), st.st_size]
        return sig

    def _passages_from_file(self, path):
        rel = os.path.relpath(path, KNOWLEDGE_DIR).replace("\\", "/")
        domain = rel.split("/")[0] if "/" in rel else "general"
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        out = []
        title = domain
        for block in re.split(r"\n\s*\n", raw):
            block = block.strip()
            if not block:
                continue
            # Metadato inline: si el bloque empieza con un comentario, extrae
            # la página y elimina el comentario del texto a indexar. Un bloque
            # que es SOLO comentario (formato viejo) no se indexa como pasaje.
            page = None
            m = re.match(r"^<!--(.*?)-->", block, re.DOTALL)
            if m:
                pm = re.search(r"pag:(\d+)", m.group(1))
                if pm:
                    page = int(pm.group(1))
                block = block[m.end():].strip()
                if not block:
                    continue
            lines = [ln for ln in block.splitlines() if ln.strip()]
            if lines and all(ln.lstrip().startswith("#") for ln in lines):
                title = lines[0].lstrip("#").strip() or title
                continue
            clean = re.sub(r"^#+\s*", "", block, flags=re.M).strip()
            if clean:
                p = {"domain": domain, "source": rel, "title": title, "text": clean}
                if page is not None:
                    p["page"] = page
                out.append(p)
        return out

    def build(self):
        files = self._scan()
        passages = []
        for path in files:
            passages.extend(self._passages_from_file(path))
        if len(passages) > self.limits["max_passages"]:
            passages = passages[: self.limits["max_passages"]]

        tokenized = []
        for i, p in enumerate(passages):
            p["id"] = i
            toks = _content_tokens(p["text"], self.stopwords)
            tokenized.append(toks)

        # BM25: calcula IDF y longitud media de documentos
        df = defaultdict(int)
        lengths = []
        for toks in tokenized:
            lengths.append(len(toks))
            for t in set(toks):
                df[t] += 1
        n = max(1, len(passages))
        self.avgdl = (sum(lengths) / n) if lengths else 1.0
        idf = {t: math.log((n - dft + 0.5) / (dft + 0.5) + 1)
               for t, dft in df.items()}

        postings = defaultdict(list)
        for p, toks, dl in zip(passages, tokenized, lengths):
            tf_map = defaultdict(int)
            for t in toks:
                tf_map[t] += 1
            for t, tf in tf_map.items():
                k1, b = BM25_K1, BM25_B
                bm25 = idf[t] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / self.avgdl))
                postings[t].append([p["id"], round(bm25, 6)])

        cap = self.limits["max_postings_per_term"]
        for t, lst in postings.items():
            if len(lst) > cap:
                lst.sort(key=lambda x: x[1], reverse=True)
                postings[t] = lst[:cap]

        domains = defaultdict(int)
        for p in passages:
            domains[p["domain"]] += 1

        self.passages = passages
        self.postings = dict(postings)
        self.idf = idf
        self.domains = dict(domains)
        self.signature = self._signature(files)
        self.built = True

    def save_cache(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(INDEX_CACHE, "w", encoding="utf-8") as f:
                json.dump({
                    "version": INDEX_VERSION,
                    "tier": self.tier,
                    "signature": self.signature,
                    "passages": self.passages,
                    "postings": self.postings,
                    "idf": self.idf,
                    "avgdl": self.avgdl,
                    "domains": self.domains,
                }, f, ensure_ascii=False)
        except OSError:
            pass

    def _load_cache(self):
        if not os.path.exists(INDEX_CACHE):
            return False
        try:
            with open(INDEX_CACHE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        files = self._scan()
        if data.get("version") != INDEX_VERSION:
            return False
        if data.get("tier") != self.tier:
            return False
        if data.get("signature") != self._signature(files):
            return False
        self.passages = data["passages"]
        self.postings = data["postings"]
        self.idf = data["idf"]
        self.avgdl = data.get("avgdl", 1.0)
        self.domains = data.get("domains", {})
        self.signature = data["signature"]
        self.built = True
        return True

    def ensure(self, force=False):
        if self.built and not force:
            return False
        if not force and self._load_cache():
            return False
        self.build()
        self.save_cache()
        return True

    def needs_rebuild(self):
        return self.signature != self._signature(self._scan())

    def start_watcher(self, interval=30):
        """Inicia un hilo que reconstruye el indice si detecta archivos nuevos."""
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._watch_stop.clear()

        def _loop():
            while not self._watch_stop.wait(interval):
                if self.needs_rebuild():
                    try:
                        self.build()
                        self.save_cache()
                    except Exception:
                        pass

        self._watch_thread = threading.Thread(target=_loop, daemon=True,
                                               name="kb-watcher")
        self._watch_thread.start()

    def stop_watcher(self):
        self._watch_stop.set()

    def _score_query(self, tokens):
        scores = defaultdict(float)
        for t in tokens:
            for pid, bw in self.postings.get(t, ()):
                scores[pid] += bw
        return scores

    def search(self, text, top_k=None, include_meta=False):
        if not self.built:
            self.ensure()
        tokens = _expand_query(text, self.stopwords)
        if not tokens:
            return []
        scores = self._score_query(tokens)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        # Excluye dominios meta (green_tail) salvo que se pidan explicitamente.
        if not include_meta:
            ranked = [(pid, sc) for pid, sc in ranked
                      if self.passages[pid]["domain"] not in META_DOMAINS]
        if not ranked:
            return []
        k = top_k or self.limits["top_k"]
        # Normaliza por la puntuacion maxima para obtener un valor 0-1 comparable
        max_score = ranked[0][1]
        out = []
        for pid, sc in ranked[:k]:
            p = self.passages[pid]
            out.append({
                "score": round(sc / max_score, 4),
                "raw_score": round(sc, 4),
                "domain": p["domain"],
                "source": p["source"],
                "title": p["title"],
                "text": p["text"],
                "page": p.get("page"),
            })
        return out

    def related(self, topic, max_terms=8):
        hits = self.search(topic, top_k=min(10, self.limits["top_k"] + 3))
        if not hits:
            return {"topic": topic, "terms": [], "domains": []}
        topic_terms = set(_expand_query(topic, self.stopwords))
        weight = defaultdict(float)
        term_domains = defaultdict(set)
        for h in hits:
            seen = set()
            for t in _content_tokens(h["text"], self.stopwords):
                if t in topic_terms or t not in self.idf or t in seen:
                    continue
                seen.add(t)
                weight[t] += self.idf[t]
                term_domains[t].add(h["domain"])
        ranked = sorted(weight.items(), key=lambda x: x[1], reverse=True)[:max_terms]
        return {
            "topic": topic,
            "domains": sorted({h["domain"] for h in hits}),
            "terms": [{"term": t, "domains": sorted(term_domains[t])} for t, _ in ranked],
        }

    def stats(self):
        return {
            "passages": len(self.passages),
            "terms": len(self.postings),
            "domains": dict(sorted(self.domains.items())),
            "tier": self.tier,
            "built": self.built,
        }

    # ── Autoedicion: clasificacion, ingesta y enriquecimiento ──────────────

    # Umbral de confianza para asignar a un dominio existente. Si la
    # puntuacion maxima es menor, se propone un dominio nuevo.
    DOMAIN_THRESHOLD = 0.08

    def classify_domain(self, text):
        """Clasifica texto en uno de los dominios existentes usando el indice BM25.

        Devuelve:
          {
            "domain":      str  — dominio mas probable o None si es nuevo,
            "confidence":  float 0-1,
            "alternatives": [(domain, score), ...],
            "is_new":      bool — True si no encaja bien en ningun dominio existente,
            "reasoning":   str  — explicacion del razonamiento
          }
        """
        if not self.built:
            self.ensure()

        tokens = _expand_query(text, self.stopwords)
        if not tokens:
            return {"domain": None, "confidence": 0.0, "alternatives": [],
                    "is_new": True, "reasoning": "Texto sin terminos reconocibles."}

        # Suma de puntuaciones BM25 agrupadas por dominio (excluye dominios meta:
        # el contenido nuevo del usuario nunca se clasifica como 'green_tail').
        domain_scores: dict[str, float] = defaultdict(float)
        domain_hits:   dict[str, int]   = defaultdict(int)
        for t in tokens:
            for pid, bw in self.postings.get(t, ()):
                d = self.passages[pid]["domain"]
                if d in META_DOMAINS:
                    continue
                domain_scores[d] += bw
                domain_hits[d]   += 1

        if not domain_scores:
            return {"domain": None, "confidence": 0.0, "alternatives": [],
                    "is_new": True,
                    "reasoning": "Ninguno de los terminos del texto aparece en el indice. "
                                 "El tema no tiene cobertura actual — se recomienda crear un dominio nuevo."}

        # Normaliza por numero de pasajes de cada dominio (evita sesgo hacia
        # dominios con mas contenido) y por total de hits
        ranked = sorted(
            ((d, score / max(1, self.domains.get(d, 1)))
             for d, score in domain_scores.items()),
            key=lambda x: x[1], reverse=True
        )
        top_domain, top_raw = ranked[0]
        max_raw = max(s for _, s in ranked)
        confidence = round(top_raw / max_raw, 3) if max_raw > 0 else 0.0

        # Umbral absoluto: el score debe superar una minima densidad
        density = domain_hits[top_domain] / max(1, len(tokens))
        is_new  = density < self.DOMAIN_THRESHOLD

        alternatives = [(d, round(s / max_raw, 3)) for d, s in ranked[1:4]]

        if is_new:
            reasoning = (
                f"El texto comparte algunos terminos con '{top_domain}' pero la densidad "
                f"de coincidencia ({density:.2f}) es baja. El contenido parece ser sobre "
                f"un tema que no esta bien cubierto por ninguna materia actual. "
                f"Se recomienda crear un dominio nuevo o especificar uno manualmente."
            )
        else:
            alt_str = ", ".join(f"'{d}' ({s:.2f})" for d, s in alternatives[:2])
            reasoning = (
                f"El texto contiene vocabulario consistente con '{top_domain}' "
                f"(densidad de coincidencia: {density:.2f}, confianza relativa: {confidence:.2f}). "
                + (f"Alternativas cercanas: {alt_str}." if alt_str else "")
            )

        return {
            "domain":       top_domain if not is_new else None,
            "confidence":   confidence,
            "alternatives": alternatives,
            "is_new":       is_new,
            "reasoning":    reasoning,
        }

    @staticmethod
    def _slugify(text, max_len=40):
        """Convierte un titulo en nombre de archivo seguro."""
        import unicodedata
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(c for c in text
                       if unicodedata.category(c) != "Mn" and (c.isalnum() or c in " -_"))
        text = re.sub(r"[^a-z0-9]+", "-", text.strip())
        return text[:max_len].strip("-") or "nuevo-tema"

    def _next_file_index(self, domain_dir):
        """Devuelve el siguiente numero de archivo disponible en la carpeta."""
        existing = []
        if os.path.isdir(domain_dir):
            for f in os.listdir(domain_dir):
                m = re.match(r"^(\d+)-", f)
                if m:
                    existing.append(int(m.group(1)))
        return (max(existing) + 1) if existing else 1

    def _format_markdown(self, title, text, sections=None):
        """Formatea texto plano como markdown estructurado.

        Si el texto ya contiene encabezados ## lo respeta.
        Si no, lo divide en parrafos logicos y crea secciones.
        """
        # Ya tiene estructura markdown
        if "##" in text or "# " in text:
            if not text.startswith("#"):
                text = f"# {title}\n\n{text}"
            return text

        # Divide en bloques por parrafo doble o por punto final largo
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        if not blocks:
            return f"# {title}\n\n{text}"

        lines = [f"# {title}", ""]
        for i, block in enumerate(blocks):
            # Si el bloque es corto y parece un titulo, lo convierte en ##
            first_line = block.split("\n")[0]
            if len(first_line) < 80 and not first_line.endswith(".") and len(blocks) > 1:
                lines.append(f"## {first_line}")
                rest = "\n".join(block.split("\n")[1:]).strip()
                if rest:
                    lines.append("")
                    lines.append(rest)
            else:
                if i == 0:
                    lines.append(block)
                else:
                    lines.append(f"## Sección {i+1}")
                    lines.append("")
                    lines.append(block)
            lines.append("")

        return "\n".join(lines)

    def ingest(self, text, title=None, domain=None, force_new_domain=False):
        """Clasifica y guarda nuevo contenido en el archivo correcto.

        Argumentos:
          text             — contenido a guardar
          title            — titulo del tema (opcional, se infiere si no se da)
          domain           — dominio a usar (opcional; si None, se clasifica auto)
          force_new_domain — si True, crea dominio aunque exista uno cercano

        Devuelve:
          {
            "saved":     bool,
            "file":      str  — ruta relativa del archivo escrito,
            "domain":    str  — dominio asignado,
            "is_new_domain": bool,
            "classification": dict — resultado completo de classify_domain,
            "message":   str
          }
        """
        if not text or not text.strip():
            return {"saved": False, "message": "Texto vacio."}

        text = text.strip()

        # Inferir titulo si no se dio
        if not title:
            first_line = text.split("\n")[0].lstrip("#").strip()
            title = first_line[:60] if first_line else "Sin titulo"

        # Clasificar dominio
        classification = self.classify_domain(text)
        is_new_domain  = False

        if domain:
            # El usuario especifico dominio — respetarlo
            assigned_domain = self._slugify(domain, max_len=30)
        elif force_new_domain or classification["is_new"]:
            # Crear dominio nuevo: usa la primera palabra significativa del titulo
            # (max 20 chars) para que el nombre de carpeta sea limpio y legible.
            first_word = re.split(r"[\s\-_]+", title.strip())[0]
            assigned_domain = self._slugify(first_word, max_len=20) or self._slugify(title, max_len=20)
            is_new_domain   = True
        else:
            assigned_domain = classification["domain"]

        # Carpeta del dominio
        domain_dir = os.path.join(KNOWLEDGE_DIR, assigned_domain)
        os.makedirs(domain_dir, exist_ok=True)

        # Numero y nombre del archivo
        idx      = self._next_file_index(domain_dir)
        slug     = self._slugify(title)
        filename = f"{idx:02d}-{slug}.md"
        filepath = os.path.join(domain_dir, filename)

        # Formatear y escribir
        content = self._format_markdown(title, text)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        # Reconstruir indice inmediatamente
        self.build()
        self.save_cache()

        rel = os.path.relpath(filepath, KNOWLEDGE_DIR).replace("\\", "/")
        return {
            "saved":          True,
            "file":           rel,
            "domain":         assigned_domain,
            "is_new_domain":  is_new_domain,
            "classification": classification,
            "message":        (
                f"Guardado en knowledge/{rel}. "
                f"Dominio: '{assigned_domain}'"
                + (" (nuevo)" if is_new_domain else " (existente)")
                + f". Indice reconstruido: {len(self.passages)} pasajes."
            ),
        }

    def enrich_file(self, source_rel, additional_text, section_title=None):
        """Añade contenido a un archivo existente del indice.

        source_rel  — ruta relativa al archivo (como aparece en 'source' de los hits)
        additional_text — texto a añadir
        section_title   — titulo de la nueva seccion (## ); si None se genera automatico
        """
        filepath = os.path.join(KNOWLEDGE_DIR, source_rel.replace("/", os.sep))
        if not os.path.isfile(filepath):
            return {"saved": False, "message": f"Archivo no encontrado: {source_rel}"}

        with open(filepath, encoding="utf-8") as f:
            existing = f.read()

        if not section_title:
            # Contar secciones actuales para numerar la nueva
            n_sections = len(re.findall(r"^##\s", existing, re.M))
            section_title = f"Ampliación {n_sections + 1}"

        addition = f"\n\n## {section_title}\n\n{additional_text.strip()}\n"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(addition)

        self.build()
        self.save_cache()

        return {
            "saved":   True,
            "file":    source_rel,
            "message": f"Seccion '{section_title}' añadida a {source_rel}. "
                       f"Indice reconstruido: {len(self.passages)} pasajes.",
        }

    def enrich_by_query(self, query, additional_text, section_title=None):
        """Busca el pasaje mas relevante para 'query' y le añade contenido."""
        hits = self.search(query, top_k=1)
        if not hits or hits[0]["score"] < 0.1:
            return {"saved": False,
                    "message": "No encontre un pasaje existente suficientemente relevante. "
                               "Usa ingest() para crear contenido nuevo sobre este tema."}
        return self.enrich_file(hits[0]["source"], additional_text, section_title)

    def list_files(self):
        """Lista todos los archivos indexados con su dominio y numero de pasajes."""
        from collections import Counter
        counts = Counter(p["source"] for p in self.passages)
        result = []
        for path in self._scan():
            rel = os.path.relpath(path, KNOWLEDGE_DIR).replace("\\", "/")
            domain = rel.split("/")[0] if "/" in rel else "general"
            result.append({
                "file":     rel,
                "domain":   domain,
                "passages": counts.get(rel, 0),
                "size_kb":  round(os.path.getsize(path) / 1024, 1),
            })
        return result
