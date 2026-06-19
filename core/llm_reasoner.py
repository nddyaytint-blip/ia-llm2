"""Razonador LLM con RAG: usa BM25 para recuperar contexto y LLM para generar respuesta.

Flujo:
  1. BM25 recupera los N pasajes más relevantes de knowledge/
  2. Se construye un prompt con: instrucción de sistema + pasajes + pregunta
  3. El LLM genera una respuesta fundamentada en esos pasajes
  4. Si el LLM no está disponible, delega al Reasoner BM25 original

El sistema conserva memoria de conversación (10 turnos, persistente) y
defiende sus respuestas con la misma lógica que el Reasoner base.
"""

import re
import time
from collections import deque

from core.llm_client import LLMClient
from core.storage import (
    save_conversation, load_conversation, append_knowledge_gap,
    append_improvement,
)

# Turnos de contexto conversacional que se pasan al LLM
MEMORY_TURNS = 10

# Máximo de pasajes BM25 que se incluyen en el prompt de contexto
MAX_CONTEXT_PASSAGES = 5

# Longitud máxima de cada pasaje incluido en el prompt (caracteres)
MAX_PASSAGE_CHARS = 600

# Umbral de score BM25 para incluir pasaje en el prompt
MIN_PASSAGE_SCORE = 0.05

SYSTEM_PROMPT_ES = """Eres Green Tail, un asistente de conocimiento bilingüe (español/inglés).
Respondes ÚNICAMENTE basándote en los pasajes de conocimiento que se te proporcionan.
Si la información no está en los pasajes, lo dices claramente.
Respondes en el mismo idioma en que te preguntan.
Eres preciso, conciso y citas la fuente cuando es relevante.
No inventas información que no esté en los pasajes."""

SYSTEM_PROMPT_EN = """You are Green Tail, a bilingual (Spanish/English) knowledge assistant.
You answer ONLY based on the knowledge passages provided to you.
If the information is not in the passages, you say so clearly.
You respond in the same language as the question.
You are precise, concise, and cite the source when relevant.
You do not invent information not found in the passages."""

CHALLENGE_PATTERNS = re.compile(
    r"(no es así|no es correcto|estás mal|eso está mal|te equivocas|"
    r"incorrecto|mentira|falso|eso no es|"
    r"that's wrong|you're wrong|incorrect|not right|that is false)",
    re.IGNORECASE,
)


def _build_context_block(hits: list, lang: str) -> str:
    """Convierte los hits BM25 en un bloque de texto para el prompt."""
    if not hits:
        return ""

    label_es = "Pasajes de conocimiento relevantes"
    label_en = "Relevant knowledge passages"
    label = label_es if lang == "es" else label_en

    lines = [f"=== {label} ==="]
    for i, h in enumerate(hits[:MAX_CONTEXT_PASSAGES], 1):
        if h["score"] < MIN_PASSAGE_SCORE:
            break
        text  = h["text"][:MAX_PASSAGE_CHARS]
        src   = h.get("source", "")
        lines.append(f"\n[{i}] Fuente: {src}\n{text}")

    lines.append("=" * 40)
    return "\n".join(lines)


def _build_history_block(memory: deque, lang: str) -> str:
    """Convierte los últimos turnos de memoria en historial para el prompt."""
    if not memory:
        return ""
    label = "Historial reciente" if lang == "es" else "Recent history"
    lines = [f"--- {label} ---"]
    for turn in list(memory)[-4:]:  # últimos 4 para no saturar el contexto
        q = turn.get("query", "")[:120]
        r = turn.get("reply",  "")[:200]
        lines.append(f"Usuario: {q}")
        lines.append(f"Asistente: {r}")
    lines.append("-" * 30)
    return "\n".join(lines)


