"""Qt bridge that feeds log records to the Full edition's log panel."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from .logging_setup import PANEL_DATEFMT, PANEL_FORMAT, is_panel_record


class _LogBridge(QObject):
    message = Signal(str, int)  # formatted text, level


class QtLogHandler(logging.Handler):
    """Thread-safe: records emitted from workers are queued to the GUI thread."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.bridge = _LogBridge()
        self.setFormatter(logging.Formatter(PANEL_FORMAT, datefmt=PANEL_DATEFMT))

    def emit(self, record: logging.LogRecord) -> None:
        if not is_panel_record(record):
            return
        try:
            self.bridge.message.emit(self.format(record), record.levelno)
        except RuntimeError:
            pass  # bridge already destroyed during shutdown
