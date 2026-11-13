"""Size trimming rules for the Full edition (used by MarkItDownStudio-slim.spec).

Rule of the house: nothing the app can do is removed and nothing is swapped for
a lighter stand-in. Only files that the app can never load are left out:

* Qt modules the app does not use (it needs QtCore, QtGui, QtWidgets only),
  together with the Qt plugins that are the sole reason those modules get
  bundled (virtual keyboard -> Qt Quick/QML, TUIO touch + TLS -> Qt Network...).
  A Qt library is only dropped when no remaining binary links against it.
* Qt's own UI translations (the app is English-only and installs no translator).
* Files for other operating systems (FLAC encoders for Windows/Linux on a Mac).
* The offline PocketSphinx speech model: it needs the `pocketsphinx` package,
  which is not installed, so it is unreachable. Audio is transcribed with
  `recognize_google`, exactly as before.
* Python packages no code path of the app reaches (Azure Document Intelligence
  client, packaging tools).
"""

from __future__ import annotations

import re
import sys

# --------------------------------------------------------------- Python modules
EXCLUDES = [
    "tkinter", "_tkinter",
    # Qt bindings the app does not import
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtDBus", "PySide6.QtVirtualKeyboard", "PySide6.QtSvgWidgets",
    # markitdown only uses these when it is given an Azure endpoint; the app never passes one
    "azure", "msal", "msal_extensions",
    # (xlsxwriter stays: python-pptx imports it in its chart code, used for PPTX charts)
    # build-time tooling
    "setuptools", "pkg_resources", "_distutils_hack", "pip", "wheel",
    # text of Python's interactive help() topics
    "pydoc_data",
]

# ------------------------------------------------------------------- Qt plugins
# plugin folder -> file-name fragments to keep (None keeps the whole folder)
if sys.platform == "darwin":
    _PLATFORM_PLUGINS = ("qcocoa",)
elif sys.platform == "win32":
    _PLATFORM_PLUGINS = ("qwindows",)
else:
    _PLATFORM_PLUGINS = None
QT_PLUGINS_KEPT = {
    "platforms": _PLATFORM_PLUGINS,
    "styles": None,
    "iconengines": None,
    "imageformats": None,  # all image readers stay, except the PDF one below
}
# "qpdf" renders a PDF as if it were a picture; it is the only user of the 4.5 MB Qt PDF module.
QT_PLUGINS_DROPPED = ("imageformats/qpdf", "imageformats/libqpdf")

_PLUGIN_RE = re.compile(r"(?:^|/)plugins/([^/]+)/([^/]+)$")
_QT_FRAMEWORK_RE = re.compile(r"(?:^|/)(Qt[A-Za-z0-9]+)\.framework/")  # macOS
_QT_DLL_RE = re.compile(r"(?:^|/)Qt6([A-Za-z0-9]+)\.dll$", re.IGNORECASE)  # Windows
_QT_SO_RE = re.compile(r"(?:^|/)libQt6([A-Za-z0-9]+)\.so[.\d]*$")  # Linux
# How a binary names the Qt libraries it links against (plain ASCII inside the file).
_LINK_RES = (
    re.compile(rb"(Qt[A-Za-z0-9]+)\.framework/"),
    re.compile(rb"Qt6([A-Za-z0-9]+)\.dll", re.IGNORECASE),
    re.compile(rb"libQt6([A-Za-z0-9]+)\.so"),
)


def _norm(dest: str) -> str:
    return dest.replace("\\", "/")


def qt_library(dest: str) -> str | None:
    """'QtGui' if *dest* belongs to that Qt library (any file inside its framework), else None."""
    d = _norm(dest)
    m = _QT_FRAMEWORK_RE.search(d)
    if m:
        return m.group(1)
    m = _QT_DLL_RE.search(d) or _QT_SO_RE.search(d)
    if m:
        return "Qt" + m.group(1)
    return None


def _linked_qt_libraries(path: str) -> set[str]:
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return set()
    found = {m.group(1).decode() for m in _LINK_RES[0].finditer(blob)}
    for pattern in _LINK_RES[1:]:
        found |= {"Qt" + m.group(1).decode() for m in pattern.finditer(blob)}
    return found


def _unwanted(dest: str) -> str | None:
    """Reason for leaving *dest* out, or None to keep it. Qt libraries are handled separately."""
    d = _norm(dest)
    low = d.lower()

    m = _PLUGIN_RE.search(d)
    if m and "PySide6" in d:
        kind, name = m.group(1), m.group(2).lower()
        if kind not in QT_PLUGINS_KEPT:
            return f"Qt plugin type '{kind}' is not used"
        if any(low.endswith(x) or f"{x}." in low for x in QT_PLUGINS_DROPPED):
            return "Qt PDF-as-image plugin is not used"
        wanted = QT_PLUGINS_KEPT[kind]
        if wanted is not None and not any(w in name for w in wanted):
            return "Qt platform plugin for another windowing system"
        return None

    if "PySide6" in d and "/translations/" in d:
        return "Qt UI translations (app is English-only)"
    if low.endswith("opengl32sw.dll"):
        return "software OpenGL fallback (the app does not use OpenGL)"

    if "speech_recognition/pocketsphinx-data/" in d:
        return "offline PocketSphinx model (its engine is not installed)"
    if "speech_recognition/flac-" in d:
        base = d.rsplit("/", 1)[-1]
        mine = {"darwin": "flac-mac", "win32": "flac-win32.exe"}.get(sys.platform)
        if mine is None:
            mine = "flac-linux"
        if not base.startswith(mine):
            return "FLAC encoder for another operating system"
    return None


def trim(analysis, log=print) -> None:
    """Filter analysis.binaries / analysis.datas in place and log what was saved."""
    import os

    removed: dict[str, int] = {}

    def size_of(src: str) -> int:
        try:
            return os.path.getsize(src)
        except OSError:
            return 0

    def drop(entry, reason: str) -> None:
        removed[reason] = removed.get(reason, 0) + size_of(entry[1])

    # Pass 1: rule-based removals.
    kept_bin, kept_data = [], []
    for source, kept in ((analysis.binaries, kept_bin), (analysis.datas, kept_data)):
        for entry in source:
            reason = _unwanted(entry[0])
            if reason:
                drop(entry, reason)
            else:
                kept.append(entry)

    # Pass 2: keep only the Qt libraries still linked by something that remains.
    needed: set[str] = set()
    libs: dict[str, str] = {}  # Qt library name -> path of its main binary
    for dest, src, _kind in kept_bin:
        name = qt_library(dest)
        if name is None:
            needed |= _linked_qt_libraries(src)  # extension modules, plugins, other libraries
        else:
            libs.setdefault(name, src)
    frontier = set(needed)
    while frontier:  # follow library -> library links
        name = frontier.pop()
        if name in libs:
            more = _linked_qt_libraries(libs[name]) - needed
            needed |= more
            frontier |= more

    def qt_ok(entry) -> bool:
        name = qt_library(entry[0])
        if name is None or name in needed:
            return True
        drop(entry, f"Qt library not linked by anything: {name}")
        return False

    analysis.binaries[:] = [e for e in kept_bin if qt_ok(e)]
    analysis.datas[:] = [e for e in kept_data if qt_ok(e)]

    log("size_trim: Qt libraries kept: " + ", ".join(sorted(n for n in libs if n in needed)))
    for reason, size in sorted(removed.items(), key=lambda kv: -kv[1]):
        log(f"size_trim: -{size / 1e6:7.2f} MB  {reason}")
    log(f"size_trim: -{sum(removed.values()) / 1e6:7.2f} MB  total (before compression)")