class LLMReasoner:
    """Razonador que combina BM25 (recuperación) con LLM (generación).

    Compatible con la misma interfaz que Reasoner para que engine.py
    pueda usarlos de forma intercambiable.
    """

    def __init__(self, kb, session_id: str = "default"):
        self.kb         = kb
        self.session_id = session_id
        self.last       = None
        self._memory: deque = deque(maxlen=MEMORY_TURNS)
        self._client    = LLMClient.from_config()
        self._load_memory()

    # ------------------------------------------------------------------
    # Compatibilidad con engine.py
    # ------------------------------------------------------------------

    def set_session(self, session_id: str):
        if session_id != self.session_id:
            self.session_id = session_id
            self._memory.clear()
            self._load_memory()

    def memory_summary(self) -> list:
        return list(self._memory)

    def is_question(self, text: str) -> bool:
        toks = text.split()
        starts = {"qué","que","cómo","como","cuál","cual","cuándo","cuando",
                  "dónde","donde","quién","quien","por","para","es","son",
                  "what","how","which","when","where","who","why","is","are","can"}
        return "?" in text or "¿" in text or (bool(toks) and toks[0].lower() in starts)

    def is_challenge(self, text: str) -> bool:
        return bool(CHALLENGE_PATTERNS.search(text))

    # ------------------------------------------------------------------
    # Memoria persistente
    # ------------------------------------------------------------------

    def _load_memory(self):
        for turn in load_conversation(self.session_id)[-MEMORY_TURNS:]:
            self._memory.append(turn)

    def _save_memory(self):
        save_conversation(self.session_id, list(self._memory))

    def _store_turn(self, query: str, reply: str, lang: str,
                    domains: list, confidence: float = 0.0):
        self._memory.append({
            "query":      query,
            "reply":      reply[:200],
            "lang":       lang,
            "domains":    domains,
            "confidence": confidence,
        })
        self._save_memory()

    # ------------------------------------------------------------------
    # Respuesta principal
    # ------------------------------------------------------------------

    def answer(self, text: str, lang: str, verbosity: str = "normal") -> dict:
        """Genera respuesta usando RAG (BM25 + LLM) o solo BM25 si no hay LLM."""

        # 1. Recuperar pasajes BM25
        hits = self.kb.search(text)
        conf = hits[0]["score"] if hits else 0.0

        self.last = {"query": text, "hits": hits, "confidence": conf,
                     "lang": lang, "reply": ""}

        # 2. Sin LLM → respuesta BM25 directa (fallback)
        if not self._client:
            return self._fallback_bm25(text, hits, lang, conf)

        # 3. Con LLM → RAG
        return self._rag_answer(text, hits, lang, conf)

    def _rag_answer(self, text: str, hits: list, lang: str, conf: float) -> dict:
        """Genera respuesta con LLM usando los pasajes BM25 como contexto."""

        sys_prompt  = SYSTEM_PROMPT_ES if lang == "es" else SYSTEM_PROMPT_EN
        ctx_block   = _build_context_block(hits, lang)
        hist_block  = _build_history_block(self._memory, lang)

        if ctx_block:
            prompt = f"{sys_prompt}\n\n{hist_block}\n\n{ctx_block}\n\nPregunta: {text}"
        else:
            no_ctx = ("No tengo pasajes relevantes en mi base de conocimiento para esta pregunta. "
                      if lang == "es" else
                      "I have no relevant passages in my knowledge base for this question. ")
            prompt = f"{sys_prompt}\n\n{hist_block}\n\nNota: {no_ctx}\n\nPregunta: {text}"

        try:
            t0    = time.time()
            reply = self._client.chat(prompt)
            ms    = round((time.time() - t0) * 1000)
        except Exception as e:
            return self._fallback_bm25(
                text, hits, lang, conf,
                note=f"LLM error ({e}) — respuesta BM25"
            )

        sources  = list({h["source"] for h in hits[:MAX_CONTEXT_PASSAGES] if h.get("source")})
        domains  = list({h.get("domain", "") for h in hits if h.get("domain")})

        self.last["reply"] = reply[:200]
        self._store_turn(text, reply, lang, domains, confidence=conf)

        return {
            "mode":       "llm_rag",
            "backend":    self._client.backend_name,
            "model":      self._client.model,
            "reply":      reply,
            "score":      round(conf, 3),
            "confidence": self._confidence_label(conf, lang),
            "sources":    sources,
            "connections":domains,
            "latency_ms": ms,
        }

    def _fallback_bm25(self, text: str, hits: list, lang: str,
                        conf: float, note: str = "") -> dict:
        """Respuesta BM25 pura cuando el LLM no está disponible."""
        if not hits or conf < 0.05:
            msg = ("No tengo información suficiente sobre eso en mi base de conocimiento."
                   if lang == "es" else
                   "I don't have enough information about that in my knowledge base.")
            return {"mode": "bm25_fallback", "reply": msg, "score": 0.0,
                    "confidence": "baja" if lang == "es" else "low",
                    "sources": [], "connections": []}

        top    = hits[0]
        frag   = top["text"][:400].rstrip()
        source = top.get("source", "")
        prefix = f"[{note}] " if note else ""

        if lang == "es":
            reply = f"{prefix}Según {source}:\n\n{frag}"
        else:
            reply = f'{prefix}According to {source}:\n\n{frag}'

        domains = list({h.get("domain","") for h in hits[:3] if h.get("domain")})
        self._store_turn(text, reply, lang, domains, confidence=conf)
        self.last["reply"] = reply[:200]

        return {"mode": "bm25_fallback", "reply": reply, "score": round(conf, 3),
                "confidence": self._confidence_label(conf, lang),
                "sources": [source], "connections": domains}

    # ------------------------------------------------------------------
    # Debate / defensa
    # ------------------------------------------------------------------

    def debate(self, text: str, lang: str) -> dict:
        """Cuando el usuario objeta, re-verifica y defiende o corrige."""
        if not self.last or self.last.get("confidence", 0) <= 0.0:
            msg = ("No tengo una afirmación previa con evidencia que defender."
                   if lang == "es" else
                   "I don't have a previous evidence-backed claim to defend.")
            return {"mode": "debate", "reply": msg, "score": 0.0,
                    "confidence": self._confidence_label(0.0, lang),
                    "sources": [], "connections": []}

        prev_query = self.last["query"]
        prev_conf  = self.last.get("confidence", 0)
        prev_reply = self.last.get("reply", "")
        pct        = round(prev_conf * 100)

        # Re-buscar para verificar
        fresh_hits   = self.kb.search(prev_query)
        fresh_conf   = fresh_hits[0]["score"] if fresh_hits else 0.0

        if self._client and fresh_hits and fresh_conf >= 0.15:
            # Pedir al LLM que evalúe si la objeción es válida
            sys_p = SYSTEM_PROMPT_ES if lang == "es" else SYSTEM_PROMPT_EN
            ctx   = _build_context_block(fresh_hits, lang)
            if lang == "es":
                debate_prompt = (
                    f"{sys_p}\n\n{ctx}\n\n"
                    f"Mi respuesta anterior fue: «{prev_reply[:300]}»\n"
                    f"El usuario objeta: «{text}»\n\n"
                    f"Analiza si la objeción es correcta según los pasajes. "
                    f"Si mi respuesta era correcta, defiéndela citando la fuente. "
                    f"Si había un error, corrígelo claramente."
                )
            else:
                debate_prompt = (
                    f"{sys_p}\n\n{ctx}\n\n"
                    f"My previous answer was: «{prev_reply[:300]}»\n"
                    f"The user objects: «{text}»\n\n"
                    f"Analyze whether the objection is correct according to the passages. "
                    f"If my answer was correct, defend it citing the source. "
                    f"If there was an error, correct it clearly."
                )
            try:
                reply = self._client.chat(debate_prompt)
                sources = [h.get("source","") for h in fresh_hits[:3] if h.get("source")]
                return {"mode": "debate", "stance": "llm_eval", "reply": reply,
                        "score": round(fresh_conf, 3),
                        "confidence": self._confidence_label(fresh_conf, lang),
                        "sources": sources, "connections": []}
            except Exception:
                pass  # si falla el LLM, caer en lógica BM25

        # Fallback: lógica BM25 de defensa
        if fresh_conf >= 0.30 and fresh_hits:
            top  = fresh_hits[0]
            frag = top["text"][:240]
            if lang == "es":
                reply = (f"He re-verificado y mantengo mi posición (confianza {pct}%). "
                         f"Según {top['source']}: «{frag}»\n\n"
                         f"Si tienes una fuente que lo contradiga, agrégala a knowledge/.")
            else:
                reply = (f"I've re-verified and stand by my position (confidence {pct}%). "
                         f"According to {top['source']}: \"{frag}\"\n\n"
                         f"If you have a contradicting source, add it to knowledge/.")
            return {"mode": "debate", "stance": "defiende", "reply": reply,
                    "score": round(fresh_conf, 3),
                    "confidence": self._confidence_label(fresh_conf, lang),
                    "sources": [top.get("source","")], "connections": []}

        # Ceder
        append_knowledge_gap(prev_query, f"objeción usuario; conf {pct}%")
        append_improvement(f"Cedido tras objeción: '{prev_query}' (conf {pct}%)")
        msg = (f"Puede que tengas razón. Mi evidencia era débil ({pct}%). "
               f"He marcado el tema para expandir mi conocimiento."
               if lang == "es" else
               f"You may be right. My evidence was weak ({pct}%). "
               f"I've flagged this topic to expand my knowledge.")
        return {"mode": "debate", "stance": "cede", "reply": msg,
                "score": round(prev_conf, 3),
                "confidence": self._confidence_label(prev_conf, lang),
                "sources": [], "connections": []}

    # ------------------------------------------------------------------
    # Info del backend activo
    # ------------------------------------------------------------------

    def llm_info(self) -> dict:
        if self._client:
            return {
                "available": True,
                "backend":   self._client.backend_name,
                "model":     self._client.model,
            }
        return {"available": False, "backend": None, "model": None}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _confidence_label(self, score: float, lang: str) -> str:
        if score >= 0.5:
            return "alta"  if lang == "es" else "high"
        if score >= 0.2:
            return "media" if lang == "es" else "medium"
        return "baja" if lang == "es" else "low"
