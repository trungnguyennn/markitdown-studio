"""Reusable custom widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .icons import Glyph, glyph_icon, set_glyph


class Card(QFrame):
    """Rounded 'layer' surface, as used in Fluent dashboards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


class DropZone(QFrame):
    """Drag-and-drop target with a 'Browse files' button."""

    filesDropped = Signal(list)  # list[Path]
    browseRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self.setMinimumHeight(190)

        glyph = QLabel()
        set_glyph(glyph, Glyph.UPLOAD, 36, theme.ACCENT)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)

        headline = QLabel("Drop files here to convert")
        headline.setObjectName("SectionLabel")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("PDF, Word, PowerPoint, Excel, HTML, CSV, JSON, images, ZIP…")
        hint.setObjectName("Tertiary")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        self.browse_button = QPushButton("  Browse files")
        self.browse_button.setProperty("accent", True)
        self.browse_button.setIcon(glyph_icon(Glyph.OPEN, theme.ON_ACCENT))
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setToolTip(f"Choose one or more files ({theme.shortcut_text('Ctrl+O')})")
        self.browse_button.clicked.connect(self.browseRequested)

        for label in (headline, hint):
            label.setStyleSheet("background: transparent; border: none;")

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.browse_button)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(6)
        layout.addStretch(1)
        layout.addWidget(glyph)
        layout.addWidget(headline)
        layout.addWidget(hint)
        layout.addSpacing(10)
        layout.addLayout(button_row)
        layout.addStretch(1)

    def _set_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    @staticmethod
    def _local_paths(event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._local_paths(event):
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_active(False)
        paths = self._local_paths(event)
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)


class MessagePanel(QWidget):
    """Large centred glyph + title + body, used for empty/busy/error states."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph = QLabel()
        self._glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel()
        self._title.setObjectName("BigMessage")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._body = QLabel()
        self._body.setObjectName("Secondary")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.action_button = QPushButton()
        self.action_button.hide()

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.action_button)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(1)
        layout.addWidget(self._glyph)
        layout.addSpacing(8)
        layout.addWidget(self._title)
        layout.addWidget(self._body)
        layout.addSpacing(12)
        layout.addLayout(row)
        layout.addStretch(2)

    def show_message(
        self, glyph: str, color: str, title: str, body: str = "", action_text: str | None = None
    ) -> None:
        set_glyph(self._glyph, glyph, 48, color)
        self._title.setText(title)
        self._body.setText(body)
        self._body.setVisible(bool(body))
        if action_text:
            self.action_button.setText(action_text)
            self.action_button.show()
        else:
            self.action_button.hide()
