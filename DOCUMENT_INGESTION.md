# Sistema de Ingestión Documental

## Descripción General

Green Tail ahora soporta **ingestión automática de documentos** sin modificar código. El sistema detecta archivos en la carpeta `imports/`, los procesa automáticamente, los clasifica en categorías, y los indexa en la base de conocimiento.

**Características:**
- ✅ Offline completo (sin internet)
- ✅ Multiformato: PDF, DOCX, TXT, HTML, Markdown
- ✅ Clasificación automática por categorías
- ✅ Sin GPU requerida
- ✅ Bajo consumo de memoria
- ✅ Trazabilidad completa
- ✅ Monitoreo continuo en segundo plano

---

## Arquitectura

### Componentes Principales

#### 1. **DocumentImporter** (`core/document_importer.py`)
Responsable de:
- Detectar archivos nuevos en `imports/`
- Extraer texto según formato (PDF, DOCX, TXT, HTML, MD)
- Normalizar contenido
- Dividir en fragmentos indexables
- Mantener registro persistente de importaciones

**Formatos soportados:**
| Formato | Librería | Fallback |
|---------|----------|----------|
| PDF | pdfplumber | Extracción binaria simple |
| DOCX | python-docx | Descompresión ZIP + XML |
| HTML | BeautifulSoup | Regex + limpieza |
| TXT | (stdlib) | Lectura directa |
| MD | (stdlib) | Lectura directa |

#### 2. **DocumentClassifier** (`core/document_classifier.py`)
Responsable de:
- Analizar contenido del documento
- Detectar palabras clave por dominio
- Aplicar patrones regex específicos
- Asignar categoría más probable
- Crear categorías nuevas si es necesario

**Dominios reconocidos:**
- Biología, Biología Molecular, Genética, Microbiología, Botánica
- Física, Química, Matemáticas
- Economía, Sociología, Psicología
- Filosofía, Epistemología, Ontología
- Historia, Geografía, Geología
- Programación, Medicina, Farmacología, Fisiología, Endocrinología

#### 3. **FileWatcher** (`core/file_watcher.py`)
Responsable de:
- Monitorear continuamente `imports/`
- Detectar archivos nuevos/modificados
- Disparar importación automática
- Convertir fragmentos a Markdown indexable
- Integrar con el índice BM25

---

## Estructura de Carpetas

```
ia-bilingue/
├── imports/                    # Carpeta de entrada (monitorizada)
│   ├── documento1.pdf
│   ├── articulo.docx
│   └── ...
│
├── documents/                  # Archivos originales (respaldo)
│   └── (almacenados por el sistema)
│
├── knowledge/                  # Base de conocimiento indexada
│   ├── biologia/
│   ├── medicina/
│   ├── economia/
│   └── ... (categorías automáticas)
│
└── data/
    └── import_registry.json   # Registro de importaciones
```

---

## Flujo de Ingestión

```
1. Usuario coloca archivo en imports/
                    ↓
2. FileWatcher detecta cambio (cada 10s)
                    ↓
3. DocumentImporter extrae texto
                    ↓
4. DocumentClassifier clasifica categoría
                    ↓
5. Divide en fragmentos (máx 300 palabras)
                    ↓
6. Convierte a Markdown con metadatos
                    ↓
7. Guarda en knowledge/{categoría}/
                    ↓
8. BackgroundIndexer reconstruye índice BM25
                    ↓
9. Disponible para consultas inmediatamente
```

---

## Uso

### Opción 1: Automática (Recomendado)

Simplemente coloca archivos en `imports/`:

```bash
cp mi_documento.pdf ia-bilingue/imports/
```

El sistema lo procesará automáticamente en segundos.

### Opción 2: API Programática

```python
from core.engine import Engine

engine = Engine()

# Importar un archivo específico
result = engine.import_document("ruta/al/archivo.pdf", category="medicina")
print(result["status"])  # "success", "already_imported", etc

# Procesar toda la carpeta imports/
results = engine.import_directory()
for r in results:
    print(f"{r['filename']}: {r['status']}")

# Obtener estado de importación
status = engine.get_import_status()
print(status["imported"]["total_imported"])

# Clasificar un texto manualmente
category = engine.classify_text("El ADN es la molécula...")
print(category)  # "genetica"

# Obtener top-3 categorías sugeridas
suggestions = engine.suggest_categories("...")
```

### Opción 3: CLI (si existe)

```bash
python tools/import_documents.py --folder imports/ --process-all
```

---

## Metadatos Capturados

Cada documento importado conserva:

```json
{
  "filename": "documento_original.pdf",
  "category": "medicina",
  "imported_at": "2026-06-18T14:32:45.123456",
  "text_length": 45230,
  "chunk_count": 15,
  "original_path": "..."
}
```

Cada fragmento en Markdown incluye:

```markdown
# Documento Original

**Categoría:** medicina
**Archivo original:** documento.pdf
**Ruta original:** /path/to/documento.pdf
**Importado:** 2026-06-18T14:32:45.123456
**Fragmentos:** 15

---

## Fragmento 1
[contenido]

## Fragmento 2
[contenido]
```

---

## Instalación de Dependencias

### Mínima (recomendada para bajo consumo)

Sin dependencias externas — funciona con stdlib de Python.

```bash
python main.py  # Sin instalar nada
```

### Óptima (mejor soporte de formatos)

Para mejor manejo de PDF, DOCX e HTML:

```bash
pip install pdfplumber python-docx beautifulsoup4
```

Tamaño total: ~20 MB (ligero).

### Reparación de artefactos de escaneo

