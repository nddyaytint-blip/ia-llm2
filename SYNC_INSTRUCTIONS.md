# Sincronización OneDrive ↔ GitHub

## Estado Actual ✅

Tu proyecto está **correctamente configurado**:

```
Local (OneDrive)
C:\Users\moral\OneDrive\escritorio\jj\ia-bilingue/
         ↕ (Git sincronizado)
         ↓
Remote (GitHub)
https://github.com/nddyaytint-blip/ia-bilingue
```

---

## Flujos de Sincronización

### Opción 1: Sincronización Manual (Recomendada)

**Windows:**
```cmd
# Ejecuta el script
sync_github.bat
```

**Linux/macOS:**
```bash
bash sync_github.sh
```

**Qué hace:**
1. `git pull origin main` — Trae cambios desde GitHub
2. `git add -A` — Agrega cambios locales
3. `git commit` — Crea commit (si hay cambios)
4. `git push origin main` — Envía a GitHub

---

### Opción 2: Comandos Manuales

```bash
# Desde la carpeta del proyecto
cd C:\Users\moral\OneDrive\escritorio\jj\ia-bilingue

# Traer cambios desde GitHub
git pull origin main

# Ver qué cambió
git status

# Agregar cambios locales
git add -A

# Crear commit
git commit -m "Descripción de cambios"

# Enviar a GitHub
git push origin main
```

---

### Opción 3: Sincronización Automática (Windows Task Scheduler)

**Para que se sincronice automáticamente cada hora:**

1. Abre **Programador de tareas de Windows**
2. Clic en **Crear tarea básica**
3. Nombre: "Sincronizar ia-bilingue GitHub"
4. Trigger: **Diario** (o cada hora)
5. Acción: **Iniciar programa**
   - Programa: `cmd.exe`
   - Argumentos: `/c "C:\Users\moral\OneDrive\escritorio\jj\ia-bilingue\sync_github.bat"`
6. Guardar

---

## Estructura de Repositorio

```
GitHub (https://github.com/nddyaytint-blip/ia-bilingue)
├── core/
│   ├── engine.py
│   ├── nlu.py
│   ├── knowledge.py
│   ├── document_importer.py        ← NUEVO
│   ├── document_classifier.py       ← NUEVO
│   ├── file_watcher.py              ← NUEVO
│   └── ...
├── tools/
│   ├── import_documents.py          ← NUEVO
│   ├── clean_knowledge.py
│   └── ...
├── knowledge/                       ← Disponible en GitHub
│   ├── biologia/
│   ├── economia/
│   └── ... (20+ dominios)
├── DOCUMENT_INGESTION.md            ← NUEVO
├── IMPLEMENTATION_SUMMARY.md        ← NUEVO
├── SYNC_INSTRUCTIONS.md             ← NUEVO
└── ...

Local OneDrive (C:\Users\moral\OneDrive\escritorio\jj\ia-bilingue)
├── (Todo lo anterior)
├── imports/                         ← NO EN GITHUB (local)
├── documents/                       ← NO EN GITHUB (local)
├── data/
│   ├── import_registry.json         ← NO EN GITHUB (local)
│   ├── knowledge_index.json         ← NO EN GITHUB (local)
│   └── ...
└── config.json                      ← NO EN GITHUB (local)
```

---

## Flujo Típico en Dos Máquinas

### PC 1 (OneDrive + GitHub)
```
1. Trabajas en código
   ↓
2. Ejecutas: sync_github.bat
   ↓
3. Cambios suben a GitHub
```

### PC 2 (La otra máquina)
```
1. Ejecutas: git pull origin main
   ↓
2. Tienes los cambios más recientes
   ↓
3. Trabajas en código
   ↓
4. Ejecutas: sync_github.bat (o git push)
   ↓
5. Cambios suben a GitHub
```

### De vuelta a PC 1
```
1. Ejecutas: git pull origin main
   ↓
2. Tienes los cambios que hizo PC 2
```

---

## Archivos Ignorados (No van a GitHub)

