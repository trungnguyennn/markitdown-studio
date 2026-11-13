"""Application bootstrap: logging, theme, global error handling."""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, ORG_NAME, __version__
from .icons import app_icon
from .logging_setup import setup_logging
from .theme import apply_theme
from .win_effects import set_app_user_model_id

log = logging.getLogger(__name__)


class Application(QApplication):
    """QApplication that also accepts files opened from the macOS Finder.

    Windows passes "Open with" files on the command line. macOS instead sends a
    FileOpen event (Finder "Open With", or a file dropped on the Dock icon),
    possibly before the main window exists, so early files are kept until then.
    """

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self._pending_files: list[Path] = []
        self._window = None

    def attach_window(self, window) -> None:
        self._window = window
        if self._pending_files:
            window.add_files(self._pending_files)
            self._pending_files = []

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            local = event.file()
            if local:
                if self._window is not None:
                    self._window.add_files([Path(local)])
                    self._window.raise_()
                    self._window.activateWindow()
                else:
                    self._pending_files.append(Path(local))
            return True
        return super().event(event)


def _install_exception_hooks() -> None:
    """Never let an unexpected exception kill the app silently."""

    def show(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.critical("Unhandled exception:\n%s", text, extra={"file_only": True})
        log.error("Unexpected error: %s", exc)
        app = QApplication.instance()
        if app is not None:
            box = QMessageBox(QMessageBox.Icon.Critical, "Something went wrong",
                              "An unexpected error occurred. The app will keep running.\n\n"
                              f"{exc_type.__name__}: {exc}")
            box.setDetailedText(text)
            box.exec()

    sys.excepthook = show

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        log.critical("Unhandled exception in thread %s:\n%s", args.thread, text)

    threading.excepthook = thread_hook


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    smoke_dir = None
    if "--smoke-test" in argv[1:]:  # build self-test, see smoke.py
        i = argv.index("--smoke-test")
        if i + 1 < len(argv):
            smoke_dir = Path(argv[i + 1])
        del argv[i : i + 2]
    set_app_user_model_id(APP_ID)

    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationVersion(__version__)

    app = Application(argv)
    # A frozen macOS app takes its Dock icon from the bundle's .icns (which has
    # the padding macOS expects), so the window icon is only set elsewhere.
    if not (sys.platform == "darwin" and getattr(sys, "frozen", False)):
        app.setWindowIcon(app_icon())
    apply_theme(app)

    log_file = setup_logging()
    _install_exception_hooks()
    log.info("%s %s starting (Python %s)", APP_NAME, __version__, sys.version.split()[0])

    from .main_window import MainWindow  # imported after QApplication exists

    window = MainWindow(log_file)
    window.show()
    app.attach_window(window)

    # Files passed on the command line (e.g. "Open with…" or drag onto the .exe)
    files = [Path(a) for a in argv[1:] if Path(a).exists()]
    if smoke_dir is not None:
        from . import smoke

        smoke.start(app, window, smoke_dir, files)
    elif files:
        window.add_files(files)

    return app.exec()
