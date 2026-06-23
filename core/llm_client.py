"""Cliente LLM unificado: soporta Ollama (offline), OpenAI y Anthropic.

Prioridad automática:
  1. Ollama  — local, offline, sin API key (requiere Ollama instalado)
  2. OpenAI  — requiere OPENAI_API_KEY en config_llm.json
  3. Anthropic — requiere ANTHROPIC_API_KEY en config_llm.json
  4. None    — sin LLM disponible (el sistema cae en BM25 puro)

Uso:
    client = LLMClient.from_config()
    reply  = client.chat("¿Qué es la fotosíntesis?", context="...pasajes BM25...")
"""

import json
import os
import urllib.request
import urllib.error

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLM_CFG_PATH = os.path.join(BASE_DIR, "config_llm.json")

DEFAULT_CFG = {
    "backend":          "auto",        # auto | ollama | openai | anthropic | none
    "ollama_url":       "http://localhost:11434",
    "ollama_model":     "qwen2.5:1.5b",  # modelo ligero recomendado al tester
    "openai_model":     "gpt-4o-mini",
    "anthropic_model":  "claude-haiku-4-5-20251001",
    "openai_api_key":   "",
    "anthropic_api_key":"",
    "max_tokens":       512,
    "temperature":      0.3,
    "timeout":          120,             # arranque en frío de qwen2.5 ~20-25s
}


def load_llm_config() -> dict:
    if not os.path.exists(LLM_CFG_PATH):
        _save_llm_config(DEFAULT_CFG)
        return dict(DEFAULT_CFG)
    with open(LLM_CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CFG)
    merged.update(cfg)
    return merged


def _save_llm_config(cfg: dict):
    with open(LLM_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class _OllamaBackend:
    name = "ollama"

    def __init__(self, cfg: dict):
        self.base_url   = cfg["ollama_url"].rstrip("/")
        self.model      = cfg["ollama_model"]
        self.max_tokens = cfg["max_tokens"]
        self.temp       = cfg["temperature"]
        self.timeout    = cfg["timeout"]

    def is_available(self) -> bool:
        """Disponible = Ollama responde Y el modelo configurado está descargado.

        Comprobar solo que Ollama responda no basta: si el modelo no está
        bajado, cada chat() devuelve 404 y el sistema cae a BM25 en silencio,
        diciendo "LLM activo" cuando no lo está. Aquí verificamos el modelo.
        """
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
        except Exception:
            return False
        names = [m.get("name", "") for m in data.get("models", [])]
        base  = self.model.split(":")[0]
        return any(n == self.model or n.startswith(base + ":") for n in names)

    def chat(self, prompt: str) -> str:
        payload = json.dumps({
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temp,
            },
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())
        return data.get("response", "").strip()


class _OpenAIBackend:
    name = "openai"

    def __init__(self, cfg: dict):
        self.api_key    = cfg.get("openai_api_key", "")
        self.model      = cfg["openai_model"]
        self.max_tokens = cfg["max_tokens"]
        self.temp       = cfg["temperature"]
        self.timeout    = cfg["timeout"]
        self._client    = None   # se crea una sola vez (lazy) en chat()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, prompt: str) -> str:
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise RuntimeError("openai no instalado — ejecuta: pip install openai")
            # Reutiliza el pool de conexiones HTTP entre llamadas.
            self._client = openai.OpenAI(api_key=self.api_key)
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.max_tokens,
            temperature=self.temp,
        )
        return resp.choices[0].message.content.strip()


class _AnthropicBackend:
    name = "anthropic"

    def __init__(self, cfg: dict):
        self.api_key    = cfg.get("anthropic_api_key", "")
        self.model      = cfg["anthropic_model"]
        self.max_tokens = cfg["max_tokens"]
        self.temp       = cfg["temperature"]
        self.timeout    = cfg["timeout"]

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, prompt: str) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            msg = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temp,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except ImportError:
            raise RuntimeError("anthropic no instalado — ejecuta: pip install anthropic")


# ---------------------------------------------------------------------------
# Cliente unificado
# ---------------------------------------------------------------------------

class LLMClient:
    """Interfaz única para todos los backends LLM."""

    def __init__(self, backend, cfg: dict):
        self._backend = backend
        self._cfg     = cfg

    @classmethod
    def from_config(cls) -> "LLMClient | None":
        """Devuelve un LLMClient listo, o None si ningún backend está disponible."""
        cfg     = load_llm_config()
        chosen  = cfg.get("backend", "auto").lower()

        candidates = []
        if chosen == "auto":
            candidates = [
                _OllamaBackend(cfg),
                _OpenAIBackend(cfg),
                _AnthropicBackend(cfg),
            ]
        elif chosen == "ollama":
            candidates = [_OllamaBackend(cfg)]
        elif chosen == "openai":
            candidates = [_OpenAIBackend(cfg)]
        elif chosen == "anthropic":
            candidates = [_AnthropicBackend(cfg)]
        else:
            return None

        for b in candidates:
            if b.is_available():
                return cls(b, cfg)

        return None

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def model(self) -> str:
        return getattr(self._backend, "model", "?")

    def chat(self, prompt: str) -> str:
        return self._backend.chat(prompt)

    def is_available(self) -> bool:
        return self._backend.is_available()
