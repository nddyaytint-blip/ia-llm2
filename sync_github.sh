#!/bin/bash
# Sincronizador automático OneDrive <-> GitHub
# Ejecuta: git pull, add, commit, push

set -e

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "Sincronizador GitHub - ia-bilingue"
echo "========================================"
echo ""

echo "[1] Trayendo cambios desde GitHub..."
git pull origin main

echo ""
echo "[2] Agregando cambios locales..."
git add -A

echo ""
echo "[3] Verificando estado..."
git status

echo ""
echo "[4] Creando commit si hay cambios..."
if git commit -m "Auto-sync: cambios locales OneDrive -> GitHub ($(date '+%Y-%m-%d %H:%M:%S'))" 2>/dev/null; then
    echo "Commit creado"
else
    echo "(Sin cambios nuevos para commitear)"
fi

echo ""
echo "[5] Enviando a GitHub..."
git push origin main

echo ""
echo "========================================"
echo "Sincronización completada exitosamente"
echo "========================================"
echo ""
