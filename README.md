# MarkItDown Studio

Copyright 2026 Nguyen Tran Trung. All rights reserved.

A native-feeling Windows 10/11 and macOS desktop app (Python + PySide6/Qt 6) that converts
documents to Markdown with [Microsoft MarkItDown](https://github.com/microsoft/markitdown),
ready for LLMs and text-analysis pipelines.

## Downloads

Ready-to-run apps are on the [Releases page](../../releases/latest).

| System | File | What it is |
|---|---|---|
| Windows 10/11 | `MarkItDownStudio-1.0.0-Windows-Setup.exe` | installer (Start menu entry, uninstaller) |
| Windows 10/11 | `MarkItDownStudio-1.0.0-Windows-Portable.exe` | one file, no install, all features |
| Windows 10/11 | `MarkItDownStudio-Lite-1.0.0-Windows-Portable.exe` | one small file, fewer formats (see below) |
| macOS, Apple Silicon | `MarkItDownStudio-1.0.0-macOS-AppleSilicon.dmg` | disk image; drag the app to Applications |

Source code is organised the same way: [`windows/`](windows/) and [`macos/`](macos/) hold each
system's scripts and build recipes, and the app code they share sits at the top level.

## Features

- Fluent-style dark dashboard (Windows 11 dark palette, dark title bar, Segoe Fluent icons)
- **Browse files** button (Ctrl+O) **and** drag-and-drop; multi-file queue
- Conversion runs on a background thread; the UI never freezes
- Editable Markdown source view + rendered **Preview**
- **Export .md** (Ctrl+S), **Export all** to a folder (Ctrl+Shift+S), **Copy** (Ctrl+Shift+C)
- Friendly error messages for unsupported, corrupted, locked, empty or password-protected files
- Activity log panel + rotating log file at `%LOCALAPPDATA%\MarkItDownStudio\logs\app.log`
- Remembers window size, splitter layout and last-used folders
- **About** dialog (header button or F1) with version and copyright notice

The copyright text lives in one place, `COPYRIGHT` in `markitdown_app/__init__.py`, which both
editions' About dialogs use. The same text is also in `windows/installer/version_info.txt` (shown under the
.exe's Properties → Details) and `windows/installer/MarkItDownStudio.iss` (installer and Apps & features).

Supported inputs (via `markitdown[all]`): PDF, DOCX, PPTX, XLSX/XLS, EPUB, Outlook MSG,
HTML, CSV, JSON, XML, IPYNB, TXT, images (EXIF metadata), audio (metadata/transcription), ZIP.

## Project structure

The app code is shared by both systems. Each system has its own folder with its scripts and build recipes.

```
markitdown-studio/
├── main.py, main_lite.py    # entry points (Full, Lite)
├── markitdown_app/          # shared app code: Full edition (Qt) + conversion core
├── markitdown_lite/         # Lite edition (Tkinter, Windows)
├── assets/                  # icons
├── tools/                   # icon generator, samples, size rules, LZMA packer
├── requirements.txt, requirements-lite.txt
├── windows/                 # WINDOWS VERSION  (see windows/README.md)
│   ├── setup.bat, run.bat
│   ├── build.bat, make_installer.bat, build_portable.bat
│   ├── setup_lite.bat, build_lite.bat
│   ├── MarkItDownStudio-portable.spec, markitdown_lite.spec
│   └── installer/           # Inno Setup script, version info, notices
└── macos/                   # MACOS VERSION  (see macos/README.md)
    ├── setup_mac.sh, run_mac.sh, build_mac.sh
    └── MarkItDownStudio-mac.spec
```

Run every script from the project root, for example `windows\run.bat` or `bash macos/run_mac.sh`.

## Editions and sizes

| Build | Command | Output | Size |
|---|---|---|---|
| Full, installer | `windows\make_installer.bat` | `dist\installer\MarkItDownStudio-Setup-1.0.0.exe` | 107 MB |
| Full, portable one file | `windows\build_portable.bat` | `dist\portable\MarkItDownStudio-Portable.exe` | 53 MB |
| **Lite, portable one file** | `windows\build_lite.bat` | `dist\lite\MarkItDownStudio-Lite.exe` | **9.7 MB** |

The Lite edition opens in about 1 second, compared with about 4 seconds for the Full portable build.

### Where the Full edition's size goes, and how Lite avoids it

| Full edition component (unpacked) | Size | Lite edition |
|---|---|---|
| PySide6 / Qt UI | 94 MB | Tkinter (ships with Python) + sv-ttk Windows 11 theme |
| speech_recognition (audio) | 43 MB | not included |
| onnxruntime + numpy + magika (AI file-type sniffing) | 70 MB | stand-in; type is detected from the file extension |
| pandas (Excel) | 13 MB | own XLSX/XLS converter with openpyxl / xlrd |
| pdfplumber + pypdfium2 + Pillow | 21 MB | PDF through pdfminer only (markitdown's own fallback path) |
| cryptography + OpenSSL | 21 MB | stand-in (only AES-encrypted PDFs are affected) |
| python-pptx + lxml | 7 MB+ | own PPTX converter using only the standard library |
| pdfminer CJK CMaps | 6 MB (compressed) | removed |

### What Lite does not do (use the Full edition for these)

- Rendered Markdown **Preview** (Lite shows the editable Markdown source only)
- Audio transcription and image metadata
- Converting URLs (Lite is offline-only: it never opens a network connection)
- PDF table detection (pdfplumber). Lite extracts PDF text in reading order.
- AES-encrypted PDFs
- CJK PDFs whose fonts rely on Adobe's predefined CMaps instead of an embedded Unicode map
  (most modern PDFs embed the map; the tested Chinese/Japanese/Korean sample converted fine)
- PPTX charts and SmartArt (text, tables, picture alt text and speaker notes are extracted)
- Content-based detection of files with a wrong or missing extension

### Build the Lite edition

```bash
windows\setup_lite.bat
```

```bash
windows\build_lite.bat
```

Run it from source with:

```bash
.venv-lite\Scripts\python.exe main_lite.py
```

## macOS version

The Mac app is the **Full edition**: same code, same converters, same features as on Windows
(PySide6/Qt UI, `markitdown[all]`). Nothing is replaced by a lighter stand-in.

| File | Purpose |
|---|---|
| `macos/setup_mac.sh` | create `.venv-mac` and install `requirements.txt` |
| `macos/run_mac.sh` | run from source |
| `macos/build_mac.sh` | build `dist/mac/MarkItDown Studio.app`, self-test it, package a `.dmg` |
| `macos/MarkItDownStudio-mac.spec` | PyInstaller spec for the Mac app |
| `tools/size_trim.py` | the size rules, each with its reason |
| `tools/make_samples.py` | one sample file per format, for the self-test |
| `.github/workflows/build-macos.yml` | builds the `.dmg` on GitHub's Macs (no Mac needed) |

### Build on a Mac

Needs Python 3.10–3.13 and the Xcode command line tools (`xcode-select --install`).

```bash
bash macos/build_mac.sh
```

Output: `dist/mac/MarkItDown Studio.app` (189 MB installed) and
`dist/mac/MarkItDownStudio-1.0.0-mac-arm64.dmg` (59 MB to share).

The supported target is **Apple Silicon** (M-series Macs). Intel Macs are not a target: the Intel
build hung in its self-test on GitHub's Intel machines and was dropped instead of investigated.

A Mac app cannot be built on Windows (PyInstaller does not cross-compile). Without a Mac, push the
project to a GitHub repository and run the **Build macOS app** workflow from the Actions tab; it
attaches the `.dmg` and a self-test screenshot to the run.

### How the size is kept down (no feature removed)

Measured by building the same spec on Windows, where it takes the app folder from 305 MB to 183 MB;
all 16 sample files convert to byte-identical Markdown before and after.

| Left out | Why the app never needs it | Windows size |
|---|---|---|
| PocketSphinx offline speech model | its engine (`pocketsphinx`) is not installed; audio uses `recognize_google` as before | 39 MB |
| Qt Quick, QML, PDF, Network, OpenGL, virtual keyboard | the app uses QtCore, QtGui, QtWidgets; a Qt library is dropped only when no remaining binary links to it | 22 MB |
| Qt UI translations | the app is English-only | 7 MB |
| FLAC encoders for other operating systems | only the Mac one can run on a Mac | 2–5 MB |
| Azure client, MSAL, setuptools | markitdown only uses Azure when given an endpoint, which the app never does | 3 MB |
| Second copy of the onnxruntime engine | the wheel also ships it as a stand-alone library for C/C++ programs; Python never loads it | 19 MB (31 MB on Mac) |
| Second CPU architecture | Apple Silicon only instead of a universal binary | about half of Qt and Python |

Also applied: debug symbols stripped, bytecode without docstrings (`optimize=2`), LZMA-compressed
`.dmg`. Kept in full: PDF tables (pdfplumber), CJK CMaps, encrypted PDFs (cryptography), pandas,
magika content detection, Pillow, python-pptx charts, audio transcription.

### Differences from Windows

- Icons are drawn as vector shapes (the Segoe icon fonts exist only on Windows).
- Shortcuts use ⌘ (⌘O, ⌘S, ⇧⌘S, ⇧⌘C); Backspace also removes a queue item; commands are in the menu bar too.
- Files opened from Finder (**Open With**, or dropped on the Dock icon) are queued.
- Log file: `~/Library/Logs/MarkItDownStudio/app.log`. Settings: `~/Library/Preferences`.
- The app is not notarised. On first launch, right-click the app → **Open**, or allow it under
  System Settings → Privacy & Security. Signing with an Apple Developer ID
  (`CODESIGN_IDENTITY=... bash macos/build_mac.sh`) plus notarisation removes the warning.
- Audio on Apple Silicon: the FLAC encoder bundled by the speech library is Intel-only, so it needs
  Rosetta, or `brew install flac`. MP3/M4A need `ffmpeg` on the PATH, as on Windows.

## Setup and run (Windows)

Requires Python 3.10–3.13 (64-bit) from python.org.

```bash
cd "D:\Work\AI\Markdown convert app"
```

```bash
windows\setup.bat
```

```bash
windows\run.bat
```

Manual equivalent:

```bash
py -3 -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe main.py
```

## Build the portable single-file exe (no install)

```bash
windows\build_portable.bat
```

Output: `dist\portable\MarkItDownStudio-Portable.exe` (about 53 MB). Copy it anywhere, such as a USB
stick, the desktop or a network share, and double-click it. No installer, no admin rights and no Python needed.

How it works: each launch unpacks the bundled runtime to a temporary `%TEMP%\_MEIxxxxx` folder, which
is deleted when you close the app. Startup takes about 4 seconds, compared with about 1 second for
the installed version. If the process is killed (Task Manager, crash), that temp folder is left behind
and can be deleted safely.

### How the portable exe got from 152 MB to 53 MB with every feature kept

It is the Full edition: same code, same converters, nothing replaced by a lighter stand-in. On the
16 sample files from `tools/make_samples.py` it produces Markdown byte-identical to the app run from
source, and the files it unpacks are identical to a plain PyInstaller folder build.

| Step | Size |
|---|---|
| Original one-file build (PyInstaller, zlib) | 152 MB |
| Leave out files the app can never load (`tools/size_trim.py`: offline speech model whose engine is not installed, unused Qt modules and translations, a second copy of the onnxruntime engine, FLAC encoders for other systems) | about 85 MB (calculated from the files; this stage was not built as an exe) |
| Store the files in LZMA streams appended to the exe instead of PyInstaller's zlib archive | 57 MB |
| Store pdfminer's gzipped character maps un-gzipped inside the LZMA stream; they are gzipped again while unpacking | 53 MB |

`windows/MarkItDownStudio-portable.spec` drives the build. `tools/lzma_onefile.py` packs the files into four
streams (three for machine code with an x86 filter, one for everything else). `tools/portable_boot.py`
runs first inside the exe and unpacks the streams in four threads into the temporary folder PyInstaller
uses anyway, so start-up time is unchanged. Only the files Python needs before that hook runs
(about 4 MB, found automatically by a probe run during the build) stay in PyInstaller's own archive.
Unpacking needs about 250 MB of free memory for a few seconds.

Settings (window size, last folders) are saved under `HKCU\Software\MarkItDownStudio`, and logs under
`%LOCALAPPDATA%\MarkItDownStudio\logs`, the same as the installed version.

## Build the setup installer (to share)

One-time: install Inno Setup 6.

```bash
winget install --id JRSoftware.InnoSetup -e
```

Build the app and the installer:

```bash
windows\make_installer.bat rebuild
```

Output: `dist\installer\MarkItDownStudio-Setup-1.0.0.exe` (about 105 MB). This single file is what you share.

The installer:
- installs per-user without admin rights by default (it can also install for all users)
- adds a Start menu shortcut, plus an optional desktop icon
- optionally adds the app to Explorer's "Open with" menu for PDF, Office, HTML, CSV and similar files
- registers in Apps & features with a full uninstaller

To release a new version, bump `__version__` in `markitdown_app/__init__.py` and the numbers in
`windows/installer/version_info.txt`, then run `windows\make_installer.bat rebuild`. Keep `AppId` in the `.iss`
unchanged so new versions upgrade in place.

`windows\build.bat` on its own builds only the portable app folder `dist\MarkItDownStudio\`.

Note: the installer isn't code-signed, so Windows SmartScreen will warn
"Windows protected your PC" the first time. Recipients click **More info → Run anyway**. Signing it
with a code-signing certificate removes the warning.
