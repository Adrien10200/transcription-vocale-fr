# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour « Transcription Vocale FR ».

Mode onedir (dossier) : démarrage rapide. ffmpeg portable et les assets VAD
de faster-whisper sont embarqués. Le modèle large-v3 (~3 Go) N'EST PAS
embarqué : il reste dans le cache externe `models/` à côté de l'exe.
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

PROJECT_DIR = os.path.abspath(os.getcwd())

# --- Données à embarquer -------------------------------------------------- #
datas = []

# ffmpeg portable -> tools/ffmpeg/bin dans le bundle
ffmpeg_bin = os.path.join(PROJECT_DIR, "tools", "ffmpeg", "bin")
if os.path.isdir(ffmpeg_bin):
    for name in os.listdir(ffmpeg_bin):
        if name.lower().endswith(".exe"):
            datas.append((os.path.join(ffmpeg_bin, name), "tools/ffmpeg/bin"))

# Icônes de l'application
for asset in ("icon.ico", "icon.png", "icon.svg"):
    ap = os.path.join(PROJECT_DIR, "assets", asset)
    if os.path.isfile(ap):
        datas.append((ap, "assets"))

# Assets VAD (silero_vad) de faster-whisper
datas += collect_data_files("faster_whisper")

# Icône de l'exécutable Windows
ICON_FILE = os.path.join(PROJECT_DIR, "assets", "icon.ico")
if not os.path.isfile(ICON_FILE):
    ICON_FILE = None

# --- Bibliothèques dynamiques (ctranslate2, onnxruntime) ------------------ #
binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")

hiddenimports = [
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "tokenizers",
    "av",
    "transcribe_worker",   # worker relancé via --run-worker
    "transcriber_core",
]

a = Analysis(
    ["app.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
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
    name="Transcription Vocale FR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # pas de fenêtre console (app GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Transcription Vocale FR",
)