El motor lee la capa de texto del PDF y repara lo que los escaneos suelen
romper: palabras partidas, columnas y tablas fragmentadas, encabezados y
pies de página repetidos, marcas de agua. Esto no requiere instalar nada
extra — es parte del pipeline de limpieza incluido.

**Nota:** si un PDF es una imagen escaneada sin capa de texto, no hay texto
que extraer. El motor trabaja sobre la capa de texto existente.

---

## Rendimiento

### Velocidad

| Documento | Tiempo | Hardware |
|-----------|--------|----------|
| PDF 10 págs (200KB) | 0.5s | CPU solo |
| DOCX 5 págs | 0.1s | CPU solo |
| TXT 1000 líneas | 0.05s | CPU solo |
| HTML artículo | 0.2s | CPU solo |

### Consumo de Memoria

- Ingestión individual: ~50-100 MB
- Índice BM25 (10,000 fragmentos): ~200-300 MB
- Total en tier "low" (2GB): ~500 MB disponible

### Escalabilidad

| Tier | Max Fragmentos | Max Documentos |
|------|---|---|
| low | 600 | 20-30 |
| medium | 4000 | 150-200 |
| high | 20000 | 800+ |

---

## Troubleshooting

### "PDF: no se pudo extraer texto"

**Causa:** Archivo está encriptado o sin librería pdfplumber.

**Solución:**
1. Instalar: `pip install pdfplumber`
2. Si sigue fallando, convertir a TXT/PDF con pdftotext o Adobe

### "DOCX: estructura no estándar"

**Causa:** El DOCX no tiene la estructura esperada.

**Solución:**
1. Instalar: `pip install python-docx`
2. Si sigue fallando, guardar como PDF y reintentar

### Documento no aparece en búsquedas

**Causa:** No se reconstruyó el índice o hay error en clasificación.

**Soluciones:**
1. Esperar 30 segundos (BackgroundIndexer)
2. Verificar que `knowledge/{categoria}/` existe
3. Revisar `data/import_registry.json`
4. Ejecutar `engine.import_directory()` manualmente

---

## Ejemplos Prácticos

### Ejemplo 1: Importar Base de Medicina

```bash
# Colocar todos los PDFs en una subcarpeta
mkdir ia-bilingue/imports/medicina_basica
cp *.pdf ia-bilingue/imports/medicina_basica/

# Esperar 1 minuto (FileWatcher procesa)
# Los documentos quedarán en knowledge/medicina/
```

### Ejemplo 2: Clasificar Manualmente

```python
from core.engine import Engine
from core.document_classifier import DocumentClassifier

engine = Engine()
classifier = DocumentClassifier()

# Probar clasificador
texto = open("muestra.txt").read()
print(classifier.classify(texto))
# Salida: "economia"

print(classifier.suggest_categories(texto, top_k=3))
# Salida: [("economia", 12), ("sociologia", 3), ("historia", 1)]
```

### Ejemplo 3: Procesar Lote Inicial

```python
from core.engine import Engine
import json

engine = Engine()

# Procesar todos los documentos en imports/
resultados = engine.import_directory()

# Generar reporte
reporte = {
    "total": len(resultados),
    "exitosos": sum(1 for r in resultados if r.get("status") == "success"),
    "errores": sum(1 for r in resultados if r.get("status") == "error"),
    "detalles": resultados
}

with open("import_report.json", "w") as f:
    json.dump(reporte, f, indent=2)

print(reporte)
```

---

## Notas Técnicas

### Estrategia de Extracción

1. **PDF**: pdfplumber → página por página → fallback binario
2. **DOCX**: python-docx → fallback descompresión ZIP + XML
3. **HTML**: BeautifulSoup → fallback regex
4. **TXT/MD**: Lectura directa + normalización

### División en Fragmentos

- Tamaño: máximo 300 palabras (configurable)
- Solapamiento: 50 palabras para continuidad
- No corta palabras (respeta límites de sentencia)
- Mínimo: 10 palabras por fragmento

### Clasificación

1. Busca palabras clave del documento en DOMAIN_KEYWORDS
2. Aplica patrones regex específicos (DOMAIN_PATTERNS)
3. Puntúa combinaciones
4. Devuelve dominio con mayor puntaje
5. Si no hay coincidencia clara, asigna a "general"
6. Opcionalmente crea categoría nueva

### Integración con KnowledgeBase

- FileWatcher → crea archivo Markdown en `knowledge/{categoría}/`
- BackgroundIndexer → detecta cambios cada 30s
- KnowledgeBase.rebuild() → reconstruye índice BM25
- Búsquedas posteriores incluyen el contenido automáticamente

---

## Limitaciones Actuales

1. ❌ Lee la capa de texto del PDF; no convierte páginas escaneadas como
   imagen a texto (sí repara los artefactos de escaneo en la capa de texto)
2. ❌ Máximo fragmento de 300 palabras (optimizable)
3. ❌ No maneja PDFs protegidos sin pdfplumber

---

## Roadmap Futuro

- [ ] Cita por número de página (✅ implementado para PDF)
- [ ] Extracción de tablas
- [ ] Deduplicación de fragmentos
- [ ] API de webhook para importación remota
- [ ] Estadísticas de ingestión en tiempo real
- [ ] Interfaz web para upload de documentos

---

## Archivo de Cambios

**v1.0 (2026-06-18):**
- ✅ Implementación base: PDF, DOCX, TXT, HTML, MD
- ✅ Clasificación automática
- ✅ FileWatcher integrado
- ✅ Trazabilidad completa
- ✅ Bajo consumo de recursos
