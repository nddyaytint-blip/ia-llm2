# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Green Tail LLM
# Genera: dist/green-tail-llm/ con green-tail-llm.exe

block_cipher = None

# Recursos de SOLO LECTURA (el launcher los siembra junto al exe). Solo los
# 3 recursos del motor — NO datos de usuario (privacidad e índice obsoleto).
added_datas = [
    ("web",                    "web"),
    ("data/intents.json",      "data"),
    ("data/stopwords_es.txt",  "data"),
    ("data/stopwords_en.txt",  "data"),
]

hidden = [
    "core.engine",
    "core.knowledge",
    "core.reasoning",
    "core.nlu",
    "core.storage",
    "core.document_importer",
    "core.document_cleaner",
    "core.document_classifier",
    "core.file_watcher",
    "core.background_indexer",
    "core.user_manager",
    "core.responder",
    "core.code_tools",
    "core.resources",
    "core.self_analyst",
    "core.self_improve",
    "core.llm_client",
    "core.llm_reasoner",
    "core.ollama_reformulador",
    "pdfplumber",
    "pdfminer",
    "docx",
    "bs4",
    "openpyxl",
    "pptx",
    "csv",
    "zipfile",
    "xml.etree.ElementTree",
    "urllib.request",
    "urllib.error",
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="green-tail-llm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="green-tail-llm",
)
