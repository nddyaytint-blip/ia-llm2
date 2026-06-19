#!/bin/bash

echo "╔════════════════════════════════════════╗"
echo "║        GREEN TAIL - INICIADOR         ║"
echo "║     (Asistente de Conocimiento)       ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Verifica Python
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python3 no está instalado"
    echo ""
    echo "Solución:"
    echo "  Ubuntu/Debian: sudo apt install python3"
    echo "  macOS: brew install python3"
    echo "  O descarga desde https://www.python.org/downloads/"
    exit 1
fi

# Muestra versión
PYVER=$(python3 --version 2>&1)
echo "✓ Detectado: $PYVER"
echo ""

# Verifica que estamos en la carpeta correcta
if [ ! -f "server.py" ]; then
    echo "❌ ERROR: No encuentro server.py"
    echo "Asegúrate de estar en la carpeta raíz de Green Tail"
    exit 1
fi

echo "⏳ Iniciando servidor..."
echo "   (Espera a que diga 'servidor listo')"
echo ""

# Lanza el servidor en background
python3 server.py --host 127.0.0.1 --port 8765 &
SERVER_PID=$!

# Espera a que esté listo
RETRIES=0
MAX_RETRIES=30
while [ $RETRIES -lt $MAX_RETRIES ]; do
    sleep 1
    RETRIES=$((RETRIES + 1))

    if curl -s http://127.0.0.1:8765/health > /dev/null 2>&1; then
        echo ""
        echo "✓ SERVIDOR LISTO"
        echo ""
        echo "╔════════════════════════════════════════╗"
        echo "║   📌 Abriendo navegador en 3 seg...   ║"
        echo "║                                        ║"
        echo "║  URL: http://127.0.0.1:8765          ║"
        echo "║                                        ║"
        echo "║  Presiona Ctrl+C para parar           ║"
        echo "╚════════════════════════════════════════╝"
        echo ""

        sleep 3

        # Abre navegador según sistema
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open http://127.0.0.1:8765
        else
            xdg-open http://127.0.0.1:8765 2>/dev/null || echo "Abre http://127.0.0.1:8765 en tu navegador"
        fi

        echo "✓ Navegador abierto"
        echo ""
        echo "💡 Tips:"
        echo "   - Pregunta en español o inglés"
        echo "   - Botón 📎 para subir archivos/código"
        echo "   - Botón ✎ para enseñar nuevo conocimiento"
        echo "   - Botón ☀ para cambiar tema"
        echo "   - Botón ⊞ para ver estadísticas"
        echo ""
        echo "⏳ El servidor está corriendo..."
        echo ""

        # Mantén el script en foreground esperando Ctrl+C
        wait $SERVER_PID
        exit 0
    fi
done

echo "❌ ERROR: El servidor tardó demasiado en iniciar"
kill $SERVER_PID 2>/dev/null
exit 1
