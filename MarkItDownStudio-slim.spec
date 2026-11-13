# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: Full edition, trimmed for size. This is the macOS build
# (-> dist/mac/MarkItDown Studio.app). It also builds on Windows
# (-> dist\slim\MarkItDownStudio\) so the trimming rules can be tested there.
#
#   macOS:    ./build_mac.sh
#   Windows:  .venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist\slim --workpath build\slim MarkItDownStudio-slim.spec
#
# Every feature of the Full edition is kept; see tools/size_trim.py for what is left out and why.

import os
import platform
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

ROOT = os.path.abspath(SPECPATH)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import size_trim  # noqa: E402
from markitdown_app import APP_NAME, BUNDLE_ID, COPYRIGHT, __version__  # noqa: E402
from markitdown_app.core import SUPPORTED_EXTENSIONS  # noqa: E402

IS_MAC = sys.platform == "darwin"

datas, binaries, hiddenimports = [], [], []
datas += collect_data_files("pdfminer")
datas += collect_data_files("pptx")
datas += copy_metadata("markitdown")
datas += copy_metadata("magika")
for package in ("markitdown", "magika"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=size_trim.EXCLUDES,
    noarchive=bool(os.environ.get("MDS_NOARCHIVE")),  # loose .pyc files: used by the LZMA portable build
    optimize=2,  # drop docstrings and asserts from the bundled bytecode
)
# One CPU architecture per build: Qt and Python ship as universal (arm64 + x86_64)
# binaries, and naming the target makes PyInstaller keep only that half.
# MAC_ARCH=universal2 builds a single app for both, at roughly twice the size.
target_arch = (os.environ.get("MAC_ARCH") or platform.machine()) if IS_MAC else None

# Dropping onnxruntime's second engine copy is verified on Windows and Apple Silicon.
# On Intel Macs (which get an older onnxruntime) the self-test hung with it removed,
# so it is kept there.
size_trim.trim(a, drop_duplicate_onnxruntime=target_arch in (None, "arm64"))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MarkItDownStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=IS_MAC,  # remove debug symbols (needs Xcode command line tools)
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,  # Finder "Open With" is handled in markitdown_app/app.py
    target_arch=target_arch,
    codesign_identity=os.environ.get("CODESIGN_IDENTITY") or None,  # default: ad-hoc signature
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "app.icns" if IS_MAC else "app.ico"),
    version=None if IS_MAC else os.path.join(ROOT, "installer", "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=IS_MAC,
    upx=False,
    name="MarkItDownStudio",
)

if IS_MAC:
    extensions = sorted({e.lstrip(".") for group in SUPPORTED_EXTENSIONS.values() for e in group})
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=os.path.join(ROOT, "assets", "app.icns"),
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHumanReadableCopyright": COPYRIGHT,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # allow the dark title bar
            "LSApplicationCategoryType": "public.app-category.productivity",
            # Adds the app to Finder's "Open With" for the supported files
            # (the Windows installer offers the same thing as an option).
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Document convertible to Markdown",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "CFBundleTypeExtensions": extensions,
                }
            ],
        },
    )
