import json
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LEARNED_VOCAB_PATH = os.path.join(DATA_DIR, "learned_vocab.json")
KNOWLEDGE_REVIEW_PATH = os.path.join(DATA_DIR, "knowledge_review.json")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
USAGE_LOG = os.path.join(LOGS_DIR, "usage.log")
IMPROVEMENT_LOG = os.path.join(LOGS_DIR, "self_improvement.log")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")
MAX_HISTORY_TURNS = 10

DEFAULT_CONFIG = {
    "max_threads": 1,
    "history_size": 20,
    "cache_size": 200,
    "verbosity": "normal",
    "min_intent_score": 0.2,
    "tier": "unknown",
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_learned_vocab():
    if not os.path.exists(LEARNED_VOCAB_PATH):
        return {"es": [], "en": []}
    with open(LEARNED_VOCAB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {"es": data.get("es", []), "en": data.get("en", [])}


def save_learned_vocab(vocab):
    payload = {"es": sorted(vocab.get("es", [])), "en": sorted(vocab.get("en", []))}
    with open(LEARNED_VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def append_usage(entry):
    os.makedirs(LOGS_DIR, exist_ok=True)
    entry = dict(entry)
    entry["ts"] = time.time()
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_usage(limit=500):
    if not os.path.exists(USAGE_LOG):
        return []
    with open(USAGE_LOG, encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def read_knowledge_gaps(limit=100):
    if not os.path.exists(KNOWLEDGE_REVIEW_PATH):
        return []
    with open(KNOWLEDGE_REVIEW_PATH, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except ValueError:
            return []
    return data[-limit:]


def append_knowledge_gap(topic, reason):
    gaps = read_knowledge_gaps(limit=200)
    gaps.append({"topic": topic, "reason": reason, "ts": time.time()})
    with open(KNOWLEDGE_REVIEW_PATH, "w", encoding="utf-8") as f:
        json.dump(gaps[-200:], f, indent=2, ensure_ascii=False)


def _conv_path(session_id):
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(session_id))
    return os.path.join(CONVERSATIONS_DIR, f"{safe}.json")


def save_conversation(session_id, turns):
    """Guarda los últimos MAX_HISTORY_TURNS turnos de una sesión."""
    turns = turns[-MAX_HISTORY_TURNS:]
    with open(_conv_path(session_id), "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "turns": turns, "saved_at": time.time()},
                  f, indent=2, ensure_ascii=False)


def load_conversation(session_id):
    """Carga el historial persistente de una sesión. Devuelve lista de turnos."""
    path = _conv_path(session_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("turns", [])[-MAX_HISTORY_TURNS:]
    except (ValueError, KeyError):
        return []


def list_sessions():
    """Lista todas las sesiones guardadas."""
    if not os.path.isdir(CONVERSATIONS_DIR):
        return []
    sessions = []
    for fname in os.listdir(CONVERSATIONS_DIR):
        if fname.endswith(".json"):
            path = os.path.join(CONVERSATIONS_DIR, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "turns": len(data.get("turns", [])),
                    "saved_at": data.get("saved_at"),
                })
            except (ValueError, KeyError):
                pass
    return sorted(sessions, key=lambda x: x.get("saved_at", 0), reverse=True)


def append_improvement(note):
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(IMPROVEMENT_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {note}\n")


def read_improvements(limit=20):
    if not os.path.exists(IMPROVEMENT_LOG):
        return []
    with open(IMPROVEMENT_LOG, encoding="utf-8") as f:
        return [l.strip() for l in f.readlines()[-limit:]]
