@echo off
REM Sincronizador automático OneDrive <-> GitHub
REM Ejecuta: git pull (traer cambios desde GitHub)
REM           git add -A (agregar cambios locales)
REM           git commit (si hay cambios)
REM           git push (enviar a GitHub)

echo.
echo ========================================
echo Sincronizador GitHub - ia-bilingue
echo ========================================
echo.

cd /d "%~dp0"

echo [1] Trayendo cambios desde GitHub...
git pull origin main
if errorlevel 1 (
    echo ERROR en git pull
    pause
    exit /b 1
)

echo.
echo [2] Agregando cambios locales...
git add -A

echo.
echo [3] Verificando estado...
git status

echo.
echo [4] Creando commit si hay cambios...
git commit -m "Auto-sync: cambios locales OneDrive -> GitHub (%date% %time%)" 2>nul
if errorlevel 1 (
    echo (Sin cambios nuevos para commitear)
)

echo.
echo [5] Enviando a GitHub...
git push origin main
if errorlevel 1 (
    echo ERROR en git push
    pause
    exit /b 1
)

echo.
echo ========================================
echo Sincronizacion completada exitosamente
echo ========================================
echo.
pause
