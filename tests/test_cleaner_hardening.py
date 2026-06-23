"""Pruebas de las capas de endurecimiento de document_cleaner.

Cada caso prueba que la capa ARREGLA su artefacto objetivo Y que NO destruye
prosa normal (falsos positivos). Ejecutar:  py tests/test_cleaner_hardening.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.document_cleaner import (
    clean,
    _merge_double_columns,
    _rebuild_broken_tables,
    _drop_repeated_headers,
    _strip_watermarks,
)

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  OK   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}  {detail}")


# --- 1. Doble columna --------------------------------------------------------
double_col = """La fotosintesis es el proceso        El floema es el tejido que
por el cual las plantas              transporta la savia elaborada
convierten la luz solar en           desde las hojas hacia el resto
energia quimica almacenada.          de la planta y sus raices."""

merged = _merge_double_columns(double_col)
check("doble columna: izquierda reflujada",
      "fotosintesis es el proceso por el cual las plantas" in merged,
      repr(merged[:80]))
check("doble columna: derecha reflujada",
      "floema es el tejido que transporta la savia" in merged,
      repr(merged))

# Falso positivo: prosa normal con dobles espacios ocasionales NO debe reflujarse
normal_prose = """Este es un parrafo normal de texto.
Tiene varias lineas seguidas.
Ninguna deberia partirse en columnas.
El contenido permanece intacto siempre."""
check("doble columna: prosa normal intacta",
      _merge_double_columns(normal_prose) == normal_prose)

# --- 2. Tablas rotas ---------------------------------------------------------
table = """Elemento    Simbolo    Masa
Hidrogeno    H    1.008
Oxigeno    O    15.999
Carbono    C    12.011"""
rebuilt = _rebuild_broken_tables(table)
check("tabla: fila compactada con pipes",
      "Hidrogeno | H | 1.008" in rebuilt, repr(rebuilt))
check("tabla: cabecera compactada",
      "Elemento | Simbolo | Masa" in rebuilt)

# Falso positivo: una sola linea con dobles espacios NO es tabla
check("tabla: linea suelta no se toca",
      _rebuild_broken_tables("Solo una   linea aislada aqui.")
      == "Solo una   linea aislada aqui.")

# --- 3. Encabezados/pies repetidos ------------------------------------------
headers = """Capitulo 4 Fotosintesis
Contenido real de la pagina uno aqui.
Capitulo 4 Fotosintesis
Contenido real de la pagina dos aqui.
Capitulo 4 Fotosintesis
Contenido real de la pagina tres aqui."""
dropped = _drop_repeated_headers(headers)
check("encabezado repetido: eliminado",
      "Capitulo 4 Fotosintesis" not in dropped, repr(dropped))
check("encabezado repetido: contenido conservado",
      "Contenido real de la pagina dos aqui." in dropped)

# Falso positivo: una frase corta que aparece 2 veces NO se elimina (umbral 3)
twice = "Hola mundo.\nOtra cosa.\nHola mundo."
check("encabezado: 2 repeticiones se conservan",
      twice == _drop_repeated_headers(twice))

# --- 4. Marcas de agua -------------------------------------------------------
watermarked = """CONFIDENCIAL
Texto importante del documento.
DRAFT
Mas texto valioso aqui.
BORRADOR"""
stripped = _strip_watermarks(watermarked)
check("marca de agua: CONFIDENCIAL eliminado",
      "CONFIDENCIAL" not in stripped, repr(stripped))
check("marca de agua: contenido conservado",
      "Texto importante del documento." in stripped)

# ALL-CAPS repetida
caps = "SAMPLE\nContenido.\nSAMPLE\nMas.\nSAMPLE"
check("marca de agua: caps repetida eliminada",
      "SAMPLE" not in _strip_watermarks(caps))

# Falso positivo: una sigla legitima en mayusculas NO se elimina si aparece poco
check("marca de agua: sigla unica conservada",
      "ADN" in _strip_watermarks("El ADN es la molecula.\nContiene genes."))

# --- 5. Integracion completa: PDF pesadilla en modo agresivo -----------------
nightmare = """CONFIDENCIAL
Introduccion a la biologia        El estudio de la vida abarca
celular y sus componentes         desde moleculas hasta ecosistemas
fundamentales para la vida y       complejos e interconectados entre
para entender los procesos.        si a multiples escalas distintas.
CONFIDENCIAL
Elemento    Funcion    Ubicacion
Nucleo    Control    Centro
Mitocondria    Energia    Citoplasma"""
result = clean(nightmare, aggressive=True)
check("integracion: sin marcas de agua", "CONFIDENCIAL" not in result, repr(result))
check("integracion: prosa reflujada presente",
      "Introduccion a la biologia celular" in result, repr(result))
check("integracion: tabla compactada presente",
      "Nucleo | Control | Centro" in result, repr(result))

print(f"\n{'='*50}")
print(f"  PASARON: {_passed}   FALLARON: {_failed}")
print(f"{'='*50}")
sys.exit(1 if _failed else 0)
