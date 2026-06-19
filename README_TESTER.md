# Green Tail — Guía para Testers

Gracias por probar Green Tail. Esta guía te explica cómo instalar, lanzar y evaluar el programa.

## Instalación rápida (2 minutos)

### Requisitos
- **Python 3.8+** (descarga desde https://www.python.org/downloads/)
- **Git** (para clonar el repo, o descarga el ZIP)
- Un navegador web (Chrome, Firefox, Edge, Safari)

### Pasos

1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/nddyaytint-blip/ia-bilingue.git
   cd ia-bilingue
   ```
   O descarga el ZIP desde https://github.com/nddyaytint-blip/ia-bilingue/archive/refs/heads/main.zip y descomprímelo.

2. **Verifica Python:**
   ```bash
   python --version
   ```
   Debe ser 3.8 o mayor.

3. **Lanza el servidor:**
   
   **Windows:**
   - Haz doble clic en `iniciar_servidor.bat`
   - Se abrirá una ventana negra. Espera a que diga `servidor listo en http://127.0.0.1:8765`
   - El navegador se abrirá automáticamente

   **macOS / Linux:**
   ```bash
   bash iniciar.sh
   ```

4. **Usa Green Tail:**
   - Se abre en `http://127.0.0.1:8765`
   - Escribe preguntas en español o inglés
   - Prueba los botones de ejemplo

---

## Casos de prueba recomendados

### 1. Comprensión de preguntas indirectas
**Objetivo:** Verifica que entienda paráfrasis y frases coloquiales.

- ✅ `¿para qué sirve el ADN?` 
  - Debe responder sobre su función
- ✅ `oye una pregunta, quería saber para qué serve el adn`
  - Debe limpiar muletillas y responder lo mismo que arriba
- ✅ `eso de los genes que se activan y se desactivan`
  - Debe ir a epigenética/genética, NO heredar contexto de pregunta anterior

**Éxito:** Las tres responden sobre ADN/genética sin mezclar temas previos.

---

### 2. Clarificación en consultas ambiguas
**Objetivo:** Verifica que pida ayuda cuando no está claro.

- ✅ `teoría`
  - Debe mostrar 4+ opciones: "¿En Epistemología? ¿En Sociología?"
- ✅ `estructura`
  - Debe ofercer: estructura geológica, sociológica, botánica, química
- ✅ `¿qué es la energía?` (pregunta enmarcada)
  - Debe responder directo (NO pide clarificación, porque "energía" está en contexto)

**Éxito:** Una palabra sola ambigua pide confirmación; una pregunta enmarcada responde directo.

---

### 3. Código: Análisis profundo
**Objetivo:** Verifica que detecte errores reales en código Python.

Sube este archivo (botón 📎) o pégalo en el chat:
```python
import os
import json

def procesar(datos, cache=[]):
    try:
        for d in datos:
            if d == None:
                continue
            cache.append(d)
    except:
        pass
    return cache

result = procesar([1,2,3])
```

**Debe detectar:**
- 🔴 Argumento mutable por defecto (`cache=[]`)
- 🟠 Cláusula `except:` sin tipo (bare except)
- 🟠 Excepción silenciada con `pass`
- 🔵 Comparación `== None` (debe ser `is None`)
- Imports sin usar (`os`, `json`)

**Éxito:** Reporta al menos 4 de los 5 problemas listados.

---

### 4. Código: Generación desde plantillas
**Objetivo:** Verifica que genere código correctamente cuando está en su repertorio.

- ✅ `escribe una función que verifique si un número es primo`
  - Debe devolver código de función `es_primo()`
- ✅ `dame código para leer un archivo csv`
  - Debe usar `csv.DictReader`
- ✅ `crea un fizzbuzz`
  - Debe devolver el clásico FizzBuzz
- ❌ `construye un framework web completo`
  - Debe decir honestamente "No tengo plantilla para eso"

**Éxito:** Los primeros tres generan código; el cuarto rechaza honestamente.

---

### 5. Autopreguntas: Funcionamiento propio
**Objetivo:** Verifica que responda sobre sí misma coherentemente.

- ✅ `¿Cómo funcionas?`
  - Debe explicar que es offline, BM25, RAG
- ✅ `¿Necesitas una GPU?`
  - Debe explicar que NO necesita GPU, que usa BM25 en CPU
- ✅ `¿Puedes correr en dispositivos de bajos recursos?`
  - Debe explicar que sí, perfil bajo, eficiencia
- ✅ `¿Qué es la complejidad Big-O?`
  - Debe ir a **conocimiento**, no a autoexplicación

**Éxito:** Las primeras 3 son "self" (autoexplicación); la 4 es "knowledge".

---

### 6. Bilingüismo
**Objetivo:** Verifica que mantenga idiomas sin confundirse.

Conversación en inglés:
1. `What is photosynthesis?`
2. `And how does it relate to energy?`
3. `¿Y en la psicología?` (cambio a español)
4. `What about quantum mechanics?` (vuelvo a inglés)

**Éxito:** Las respuestas están en el idioma correspondiente (1,2,4 en inglés; 3 en español).

---

### 7. Enseñar nuevo conocimiento
**Objetivo:** Verifica que pueda aprender de documentos nuevos.

1. Haz clic en ✎ (botón Enseñar)
2. Tab "Nuevo tema"
3. Pega este texto:
   ```
   La inteligencia artificial es la simulación de procesos cognitivos
   mediante máquinas. Los sistemas IA incluyen aprendizaje automático,
   procesamiento de lenguaje natural y visión por computadora.
   La IA débil realiza tareas específicas; la IA fuerte sería consciente.
   ```
4. Haz clic en "Analizar dominio"
5. Debe sugerir "programacion" o "filosofia" como dominio
6. Confirma y guarda
7. Luego pregunta: `¿Qué es la IA?`

**Éxito:** El sistema aprende y luego puedes preguntarle sobre IA.

---

### 8. Render de markdown
**Objetivo:** Verifica que la UI muestre **negrita** y bloques de código correctamente.

Pregunta: `escribe código para leer un json`

**Debe verse:**
- Título en **negrita** (no `**texto**` literal)
- Bloque de código con fondo oscuro y botón "copiar"
- El botón "copiar" debe funcionar y poner el código en el portapapeles

**Éxito:** Las negritas se ven negras, no literales; el código es copiable.

---

### 9. Eficiencia en bajos recursos
**Objetivo:** Verifica que sea ligero incluso con poco hardware.

1. Abre Task Manager (Windows) o Activity Monitor (Mac)
2. Busca el proceso `python` o `py`
3. Fíjate en:
   - **RAM usada:** debe ser <200 MB en reposo, <500 MB con respuesta activa
   - **CPU:** debe estar entre 0-5% en reposo; picos al buscar, pero no sostenido

**Éxito:** La memoria es mucho menor que un navegador o un editor; no se dispara.

---

### 10. Manejo de contexto vs. seguimiento
**Objetivo:** Verifica el equilibrio entre memoria y autonomía.

1. `Explica la mecánica cuántica`
2. `¿Y eso cómo se relaciona con la filosofía?` (DEBE usar contexto)
3. `¿Qué es la fotosíntesis?` (nueva pregunta, SIN contexto)
4. `¿Y la ecología?` (contexto de fotosíntesis, no de mecánica cuántica)

**Éxito:** 
- (2) menciona mecánica cuántica como contexto
- (3) NO hereda contexto de mecánica cuántica
- (4) hereda contexto de fotosíntesis solamente

---

## Problemas conocidos / esperados

- **Primer arranque es lento (5-10s):** El índice se carga en memoria. Luego es instant.
- **En equipos muy antiguos con RAM <2GB:** Puede haber retardo. Es normal; Green Tail está diseñada para "bajo", pero necesita al menos 1-2 GB.
- **Las respuestas son "recuperadas", no inventadas:** A veces parecen mecánicas porque ensamblan fragmentos. Eso es deliberado (evita "alucinaciones").

---

## Reportar problemas

Si encuentras un bug:
1. **Describe qué hiciste** (pregunta exacta, pasos)
2. **Qué esperabas** vs. **qué pasó**
3. **Captura de pantalla o video** si es sobre UI
4. **Abre un issue en GitHub:** https://github.com/nddyaytint-blip/ia-bilingue/issues

Ejemplo de buen reporte:
> **Título:** Pregunta sobre hardware va a física
> **Pasos:** Pregunto "¿necesitas una GPU?"
> **Esperado:** Debe reconocer como autopregunta y responder sobre sus necesidades
> **Actual:** Responde con contenido de física

---

## Preguntas frecuentes

**P: ¿Por qué no genera cualquier código que le pida?**
R: No es un modelo generativo. Solo genera desde un catálogo de patrones comunes. Es deliberado para evitar generar código erróneo.

**P: ¿Funciona sin internet?**
R: Totalmente. Todo ocurre en tu máquina. No envía nada a internet.

**P: ¿Dónde se guardan mis datos?**
R: En tu disco duro, carpeta `knowledge/`. Tú controlas esos archivos.

**P: ¿Puedo borrar la conversación?**
R: Sí. Botón ⌫ (borrar). Se borra todo el chat.

**P: ¿Funciona en móvil?**
R: La UI web se abre en cualquier navegador, pero el servidor corre solo en Windows/Mac/Linux de escritorio.

---

## Duración estimada de pruebas

- **Rápido (15 min):** Pruebas 1-5 (preguntas y código)
- **Completo (1 hora):** Todas las pruebas + exploración libre
- **Profundo (2+ horas):** Crear 5-10 documentos nuevos y evaluar su impacto

---

¡Gracias por probar Green Tail! Tus comentarios ayudan a mejorar el sistema.
