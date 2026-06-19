@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ╔════════════════════════════════════════╗
echo ║        GREEN TAIL - INICIADOR         ║
echo ║     (Asistente de Conocimiento)       ║
echo ╚════════════════════════════════════════╝
echo.

:: Verifica Python (prueba py, luego python)
where py > nul 2>&1
if not errorlevel 1 (
    set PYTHON=py
    goto python_ok
)
where python > nul 2>&1
if not errorlevel 1 (
    set PYTHON=python
    goto python_ok
)
echo ERROR: Python no esta instalado o no esta en PATH
echo.
echo Solucion:
echo 1. Descarga Python desde https://www.python.org/downloads/
echo 2. Marca "Add Python to PATH" durante la instalacion
echo 3. Reinicia esta ventana
pause
exit /b 1

:python_ok
for /f "tokens=*" %%i in ('%PYTHON% --version 2^>^&1') do set PYVER=%%i
echo Detectado: %PYVER%
echo.

:: Verifica que estamos en la carpeta correcta
if not exist "server.py" (
    echo ❌ ERROR: No encuentro server.py
    echo Asegúrate de estar en la carpeta raíz de Green Tail
    pause
    exit /b 1
)

echo ⏳ Iniciando servidor...
echo    (Espera a que diga "servidor listo")
echo.

:: Lanza el servidor
start /B %PYTHON% server.py --host 127.0.0.1 --port 8765

:: Espera a que esté listo (máx 15 segundos)
set "RETRIES=0"
set "MAX_RETRIES=30"

:wait_for_server
timeout /t 1 /nobreak > nul
set /a RETRIES+=1

:: Intenta conectar
powershell -Command "try { $null = Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 1 -ErrorAction Stop; exit 0 } catch { exit 1 }" 2>nul
if not errorlevel 1 goto server_ready

if %RETRIES% lss %MAX_RETRIES% goto wait_for_server

echo ❌ ERROR: El servidor tardó demasiado en iniciar
pause
exit /b 1

:server_ready
echo.
echo ✓ SERVIDOR LISTO
echo.
echo ╔════════════════════════════════════════╗
echo ║   📌 Abriendo navegador en 3 seg...   ║
echo ║                                        ║
echo ║  URL: http://127.0.0.1:8765          ║
echo ║                                        ║
echo ║  Cierra esta ventana para parar       ║
echo ╚════════════════════════════════════════╝
echo.

timeout /t 3 > nul

:: Abre el navegador
start http://127.0.0.1:8765

echo ✓ Navegador abierto
echo.
echo 💡 Tips:
echo   - Pregunta en español o inglés
echo   - Botón 📎 para subir archivos/código
echo   - Botón ✎ para enseñar nuevo conocimiento
echo   - Botón ☀ para cambiar tema
echo   - Botón ⊞ para ver estadísticas
echo.
echo ⏳ El servidor está corriendo. Presiona Ctrl+C para parar.
echo.

:loop
timeout /t 10 > nul
goto loop