Estos archivos **permanecen solo en OneDrive** y NO se sincronizan a GitHub:

```
imports/                    # Documentos a importar (locales)
documents/                  # Documentos originales (locales)
config.json                 # Configuración local
logs/*.log                  # Logs de ejecución
data/users.json             # Datos de usuarios (privados)
data/learned_vocab.json     # Vocabulario aprendido (específico de PC)
data/import_registry.json   # Registro de importaciones (específico de PC)
data/knowledge_index.json   # Índice BM25 (específico de PC)
__pycache__/                # Caché de Python
*.pyc                       # Archivos compilados
.git/                       # Metadatos Git (local)
```

Ver `.gitignore` para la lista completa.

---

## Conflictos (Evitarlos)

**Situación:** Editas el mismo archivo en dos PCs simultáneamente

**Solución:**
1. En ambas PCs: `git pull origin main` antes de editar
2. Edita en una sola PC a la vez
3. Después de terminar: `git push origin main`
4. En la otra PC: `git pull origin main` para traer cambios

**Si ocurre conflicto:**
```bash
# Ver conflictos
git status

# Ver el archivo conflictado
cat archivo_con_conflicto.py

# Editar manualmente (busca <<<<<<, ======, >>>>>>)
# Elimina los marcadores y deja la versión correcta

# Completar resolución
git add archivo_con_conflicto.py
git commit -m "Resolver conflicto"
git push origin main
```

---

## Verificación

**Para verificar que todo está sincronizado:**

```bash
cd C:\Users\moral\OneDrive\escritorio\jj\ia-bilingue

# Verificar conexión a GitHub
git remote -v

# Ver últimos commits
git log --oneline -5

# Ver diferencias locales vs GitHub
git status

# Detalles de cambios
git diff
```

**Resultado esperado:**
```
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

---

## Flujo Recomendado (Diario)

**Al iniciar:**
```bash
git pull origin main
```

**Después de trabajar:**
```bash
sync_github.bat  # (o sync_github.sh en Linux/Mac)
```

**Antes de cerrar:**
```bash
git status  # Verificar que todo está sincronizado
```

---

## URLs Importantes

- **Repositorio:** https://github.com/nddyaytint-blip/ia-bilingue
- **Issues:** https://github.com/nddyaytint-blip/ia-bilingue/issues
- **Commits:** https://github.com/nddyaytint-blip/ia-bilingue/commits/main

---

## Troubleshooting

### "git: command not found"
Instala Git desde https://git-scm.com/download/win

### "Permission denied (publickey)"
Genera SSH key:
```bash
ssh-keygen -t ed25519 -C "nddyaytint@gmail.com"
# Agrega la clave pública a GitHub Settings > SSH Keys
```

### "Your branch is ahead of 'origin/main'"
Tienes commits locales no enviados:
```bash
git push origin main
```

### "Your branch is behind 'origin/main'"
Alguien hizo cambios en GitHub:
```bash
git pull origin main
```

### "fatal: not a git repository"
No estás en la carpeta correcta:
```bash
cd C:\Users\moral\OneDrive\escritorio\jj\ia-bilingue
git status
```

---

## Estadísticas

```bash
# Ver estadísticas del repositorio
git log --oneline | wc -l          # Total de commits
git log --stat | head -50          # Cambios recientes
git remote show origin              # Info del remote
```

---

## Resumen

✅ **Configuración actual:**
- Repositorio local: OneDrive (carpeta en nube)
- Repositorio remoto: GitHub (público, versionado)
- Sincronización: Manual (con scripts automáticos disponibles)
- Estado: Completamente sincronizado

✅ **Flujo:**
1. Cambios locales → `git add -A`
2. Commit → `git commit -m "..."`
3. Push → `git push origin main`

✅ **Otros equipos:**
1. Clonar: `git clone https://github.com/nddyaytint-blip/ia-bilingue.git`
2. Traer cambios: `git pull origin main`
3. Contribuir: Edit → `git add` → `git commit` → `git push`

---

**Última actualización:** 2026-06-19
