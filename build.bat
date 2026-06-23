@echo off
chcp 65001 >nul
echo ============================================
echo   Green Tail LLM — Generador de .exe
echo ============================================
echo.

where py >nul 2>&1 && set PY=py || set PY=python
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado.
    echo Instala Python desde https://python.org
    pause & exit /b 1
)

echo [1/3] Instalando dependencias...
%PY% -m pip install --quiet --upgrade pyinstaller ^
    pdfplumber python-docx beautifulsoup4 openpyxl python-pptx
if errorlevel 1 (
    echo [ERROR] Fallo al instalar dependencias.
    pause & exit /b 1
)

echo [2/3] Limpiando build anterior...
if exist build rmdir /s /q build
if exist dist\green-tail-llm rmdir /s /q dist\green-tail-llm

echo [3/3] Construyendo .exe (puede tardar 1-2 min)...
%PY% -m PyInstaller green_tail_llm.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Fallo en PyInstaller.
    pause & exit /b 1
)

echo.
echo Creando carpetas de datos...
mkdir dist\green-tail-llm\knowledge  2>nul
mkdir dist\green-tail-llm\imports    2>nul
mkdir dist\green-tail-llm\documents  2>nul
mkdir dist\green-tail-llm\data       2>nul
mkdir dist\green-tail-llm\logs       2>nul

if exist knowledge\biologia (
    xcopy /e /i /q knowledge\biologia dist\green-tail-llm\knowledge\biologia >nul
)
if exist knowledge\quimica (
    xcopy /e /i /q knowledge\quimica dist\green-tail-llm\knowledge\quimica >nul
)
if exist knowledge\fisica (
    xcopy /e /i /q knowledge\fisica dist\green-tail-llm\knowledge\fisica >nul
)
if exist knowledge\green_tail (
    xcopy /e /i /q knowledge\green_tail dist\green-tail-llm\knowledge\green_tail >nul
)

REM ── Copiar config por defecto (sin API keys) ──
echo {"backend":"auto","ollama_url":"http://localhost:11434","ollama_model":"qwen2.5:1.5b","openai_model":"gpt-4o-mini","anthropic_model":"claude-haiku-4-5-20251001","openai_api_key":"","anthropic_api_key":"","max_tokens":512,"temperature":0.3,"timeout":120} > dist\green-tail-llm\config_llm.json

echo.
echo ============================================
echo   BUILD COMPLETADO
echo   Carpeta: dist\green-tail-llm\
echo   Exe    : dist\green-tail-llm\green-tail-llm.exe
echo ============================================
echo.
echo NOTA PARA EL TESTER:
echo   Esta version usa IA local (Ollama).
echo   Si el tester quiere el modo LLM debe instalar:
echo   1. Ollama desde https://ollama.com
echo   2. Ejecutar: ollama pull qwen2.5:1.5b
echo   Sin Ollama funciona en modo BM25 de respaldo.
echo.
pause
