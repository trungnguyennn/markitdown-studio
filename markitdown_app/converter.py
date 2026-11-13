"""Qt background tasks for the Full edition (conversion logic lives in core.py)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .core import (  # noqa: F401 - re-exported for main_window
    SUPPORTED_EXTENSIONS,
    ConversionError,
    ConversionResult,
    convert_file,
    file_dialog_filter,
    format_exception,
    warm_up,
)


class _TaskSignals(QObject):
    # Signals live on a QObject created in the GUI thread; emitting from a
    # worker thread is delivered to GUI slots via a queued connection.
    succeeded = Signal(str, object)  # key, ConversionResult
    failed = Signal(str, str, str)  # key, user message, detail


class ConversionTask(QRunnable):
    """Runs convert_file() on a QThreadPool worker."""

    def __init__(self, key: str, path: Path) -> None:
        super().__init__()
        self.key = key
        self.path = path
        self.signals = _TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = convert_file(self.path)
        except ConversionError as exc:
            self.signals.failed.emit(self.key, exc.user_message, exc.detail)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.key, "Unexpected internal error.", format_exception(exc))
        else:
            self.signals.succeeded.emit(self.key, result)


class WarmUpTask(QRunnable):
    @Slot()
    def run(self) -> None:
        warm_up()
