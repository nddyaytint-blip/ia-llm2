import json
import re
import os
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def tokenize(text):
    text = _strip_accents(text.lower())
    return re.findall(r"[a-z0-9']+", text)


def _load_stopwords(lang):
    path = os.path.join(DATA_DIR, f"stopwords_{lang}.txt")
    with open(path, encoding="utf-8") as f:
        return set(f.read().split())


class NLU:
    def __init__(self):
        with open(os.path.join(DATA_DIR, "intents.json"), encoding="utf-8") as f:
            self.intents = json.load(f)
        self.stopwords = {
            "es": _load_stopwords("es"),
            "en": _load_stopwords("en"),
        }
        self._vocab = {"es": set(), "en": set()}
        for intent in self.intents.values():
            for lang, examples in intent["examples"].items():
                for ex in examples:
                    self._vocab[lang].update(tokenize(ex))
        self._learned = {"es": set(), "en": set()}
        self._dirty = False

    def load_learned(self, learned):
        for lang in ("es", "en"):
            tokens = set(learned.get(lang, []))
            self._learned[lang].update(tokens)
            self._vocab[lang].update(tokens)

    def learned_snapshot(self):
        return {lang: sorted(tokens) for lang, tokens in self._learned.items()}

    @property
    def dirty(self):
        return self._dirty

    def detect_language(self, text):
        lang, _es, _en = self.detect_language_scored(text)
        return lang

    def detect_language_scored(self, text):
        """Devuelve (idioma, score_es, score_en). Los scores permiten al
        motor saber si la deteccion fue decisiva o ambigua."""
        tokens = set(tokenize(text))
        if not tokens:
            return "es", 0, 0
        score_es = len(tokens & self.stopwords["es"]) + len(tokens & self._vocab["es"])
        score_en = len(tokens & self.stopwords["en"]) + len(tokens & self._vocab["en"])
        lang = "en" if score_en > score_es else "es"
        return lang, score_es, score_en

    def classify(self, text, lang, min_score=0.2):
        tokens = set(tokenize(text))
        if not tokens:
            return None, 0.0
        best_intent, best_score = None, 0.0
        for name, intent in self.intents.items():
            examples = intent["examples"].get(lang, [])
            for ex in examples:
                ex_tokens = set(tokenize(ex))
                if not ex_tokens:
                    continue
                overlap = len(tokens & ex_tokens)
                score = overlap / len(ex_tokens | tokens)
                if score > best_score:
                    best_score = score
                    best_intent = name
        if best_score < min_score:
            return None, best_score
        return best_intent, best_score

    def expand_vocab(self, text, lang):
        new_tokens = set(tokenize(text)) - self._vocab[lang]
        if new_tokens:
            self._vocab[lang].update(new_tokens)
            self._learned[lang].update(new_tokens)
            self._dirty = True

    def mark_saved(self):
        self._dirty = False

    def response_for(self, intent_name, lang, index=0):
        responses = self.intents[intent_name]["responses"].get(lang)
        if not responses:
            return None
        return responses[index % len(responses)]
