import time
from collections import Counter, deque

from core import resources, storage, self_improve, responder, knowledge, code_tools
from core.nlu import NLU
from core.reasoning import Reasoner
from core.llm_reasoner import LLMReasoner
from core.background_indexer import BackgroundIndexer
from core.file_watcher import FileWatcher
from core.self_analyst import SelfAnalyst
from core import user_manager

# Intenciones que disparan una accion concreta del motor (no charla).
COMMAND_INTENTS = {"sugerencias", "hardware"}

# Cuantos idiomas recientes se recuerdan para decidir el idioma de respuesta.
LANG_MEMORY = 6


class Engine:
    """Nucleo compartido por la CLI y el servicio en segundo plano.

    Usa LLMReasoner (BM25 + LLM) si hay un backend LLM disponible.
    Si no hay LLM, cae en el Reasoner BM25 puro original.
    """

    def __init__(self):
        self.snap = resources.snapshot()
        self.config = storage.load_config()
        tier = resources.tier_for(self.snap)
        if self.config.get("tier") != tier:
            self.config.update(resources.TIER_PROFILES[tier])
            self.config["tier"] = tier
            storage.save_config(self.config)
            storage.append_improvement(
                f"Perfil de recursos ajustado a '{tier}' segun hardware detectado: "
                f"{self.snap['cpu_cores']} nucleos, {self.snap['ram_total_mb']}MB RAM total."
            )
        self.nlu = NLU()
        self.nlu.load_learned(storage.load_learned_vocab())

        self.kb = knowledge.KnowledgeBase(tier=tier)
        if self.kb.ensure():
            st = self.kb.stats()
            storage.append_improvement(
                f"Indice de conocimiento construido: {st['passages']} pasajes en "
                f"{len(st['domains'])} materias (perfil '{tier}')."
            )

        # Intentar LLMReasoner primero; si no hay LLM, usar Reasoner BM25
        llm_candidate = LLMReasoner(self.kb, session_id="default")
        if llm_candidate.llm_info()["available"]:
            self.reasoner = llm_candidate
            info = llm_candidate.llm_info()
            storage.append_improvement(
                f"LLM activo: backend={info['backend']}, modelo={info['model']}"
            )
        else:
            self.reasoner = Reasoner(self.kb, session_id="default")
            storage.append_improvement("LLM no disponible — usando razonador BM25.")

        self._using_llm = isinstance(self.reasoner, LLMReasoner)
        self.interaction_count = 0
        # Historial de idiomas claros de la conversacion (para responder en el
        # idioma principal o el ultimo cuando un mensaje sea ambiguo).
        self._lang_history = deque(maxlen=LANG_MEMORY)

        # Monitor de cambios: detecta archivos nuevos y reconstruye el índice (30s)
        self.indexer = BackgroundIndexer(kb=self.kb, check_interval=30)
        self.indexer.start()

        # Monitor de ingestión: detecta archivos en imports/ y los procesa automáticamente (10s)
        self.file_watcher = FileWatcher(kb=self.kb, check_interval=10)
        self.file_watcher.start()

        # Analizador autónomo: revisa documentos + código y repara errores (5 min)
        self.analyst = SelfAnalyst(kb=self.kb, check_interval=300)
        self.analyst.start()

    def refresh_resources(self):
        self.snap = resources.snapshot()
        return self.snap

    def status(self):
        llm_info = (self.reasoner.llm_info()
                    if hasattr(self.reasoner, "llm_info") else
                    {"available": False, "backend": None, "model": None})
        return dict(self.snap, **{
            "tier": self.config["tier"],
            "max_threads": self.config["max_threads"],
            "history_size": self.config["history_size"],
            "cache_size": self.config["cache_size"],
            "llm": llm_info,
        })

    def suggestions(self):
        return self_improve.current_suggestions(self.snap, self.config, self.kb)

    def hardware_needs(self):
        return resources.recommend_hardware(self.snap)

    # ── Análisis autónomo ──────────────────────────────────────────────
    def analysis_report(self) -> dict:
        """Devuelve el último informe del analizador autónomo."""
        return self.analyst.get_report()

    def run_analysis_now(self) -> dict:
        """Ejecuta un ciclo de análisis completo de forma inmediata."""
        return self.analyst.run_now()

    # ── Métodos de usuario (perfiles locales) ──────────────────────────
    def register_user(self, username, password):
        """Crea un nuevo perfil de usuario."""
        return user_manager.create_user(username, password)

    def login_user(self, username, password):
        """Autentica un usuario."""
        return user_manager.login(username, password)

    def list_users(self):
        """Lista todos los perfiles."""
        return user_manager.list_users()

    def get_user_folder(self, username):
        """Obtiene la carpeta del usuario."""
        return user_manager.get_user_folder(username)

    def delete_user(self, username, password):
        """Elimina un perfil (requiere contraseña)."""
        return user_manager.delete_user(username, password)

    def knowledge_stats(self):
        return self.kb.stats()

    def connections(self, topic):
        return self.kb.related(topic)

    # ── Ingestión de documentos ────────────────────────────────────────
    def import_document(self, file_path, category=None):
        """Importa un documento manualmente (API)."""
        result = self.file_watcher.importer.import_file(
            file_path, target_category=category,
            document_classifier=self.file_watcher.classifier
        )
        if result and result.get("chunks"):
            category = result.get("category", "general")
            self.file_watcher._process_file(file_path)
        return result

    def import_directory(self):
        """Procesa todos los documentos en imports/ (batch inicial)."""
        return self.file_watcher.process_directory()

    def get_import_status(self):
        """Obtiene el estado de la ingestión de documentos."""
        return {
            "file_watcher": self.file_watcher.get_stats(),
            "imported": self.file_watcher.importer.get_import_status(),
        }

    def classify_text(self, text):
        """Clasifica un texto para determinar su categoría."""
        return self.file_watcher.classifier.classify(text)

    def suggest_categories(self, text):
        """Devuelve las categorías más probables para un texto."""
        return self.file_watcher.classifier.suggest_categories(text)

    # ── Capacidades de codigo ──────────────────────────────────────────────
    def analyze_code(self, code, filename=None, language=None):
        return code_tools.analyze(code, filename=filename, language=language)

    def generate_code(self, request, lang="es"):
        return code_tools.generate(request, lang=lang)

    def save_code(self, code, filename, directory=None):
        return code_tools.save_code(code, filename, directory=directory)

    def _code_analysis_result(self, code, lang):
        """Formatea un analisis de codigo como respuesta de chat."""
        a = self.analyze_code(code)
        lines = [a["summary"], ""]
        if a.get("structure", {}).get("funciones") or a.get("structure", {}).get("clases"):
            st = a["structure"]
            if st.get("funciones"):
                lines.append(f"**Funciones:** {', '.join(st['funciones'])}")
            if st.get("clases"):
                lines.append(f"**Clases:** {', '.join(st['clases'])}")
            lines.append("")
        if a["issues"]:
            lines.append("**Problemas detectados:**")
            for i in a["issues"]:
                sev = {"error": "🔴", "warning": "🟠", "info": "🔵"}.get(i["severity"], "•")
                lines.append(f"{sev} L{i['line']}: {i['message']}")
                lines.append(f"   → {i['suggestion']}")
            lines.append("")
        if a["suggestions"]:
            lines.append("**Sugerencias de mejora:**")
            for s in a["suggestions"][:6]:
                lines.append(f"• L{s['line']}: {s['message']} → {s['suggestion']}")
        if not a["issues"] and not a["suggestions"]:
            lines.append("✓ No detecté problemas. El código se ve correcto y limpio.")
        return {
            "mode": "code", "intent": "code_analysis",
            "reply": "\n".join(lines).strip(),
            "score": 1.0, "confidence": "alta" if lang == "es" else "high",
            "sources": [], "connections": ["programacion"],
            "code_analysis": a,
        }

    def _code_generation_result(self, request, lang):
        """Formatea codigo generado como respuesta de chat."""
        g = self.generate_code(request, lang=lang)
        if g["found"]:
            reply = (f"**{g['title']}**\n\n```python\n{g['code']}\n```\n\n{g['explanation']}")
        else:
            reply = g["explanation"]
        return {
            "mode": "code", "intent": "code_generation",
            "reply": reply,
            "score": 1.0 if g["found"] else 0.3,
            "confidence": ("alta" if g["found"] else "baja") if lang == "es"
                          else ("high" if g["found"] else "low"),
            "sources": [], "connections": ["programacion"],
            "code_generated": g,
        }

    def _self_facts(self):
        """Datos en vivo del sistema para responder preguntas sobre si misma."""
        st = self.kb.stats()
        return {
            "passages": st["passages"],
            "domains":  len(st["domains"]),
            "tier":     self.config.get("tier", "?"),
            "cores":    self.snap.get("cpu_cores", "?"),
            "ram_mb":   self.snap.get("ram_total_mb", "?"),
            "k1":       knowledge.BM25_K1,
            "b":        knowledge.BM25_B,
        }

    def reload_knowledge(self):
        rebuilt = self.kb.ensure(force=True)
        if rebuilt:
            st = self.kb.stats()
            storage.append_improvement(
                f"Indice de conocimiento recargado por peticion: {st['passages']} pasajes."
            )
        return self.kb.stats()

    def _route(self, text, lang):
        r = self.reasoner

        # 1. Debate / autocritica sobre la respuesta anterior.
        if r.is_challenge(text):
            return r.debate(text, lang)
        if r.is_explain_request(text) and r.last:
            return r.explain(text, lang)

        # 1b. Pregunta sobre el propio funcionamiento (auto-introspeccion).
        if r.is_self_question(text):
            self.nlu.expand_vocab(text, lang)
            return r.self_explain(text, lang, facts=self._self_facts())

        # 1c. Peticiones de codigo: analizar/corregir o generar.
        action, payload = code_tools.classify_code_request(text)
        if action == "analyze":
            return self._code_analysis_result(payload, lang)
        if action == "generate":
            return self._code_generation_result(payload, lang)

        # 2. Comandos del sistema (sugerencias / hardware). Solo se disparan
        #    con una coincidencia solida del clasificador, para que consultas
        #    de contenido como "sistema social" no caigan aqui por una palabra.
        intent, score = self.nlu.classify(
            text, lang, min_score=self.config["min_intent_score"]
        )
        if intent in COMMAND_INTENTS and score >= 0.5:
            if intent == "sugerencias":
                extra = self.suggestions()
                reply = ("He analizado mi estado actual y el hardware disponible. "
                         "Aqui esta mi evaluacion razonada:" if lang == "es" else
                         "I have analyzed my current state and available hardware. "
                         "Here is my reasoned evaluation:")
            else:
                extra = self.hardware_needs()
                reply = responder.respond(self.nlu, intent, lang)
            self.nlu.expand_vocab(text, lang)
            return {"mode": "command", "intent": intent, "score": round(score, 3),
                    "reply": reply, "extra": extra}

        # 3. Charla social CLARA (saludo, agradecimiento…): solo con match fuerte,
        #    para no robar consultas de contenido que coinciden debilmente.
        if intent is not None and intent not in COMMAND_INTENTS and score >= 0.5:
            reply = responder.respond(self.nlu, intent, lang)
            self.nlu.expand_vocab(text, lang)
            return {"mode": "smalltalk", "intent": intent, "score": round(score, 3),
                    "reply": reply}

        # 4. El conocimiento tiene prioridad: cualquier consulta con contenido
        #    se intenta responder o clarificar.
        kb = r.answer(text, lang, verbosity=self.config.get("verbosity", "normal"))
        if kb.get("mode") == "clarify" or kb["score"] > 0:
            self.nlu.expand_vocab(text, lang)
            kb["intent"] = kb["mode"]
            return kb

        # 5. El conocimiento no encontro nada. Si el mensaje es breve y social
        #    (p.ej. "ok", "vale"), se responde como charla; pero si tiene
        #    contenido real (una pregunta sobre algo que no cubro), se reconoce
        #    honestamente que no lo sé en lugar de soltar una frase de charla.
        if intent is not None and len(text.split()) <= 3:
            reply = responder.respond(self.nlu, intent, lang)
            self.nlu.expand_vocab(text, lang)
            return {"mode": "smalltalk", "intent": intent, "score": round(score, 3),
                    "reply": reply}
        kb["intent"] = kb["mode"]
        return kb

    def _resolve_language(self, text):
        """Decide el idioma de respuesta combinando la deteccion del mensaje
        con el idioma principal/ultimo de la conversacion.

        - Si el mensaje es claro (margen amplio), se usa ese idioma y se
          registra en el historial.
        - Si es ambiguo (mezcla o sin senal), se responde en el idioma
          dominante de la conversacion; en empate, el ultimo usado.
        """
        lang, es, en = self.nlu.detect_language_scored(text)
        total = es + en
        margin = abs(es - en)
        decisive = total >= 2 and margin >= 2

        if decisive:
            self._lang_history.append(lang)
            return lang

        if not self._lang_history:
            self._lang_history.append(lang)
            return lang

        # Ambiguo: idioma dominante de la conversacion (desempate: el ultimo).
        counts = Counter(self._lang_history)
        top = counts.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            resolved = self._lang_history[-1]
        else:
            resolved = top[0][0]
        self._lang_history.append(resolved)
        return resolved

    def handle(self, text):
        """Procesa una solicitud y devuelve un dict con la respuesta y metadatos."""
        start = time.perf_counter()
        lang = self._resolve_language(text)

        result = self._route(text, lang)

        latency_ms = (time.perf_counter() - start) * 1000
        result["lang"] = lang
        result["latency_ms"] = round(latency_ms, 2)
        for key in ("extra", "sources", "connections", "confidence"):
            result.setdefault(key, None)
        result.setdefault("intent", result.get("mode"))
        result.setdefault("score", 0.0)

        storage.append_usage({
            "text": text,
            "lang": lang,
            "intent": result.get("intent"),
            "mode": result.get("mode"),
            "score": result.get("score"),
            "latency_ms": result["latency_ms"],
        })

        self.interaction_count += 1
        self.config = self_improve.maybe_tune(
            self.config, self.snap, self.interaction_count
        )

        if self.nlu.dirty:
            storage.save_learned_vocab(self.nlu.learned_snapshot())
            self.nlu.mark_saved()

        return result
