"""Fluent-inspired dark theme (Windows 11 dark palette), also used on macOS."""

from __future__ import annotations

import re
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette
from PySide6.QtWidgets import QApplication

# Windows 11 dark-mode tokens
BG = "#202020"  # Mica-like window background
LAYER = "#272727"  # cards
LAYER_ALT = "#2D2D2D"  # inputs / hover
STROKE = "#363636"
STROKE_STRONG = "#454545"
TEXT = "#FFFFFF"
TEXT_SECONDARY = "#C5C5C5"
TEXT_TERTIARY = "#8A8A8A"
ACCENT = "#60CDFF"
ACCENT_HOVER = "#5AB9E6"
ACCENT_PRESSED = "#4FA3CC"
ON_ACCENT = "#000000"
SUCCESS = "#6CCB5F"
CRITICAL = "#FF99A4"
CAUTION = "#FCE100"

IS_MAC = sys.platform == "darwin"

# A point is 1/72 inch. Windows lays text out at 96 px per inch and macOS at 72,
# so the same point size is a quarter smaller on a Mac. Scaling by 4/3 gives the
# same pixel sizes on both (10 pt on Windows = 13 pt on macOS, its standard size).
PT_SCALE = 4 / 3 if IS_MAC else 1.0

if IS_MAC:
    MONO_FAMILIES = ["Menlo", "Monaco"]
    UI_FAMILIES: list[str] = []  # keep the system font (San Francisco)
else:
    MONO_FAMILIES = ["Cascadia Mono", "Cascadia Code", "Consolas"]
    UI_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]


def pt(points: float) -> float:
    """A Windows point size converted for the current platform."""
    return round(points * PT_SCALE, 1)


def shortcut_text(keys) -> str:
    """Shortcut as the platform writes it: 'Ctrl+O' on Windows, the Command symbol + O on macOS."""
    return QKeySequence(keys).toString(QKeySequence.SequenceFormat.NativeText)


