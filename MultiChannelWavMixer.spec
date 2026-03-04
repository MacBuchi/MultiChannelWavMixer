# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MultiChannelWavMixer
Build with:  uv run pyinstaller MultiChannelWavMixer.spec
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Data files to bundle ────────────────────────────────────────────────────────
datas = []

# customtkinter — themes, images, assets
datas += collect_data_files("customtkinter")

# librosa — some datasets/filters shipped as package data
datas += collect_data_files("librosa")

# pyloudnorm — no package data, but include for safety
datas += collect_data_files("pyloudnorm")

# matplotlib — fonts, style sheets, etc.
datas += collect_data_files("matplotlib")

# soundfile native library (libsndfile) — resolved portably so local
# and CI runner builds both work without a hardcoded .venv path.
datas += collect_data_files("soundfile")

# ── Hidden imports ──────────────────────────────────────────────────────────────
hiddenimports = [
    # customtkinter
    "customtkinter",
    # sounddevice / soundfile backends
    "sounddevice",
    "soundfile",
    "cffi",
    "_cffi_backend",
    # audio / signal processing
    "librosa",
    "librosa.core",
    "librosa.feature",
    "librosa.util",
    "pyloudnorm",
    "pydub",
    "pydub.audio_segment",
    "pydub.effects",
    "pydub.silence",
    "audioop",
    # numpy / scipy internals
    "numpy",
    "numpy.core",
    "scipy",
    "scipy.signal",
    "scipy.fft",
    # matplotlib backends
    "matplotlib",
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_agg",
    # tkinter
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    # misc
    "xml.etree.ElementTree",
    "numba",
    "llvmlite",
]

# collect all submodules of scipy and librosa to avoid missing-module errors
hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("librosa")

# ── Analysis ────────────────────────────────────────────────────────────────────
a = Analysis(
    ["MultiChannelWavMixer.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_env.py"],
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "wx", "gi",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── macOS .app bundle ───────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MultiChannelWavMixer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,       # native arch; use 'universal2' for fat binary
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
    name="MultiChannelWavMixer",
)

app = BUNDLE(
    coll,
    name="MultiChannelWavMixer.app",
    icon=None,              # set to "path/to/icon.icns" when available
    bundle_identifier="com.macbuchi.multichannelwavmixer",
    info_plist={
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Required for audio playback via sounddevice.",
        "LSUIElement": False,
    },
)
