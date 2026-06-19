import sys

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

from core.engine import Engine

EXIT_WORDS = {"salir", "exit", "quit"}
STATUS_WORDS = {"estado", "status"}
SUGGEST_WORDS = {"sugerencias", "suggestions"}
HARDWARE_WORDS = {"hardware"}
KNOWLEDGE_WORDS = {"conocimiento", "knowledge"}
RELOAD_WORDS = {"recargar", "reload"}
CONNECT_PREFIXES = ("conexiones ", "connections ")


def print_status(engine):
    s = engine.status()
    print("--- estado / status ---")
    print(f"CPU: {s['cpu_cores']} nucleos  RAM: {s['ram_total_mb']}MB total / "
          f"{s['ram_available_mb']}MB libre  OS: {s['os']}")
    print(f"Perfil: {s['tier']}  hilos: {s['max_threads']}  "
          f"historial: {s['history_size']}  cache: {s['cache_size']}")


def print_knowledge(engine):
    st = engine.knowledge_stats()
    materias = len(st["domains"])
    print(f"[conocimiento: {st['passages']} pasajes · {materias} materias · perfil {st['tier']}]")


def print_connections(engine, topic):
    rel = engine.connections(topic)
    print(f"--- conexiones: {topic} ---")
    if not rel["terms"]:
        print("Sin conexiones. Agrega documentos a knowledge/.")
        return
    print(f"Materias relacionadas: {', '.join(rel['domains'])}")
    for item in rel["terms"]:
        print(f"  {item['term']}  ({', '.join(item['domains'])})")


def print_list(title, items):
    print(f"--- {title} ---")
    for item in items:
        print(f"  {item}")


def print_result(result):
    print()
    print(result["reply"])
    # Linea compacta de metadatos
    parts = []
    if result.get("confidence"):
        parts.append(f"confianza: {result['confidence']}")
    if result.get("connections"):
        parts.append(f"conecta: {', '.join(result['connections'][:5])}")
    if parts:
        print(f"[{' · '.join(parts)}]")
    if result.get("extra"):
        print_list("detalle", result["extra"])
    print()


def main():
    engine = Engine()
    print("Green Tail iniciado  |  'salir' para terminar  |  ES / EN")
    print_status(engine)
    print_knowledge(engine)

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue

        lower = text.lower()
        if lower in EXIT_WORDS:
            print("Hasta luego.")
            break
        if lower in STATUS_WORDS:
            engine.refresh_resources()
            print_status(engine)
            continue
        if lower in KNOWLEDGE_WORDS:
            print_knowledge(engine)
            continue
        if lower in RELOAD_WORDS:
            engine.reload_knowledge()
            print_knowledge(engine)
            continue
        if lower.startswith(CONNECT_PREFIXES):
            topic = text.split(" ", 1)[1].strip()
            print_connections(engine, topic)
            continue
        if lower in SUGGEST_WORDS:
            print_list("sugerencias", engine.suggestions())
            continue
        if lower in HARDWARE_WORDS:
            print_list("hardware", engine.hardware_needs())
            continue

        print_result(engine.handle(text))


if __name__ == "__main__":
    main()
