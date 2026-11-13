"""Main dashboard window."""

from __future__ import annotations

import html
import logging
import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt, QThreadPool, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, COPYRIGHT, CREDITS, __version__, theme
from .converter import ConversionResult, ConversionTask, WarmUpTask, file_dialog_filter
from .icons import Glyph, app_icon, glyph_icon
from .qt_log import QtLogHandler
from .widgets import Card, DropZone, MessagePanel
from .win_effects import apply_dark_title_bar

log = logging.getLogger(__name__)

PREVIEW_CHAR_LIMIT = 2_000_000  # rendering huge docs as rich text is slow


class Status(Enum):
    QUEUED = "Queued"
    CONVERTING = "Converting…"
    DONE = "Converted"
    FAILED = "Failed"


@dataclass
class Job:
    path: Path
    status: Status = Status.QUEUED
    markdown: str = ""
    error: str = ""
    detail: str = ""
    elapsed: float = 0.0
    dirty: bool = False  # edited or converted but not yet exported
    saved_to: Path | None = None


# Pages of the content stack
PAGE_MESSAGE, PAGE_RAW, PAGE_PREVIEW = range(3)


class MainWindow(QMainWindow):
    def __init__(self, log_file: Path) -> None:
        super().__init__()
        self._log_file = log_file
        self._settings = QSettings()
        self._jobs: dict[str, Job] = {}
        self._items: dict[str, QListWidgetItem] = {}
        self._tasks: dict[str, ConversionTask] = {}
        self._run_order: list[str] = []
        self._current_key: str | None = None
        self._loading_editor = False
        self._title_bar_styled = False

        # One worker: MarkItDown is serialised anyway and this keeps queue order.
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1240, 780)
        self.setMinimumSize(920, 580)

        self._build_ui()
        self._build_actions()
        self._install_log_bridge()
        self._restore_settings()
        self._show_empty_state()
        self._update_controls()

        self._pool.start(WarmUpTask())  # load the engine in the background

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        # Header -----------------------------------------------------------
        title = QLabel(APP_NAME, objectName="Title")
        subtitle = QLabel(
            "Convert documents to clean Markdown for LLMs and text-analysis pipelines.",
            objectName="Subtitle",
        )
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        self.stats_label = QLabel(objectName="Secondary")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(self.stats_label)
        header.addSpacing(12)
        about_key = theme.shortcut_text(QKeySequence.StandardKey.HelpContents)  # F1 on Windows
        about_button = self._button("About", Glyph.INFO, f"About MarkItDown Studio ({about_key})", subtle=True)
        about_button.clicked.connect(self.show_about)
        header.addWidget(about_button, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(header)

        # Left column: drop zone + queue ---------------------------------
        self.drop_zone = DropZone()
        self.drop_zone.filesDropped.connect(self.add_files)
        self.drop_zone.browseRequested.connect(self.browse_files)

        queue_title = QLabel("Files", objectName="SectionLabel")
        self.clear_button = self._button("Clear", Glyph.CLEAR, "Remove all finished items", subtle=True)
        self.clear_button.clicked.connect(self.clear_queue)
        queue_header = QHBoxLayout()
        queue_header.addWidget(queue_title)
        queue_header.addStretch(1)
        queue_header.addWidget(self.clear_button)

        self.queue = QListWidget()
        self.queue.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue.customContextMenuRequested.connect(self._show_queue_menu)
        self.queue.currentItemChanged.connect(self._on_current_item_changed)
        self.queue.setUniformItemSizes(True)

        self.queue_empty = QLabel("No files yet.", objectName="Tertiary")
        self.queue_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        left_card = Card()
        left = QVBoxLayout(left_card)
        left.setContentsMargins(16, 16, 16, 16)
        left.setSpacing(12)
        left.addWidget(self.drop_zone)
        left.addLayout(queue_header)
        left.addWidget(self.queue_empty)
        left.addWidget(self.queue, 1)

        # Right column: result viewer ------------------------------------
        self.file_label = QLabel("No file selected", objectName="FileName")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.meta_label = QLabel(objectName="Tertiary")
        # Long paths must not push the toolbar buttons off-screen.
        for label in (self.file_label, self.meta_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        file_info = QVBoxLayout()
        file_info.setSpacing(2)
        file_info.addWidget(self.file_label)
        file_info.addWidget(self.meta_label)

        self.raw_button = self._button("Markdown", Glyph.CODE, "Show editable Markdown source")
        self.preview_button = self._button("Preview", Glyph.PREVIEW, "Show rendered preview")
        for btn, pos in ((self.raw_button, "first"), (self.preview_button, "last")):
            btn.setObjectName("Segment")
            btn.setProperty(pos, True)
            btn.setCheckable(True)
        self.raw_button.setChecked(True)
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.view_group.addButton(self.raw_button)
        self.view_group.addButton(self.preview_button)
        self.view_group.buttonToggled.connect(self._on_view_toggled)

        segment = QHBoxLayout()
        segment.setSpacing(0)
        segment.addWidget(self.raw_button)
        segment.addWidget(self.preview_button)

        self.copy_button = self._button("Copy", Glyph.COPY, f"Copy Markdown to clipboard ({theme.shortcut_text('Ctrl+Shift+C')})")
        self.copy_button.clicked.connect(self.copy_markdown)
        self.save_button = self._button(
            "Export .md", Glyph.SAVE, f"Save this result as a Markdown file ({theme.shortcut_text('Ctrl+S')})", accent=True
        )
        self.save_button.clicked.connect(self.save_current)
        self.save_all_button = self._button(
            "Export all", Glyph.SAVE_ALL, f"Save every converted file into a folder ({theme.shortcut_text('Ctrl+Shift+S')})"
        )
        self.save_all_button.clicked.connect(self.save_all)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addLayout(file_info, 1)
        toolbar.addLayout(segment)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.copy_button)
        toolbar.addWidget(self.save_all_button)
        toolbar.addWidget(self.save_button)

        self.message_panel = MessagePanel()
        self.message_panel.action_button.clicked.connect(self._on_message_action)

        self.editor = QPlainTextEdit()
        self.editor.setFont(theme.mono_font(10))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setPlaceholderText("Markdown output")
        self.editor.textChanged.connect(self._on_editor_changed)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.document().setDocumentMargin(12)

        self.content = QStackedWidget()
        self.content.addWidget(self.message_panel)  # PAGE_MESSAGE
        self.content.addWidget(self.editor)  # PAGE_RAW
        self.content.addWidget(self.preview)  # PAGE_PREVIEW

        right_card = Card()
        right = QVBoxLayout(right_card)
        right.setContentsMargins(16, 16, 16, 16)
        right.setSpacing(12)
        right.addLayout(toolbar)
        right.addWidget(self.content, 1)

        # Log panel -----------------------------------------------------
        self.log_view = QPlainTextEdit(objectName="LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(theme.mono_font(9))
        self.log_view.setMaximumBlockCount(2000)

        open_log = self._button("Open log file", Glyph.FOLDER, str(self._log_file), subtle=True)
        open_log.clicked.connect(self._open_log_folder)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Activity log", objectName="SectionLabel"))
        log_header.addStretch(1)
        log_header.addWidget(open_log)

        self.log_card = Card()
        log_layout = QVBoxLayout(self.log_card)
        log_layout.setContentsMargins(16, 12, 16, 12)
        log_layout.setSpacing(8)
        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_view)

        # Splitters -----------------------------------------------------
        self.h_split = QSplitter(Qt.Orientation.Horizontal)
        self.h_split.addWidget(left_card)
        self.h_split.addWidget(right_card)
        self.h_split.setStretchFactor(0, 0)
        self.h_split.setStretchFactor(1, 1)
        self.h_split.setSizes([360, 860])
        self.h_split.setChildrenCollapsible(False)

        self.v_split = QSplitter(Qt.Orientation.Vertical)
        self.v_split.addWidget(self.h_split)
        self.v_split.addWidget(self.log_card)
        self.v_split.setStretchFactor(0, 1)
        self.v_split.setSizes([620, 150])
        self.v_split.setCollapsible(0, False)
        outer.addWidget(self.v_split, 1)

        # Status bar ----------------------------------------------------
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        status.setContentsMargins(20, 0, 12, 0)
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.progress.hide()
        self.log_toggle = self._button("Hide log", Glyph.LOG, "Show or hide the activity log", subtle=True)
        self.log_toggle.clicked.connect(self._toggle_log)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.log_toggle)

    def _button(
        self, text: str, glyph: str, tooltip: str, *, accent: bool = False, subtle: bool = False
    ) -> QPushButton:
        button = QPushButton(f"  {text}")
        button.setIcon(glyph_icon(glyph, theme.ON_ACCENT if accent else theme.TEXT))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if accent:
            button.setProperty("accent", True)
        if subtle:
            button.setObjectName("Subtle")
        return button

    def _build_actions(self) -> None:
        def add(shortcut, slot) -> QAction:
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(slot)
            self.addAction(action)
            return action

        open_action = add(QKeySequence.StandardKey.Open, self.browse_files)
        save_action = add(QKeySequence.StandardKey.Save, self.save_current)
        save_all_action = add("Ctrl+Shift+S", self.save_all)
        copy_action = add("Ctrl+Shift+C", self.copy_markdown)
        about_action = add(QKeySequence.StandardKey.HelpContents, self.show_about)  # F1

        remove = QAction(self.queue)
        if sys.platform == "darwin":
            # Mac laptop keyboards have no forward-delete key; Backspace is "delete" there.
            remove.setShortcuts([QKeySequence(QKeySequence.StandardKey.Delete), QKeySequence(Qt.Key.Key_Backspace)])
            self._build_mac_menu_bar(open_action, save_action, save_all_action, copy_action, about_action)
        else:
            remove.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
        remove.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        remove.triggered.connect(self.remove_current)
        self.queue.addAction(remove)

    def _build_mac_menu_bar(
        self, open_action: QAction, save_action: QAction, save_all_action: QAction,
        copy_action: QAction, about_action: QAction,
    ) -> None:
        """macOS keeps commands in the menu bar at the top of the screen.

        The same QAction objects carry the shortcuts, so nothing is duplicated.
        """
        open_action.setText("Open…")
        save_action.setText("Export .md…")
        save_all_action.setText("Export All…")
        copy_action.setText("Copy Markdown")
        about_action.setText(f"{APP_NAME} Help")
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_all_action)
        edit_menu = bar.addMenu("Edit")
        edit_menu.addAction(copy_action)
        # Qt moves an action with AboutRole into the application menu ("About MarkItDown Studio").
        about_menu_item = QAction(f"About {APP_NAME}", self)
        about_menu_item.setMenuRole(QAction.MenuRole.AboutRole)
        about_menu_item.triggered.connect(self.show_about)
        help_menu = bar.addMenu("Help")
        help_menu.addAction(about_menu_item)
        help_menu.addAction(about_action)

    def _install_log_bridge(self) -> None:
        self._log_handler = QtLogHandler()
        self._log_handler.bridge.message.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)

    # ---------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        geometry = self._settings.value("window/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        for key, splitter in (("window/hsplit", self.h_split), ("window/vsplit", self.v_split)):
            state = self._settings.value(key)
            if isinstance(state, QByteArray):
                splitter.restoreState(state)
        log_visible = self._settings.value("window/logVisible", True, type=bool)
        self._set_log_visible(log_visible)

    def _save_settings(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/hsplit", self.h_split.saveState())
        self._settings.setValue("window/vsplit", self.v_split.saveState())
        self._settings.setValue("window/logVisible", self.log_card.isVisible())

    def _last_dir(self, key: str) -> str:
        value = self._settings.value(key, "", type=str)
        if value and Path(value).is_dir():
            return value
        return str(Path.home() / "Documents")

    # ------------------------------------------------------------ events
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._title_bar_styled:
            self._title_bar_styled = True
            apply_dark_title_bar(int(self.winId()))

    def closeEvent(self, event: QCloseEvent) -> None:
        busy = any(j.status in (Status.QUEUED, Status.CONVERTING) for j in self._jobs.values())
        unsaved = [j for j in self._jobs.values() if j.status is Status.DONE and j.dirty]
        if busy or unsaved:
            parts = []
            if busy:
                parts.append("Some files are still being converted.")
            if unsaved:
                parts.append(f"{len(unsaved)} converted file(s) have not been exported.")
            answer = QMessageBox.question(
                self,
                "Quit MarkItDown Studio?",
                " ".join(parts) + "\n\nDo you want to quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._pool.clear()  # drop queued work; a running conversion finishes in background
        self._save_settings()
        logging.getLogger().removeHandler(self._log_handler)
        event.accept()

    # ----------------------------------------------------------- queue
    @Slot()
    def browse_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choose files to convert", self._last_dir("paths/open"), file_dialog_filter()
        )
        if files:
            self._settings.setValue("paths/open", str(Path(files[0]).parent))
            self.add_files([Path(f) for f in files])

    @Slot(list)
    def add_files(self, paths: list[Path]) -> None:
        added = 0
        skipped_dirs = 0
        last_key = None
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                skipped_dirs += 1
                continue
            key = os.path.normcase(str(path.resolve()))
            last_key = key
            job = self._jobs.get(key)
            if job is not None:
                if job.status is Status.FAILED:
                    self._start_job(key)  # re-adding a failed file retries it
                continue
            self._jobs[key] = Job(path=path)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(str(path))
            self.queue.addItem(item)
            self._items[key] = item
            self._start_job(key)
            added += 1

        if skipped_dirs:
            log.warning("Skipped %d folder(s) - drop individual files instead.", skipped_dirs)
            self._toast(f"Skipped {skipped_dirs} folder(s). Please choose files, not folders.")
        if added:
            log.info("Added %d file(s) to the queue.", added)
        if last_key and last_key in self._items:
            self.queue.setCurrentItem(self._items[last_key])
        self._update_controls()

    def _start_job(self, key: str) -> None:
        job = self._jobs[key]
        job.status = Status.QUEUED
        job.error = job.detail = ""
        task = ConversionTask(key, job.path)
        task.setAutoDelete(False)  # we hold the reference until a signal arrives
        task.signals.succeeded.connect(self._on_task_succeeded)
        task.signals.failed.connect(self._on_task_failed)
        self._tasks[key] = task
        self._run_order.append(key)
        self._refresh_item(key)
        self._pool.start(task)
        self._mark_running()

    def _mark_running(self) -> None:
        """Flag the job the single worker is processing (the pool is FIFO)."""
        if any(j.status is Status.CONVERTING for j in self._jobs.values()):
            return
        while self._run_order:
            key = self._run_order.pop(0)
            job = self._jobs.get(key)
            if job is not None and job.status is Status.QUEUED:
                job.status = Status.CONVERTING
                log.info("Converting %s …", job.path.name)
                self._refresh_item(key)
                if key == self._current_key:
                    self._show_job(key)
                return

    @Slot(str, object)
    def _on_task_succeeded(self, key: str, result: ConversionResult) -> None:
        self._tasks.pop(key, None)
        job = self._jobs.get(key)
        if job is None:
            return  # removed while converting
        job.status = Status.DONE
        job.markdown = result.markdown
        job.elapsed = result.elapsed
        job.dirty = True
        if result.markdown.strip():
            log.info(
                "Converted %s in %.2fs (%s characters).",
                job.path.name,
                result.elapsed,
                f"{len(result.markdown):,}",
            )
        else:
            log.warning(
                "%s converted but contained no extractable text (scanned PDF or image-only file?).",
                job.path.name,
            )
        self._after_job_finished(key)

    @Slot(str, str, str)
    def _on_task_failed(self, key: str, message: str, detail: str) -> None:
        self._tasks.pop(key, None)
        job = self._jobs.get(key)
        if job is None:
            return
        job.status = Status.FAILED
        job.error = message
        job.detail = detail
        log.error("Failed to convert %s: %s", job.path.name, message)
        if detail and detail != message:
            # Full technical detail goes to the log file only, not the panel.
            log.error("Details for %s:\n%s", job.path, detail, extra={"file_only": True})
        self._after_job_finished(key)

    def _after_job_finished(self, key: str) -> None:
        self._refresh_item(key)
        self._mark_running()
        if key == self._current_key:
            self._show_job(key)
        self._update_controls()

    def _refresh_item(self, key: str) -> None:
        item = self._items.get(key)
        job = self._jobs.get(key)
        if item is None or job is None:
            return
        glyph, color = {
            Status.QUEUED: (Glyph.CLOCK, theme.TEXT_TERTIARY),
            Status.CONVERTING: (Glyph.SYNC, theme.ACCENT),
            Status.DONE: (Glyph.CHECK, theme.SUCCESS),
            Status.FAILED: (Glyph.ERROR, theme.CRITICAL),
        }[job.status]
        if job.status is Status.DONE and not job.markdown.strip():
            glyph, color = Glyph.WARNING, theme.CAUTION
        item.setIcon(glyph_icon(glyph, color))
        suffix = " •" if job.status is Status.DONE and job.dirty else ""
        item.setText(f"{job.path.name}{suffix}\n{job.status.value}")
        item.setToolTip(f"{job.path}\n{job.error or job.status.value}")

    @Slot()
    def remove_current(self) -> None:
        item = self.queue.currentItem()
        if item is not None:
            self._remove_key(item.data(Qt.ItemDataRole.UserRole))

    def _remove_key(self, key: str) -> None:
        job = self._jobs.get(key)
        if job is None:
            return
        if job.status is Status.CONVERTING:
            self._toast("A file cannot be removed while it is being converted.")
            return
        task = self._tasks.pop(key, None)
        if task is not None:
            self._pool.tryTake(task)
        if key in self._run_order:
            self._run_order.remove(key)
        item = self._items.pop(key)
        self.queue.takeItem(self.queue.row(item))
        del self._jobs[key]
        if not self._jobs:
            self._current_key = None
            self._show_empty_state()
        self._update_controls()

    @Slot()
    def clear_queue(self) -> None:
        finished = [k for k, j in self._jobs.items() if j.status in (Status.DONE, Status.FAILED)]
        unsaved = [k for k in finished if self._jobs[k].status is Status.DONE and self._jobs[k].dirty]
        if unsaved:
            answer = QMessageBox.question(
                self,
                "Clear list?",
                f"{len(unsaved)} converted file(s) have not been exported. Clear them anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        for key in finished:
            self._remove_key(key)

    def _show_queue_menu(self, pos) -> None:
        item = self.queue.itemAt(pos)
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        job = self._jobs[key]
        menu = QMenu(self)
        export = menu.addAction(glyph_icon(Glyph.SAVE), "Export .md…")
        export.setEnabled(job.status is Status.DONE)
        retry = menu.addAction(glyph_icon(Glyph.RETRY), "Convert again")
        retry.setEnabled(job.status in (Status.DONE, Status.FAILED))
        reveal = menu.addAction(glyph_icon(Glyph.FOLDER), "Open containing folder")
        menu.addSeparator()
        remove = menu.addAction(glyph_icon(Glyph.DELETE), "Remove from list")
        remove.setEnabled(job.status is not Status.CONVERTING)
        chosen = menu.exec(self.queue.viewport().mapToGlobal(pos))
        if chosen is export:
            self.queue.setCurrentItem(item)
            self.save_current()
        elif chosen is retry:
            self._start_job(key)
            self._show_job(key)
        elif chosen is reveal:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.path.parent)))
        elif chosen is remove:
            self._remove_key(key)

    # ---------------------------------------------------------- viewer
    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous) -> None:
        self._current_key = current.data(Qt.ItemDataRole.UserRole) if current else None
        if self._current_key:
            self._show_job(self._current_key)
        else:
            self._show_empty_state()
        self._update_controls()

    def _show_empty_state(self) -> None:
        self.file_label.setText("No file selected")
        self.meta_label.setText("Add files on the left to get started.")
        self.message_panel.show_message(
            Glyph.DOCUMENT,
            theme.TEXT_TERTIARY,
            "Your Markdown will appear here",
            f"Drop files onto the panel on the left or press {theme.shortcut_text('Ctrl+O')}. "
            "Each file is converted locally with Microsoft MarkItDown.",
        )
        self.content.setCurrentIndex(PAGE_MESSAGE)

    def _show_job(self, key: str) -> None:
        job = self._jobs[key]
        self.file_label.setText(job.path.name)
        if job.status is Status.DONE:
            words = len(job.markdown.split())
            meta = (
                f"{len(job.markdown):,} characters · {words:,} words · "
                f"converted in {job.elapsed:.2f}s"
            )
            if job.saved_to:
                meta += f" · saved to {job.saved_to}"
            self.meta_label.setText(meta)
            if not job.markdown.strip():
                self.message_panel.show_message(
                    Glyph.WARNING,
                    theme.CAUTION,
                    "No text found",
                    "MarkItDown finished but the file contains no extractable text. "
                    "Scanned PDFs and photos need OCR, which MarkItDown does not perform locally.",
                    "  Convert again",
                )
                self.content.setCurrentIndex(PAGE_MESSAGE)
                return
            self._loading_editor = True
            if self.editor.toPlainText() != job.markdown:
                self.editor.setPlainText(job.markdown)
            self._loading_editor = False
            self._apply_view_mode()
        elif job.status is Status.FAILED:
            self.meta_label.setText(str(job.path.parent))
            self.message_panel.show_message(
                Glyph.ERROR, theme.CRITICAL, "Conversion failed", job.error, "  Try again"
            )
            self.content.setCurrentIndex(PAGE_MESSAGE)
        else:
            self.meta_label.setText(str(job.path.parent))
            busy = job.status is Status.CONVERTING
            self.message_panel.show_message(
                Glyph.SYNC if busy else Glyph.CLOCK,
                theme.ACCENT if busy else theme.TEXT_TERTIARY,
                "Converting…" if busy else "Waiting in queue",
                "The first conversion can take a few seconds while MarkItDown loads."
                if busy
                else "",
            )
            self.content.setCurrentIndex(PAGE_MESSAGE)

    def _apply_view_mode(self) -> None:
        job = self._current_job()
        if job is None or job.status is not Status.DONE or not job.markdown.strip():
            return
        if self.preview_button.isChecked():
            text = job.markdown
            if len(text) > PREVIEW_CHAR_LIMIT:
                text = text[:PREVIEW_CHAR_LIMIT] + "\n\n*…preview truncated – export to see everything.*"
            self.preview.setMarkdown(text)
            self.content.setCurrentIndex(PAGE_PREVIEW)
        else:
            self.content.setCurrentIndex(PAGE_RAW)

    @Slot()
    def _on_view_toggled(self, *_args) -> None:
        self._apply_view_mode()

    @Slot()
    def _on_editor_changed(self) -> None:
        if self._loading_editor:
            return
        job = self._current_job()
        if job is not None and job.status is Status.DONE:
            job.markdown = self.editor.toPlainText()
            if not job.dirty:
                job.dirty = True
                self._refresh_item(self._current_key)

    @Slot()
    def _on_message_action(self) -> None:
        if self._current_key:
            self._start_job(self._current_key)
            self._show_job(self._current_key)
            self._update_controls()

    def _current_job(self) -> Job | None:
        return self._jobs.get(self._current_key) if self._current_key else None

    # ---------------------------------------------------------- export
    @Slot()
    def copy_markdown(self) -> None:
        job = self._current_job()
        if job is None or job.status is not Status.DONE or not job.markdown:
            return
        QGuiApplication.clipboard().setText(job.markdown)
        self._toast(f"Copied {len(job.markdown):,} characters to the clipboard.")

    @Slot()
    def save_current(self) -> None:
        job = self._current_job()
        if job is None or job.status is not Status.DONE:
            return
        start_dir = self._settings.value("paths/save", "", type=str) or str(job.path.parent)
        suggested = str(Path(start_dir) / f"{job.path.stem}.md")
        target, _ = QFileDialog.getSaveFileName(
            self, "Export Markdown", suggested, "Markdown (*.md);;Text (*.txt);;All files (*.*)"
        )
        if not target:
            return
        target_path = Path(target)
        if not target_path.suffix:
            target_path = target_path.with_suffix(".md")
        if self._write_file(target_path, job.markdown):
            self._settings.setValue("paths/save", str(target_path.parent))
            job.dirty = False
            job.saved_to = target_path
            self._refresh_item(self._current_key)
            self._show_job(self._current_key)
            self._toast(f"Saved {target_path.name}")

    @Slot()
    def save_all(self) -> None:
        done = [(k, j) for k, j in self._jobs.items() if j.status is Status.DONE and j.markdown.strip()]
        if not done:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Export all Markdown files to…", self._last_dir("paths/save")
        )
        if not folder:
            return
        out_dir = Path(folder)
        self._settings.setValue("paths/save", folder)
        used: set[str] = set()
        saved = failed = 0
        for key, job in done:
            target = self._unique_path(out_dir, job.path.stem, used)
            if self._write_file(target, job.markdown, quiet=True):
                job.dirty = False
                job.saved_to = target
                saved += 1
            else:
                failed += 1
            self._refresh_item(key)
        if self._current_key:
            self._show_job(self._current_key)
        if failed:
            QMessageBox.warning(
                self,
                "Export finished with errors",
                f"Saved {saved} file(s). {failed} file(s) could not be written - see the log for details.",
            )
        else:
            self._toast(f"Exported {saved} file(s) to {out_dir}")
        log.info("Exported %d file(s) to %s (%d failed).", saved, out_dir, failed)

    @staticmethod
    def _unique_path(folder: Path, stem: str, used: set[str]) -> Path:
        candidate = folder / f"{stem}.md"
        n = 1
        while candidate.exists() or os.path.normcase(str(candidate)) in used:
            candidate = folder / f"{stem} ({n}).md"
            n += 1
        used.add(os.path.normcase(str(candidate)))
        return candidate

    def _write_file(self, target: Path, text: str, *, quiet: bool = False) -> bool:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # newline="" keeps the converter's line endings exactly as produced.
            with target.open("w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        except PermissionError:
            message = f"Permission denied while writing:\n{target}\n\nChoose another folder or close the file if it is open elsewhere."
        except OSError as exc:
            message = f"Could not write:\n{target}\n\n{exc.strerror or exc}"
        else:
            log.info("Saved %s", target)
            return True
        log.error(message.replace("\n", " "))
        if not quiet:
            QMessageBox.critical(self, "Export failed", message)
        return False

    # ----------------------------------------------------------- about
    @Slot()
    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setIconPixmap(app_icon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<p style='font-size:{theme.pt(15):g}pt; font-weight:600; margin:0'>{APP_NAME}</p>"
            f"<p style='color:{theme.TEXT_SECONDARY}; margin-top:2px'>Version {__version__}</p>"
            f"<p style='margin-top:12px'>{html.escape(COPYRIGHT)}</p>"
        )
        box.setInformativeText(
            f"<p style='color:{theme.TEXT_TERTIARY}'>{html.escape(CREDITS)}</p>"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    # ----------------------------------------------------------- misc UI
    def _update_controls(self) -> None:
        job = self._current_job()
        has_result = job is not None and job.status is Status.DONE and bool(job.markdown.strip())
        for w in (self.copy_button, self.save_button, self.raw_button, self.preview_button):
            w.setEnabled(has_result)
        done = sum(1 for j in self._jobs.values() if j.status is Status.DONE)
        failed = sum(1 for j in self._jobs.values() if j.status is Status.FAILED)
        pending = sum(1 for j in self._jobs.values() if j.status in (Status.QUEUED, Status.CONVERTING))
        self.save_all_button.setEnabled(
            any(j.status is Status.DONE and j.markdown.strip() for j in self._jobs.values())
        )
        self.clear_button.setEnabled(done + failed > 0)
        self.queue_empty.setVisible(not self._jobs)
        self.queue.setVisible(bool(self._jobs))

        parts = [f"{done} converted"]
        if failed:
            parts.append(f"{failed} failed")
        if pending:
            parts.append(f"{pending} pending")
        self.stats_label.setText(" · ".join(parts) if self._jobs else "")
        self.progress.setVisible(pending > 0)
        if pending:
            self.status_label.setText(f"Converting… {pending} file(s) remaining")
        elif not self.status_label.text().startswith(("Saved", "Copied", "Exported", "Skipped", "A file")):
            self.status_label.setText("Ready")

    def _toast(self, text: str) -> None:
        self.status_label.setText(text)
        QTimer.singleShot(5000, self._reset_status)

    def _reset_status(self) -> None:
        self.status_label.setText("Ready")
        self._update_controls()

    @Slot(str, int)
    def _append_log(self, text: str, level: int) -> None:
        color = theme.TEXT_SECONDARY
        if level >= logging.ERROR:
            color = theme.CRITICAL
        elif level >= logging.WARNING:
            color = theme.CAUTION
        self.log_view.appendHtml(f'<span style="color:{color}">{html.escape(text)}</span>')

    def _toggle_log(self) -> None:
        self._set_log_visible(not self.log_card.isVisible())

    def _set_log_visible(self, visible: bool) -> None:
        self.log_card.setVisible(visible)
        self.log_toggle.setText("  Hide log" if visible else "  Show log")

    def _open_log_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_file.parent)))
