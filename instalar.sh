#!/bin/bash
echo ""
echo "============================================="
echo " Green Tail - Instalador de dependencias"
echo "============================================="
echo ""

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "ERROR: Python no encontrado."
    echo "Instálalo con: sudo apt install python3 pip"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "Python encontrado: $($PYTHON --version)"
echo ""
echo "Instalando dependencias..."
$PYTHON -m pip install -r requirements.txt

echo ""
echo "============================================="
echo " Instalacion completada."
echo " Ahora puedes ejecutar: python3 main.py"
echo " O el servidor:         python3 server.py"
echo "============================================="
echo ""
