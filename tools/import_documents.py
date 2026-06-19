#!/usr/bin/env python
"""Herramienta CLI para importar documentos masivamente.

Uso:
    python tools/import_documents.py --process-all
    python tools/import_documents.py --file documento.pdf --category medicina
    python tools/import_documents.py --folder imports/
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.engine import Engine


def main():
    parser = argparse.ArgumentParser(
        description="Importador de documentos — agrega documentos a la base de conocimiento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python tools/import_documents.py --process-all
    Procesa todos los archivos en imports/

  python tools/import_documents.py --file documento.pdf
    Importa un archivo específico con auto-clasificación

  python tools/import_documents.py --file documento.pdf --category medicina
    Importa a una categoría específica

  python tools/import_documents.py --folder mis_docs/
    Procesa todos los archivos en una carpeta personalizada
        """
    )

    parser.add_argument(
        "--process-all",
        action="store_true",
        help="Procesa todos los archivos en imports/"
    )
    parser.add_argument(
        "--file",
        help="Importa un archivo específico"
    )
    parser.add_argument(
        "--folder",
        help="Procesa una carpeta específica"
    )
    parser.add_argument(
        "--category",
        help="Categoría destino (si no se especifica, se auto-clasifica)"
    )
    parser.add_argument(
        "--report",
        help="Guarda reporte JSON en este archivo"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Salida detallada"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Green Tail — Importador de Documentos")
    print("=" * 70)

    engine = Engine()
    results = []

    try:
        if args.file:
            print(f"\nImportando archivo: {args.file}")
            result = engine.import_document(args.file, category=args.category)
            if result:
                results.append(result)
            else:
                print(f"  ❌ No se pudo importar {args.file}")

        elif args.folder:
            print(f"\nProcesando carpeta: {args.folder}")
            if not os.path.isdir(args.folder):
                print(f"  ❌ Carpeta no encontrada: {args.folder}")
                sys.exit(1)
            for file_path in sorted(Path(args.folder).rglob("*")):
                if file_path.is_file():
                    result = engine.import_document(str(file_path))
                    if result:
                        results.append(result)

        elif args.process_all:
            print("\nProcesando imports/...")
            results = engine.import_directory()

        else:
            parser.print_help()
            sys.exit(1)

        if not results:
            print("\n  ℹ️  No hay archivos para procesar")
            sys.exit(0)

        total = len(results)
        successful = sum(1 for r in results if r.get("status") == "success")
        skipped = sum(1 for r in results if r.get("status") == "already_imported")
        errors = sum(1 for r in results if r.get("status") == "error")

        print(f"\n{'─' * 70}")
        print(f"Resumen:")
        print(f"  Total procesados    : {total}")
        print(f"  Exitosos           : {successful} ✅")
        print(f"  Ya importados      : {skipped} ⏭️")
        print(f"  Errores            : {errors} ❌")
        print(f"{'─' * 70}")

        if args.verbose or errors > 0:
            print(f"\nDetalles:")
            for r in results:
                status = r.get("status", "unknown")
                filename = r.get("filename", r.get("file", "?"))
                if status == "success":
                    category = r.get("category", "?")
                    chunks = r.get("chunk_count", 0)
                    print(f"  ✅ {filename} → {category} ({chunks} fragmentos)")
                elif status == "already_imported":
                    print(f"  ⏭️  {filename} (ya importado)")
                else:
                    error = r.get("error", status)
                    print(f"  ❌ {filename} ({error})")

        if args.report:
            report = {
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "successful": successful,
                    "skipped": skipped,
                    "errors": errors,
                },
                "results": results,
                "knowledge_stats": engine.knowledge_stats(),
            }
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\n📊 Reporte guardado en: {args.report}")

        sys.exit(0 if errors == 0 else 1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
