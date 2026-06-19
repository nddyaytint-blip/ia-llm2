from core import storage, resources

ANALYZE_EVERY = 10


def _is_unrecognized(entry):
    if entry.get("intent") is None:
        return True
    if entry.get("mode") == "knowledge" and not entry.get("score"):
        return True
    return False


def maybe_tune(config, snap, interaction_count):
    if interaction_count == 0 or interaction_count % ANALYZE_EVERY != 0:
        return config
    history = storage.read_usage(limit=ANALYZE_EVERY * 5)
    if not history:
        return config
    recent = history[-ANALYZE_EVERY:]
    unknown_rate = sum(1 for h in recent if _is_unrecognized(h)) / len(recent)
    avg_latency = sum(h.get("latency_ms", 0) for h in recent) / len(recent)
    ram_pressure = snap["ram_available_mb"] < max(256, snap["ram_total_mb"] * 0.1)

    changed = False

    if unknown_rate > 0.4 and config["min_intent_score"] > 0.1:
        old = config["min_intent_score"]
        config["min_intent_score"] = round(max(0.1, old - 0.05), 2)
        storage.append_improvement(
            f"min_intent_score {old} -> {config['min_intent_score']} "
            f"(tasa de intenciones no reconocidas: {unknown_rate:.0%})"
        )
        changed = True

    if avg_latency > 200 and config["history_size"] > 10:
        old = config["history_size"]
        config["history_size"] = max(10, old - 10)
        storage.append_improvement(
            f"history_size {old} -> {config['history_size']} "
            f"(latencia promedio alta: {avg_latency:.0f}ms)"
        )
        changed = True

    if ram_pressure and config["cache_size"] > 50:
        old = config["cache_size"]
        config["cache_size"] = max(50, old // 2)
        storage.append_improvement(
            f"cache_size {old} -> {config['cache_size']} "
            f"(memoria disponible baja: {snap['ram_available_mb']}MB)"
        )
        changed = True

    if not ram_pressure and avg_latency < 50 and config["history_size"] < 500:
        old = config["history_size"]
        config["history_size"] = old + 20
        storage.append_improvement(
            f"history_size {old} -> {config['history_size']} "
            f"(recursos sobrados, ampliando memoria de conversacion)"
        )
        changed = True

    if changed:
        storage.save_config(config)
    return config


def current_suggestions(snap, config, kb=None):
    """Genera sugerencias razonadas combinando analisis de hardware,
    estado del conocimiento y patrones de uso."""
    history = storage.read_usage(limit=50)
    kb_stats = kb.stats() if kb is not None else None

    # Analisis de hardware con contexto real
    notes = resources.recommend_hardware(snap, kb_stats=kb_stats,
                                         usage_history=history or [])

    # Analisis de patrones de uso
    if history:
        unknown_rate = sum(1 for h in history if _is_unrecognized(h)) / len(history)
        if unknown_rate > 0.3:
            notes.append(
                f"USO — Alta tasa de preguntas sin respuesta ({unknown_rate:.0%}): "
                f"el sistema no encontro informacion suficiente para {unknown_rate:.0%} "
                f"de las {len(history)} consultas recientes. Solucion: agrega mas "
                f"documentos .md/.txt en knowledge/<materia>/."
            )

    # Lagunas de conocimiento detectadas
    gaps = storage.read_knowledge_gaps(limit=5)
    if gaps:
        temas = ", ".join(f"'{g['topic']}'" for g in gaps[-3:])
        notes.append(
            f"CONOCIMIENTO — Temas donde la evidencia fue insuficiente o impugnada: "
            f"{temas}. Agrega fuentes sobre estos temas para mejorar la cobertura."
        )

    # Log de mejoras recientes del sistema (las ultimas 3, sin repetir hardware)
    recent_improvements = [
        imp for imp in storage.read_improvements(limit=10)
        if not imp.startswith("[")  # filtra entradas de log timestamp
    ]
    if recent_improvements:
        notes.append("")
        notes.append("AUTOAJUSTES RECIENTES DEL SISTEMA:")
        for imp in recent_improvements[:3]:
            notes.append(f"  • {imp}")

    return notes
