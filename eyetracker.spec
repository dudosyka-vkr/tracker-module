# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building EyeTracker.

Produces:
  - Windows: dist/EyeTracker.exe  (single-file)
  - macOS:   dist/EyeTracker.app  (application bundle, onedir — fast startup)
"""

import platform
import sys
from pathlib import Path

import mediapipe

block_cipher = None
is_mac = platform.system() == "Darwin"

# Mediapipe ships native libs and data that must be bundled
mediapipe_dir = Path(mediapipe.__file__).parent

a = Analysis(
    ["eyetracker/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        # MediaPipe package data (native libs, pbtxt configs, etc.)
        (str(mediapipe_dir), "mediapipe"),
        # Pre-downloaded face landmarker model (if present)
        ("eyetracker/models", "eyetracker/models"),
        # App icons and static assets
        ("eyetracker/assets", "eyetracker/assets"),
    ],
    hiddenimports=[
        "mediapipe",
        "mediapipe.tasks",
        "mediapipe.tasks.python",
        "mediapipe.tasks.python.vision",
        "mediapipe.tasks.python.core",
        "numpy",
        "cv2",
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if is_mac:
    # macOS: onedir mode — files live inside .app bundle, no temp extraction
    exe = EXE(
        pyz,
        a.scripts,
        [],
        name="EyeTracker",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        exclude_binaries=True,
        icon="eyetracker/assets/icon.icns" if is_mac else "eyetracker/assets/icon.ico",
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="EyeTracker",
    )

    app = BUNDLE(
        coll,
        name="EyeTracker.app",
        icon="eyetracker/assets/icon.icns",
        bundle_identifier="com.eyetracker.app",
        info_plist={
            "CFBundleName": "EyeTracker",
            "CFBundleDisplayName": "EyeTracker",
            "CFBundleVersion": "0.1.0",
            "CFBundleShortVersionString": "0.1.0",
            "NSCameraUsageDescription": "Приложению необходим доступ к камере для отслеживания взгляда.",
            "NSHighResolutionCapable": True,
        },
    )
else:
    # Windows: single-file .exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="EyeTracker",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="eyetracker/assets/icon.ico",
    )
