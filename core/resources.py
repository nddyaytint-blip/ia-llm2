"""Deteccion de recursos del sistema y analisis razonado de hardware.

El modulo no solo detecta specs sino que razona: evalua cuellos de botella
reales basandose en el uso actual (pasajes indexados, latencias, presion de
memoria) y genera recomendaciones con justificacion logica explicita.
"""
import os
import platform
import multiprocessing
import ctypes


def _ram_total_mb():
    system = platform.system()
    if system == "Windows":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.pointer(stat))
        return stat.ullTotalPhys // (1024 * 1024)
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except FileNotFoundError:
        pass
    return 2048


def _ram_available_mb():
    system = platform.system()
    if system == "Windows":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.pointer(stat))
        return stat.ullAvailPhys // (1024 * 1024)
    try:
        with open("/proc/meminfo") as f:
            data = {}
            for line in f:
                parts = line.split()
                if parts and parts[0].rstrip(":") in ("MemAvailable", "MemFree"):
                    data[parts[0].rstrip(":")] = int(parts[1]) // 1024
            return data.get("MemAvailable", data.get("MemFree", 1024))
    except FileNotFoundError:
        return 1024


def snapshot():
    return {
        "cpu_cores": multiprocessing.cpu_count(),
        "ram_total_mb": int(_ram_total_mb()),
        "ram_free_mb": int(_ram_available_mb()),
        "ram_available_mb": int(_ram_available_mb()),
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
    }


def tier_for(snap):
    ram = snap["ram_total_mb"]
    cores = snap["cpu_cores"]
    if ram < 2048 or cores <= 2:
        return "low"
    if ram < 8192 or cores <= 4:
        return "medium"
    return "high"


TIER_PROFILES = {
    "low":    {"max_threads": 1, "history_size": 20,  "cache_size": 200,  "verbosity": "short",    "min_intent_score": 0.25},
    "medium": {"max_threads": 2, "history_size": 50,  "cache_size": 500,  "verbosity": "normal",   "min_intent_score": 0.22},
    "high":   {"max_threads": 4, "history_size": 200, "cache_size": 2000, "verbosity": "detailed", "min_intent_score": 0.20},
}


# ── Limites de lo que puede hacer el sistema segun recursos ────────────────
# Estos valores son los umbrales donde el hardware actual se convierte en
# cuello de botella medible.
_RAM_FOR_LARGE_INDEX_GB  = 16   # para indices >200k pasajes sin swap
_RAM_FOR_PARALLEL_MB     = 8192 # para busquedas paralelas sin presion
_CORES_FOR_CONCURRENT    = 8    # para atender >4 usuarios simultaneos
_LATENCY_TARGET_MS       = 80   # objetivo de latencia de respuesta
_PASSAGES_PER_GB_RAM     = 30000  # pasajes indexables por GB de RAM util