QSS = f"""
* {{
    outline: none;
}}
QMainWindow, QWidget#Root {{
    background: {BG};
}}
QWidget {{
    color: {TEXT};
    font-size: 10pt;
}}
QLabel#Title {{
    font-size: 20pt;
    font-weight: 600;
}}
QLabel#Subtitle, QLabel#Secondary {{
    color: {TEXT_SECONDARY};
}}
QLabel#Tertiary {{
    color: {TEXT_TERTIARY};
    font-size: 9pt;
}}
QLabel#SectionLabel {{
    font-size: 11pt;
    font-weight: 600;
}}
QLabel#FileName {{
    font-size: 12pt;
    font-weight: 600;
}}
QLabel#BigMessage {{
    font-size: 13pt;
    font-weight: 600;
}}

QFrame#Card {{
    background: {LAYER};
    border: 1px solid {STROKE};
    border-radius: 8px;
}}
QFrame#DropZone {{
    background: {LAYER_ALT};
    border: 2px dashed {STROKE_STRONG};
    border-radius: 8px;
}}
QFrame#DropZone[dragActive="true"] {{
    border-color: {ACCENT};
    background: #24323A;
}}

QPushButton {{
    background: {LAYER_ALT};
    border: 1px solid {STROKE_STRONG};
    border-bottom-color: #3A3A3A;
    border-radius: 4px;
    padding: 6px 14px;
    min-height: 20px;
}}
QPushButton:hover {{
    background: #323232;
}}
QPushButton:pressed {{
    background: #2A2A2A;
    color: {TEXT_SECONDARY};
}}
QPushButton:disabled {{
    color: #5D5D5D;
    background: #2A2A2A;
    border-color: {STROKE};
}}
QPushButton[accent="true"] {{
    background: {ACCENT};
    color: {ON_ACCENT};
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton[accent="true"]:pressed {{
    background: {ACCENT_PRESSED};
    border-color: {ACCENT_PRESSED};
}}
QPushButton[accent="true"]:disabled {{
    background: #434343;
    border-color: #434343;
    color: #A0A0A0;
}}
QPushButton#Segment {{
    border-radius: 0px;
    padding: 5px 14px;
}}
QPushButton#Segment[first="true"] {{
    border-top-left-radius: 4px;
    border-bottom-left-radius: 4px;
}}
QPushButton#Segment[last="true"] {{
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    border-left: none;
}}
QPushButton#Segment:checked {{
    background: {ACCENT};
    color: {ON_ACCENT};
    border-color: {ACCENT};
    font-weight: 600;
}}
QPushButton#Subtle {{
    background: transparent;
    border: 1px solid transparent;
}}
QPushButton#Subtle:hover {{
    background: #2F2F2F;
}}

QListWidget {{
    background: transparent;
    border: none;
}}
QListWidget::item {{
    padding: 8px 8px;
    margin: 1px 0px;
    border-radius: 4px;
    color: {TEXT};
}}
QListWidget::item:hover {{
    background: #2F2F2F;
}}
QListWidget::item:selected {{
    background: #353535;
    border-left: 3px solid {ACCENT};
}}

QPlainTextEdit, QTextBrowser {{
    background: #1C1C1C;
    border: 1px solid {STROKE};
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #0F6CBD;
    selection-color: {TEXT};
}}
QPlainTextEdit:focus {{
    border-bottom: 2px solid {ACCENT};
}}
QPlainTextEdit#LogView {{
    font-size: 9pt;
    background: #1A1A1A;
}}

QProgressBar {{
    background: #3A3A3A;
    border: none;
    border-radius: 2px;
    max-height: 4px;
    min-height: 4px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}

QStatusBar {{
    background: {BG};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {STROKE};
}}
QStatusBar::item {{
    border: none;
}}

QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #5A5A5A;
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: #8A8A8A; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #5A5A5A;
    border-radius: 3px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{ background: #8A8A8A; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QMenu {{
    background: #2C2C2C;
    border: 1px solid {STROKE_STRONG};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{ background: #3A3A3A; }}
QMenu::item:disabled {{ color: #5D5D5D; }}
QMenu::separator {{ height: 1px; background: {STROKE_STRONG}; margin: 4px 8px; }}

QToolTip {{
    background: #2C2C2C;
    color: {TEXT};
    border: 1px solid {STROKE_STRONG};
    border-radius: 4px;
    padding: 4px 8px;
}}

QMessageBox, QDialog {{
    background: {LAYER};
}}
QMessageBox QPushButton {{
    min-width: 80px;
}}
"""


if PT_SCALE != 1.0:
    QSS = re.sub(r"(\d+)pt\b", lambda m: f"{pt(int(m.group(1))):g}pt", QSS)


def build_palette() -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    p.setColor(role.Window, QColor(BG))
    p.setColor(role.WindowText, QColor(TEXT))
    p.setColor(role.Base, QColor("#1C1C1C"))
    p.setColor(role.AlternateBase, QColor(LAYER))
    p.setColor(role.Text, QColor(TEXT))
    p.setColor(role.Button, QColor(LAYER_ALT))
    p.setColor(role.ButtonText, QColor(TEXT))
    p.setColor(role.Highlight, QColor("#0F6CBD"))
    p.setColor(role.HighlightedText, QColor(TEXT))
    p.setColor(role.ToolTipBase, QColor("#2C2C2C"))
    p.setColor(role.ToolTipText, QColor(TEXT))
    p.setColor(role.PlaceholderText, QColor(TEXT_TERTIARY))
    p.setColor(role.Link, QColor(ACCENT))
    p.setColor(role.LinkVisited, QColor("#B4A0FF"))
    if hasattr(role, "Accent"):  # Qt >= 6.6
        p.setColor(role.Accent, QColor(ACCENT))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(disabled, r, QColor("#5D5D5D"))
    return p


def ui_font(point_size: float = 10) -> QFont:
    font = QFont()
    if UI_FAMILIES:
        font.setFamilies(UI_FAMILIES)
    font.setPointSizeF(pt(point_size))
    return font


def mono_font(point_size: float = 10) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(pt(point_size))
    return font


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    hints = app.styleHints()
    # Qt >= 6.8: tells Windows to draw a dark title bar and dark native dialogs.
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark)
    app.setPalette(build_palette())
    app.setFont(ui_font(10))
    app.setStyleSheet(QSS)
