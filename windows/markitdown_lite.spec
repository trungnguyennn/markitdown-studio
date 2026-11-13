# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MarkItDown Studio Lite (single small .exe).
# Build with windows\build_lite.bat

import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.dirname(os.path.abspath(SPECPATH))  # project root (this file is one level below it)

# Modules that must never be bundled (heavy, unused, or replaced by markitdown_lite/shims.py).
EXCLUDES = [
    # replaced by shims / not used in Lite
    "magika", "onnxruntime", "numpy", "pandas", "requests", "urllib3", "certifi", "idna",
    "cryptography", "PIL", "lxml", "PySide6", "shiboken6", "pdfplumber", "pypdfium2",
    # stdlib not used by the app
    "_ssl", "ssl", "_hashlib", "sqlite3", "_sqlite3", "unittest", "pydoc", "doctest", "pdb",
    "lzma", "_lzma", "bz2", "_bz2", "_decimal", "asyncio", "multiprocessing", "xmlrpc",
    "ftplib", "http.server", "curses", "distutils", "setuptools", "pkg_resources",
    "tkinter.tix", "turtle", "turtledemo", "idlelib", "lib2to3", "venv", "ensurepip",
]

# Tcl encodings to keep: small single-byte code pages. Tk on Windows talks to
# the OS through Unicode APIs, so the big double-byte tables are not needed.
MAX_ENCODING_BYTES = 20_000


def keep_data(dest: str, src: str) -> bool:
    d = dest.replace("\\", "/")
    if d.startswith("pdfminer/cmap/"):
        return False  # ~6 MB of CJK CMaps (only needed for CJK PDFs using predefined Adobe CMaps)
    if d.startswith(("_tcl_data/tzdata/", "_tcl_data/msgs/")):
        return False  # Tcl `clock` time zones and translations - unused by tkinter
    if d.startswith("_tcl_data/encoding/"):
        return os.path.getsize(src) <= MAX_ENCODING_BYTES
    return True


a = Analysis(
    [os.path.join(ROOT, "main_lite.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "assets", "app.ico"), "assets"),
        (os.path.join(ROOT, "assets", "app.png"), "assets"),
    ] + collect_data_files("sv_ttk"),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,  # strip docstrings and asserts from bundled bytecode
)

a.datas = [entry for entry in a.datas if keep_data(entry[0], entry[1])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MarkItDownStudio-Lite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=os.path.join(ROOT, "windows", "installer", "version_info.txt"),
)