def analyze_hardware(snap, kb_stats=None, usage_history=None):
    """Analiza el hardware actual, razona sobre cuellos de botella y
    genera recomendaciones jerarquizadas con justificacion explicita.

    Devuelve un dict estructurado con:
      - estado_actual: dict con interpretacion de cada metrica
      - cuellos_de_botella: lista de limitaciones detectadas y razonadas
      - recomendaciones: lista de mejoras ordenadas por impacto
      - veredicto: conclusion general en una frase
    """
    ram_total_gb  = snap["ram_total_mb"] / 1024
    ram_free_mb   = snap.get("ram_free_mb", snap.get("ram_available_mb", 0))
    ram_used_pct  = round((1 - ram_free_mb / snap["ram_total_mb"]) * 100)
    cores         = snap["cpu_cores"]
    tier          = tier_for(snap)

    # Cuantos pasajes cabrian en RAM sin presion (regla empirica BM25)
    cap_pasajes_ram = int(ram_total_gb * _PASSAGES_PER_GB_RAM)

    # Datos de uso actual si estan disponibles
    passages   = kb_stats.get("passages", 0)   if kb_stats   else 0
    domains    = len(kb_stats.get("domains",{})) if kb_stats else 0
    avg_latency = 0
    if usage_history:
        lats = [h.get("latency_ms", 0) for h in usage_history if h.get("latency_ms")]
        avg_latency = sum(lats) / len(lats) if lats else 0

    # ── Estado actual interpretado ─────────────────────────────────────────
    estado = {
        "ram_total":    f"{ram_total_gb:.1f} GB",
        "ram_libre":    f"{ram_free_mb} MB ({100-ram_used_pct}% disponible)",
        "ram_usada":    f"{ram_used_pct}%",
        "cpu_cores":    f"{cores} nucleos logicos",
        "tier":         tier,
        "pasajes_ahora": passages,
        "capacidad_pasajes_ram": cap_pasajes_ram,
        "latencia_promedio": f"{avg_latency:.0f}ms" if avg_latency else "sin datos",
    }

    # ── Deteccion de cuellos de botella con razonamiento ──────────────────
    cuellos = []

    if ram_total_gb < 8:
        cuellos.append({
            "componente": "RAM",
            "severidad": "alta",
            "razonamiento": (
                f"Con {ram_total_gb:.1f}GB de RAM puedo indexar aproximadamente "
                f"{cap_pasajes_ram:,} pasajes antes de presionar el sistema operativo. "
                f"Ahora tengo {passages:,} pasajes en {domains} materias y ya estoy en "
                f"el {ram_used_pct}% de uso. Si agrego mas materias o documentos mas "
                f"densos el sistema comenzara a usar swap (disco como RAM), lo que "
                f"aumentaria la latencia de busqueda de <100ms a potencialmente varios "
                f"segundos. El cuello de botella es la RAM, no la CPU."
            ),
            "impacto_sin_mejora": "indice truncado, latencias altas al escalar contenido",
        })
    elif ram_total_gb < 16:
        cuellos.append({
            "componente": "RAM",
            "severidad": "media",
            "razonamiento": (
                f"Con {ram_total_gb:.1f}GB tengo margen razonable para {cap_pasajes_ram:,} "
                f"pasajes. Sin embargo, si quisiera expandirme a 10+ materias con archivos "
                f"muy densos (>500 pasajes por materia), o mantener multiples indices "
                f"simultaneos (ej. uno por idioma), la RAM se convertira en el factor "
                f"limitante antes que la CPU. Actualmente uso el {ram_used_pct}% de la RAM."
            ),
            "impacto_sin_mejora": "expansion de conocimiento limitada a mediano plazo",
        })

    if cores < _CORES_FOR_CONCURRENT:
        cuellos.append({
            "componente": "CPU",
            "severidad": "baja" if cores >= 4 else "media",
            "razonamiento": (
                f"Con {cores} nucleos el servidor puede atender hasta {max(1, cores//2)} "
                f"consultas paralelas con buena latencia. Para un uso personal esto es "
                f"suficiente. Donde si se notaria es si quisiera procesar documentos "
                f"grandes en batch (indexado de miles de paginas) en segundo plano "
                f"mientras respondo consultas: los nucleos se repartiran y la latencia "
                f"de respuesta subiria. La busqueda BM25 es O(n_terminos * largo_lista) "
                f"y escala bien con mas nucleos si se paraleliza."
            ),
            "impacto_sin_mejora": "indexado batch lento; latencia sube bajo carga paralela",
        })

    if avg_latency > _LATENCY_TARGET_MS:
        cuellos.append({
            "componente": "Latencia",
            "severidad": "media",
            "razonamiento": (
                f"La latencia promedio es {avg_latency:.0f}ms, por encima del objetivo de "
                f"{_LATENCY_TARGET_MS}ms. Con BM25 y {passages} pasajes, la busqueda "
                f"deberia ser <30ms en CPU. Si la latencia es alta, el cuello esta en "
                f"el I/O de disco al leer el indice (RAM insuficiente para mantenerlo "
                f"en cache) o en la GIL de Python bajo concurrencia. Solucion de software: "
                f"mantener el indice precargado en memoria. Solucion de hardware: mas RAM "
                f"o un SSD NVMe si el sistema usa swap."
            ),
            "impacto_sin_mejora": "experiencia de usuario degradada en consultas complejas",
        })

    if ram_free_mb < 512:
        cuellos.append({
            "componente": "Memoria disponible",
            "severidad": "alta",
            "razonamiento": (
                f"Solo hay {ram_free_mb}MB libres ahora mismo. Esto significa que el SO "
                f"puede empezar a liberar paginas del indice (que vive en RAM) para "
                f"darselas a otros procesos. La proxima consulta podria tardar mucho "
                f"mas porque debera releer desde disco. Recomendacion inmediata: cerrar "
                f"navegadores u otras aplicaciones pesadas antes de usar Green Tail."
            ),
            "impacto_sin_mejora": "ralentizacion inmediata; posible comportamiento errático",
        })

    # ── Recomendaciones jerarquizadas por impacto ─────────────────────────
    recomendaciones = []

    # RAM siempre es lo mas impactante para este sistema
    if ram_total_gb < 8:
        recomendaciones.append({
            "componente": "RAM",
            "prioridad": 1,
            "mejora": f"Ampliar de {ram_total_gb:.0f}GB a 16GB o 32GB",
            "justificacion": (
                f"La RAM es el componente mas critico para Green Tail porque el indice "
                f"BM25 completo ({passages:,} pasajes, {domains} materias) se mantiene "
                f"en memoria para busquedas rapidas. Con 16GB podria indexar "
                f"{int(16 * _PASSAGES_PER_GB_RAM / 1000)}k pasajes sin presion; con 32GB "
                f"tendria {int(32 * _PASSAGES_PER_GB_RAM / 1000)}k pasajes, equivalentes "
                f"a cientos de libros completos en todas las materias. El salto de "
                f"{ram_total_gb:.0f}GB a 16GB es el de mayor retorno por costo."
            ),
        })
    elif ram_total_gb < 48:
        next_step = 64 if ram_total_gb >= 32 else 32
        recomendaciones.append({
            "componente": "RAM",
            "prioridad": 1 if ram_used_pct > 70 else 2,
            "mejora": f"Ampliar de {ram_total_gb:.0f}GB a {next_step}GB si se planea escalar el conocimiento",
            "justificacion": (
                f"Con {ram_total_gb:.0f}GB el sistema funciona perfectamente para el "
                f"volumen actual ({passages} pasajes). El limite teorico de RAM esta en "
                f"{cap_pasajes_ram:,} pasajes — todavia muy lejos. Sin embargo, si se "
                f"quiere cargar enciclopedias completas, miles de articulos o libros "
                f"enteros por materia (>100k pasajes), ampliar a {next_step}GB garantizaria "
                f"que el indice completo permanece en RAM sin paginacion a disco. "
                f"Ahora mismo el sistema usa el {ram_used_pct}% de la RAM."
            ),
        })
    else:
        recomendaciones.append({
            "componente": "RAM",
            "prioridad": 3,
            "mejora": f"RAM actual ({ram_total_gb:.0f}GB) es excelente para este sistema",
            "justificacion": (
                f"Con {ram_total_gb:.0f}GB puedo mantener {cap_pasajes_ram:,} pasajes en "
                f"RAM comfortablemente. A este nivel la RAM no es el cuello de botella. "
                f"Si quisiera escalar mucho mas, la limitante seria la velocidad de "
                f"indexado (CPU) o el almacenamiento de los documentos fuente (disco)."
            ),
        })

    if cores < 4:
        recomendaciones.append({
            "componente": "CPU",
            "prioridad": 2,
            "mejora": "CPU con 6-8 nucleos fisicos de alta frecuencia (ej. AMD Ryzen 5/7 o Intel Core i5/i7 gen 12+)",
            "justificacion": (
                f"Con {cores} nucleos, el indexado de documentos grandes (ej. un libro "
                f"de 300 paginas) bloquearia la busqueda durante varios segundos. "
                f"Una CPU de 6-8 nucleos permitiria paralelizar el indexado en hilos "
                f"mientras el servidor sigue respondiendo. Para busquedas BM25 puras, "
                f"la frecuencia de reloj importa mas que el numero de nucleos: un "
                f"Ryzen 5 5600X a 4.6GHz seria considerablemente mas rapido que un "
                f"servidor cloud de 16 nucleos a 2.4GHz para este patron de acceso."
            ),
        })
    elif cores < _CORES_FOR_CONCURRENT:
        recomendaciones.append({
            "componente": "CPU",
            "prioridad": 3,
            "mejora": f"CPU actual ({cores} nucleos) es adecuada para uso personal",
            "justificacion": (
                f"Para un usuario simultaneo la CPU no es el cuello de botella. "
                f"Solo se volveria limitante si quisiera atender >4 usuarios en "
                f"paralelo o indexar documentos masivos en tiempo real."
            ),
        })
    else:
        recomendaciones.append({
            "componente": "CPU",
            "prioridad": 4,
            "mejora": f"CPU actual ({cores} nucleos) es excelente para este sistema",
            "justificacion": (
                f"Con {cores} nucleos puedo paralelizar busquedas y mantenimiento "
                f"del indice sin conflictos. No hay mejora necesaria en CPU para "
                f"el patron de uso actual."
            ),
        })

    # Almacenamiento
    recomendaciones.append({
        "componente": "Almacenamiento",
        "prioridad": 2,
        "mejora": "SSD NVMe PCIe 4.0 para el directorio knowledge/ y el indice cache",
        "justificacion": (
            f"El indice BM25 ({passages} pasajes) se guarda en data/knowledge_index.json. "
            f"Si la RAM es insuficiente y el SO hace swap, la velocidad de lectura del "
            f"disco determina la latencia de respuesta. Un SSD NVMe (3-7 GB/s) vs un "
            f"HDD (150 MB/s) puede suponer la diferencia entre 50ms y 3 segundos de "
            f"respuesta bajo presion de memoria. Si el sistema ya tiene SSD NVMe, este "
            f"componente esta bien cubierto."
        ),
    })

    # ── Veredicto sintetico ────────────────────────────────────────────────
    if not cuellos:
        veredicto = (
            f"El sistema esta bien equipado para el volumen actual ({passages} pasajes, "
            f"{domains} materias). No hay cuellos de botella activos. El siguiente "
            f"limite natural aparecera si el conocimiento crece mas alla de "
            f"{cap_pasajes_ram:,} pasajes (~{cap_pasajes_ram // passages:.0f}x el "
            f"volumen actual), momento en que la RAM se convertira en el factor limitante."
        ) if passages > 0 else (
            f"Hardware en buen estado ({ram_total_gb:.0f}GB RAM, {cores} nucleos). "
            f"No hay cuellos de botella detectados para el uso actual."
        )
    elif any(c["severidad"] == "alta" for c in cuellos):
        worst = next(c for c in cuellos if c["severidad"] == "alta")
        veredicto = (
            f"Cuello de botella principal detectado: {worst['componente']}. "
            f"{worst['razonamiento'][:180]}..."
        )
    else:
        componentes = ", ".join(c["componente"] for c in cuellos)
        veredicto = (
            f"El sistema funciona correctamente pero tiene limitaciones en {componentes} "
            f"que se haran evidentes al escalar el conocimiento. Ver recomendaciones."
        )

    return {
        "estado_actual": estado,
        "cuellos_de_botella": cuellos,
        "recomendaciones": sorted(recomendaciones, key=lambda r: r["prioridad"]),
        "veredicto": veredicto,
    }


