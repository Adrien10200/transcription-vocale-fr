# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour « Transcription Vocale FR » (build optimisé, léger).

Mode onedir (dossier) : démarrage rapide. Le décodage audio passe par PyAV
(bibliothèques FFmpeg embarquées automatiquement) : AUCUN exécutable ffmpeg
externe n'est nécessaire. Le modèle large-v3 (~3 Go) n'est PAS embarqué : il
reste dans le cache externe `models/` à côté de l'exe.

Optimisations de taille :
  • Pas de ffmpeg.exe / ffplay.exe / ffprobe.exe (PyAV suffit)   → ~415 Mo
  • Exclusion d'opengl32sw et des modules Qt inutiles            → ~40 Mo
  • Exclusion de Pillow (utilisé seulement hors-ligne pour l'icône)
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

PROJECT_DIR = os.path.abspath(os.getcwd())

# --- Données à embarquer -------------------------------------------------- #
datas = []

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

# Métadonnées de version (éditeur, description, version) intégrées à l'exe.
VERSION_FILE = os.path.join(PROJECT_DIR, "version_info.txt")
if not os.path.isfile(VERSION_FILE):
    VERSION_FILE = None

# --- Bibliothèques dynamiques (moteur de transcription + audio) ----------- #
binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("sounddevice")   # PortAudio DLL

# Données de sounddevice (_sounddevice_data avec la DLL PortAudio).
datas += collect_data_files("sounddevice")

hiddenimports = [
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "tokenizers",
    "av",
    "sounddevice",
    "cffi",
    "_cffi_backend",
    "numpy",
    "transcribe_worker",   # worker relancé via --run-worker
    "stream_worker",       # worker de transcription en direct (--run-stream)
    "audio_recorder",
    "transcriber_core",
]

# --- Exclusions : paquets Python jamais utilisés à l'exécution ------------ #
excludes = [
    "tkinter", "matplotlib", "pytest", "unittest", "pydoc",
    "PIL", "Pillow",              # utilisé seulement hors-ligne (make_ico.py)
    "scipy", "pandas",
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtNetwork", "PySide6.QtMultimedia", "PySide6.QtPdf",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
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
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)


# --- Filtre des binaires/données lourds et inutiles ----------------------- #
# Motifs (en minuscules) de fichiers à retirer du bundle final.
_DROP_PATTERNS = (
    "opengl32sw.dll",                 # rendu logiciel OpenGL (~20 Mo), inutile ici
    "qt6quick", "qt6qml", "qt6quick3d",
    "qt6webengine", "qt6webchannel", "qt6websockets",
    "qt6network", "qt6multimedia", "qt6pdf", "qt6sql",
    "qt6charts", "qt6datavisualization", "qt6bluetooth",
    "qt6positioning", "qt6sensors", "qt63d", "qt6designer",
    "qt6test", "qt6nfc", "qt6serialport",
    "d3dcompiler",                    # compilateur shaders D3D (~4 Mo)
    "qtquick", "qtqml",               # plugins QML
)

# Répertoires Qt de plugins jamais utilisés (multimédia, QML, position…).
_DROP_DIR_HINTS = (
    os.path.join("plugins", "multimedia"),
    os.path.join("plugins", "position"),
    os.path.join("plugins", "sqldrivers"),
    os.path.join("plugins", "webview"),
    os.path.join("qml"),
    os.path.join("translations"),     # traductions Qt intégrées, non utilisées
)


def _keep(dest_name: str) -> bool:
    low = dest_name.lower()
    if any(pat in low for pat in _DROP_PATTERNS):
        return False
    if any(hint in low for hint in _DROP_DIR_HINTS):
        return False
    return True


a.binaries = [b for b in a.binaries if _keep(b[0])]
a.datas = [d for d in a.datas if _keep(d[0])]


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
    version=VERSION_FILE,
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
