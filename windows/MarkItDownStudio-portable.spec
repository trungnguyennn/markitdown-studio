# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: Full edition as ONE small portable exe for Windows.
#   -> dist\portable\MarkItDownStudio-Portable.exe        (build with windows\build_portable.bat)
#
# Same app and same features as the installer build. Two things keep it small:
#   1. tools/size_trim.py leaves out files the app can never load (see its header).
#   2. Most files are stored in LZMA streams appended to the exe instead of
#      PyInstaller's zlib archive; tools/portable_boot.py unpacks them at start-up
#      into the temporary folder PyInstaller uses anyway.

import os
import shutil
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

ROOT = os.path.dirname(os.path.abspath(SPECPATH))  # project root (this file is one level below it)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import lzma_onefile  # noqa: E402
import size_trim  # noqa: E402

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
    # Custom run-time hooks run before PyInstaller's own, so the files are in place for them.
    runtime_hooks=[os.path.join(ROOT, "tools", "portable_boot.py")],
    excludes=size_trim.EXCLUDES,
    noarchive=True,  # Python modules as loose .pyc files: LZMA packs them much better than a zlib PYZ
    optimize=2,  # drop docstrings and asserts from the bundled bytecode
)
size_trim.trim(a)
pyz = PYZ(a.pure)

ICON = os.path.join(ROOT, "assets", "app.ico")
VERSION = os.path.join(ROOT, "windows", "installer", "version_info.txt")

# Step 1: a throw-away folder build. Running it in probe mode tells us exactly which
# files Python needs before the boot hook has run; only those stay in PyInstaller's archive.
probe_exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="probe",
    debug=False, strip=False, upx=False, console=False,
)
probe_dir = COLLECT(probe_exe, a.binaries, a.datas, strip=False, upx=False, name="portable-probe")
needed = lzma_onefile.probe(os.path.join(probe_dir.name, "probe.exe"))
keep_bin, keep_data, payload = lzma_onefile.split(a.binaries, a.datas, needed)

# Step 2: the real one-file exe, then the LZMA payload appended to it.
# (Remove an earlier result first: PyInstaller would otherwise reuse it and the
# payload would be appended a second time.)
_final = os.path.join(DISTPATH, "MarkItDownStudio-Portable.exe")
if os.path.exists(_final):
    os.remove(_final)
exe = EXE(
    pyz,
    a.scripts,
    keep_bin,
    keep_data,
    [],
    name="MarkItDownStudio-Portable",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON,
    version=VERSION,
)
lzma_onefile.append_payload(exe.name, payload)
shutil.rmtree(probe_dir.name, ignore_errors=True)