def recommend_hardware(snap, kb_stats=None, usage_history=None):
    """Wrapper de compatibilidad que devuelve una lista plana de strings
    razonados para la CLI y el campo 'extra' de la UI."""
    analysis = analyze_hardware(snap, kb_stats=kb_stats, usage_history=usage_history)
    lines = []

    lines.append(f"DIAGNÓSTICO: {analysis['veredicto']}")
    lines.append("")

    lines.append("ESTADO ACTUAL:")
    e = analysis["estado_actual"]
    lines.append(
        f"  RAM: {e['ram_total']} total, {e['ram_libre']} · "
        f"CPU: {e['cpu_cores']} · "
        f"Perfil: {e['tier'].upper()} · "
        f"Conocimiento: {e['pasajes_ahora']} pasajes"
    )
    if e["latencia_promedio"] != "sin datos":
        lines.append(f"  Latencia promedio de respuesta: {e['latencia_promedio']}")
    lines.append("")

    if analysis["cuellos_de_botella"]:
        lines.append("CUELLOS DE BOTELLA IDENTIFICADOS:")
        for c in analysis["cuellos_de_botella"]:
            sev = {"alta": "⚠ ALTO", "media": "→ MEDIO", "baja": "· BAJO"}.get(c["severidad"], c["severidad"])
            lines.append(f"  {sev} — {c['componente']}")
            lines.append(f"    {c['razonamiento']}")
        lines.append("")

    lines.append("RECOMENDACIONES DE HARDWARE (por prioridad):")
    for i, r in enumerate(analysis["recomendaciones"], 1):
        lines.append(f"  {i}. {r['componente'].upper()}: {r['mejora']}")
        lines.append(f"     Por qué: {r['justificacion']}")

    return [l for l in lines]
