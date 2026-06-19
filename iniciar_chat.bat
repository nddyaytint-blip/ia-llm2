@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   Green Tail  —  chat interactivo (consola)
echo.
py main.py
echo.
echo   --- El programa termino. Pulsa una tecla para cerrar. ---
pause >nul
