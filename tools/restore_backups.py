"""Restaura archivos de conocimiento desde los backups más recientes."""
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR     = Path(__file__).parent.parent
BACKUP_DIR   = BASE_DIR / "data" / "knowledge_backups"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 20
cutoff  = datetime.now() - timedelta(minutes=minutes)

restored = 0
skipped  = 0

for bak in BACKUP_DIR.glob("*.bak"):
    mtime = datetime.fromtimestamp(bak.stat().st_mtime)
    if mtime <= cutoff:
        continue
    m = re.match(r"^(.+)_\d{8}_\d{6}\.md\.bak$", bak.name)
    if not m:
        continue
    stem = m.group(1)
    candidates = list(KNOWLEDGE_DIR.rglob(f"{stem}.md"))
    if len(candidates) == 1:
        shutil.copy2(bak, candidates[0])
        restored += 1
    else:
        skipped += 1

print(f"Restaurados: {restored}  |  No encontrados: {skipped}")
