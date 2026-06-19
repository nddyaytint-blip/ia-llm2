@echo off
chcp 65001 > nul
echo.
echo =============================================
echo  Green Tail LLM - Configurar backend
echo =============================================
echo.
echo Opciones de backend LLM:
echo.
echo  [1] Ollama (offline, gratis, sin API key)
echo      - Descarga Ollama en https://ollama.com
echo      - Luego ejecuta: ollama pull llama3.2
echo.
echo  [2] OpenAI (API key requerida)
echo      - Necesitas una cuenta en platform.openai.com
echo.
echo  [3] Anthropic (API key requerida)
echo      - Necesitas una cuenta en console.anthropic.com
echo.

where py > nul 2>&1
if not errorlevel 1 (set PYTHON=py) else (set PYTHON=python)

echo Instalando dependencias de documentos...
%PYTHON% -m pip install -r requirements.txt
echo.

set /p CHOICE="Elige backend (1=Ollama, 2=OpenAI, 3=Anthropic): "

if "%CHOICE%"=="2" (
    %PYTHON% -m pip install openai>=1.0.0
    echo.
    echo Abre config_llm.json y pon tu clave en "openai_api_key"
    echo Cambia "backend" a "openai"
)
if "%CHOICE%"=="3" (
    %PYTHON% -m pip install anthropic>=0.20.0
    echo.
    echo Abre config_llm.json y pon tu clave en "anthropic_api_key"
    echo Cambia "backend" a "anthropic"
)
if "%CHOICE%"=="1" (
    echo.
    echo Para Ollama:
    echo   1. Descarga desde https://ollama.com/download
    echo   2. Instala y luego abre una terminal y ejecuta:
    echo      ollama pull llama3.2
    echo   3. El backend se detecta automaticamente (backend="auto")
)

echo.
echo Configuracion lista. Ejecuta iniciar_servidor.bat para arrancar.
echo.
pause
