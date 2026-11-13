"""Icons without image assets.

Windows: glyphs from the system icon fonts. Windows 11 ships "Segoe Fluent
Icons"; Windows 10 ships "Segoe MDL2 Assets". Both share the same code points
for the glyphs used here.

macOS (and anything else): those fonts do not exist, so the same glyphs are
drawn as vector line icons (see _VECTOR below). No font or image is bundled.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QLabel

ICON_FONT_FAMILIES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]

# MARKITDOWN_VECTOR_ICONS=1 forces the macOS drawing path on Windows (for testing).
USE_FONT_GLYPHS = sys.platform == "win32" and not os.environ.get("MARKITDOWN_VECTOR_ICONS")


class Glyph:
    OPEN = ""
    SAVE = ""
    SAVE_ALL = ""
    COPY = ""
    DELETE = ""
    CLEAR = ""
    DOCUMENT = ""
    CHECK = ""
    ERROR = ""
    SYNC = ""
    CLOCK = ""
    UPLOAD = ""
    FOLDER = ""
    RETRY = ""
    PREVIEW = ""
    CODE = ""
    LOG = ""
    WARNING = ""
    INFO = ""


def icon_font(pixel_size: int) -> QFont:
    font = QFont()
    font.setFamilies(ICON_FONT_FAMILIES)
    font.setPixelSize(pixel_size)
    return font


def icon_label_qss(pixel_size: int, color: str) -> str:
    """Stylesheet for a QLabel showing a glyph (QSS beats setFont, so set it here)."""
    families = ", ".join(f"'{f}'" for f in ICON_FONT_FAMILIES)
    return (
        f"font-family: {families}; font-size: {pixel_size}px; color: {color};"
        " background: transparent; border: none;"
    )


# ---------------------------------------------------------------- vector icons
# Each icon is drawn on a 24 x 24 grid with a round-capped 1.7 px stroke.


def _poly(path: QPainterPath, *points: float, close: bool = False) -> None:
    path.moveTo(points[0], points[1])
    for i in range(2, len(points), 2):
        path.lineTo(points[i], points[i + 1])
    if close:
        path.closeSubpath()


def _circle(path: QPainterPath, cx: float = 12, cy: float = 12, r: float = 9) -> None:
    path.addEllipse(QPointF(cx, cy), r, r)


def _floppy(path: QPainterPath, x: float, y: float, s: float) -> None:
    """Floppy disk inside the square (x, y, s, s)."""
    k = s / 16
    _poly(path, x, y, x + 12 * k, y, x + s, y + 4 * k, x + s, y + s, x, y + s, close=True)
    _poly(path, x + 4 * k, y, x + 4 * k, y + 5 * k, x + 11 * k, y + 5 * k, x + 11 * k, y)
    _poly(path, x + 3.5 * k, y + s, x + 3.5 * k, y + 9.5 * k, x + 12.5 * k, y + 9.5 * k, x + 12.5 * k, y + s)


def _v_open(p: QPainterPath, dots: list) -> None:
    _poly(p, 3, 19, 3, 5.5, 9, 5.5, 11, 8, 18.5, 8, 18.5, 11)
    _poly(p, 3, 19, 6, 11, 21.5, 11, 18.5, 19, close=True)


def _v_folder(p: QPainterPath, dots: list) -> None:
    _poly(p, 3, 5.5, 9, 5.5, 11, 8, 21, 8, 21, 19, 3, 19, close=True)


def _v_save(p: QPainterPath, dots: list) -> None:
    _floppy(p, 4, 4, 16)


def _v_save_all(p: QPainterPath, dots: list) -> None:
    _floppy(p, 7.5, 7.5, 13.5)
    _poly(p, 3.5, 16.5, 3.5, 3.5, 14.5, 3.5, 17, 6)


def _v_copy(p: QPainterPath, dots: list) -> None:
    p.addRoundedRect(QRectF(8.5, 8.5, 12, 12), 2, 2)
    _poly(p, 15.5, 5.5, 15.5, 3.5, 3.5, 3.5, 3.5, 15.5, 5.5, 15.5)


def _v_delete(p: QPainterPath, dots: list) -> None:
    _poly(p, 4, 6.5, 20, 6.5)
    _poly(p, 9, 6.5, 9, 3.5, 15, 3.5, 15, 6.5)
    _poly(p, 6, 6.5, 7, 20.5, 17, 20.5, 18, 6.5)
    _poly(p, 10, 10.5, 10, 16.5)
    _poly(p, 14, 10.5, 14, 16.5)


def _v_clear(p: QPainterPath, dots: list) -> None:
    _poly(p, 6, 6, 18, 18)
    _poly(p, 18, 6, 6, 18)


def _v_document(p: QPainterPath, dots: list) -> None:
    _poly(p, 5.5, 3, 14, 3, 18.5, 7.5, 18.5, 21, 5.5, 21, close=True)
    _poly(p, 14, 3, 14, 7.5, 18.5, 7.5)
    _poly(p, 9, 12.5, 15, 12.5)
    _poly(p, 9, 16.5, 15, 16.5)


def _v_check(p: QPainterPath, dots: list) -> None:
    _poly(p, 4.5, 12.5, 9.5, 17.5, 19.5, 6.5)


def _v_error(p: QPainterPath, dots: list) -> None:
    _circle(p)
    _poly(p, 9, 9, 15, 15)
    _poly(p, 15, 9, 9, 15)


def _v_sync(p: QPainterPath, dots: list) -> None:
    box = QRectF(4, 4, 16, 16)
    p.arcMoveTo(box, 180)
    p.arcTo(box, 180, -135)
    p.lineTo(20, 8.5)
    _poly(p, 20, 3.5, 20, 8.5, 15, 8.5)
    p.arcMoveTo(box, 0)
    p.arcTo(box, 0, -135)
    p.lineTo(4, 15.5)
    _poly(p, 4, 20.5, 4, 15.5, 9, 15.5)


def _v_retry(p: QPainterPath, dots: list) -> None:
    box = QRectF(4, 4, 16, 16)
    p.moveTo(4, 8.5)
    p.arcTo(box, 135, -300)
    _poly(p, 4, 3.5, 4, 8.5, 9, 8.5)


def _v_clock(p: QPainterPath, dots: list) -> None:
    _circle(p)
    _poly(p, 12, 7, 12, 12, 15.5, 14)


def _v_upload(p: QPainterPath, dots: list) -> None:
    _poly(p, 12, 15.5, 12, 3.5)
    _poly(p, 7, 8.5, 12, 3.5, 17, 8.5)
    _poly(p, 4, 15.5, 4, 20, 20, 20, 20, 15.5)


def _v_preview(p: QPainterPath, dots: list) -> None:
    p.moveTo(2.5, 12)
    p.quadTo(12, 1.5, 21.5, 12)
    p.quadTo(12, 22.5, 2.5, 12)
    _circle(p, r=3)


def _v_code(p: QPainterPath, dots: list) -> None:
    _poly(p, 8, 7, 3, 12, 8, 17)
    _poly(p, 16, 7, 21, 12, 16, 17)
    _poly(p, 13.5, 5, 10.5, 19)


def _v_log(p: QPainterPath, dots: list) -> None:
    for y in (6, 12, 18):
        _poly(p, 8.5, y, 20, y)
        dots.append((4.5, y))


def _v_warning(p: QPainterPath, dots: list) -> None:
    _poly(p, 12, 3.5, 21.5, 20, 2.5, 20, close=True)
    _poly(p, 12, 9.5, 12, 14)
    dots.append((12, 17))


def _v_info(p: QPainterPath, dots: list) -> None:
    _circle(p)
    _poly(p, 12, 11, 12, 16.5)
    dots.append((12, 7.6))


_VECTOR = {
    Glyph.OPEN: _v_open,
    Glyph.SAVE: _v_save,
    Glyph.SAVE_ALL: _v_save_all,
    Glyph.COPY: _v_copy,
    Glyph.DELETE: _v_delete,
    Glyph.CLEAR: _v_clear,
    Glyph.DOCUMENT: _v_document,
    Glyph.CHECK: _v_check,
    Glyph.ERROR: _v_error,
    Glyph.SYNC: _v_sync,
    Glyph.CLOCK: _v_clock,
    Glyph.UPLOAD: _v_upload,
    Glyph.FOLDER: _v_folder,
    Glyph.RETRY: _v_retry,
    Glyph.PREVIEW: _v_preview,
    Glyph.CODE: _v_code,
    Glyph.LOG: _v_log,
    Glyph.WARNING: _v_warning,
    Glyph.INFO: _v_info,
}


def _paint_vector(painter: QPainter, glyph: str, color: str, size: float) -> None:
    draw = _VECTOR.get(glyph)
    if draw is None:
        return
    path = QPainterPath()
    dots: list[tuple[float, float]] = []
    draw(path, dots)
    painter.scale(size / 24, size / 24)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    for x, y in dots:
        painter.drawEllipse(QPointF(x, y), 1.15, 1.15)


def glyph_pixmap(glyph: str, color: str, size: int = 32, dpr: float = 1.0) -> QPixmap:
    """*size* is in logical pixels; *dpr* > 1 renders extra detail for Retina."""
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if USE_FONT_GLYPHS:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(icon_font(int(size * 0.8)))
        painter.setPen(QColor(color))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    else:
        _paint_vector(painter, glyph, color, size)
    painter.end()
    return pixmap


def set_glyph(label: QLabel, glyph: str, pixel_size: int, color: str) -> None:
    """Show *glyph* in a QLabel: icon-font text on Windows, a drawn pixmap elsewhere."""
    if USE_FONT_GLYPHS:
        label.setText(glyph)
        label.setStyleSheet(icon_label_qss(pixel_size, color))
        return
    app = QGuiApplication.instance()
    dpr = max(2.0, app.devicePixelRatio()) if app is not None else 2.0
    label.setStyleSheet("background: transparent; border: none;")
    label.setPixmap(glyph_pixmap(glyph, color, pixel_size, dpr))


def glyph_icon(glyph: str, color: str = "#FFFFFF", disabled_color: str = "#5D5D5D") -> QIcon:
    icon = QIcon()
    # The drawn icons also get large renditions so Retina displays stay sharp.
    for size in (16, 20, 24, 32, 48) if USE_FONT_GLYPHS else (16, 20, 24, 32, 48, 64, 96):
        icon.addPixmap(glyph_pixmap(glyph, color, size), QIcon.Mode.Normal)
        icon.addPixmap(glyph_pixmap(glyph, disabled_color, size), QIcon.Mode.Disabled)
    return icon


def app_icon() -> QIcon:
    """A simple generated app icon: accent tile with 'M↓'."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_icon_pixmap(size))
    return icon


def app_icon_pixmap(size: int, margin: float = 0.0) -> QPixmap:
    """The tile at *size* px. *margin* (0-0.5) leaves transparent padding, as macOS icons need."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    inset = size * margin
    tile = size - 2 * inset
    rect = QRectF(inset, inset, tile, tile)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#7FD8FF"))
    grad.setColorAt(1.0, QColor("#2C8FD6"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    radius = tile * 0.22
    p.drawRoundedRect(rect, radius, radius)
    font = QFont()
    font.setFamilies(["Segoe UI", "Helvetica Neue", "Arial"])
    font.setBold(True)
    font.setPixelSize(max(6, int(tile * 0.46)))
    p.setFont(font)
    p.setPen(QColor("#0B1A26"))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "M↓")
    p.end()
    return pixmap
