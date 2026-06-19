@echo off
echo.
echo =============================================
echo  Green Tail - Instalador de dependencias
echo =============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python no encontrado.
        echo Descargalo en https://www.python.org/downloads/
        echo Marca "Add python.exe to PATH" al instalar.
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

echo Python encontrado. Instalando dependencias...
echo.

%PYTHON% -m pip install -r requirements.txt

echo.
echo =============================================
echo  Instalacion completada.
echo  Ahora puedes ejecutar: py main.py
echo  O el servidor:         py server.py
echo =============================================
echo.
pause
