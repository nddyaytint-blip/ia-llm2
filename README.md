# IA bilingue local con auto-ajuste

IA de consola (español/inglés) que funciona sin conexión a internet:

- `core/nlu.py`: tokenizador, detector de idioma y clasificador de intenciones por similitud, basado en `data/intents.json` (sin dependencias externas).
- `core/resources.py`: detecta CPU/RAM del equipo (vía stdlib/ctypes) y asigna un perfil (`low`/`medium`/`high`).
- `core/self_improve.py`: analiza cada 10 interacciones (latencia, tasa de intenciones no reconocidas, memoria disponible) y ajusta automáticamente parámetros menores en `config.json` (umbral de reconocimiento, tamaño de historial, tamaño de caché), dejando registro en `logs/self_improvement.log`.
- `core/knowledge.py`: base de conocimiento local. Ingiere los documentos de `knowledge/`, los trocea en pasajes y construye un índice TF-IDF (sin dependencias externas) para buscar por similitud y encontrar conexiones entre conceptos. El índice se reconstruye solo cuando cambian los archivos y limita su tamaño según el perfil de recursos.
- `core/reasoning.py`: convierte una búsqueda en una respuesta **fundamentada y con nivel de confianza**, expone sus fuentes y conexiones, y es capaz de **defender** su postura cuando la evidencia la sostiene o **ceder** y marcar el tema para ampliarlo cuando es débil.
- `core/storage.py`: persistencia de configuración y logs de uso (`logs/usage.log`).
- `main.py`: bucle interactivo.

## Requisitos

Python 3.9+ (sin librerías externas). Si no lo tienes, descárgalo desde https://www.python.org/downloads/ (marcar "Add python.exe to PATH" en el instalador).

## Uso

### Modo CLI interactivo

```
py main.py
```

Comandos especiales dentro del chat:
- `estado` / `status`: muestra recursos detectados y perfil activo.
- `conocimiento` / `knowledge`: muestra cuántos pasajes y materias tiene indexados.
- `conexiones <tema>` / `connections <topic>`: muestra conceptos y materias relacionadas con un tema.
- `recargar` / `reload`: vuelve a indexar la carpeta `knowledge/`.
- `sugerencias` / `suggestions`: muestra recomendaciones de mejora de software actuales.
- `hardware`: muestra necesidades de hardware para mejora continua.
- `salir` / `exit`: termina el programa.

Además, fuera de esos comandos puedes **hacerle preguntas** ("¿qué es la fotosíntesis?", "¿qué relación hay entre el ADN y las proteínas?"). Responderá con un pasaje fundamentado, su **nivel de confianza** y sus **fuentes**. Si le dices que se equivoca ("estás mal", "eso es falso") reevaluará su evidencia: la **defenderá** si es sólida o **cederá** y marcará el tema si es débil. Con "explica tu respuesta" / "¿en qué te basas?" mostrará las fuentes en las que se apoyó.

### Modo servicio en segundo plano (desarrollo continuo)

```
py server.py --host 127.0.0.1 --port 8765
```

API JSON local (sin dependencias externas):
- `POST /chat` o `POST /ask` con cuerpo `{"text": "..."}` → respuesta, idioma, modo, confianza, fuentes, conexiones, latencia.
- `GET /status` → recursos y perfil activo.
- `GET /knowledge` → estadísticas del conocimiento indexado (pasajes, términos, materias).
- `GET /connections?topic=...` → conceptos y materias relacionadas con un tema.
- `GET /suggestions` → sugerencias de mejora.
- `GET /hardware` → necesidades de hardware.
- `GET /health` → comprobación de vida.

Ejemplo:
```
curl -X POST http://127.0.0.1:8765/chat -H "Content-Type: application/json" -d "{\"text\":\"hola\"}"
```

Tanto la CLI como el servicio comparten el mismo núcleo ([core/engine.py](core/engine.py)).

## Aprendizaje persistente

El vocabulario que la IA aprende del uso se guarda en `data/learned_vocab.json` y se recarga en cada arranque, mejorando la detección de idioma con el tiempo.

## Base de conocimiento (materias)

La carpeta `knowledge/` contiene **compendios** en texto plano (`.md`/`.txt`) organizados por materia (una subcarpeta por materia). Se incluyen 15 materias de partida: historia, química, física, matemáticas, geografía, geología, botánica, biología, genética, microbiología, biología molecular, psicología, filosofía, epistemología y ontología.

Para **cargarle más información** (la forma de que "aprenda" más, sin internet):

1. Crea o elige una subcarpeta dentro de `knowledge/` (p. ej. `knowledge/quimica/`).
2. Suelta ahí tus documentos en `.md` o `.txt` (compendios, apuntes, repositorios de texto). Cada párrafo se indexa como un pasaje.
3. Reinicia el programa o usa el comando `recargar`. El índice se reconstruye automáticamente al detectar los cambios.

Cuanta más información de calidad le des, mejores y más confiadas serán sus respuestas y más conexiones podrá encontrar entre materias. Los temas que objetas o que no puede responder quedan registrados (visibles en `sugerencias`) para saber qué ampliar.

Limitaciones honestas: es un motor de **recuperación** (encuentra y cita lo que tiene), no un modelo neuronal que redacta texto nuevo. La recuperación funciona mejor cuando la pregunta y los documentos están en el mismo idioma.

## Cómo amplía su conocimiento (intenciones)

Edita `data/intents.json` para añadir más ejemplos en `es`/`en` por intención, o nuevas intenciones de charla/comando. No requiere reentrenamiento ni internet: se lee al iniciar.

## Auto-mejora

El sistema solo edita automáticamente valores de ajuste fino en `config.json` (no su lógica central). Cada cambio queda auditado en `logs/self_improvement.log` con la razón.
