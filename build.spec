# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Sinhala Proofreader (online Gemini + offline fallback).

Build:
    pip install -r requirements.txt
    pyinstaller build.spec

Output:
    dist/SinhalaProofreader.exe   (single-file, windowed, self-contained)
"""

import os
from PyInstaller.utils.hooks import (
    collect_data_files, collect_submodules, collect_dynamic_libs,
)

block_cipher = None

# Gemini-only app — no offline dictionary needed.
datas = []
binaries = []

# sounddevice ships the PortAudio DLL as package data + loads it via cffi.
# Bundle the DLL and cffi backend so voice recording works in the frozen .exe.
datas += collect_data_files("sounddevice")
binaries += collect_dynamic_libs("sounddevice")

# Bundle the app icon(s) so the running app can set its window/taskbar icon.
for _icon in ("icon.ico", "icon.png"):
    _p = os.path.join("assets", _icon)
    if os.path.exists(_p):
        datas += [(_p, "assets")]

# CustomTkinter ships theme JSON / assets that must be included.
datas += collect_data_files("customtkinter")

# google-generativeai pulls in grpc / google.* packages — collect them fully so
# the API works inside the frozen .exe.
hiddenimports = ["customtkinter", "requests",
                 "engine.corrections_db", "engine.lan_proxy_engine",
                 "engine.audio_recorder", "gui.voice_button",
                 "sounddevice", "cffi", "_cffi_backend"]
hiddenimports += collect_submodules("google.generativeai")
hiddenimports += collect_submodules("google.ai.generativelanguage")

# Windows EXE icons must be .ico; fall back to .png only if no .ico is present.
icon_file = os.path.join("assets", "icon.ico")
if not os.path.exists(icon_file):
    icon_file = os.path.join("assets", "icon.png")
icon_arg = icon_file if os.path.exists(icon_file) else None

# Heavy scientific / ML / dev libraries that may exist in the global Python
# environment but are NOT used by this app. Excluding them keeps the .exe small
# (otherwise torch alone adds ~2 GB) and the build fast.
EXCLUDES = [
    "torch", "torchvision", "torchaudio",
    "tensorflow", "transformers", "sentencepiece",
    "scipy", "sympy", "numpy",
    "pandas", "matplotlib", "seaborn",
    "sklearn", "scikit-learn", "nltk", "gensim",
    "cv2", "PyQt5", "PySide2", "PySide6", "wx",
    "IPython", "ipykernel", "jupyter", "notebook", "nbconvert",
    "lxml", "bs4", "pytest", "setuptools",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SinhalaProofreader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)
