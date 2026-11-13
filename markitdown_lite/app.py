"""MarkItDown Studio Lite - Tkinter + Sun Valley (Windows 11) theme.

Same workflow as the Full edition (browse / drag-and-drop, queue, editable
Markdown, export, log), built on the Tk toolkit that ships with Python so the
whole app packs into one small .exe.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from markitdown_app import APP_ID, APP_NAME, COPYRIGHT, CREDITS, __version__
from markitdown_app import core
from markitdown_app.logging_setup import PANEL_DATEFMT, PANEL_FORMAT, is_panel_record, setup_logging
from markitdown_app.win_effects import apply_dark_title_bar, set_app_user_model_id

from .converters import create_engine
from .dnd import FileDropTarget

log = logging.getLogger(__name__)

APP_TITLE = "MarkItDown Studio Lite"

LITE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "Documents": (".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".epub", ".msg"),
    "Web & data": (".html", ".htm", ".csv", ".json", ".jsonl", ".xml", ".ipynb", ".rss", ".atom"),
    "Text": (".txt", ".md", ".markdown", ".rst"),
    "Archives": (".zip",),
}

# Windows 11 dark tokens (match the Sun Valley dark theme)
BG = "#1c1c1c"
CARD = "#1c1c1c"  # Sun Valley dark surface (cards are outlined, not filled)
ZONE = "#2b2b2b"  # slightly raised layer for the drop zone
EDITOR_BG = "#202020"
TEXT = "#ffffff"
TEXT_2 = "#c5c5c5"
TEXT_3 = "#8a8a8a"
ACCENT = "#57c8ff"
SUCCESS = "#6ccb5f"
CRITICAL = "#ff99a4"
CAUTION = "#fce100"
STROKE = "#3a3a3a"

UI_FONT = "Segoe UI Variable Text"
UI_DISPLAY = "Segoe UI Variable Display"
MONO_FONT = "Cascadia Mono"
ICON_FONT = "Segoe Fluent Icons"  # falls back to MDL2 Assets below on Windows 10

GLYPH = {
    "upload": "\uE898", "doc": "\uE8A5", "error": "\uE783", "sync": "\uE895",
    "clock": "\uE823", "warning": "\uE7BA", "check": "\uE73E",
}


class Status(Enum):
    QUEUED = "Queued"
    CONVERTING = "Converting…"
    DONE = "Converted"
    FAILED = "Failed"


STATUS_STYLE = {
    Status.QUEUED: ("◷", "queued"),
    Status.CONVERTING: ("⟳", "converting"),
    Status.DONE: ("✓", "done"),
    Status.FAILED: ("✕", "failed"),
}


@dataclass
class Job:
    path: Path
    status: Status = Status.QUEUED
    markdown: str = ""
    error: str = ""
    elapsed: float = 0.0
    dirty: bool = False
    saved_to: Path | None = None


def resource_path(relative: str) -> Path:
    """Locate bundled files both from source and inside the PyInstaller one-file exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class TkLogHandler(logging.Handler):
    """Thread-safe: workers only enqueue; the UI drains the queue on its own thread."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.queue: queue.SimpleQueue[tuple[str, int]] = queue.SimpleQueue()
        self.setFormatter(logging.Formatter(PANEL_FORMAT, datefmt=PANEL_DATEFMT))

    def emit(self, record: logging.LogRecord) -> None:
        if is_panel_record(record):
            self.queue.put((self.format(record), record.levelno))


class LiteApp:
    def __init__(self, root: tk.Tk, log_file: Path) -> None:
        self.root = root
        self.log_file = log_file
        self.jobs: dict[str, Job] = {}
        self.current: str | None = None
        self._loading_editor = False
        self._work: queue.Queue[tuple[str, Path] | None] = queue.Queue()
        self._results: queue.SimpleQueue[tuple] = queue.SimpleQueue()
        self._last_open_dir = str(Path.home() / "Documents")
        self._last_save_dir = ""
        self._icon_font = self._pick_icon_font()
        self._status_after: str | None = None
        self.scale = root.winfo_fpixels("1i") / 96.0  # 1.0 at 100 %, 1.5 at 150 % ...

        self.log_handler = TkLogHandler()
        logging.getLogger().addHandler(self.log_handler)

        self._build_styles()
        self._build_ui()
        self._bind_keys()
        self._show_empty()
        self._update_controls()

        self.drop = FileDropTarget(root)
        threading.Thread(target=self._worker, name="converter", daemon=True).start()
        self._work.put(("__warmup__", Path()))
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def px(self, value: float) -> int:
        """Scale a 100 %-DPI pixel size to the current monitor."""
        return int(round(value * self.scale))

    # ----------------------------------------------------------- styling
    def _pick_icon_font(self) -> str:
        from tkinter import font as tkfont

        families = set(tkfont.families(self.root))
        for name in (ICON_FONT, "Segoe MDL2 Assets"):
            if name in families:
                return name
        return UI_FONT

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        self.root.configure(bg=BG)
        style.configure("Title.TLabel", font=(UI_DISPLAY, 20, "bold"))
        style.configure("Subtitle.TLabel", font=(UI_FONT, 10), foreground=TEXT_2)
        style.configure("Section.TLabel", font=(UI_FONT, 11, "bold"))
        style.configure("FileName.TLabel", font=(UI_FONT, 12, "bold"))
        style.configure("Meta.TLabel", font=(UI_FONT, 9), foreground=TEXT_3)
        style.configure("Stats.TLabel", font=(UI_FONT, 10), foreground=TEXT_2)
        style.configure("Big.TLabel", font=(UI_FONT, 13, "bold"))
        style.configure("Body.TLabel", font=(UI_FONT, 10), foreground=TEXT_2)
        style.configure("Status.TLabel", font=(UI_FONT, 9), foreground=TEXT_2)
        style.configure("Treeview", rowheight=self.px(30), font=(UI_FONT, 10))

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # Header
        header = ttk.Frame(root, padding=(24, 18, 24, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Convert documents to clean Markdown for LLMs and text-analysis pipelines.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w")
        self.stats = ttk.Label(header, style="Stats.TLabel")
        self.stats.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(header, text="About", command=self.show_about).grid(
            row=0, column=2, rowspan=2, sticky="e", padx=(16, 0)
        )

        # Body: vertical pane (main / log), main is a horizontal pane
        self.vpane = ttk.Panedwindow(root, orient="vertical")
        self.vpane.grid(row=1, column=0, sticky="nsew", padx=24, pady=(8, 8))
        hpane = ttk.Panedwindow(self.vpane, orient="horizontal")
        self.vpane.add(hpane, weight=4)

        # Left card: drop zone + file list
        left = ttk.Frame(hpane, style="Card.TFrame", padding=16)
        hpane.add(left, weight=0)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        self.dropzone = tk.Canvas(left, height=self.px(170), width=self.px(300), bg=ZONE, highlightthickness=0, bd=0)
        self.dropzone.grid(row=0, column=0, sticky="ew")
        self.dropzone.bind("<Configure>", self._draw_dropzone)
        zone_inner = tk.Frame(self.dropzone, bg=ZONE)
        tk.Label(zone_inner, text=GLYPH["upload"], font=(self._icon_font, 24), fg=ACCENT, bg=ZONE).pack()
        tk.Label(zone_inner, text="Drop files on this window", font=(UI_FONT, 11, "bold"),
                 fg=TEXT, bg=ZONE).pack(pady=(4, 0))
        tk.Label(zone_inner, text="PDF, Word, PowerPoint, Excel, HTML, CSV, JSON, EPUB, ZIP…",
                 font=(UI_FONT, 9), fg=TEXT_3, bg=ZONE, wraplength=self.px(250)).pack(pady=(2, 8))
        ttk.Button(zone_inner, text="Browse files", style="Accent.TButton",
                   command=self.browse_files).pack()
        self._zone_window = self.dropzone.create_window(0, 0, window=zone_inner)

        files_header = ttk.Frame(left)
        files_header.grid(row=1, column=0, sticky="ew", pady=(14, 6))
        files_header.columnconfigure(0, weight=1)
        ttk.Label(files_header, text="Files", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.clear_btn = ttk.Button(files_header, text="Clear finished", command=self.clear_finished)
        self.clear_btn.grid(row=0, column=1, sticky="e")

        tree_frame = ttk.Frame(left)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=("status",), show="tree", selectmode="browse")
        self.tree.column("#0", width=self.px(180), stretch=True)
        self.tree.column("status", width=self.px(115), stretch=False, anchor="w")
        self.tree.tag_configure("queued", foreground=TEXT_3)
        self.tree.tag_configure("converting", foreground=ACCENT)
        self.tree.tag_configure("done", foreground=SUCCESS)
        self.tree.tag_configure("failed", foreground=CRITICAL)
        self.tree.tag_configure("empty", foreground=CAUTION)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-3>", self._tree_menu)
        self.tree.bind("<Delete>", lambda e: self.remove_current())

        # Right card: toolbar + editor / message
        right = ttk.Frame(hpane, style="Card.TFrame", padding=16)
        hpane.add(right, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(right)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.columnconfigure(0, weight=1)
        info = ttk.Frame(toolbar)
        info.grid(row=0, column=0, sticky="ew")
        self.file_label = ttk.Label(info, text="No file selected", style="FileName.TLabel")
        self.file_label.pack(anchor="w")
        self.meta_label = ttk.Label(info, style="Meta.TLabel")
        self.meta_label.pack(anchor="w")
        self.copy_btn = ttk.Button(toolbar, text="Copy", command=self.copy_markdown)
        self.copy_btn.grid(row=0, column=1, padx=(8, 0))
        self.save_all_btn = ttk.Button(toolbar, text="Export all", command=self.save_all)
        self.save_all_btn.grid(row=0, column=2, padx=(8, 0))
        self.save_btn = ttk.Button(toolbar, text="Export .md", style="Accent.TButton", command=self.save_current)
        self.save_btn.grid(row=0, column=3, padx=(8, 0))

        content = ttk.Frame(right)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        self.editor_frame = ttk.Frame(content)
        self.editor_frame.grid(row=0, column=0, sticky="nsew")
        self.editor_frame.columnconfigure(0, weight=1)
        self.editor_frame.rowconfigure(0, weight=1)
        self.editor = tk.Text(
            self.editor_frame, wrap="word", undo=True, font=(MONO_FONT, 10), bg=EDITOR_BG, fg=TEXT,
            insertbackground=TEXT, selectbackground="#0f6cbd", selectforeground=TEXT, relief="flat",
            highlightthickness=1, highlightbackground=STROKE, highlightcolor=ACCENT, padx=10, pady=8,
        )
        self.editor.grid(row=0, column=0, sticky="nsew")
        ed_scroll = ttk.Scrollbar(self.editor_frame, orient="vertical", command=self.editor.yview)
        ed_scroll.grid(row=0, column=1, sticky="ns")
        self.editor.configure(yscrollcommand=ed_scroll.set)
        self.editor.bind("<<Modified>>", self._on_editor_modified)

        self.message = ttk.Frame(content)
        self.message.grid(row=0, column=0, sticky="nsew")
        inner = tk.Frame(self.message, bg=CARD)
        inner.place(relx=0.5, rely=0.42, anchor="center")
        self.msg_glyph = tk.Label(inner, font=(self._icon_font, 36), bg=CARD)
        self.msg_glyph.pack()
        self.msg_title = tk.Label(inner, font=(UI_FONT, 13, "bold"), fg=TEXT, bg=CARD)
        self.msg_title.pack(pady=(10, 2))
        self.msg_body = tk.Label(inner, font=(UI_FONT, 10), fg=TEXT_2, bg=CARD, wraplength=self.px(460), justify="center")
        self.msg_body.pack()
        self.msg_button = ttk.Button(inner, text="Try again", command=self._retry_current)

        # Log card
        log_card = ttk.Frame(self.vpane, style="Card.TFrame", padding=(16, 10, 16, 10))
        self.log_card = log_card
        self.vpane.add(log_card, weight=1)
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)
        ttk.Label(log_card, text="Activity log", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(log_card, text="Open log folder", command=self._open_log_folder).grid(row=0, column=1, sticky="e")
        self.log_view = tk.Text(
            log_card, height=6, font=(MONO_FONT, 9), bg="#1a1a1a", fg=TEXT_2, relief="flat",
            highlightthickness=1, highlightbackground=STROKE, padx=8, pady=6, state="disabled",
        )
        self.log_view.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.log_view.tag_configure("warn", foreground=CAUTION)
        self.log_view.tag_configure("error", foreground=CRITICAL)

        # Status bar
        status = ttk.Frame(root, padding=(24, 4, 24, 8))
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status, text="Ready", style="Status.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=self.px(160))
        self.log_toggle = ttk.Button(status, text="Hide log", command=self._toggle_log)
        self.log_toggle.grid(row=0, column=2, sticky="e")

    def _draw_dropzone(self, event=None) -> None:
        c = self.dropzone
        w, h = c.winfo_width(), c.winfo_height()
        c.delete("border")
        c.create_rectangle(2, 2, w - 3, h - 3, outline="#5a5a5a", dash=(6, 4), width=max(1, self.px(1.5)), tags="border")
        c.coords(self._zone_window, w / 2, h / 2)

    def _bind_keys(self) -> None:
        self.root.bind_all("<Control-o>", lambda e: self.browse_files())
        self.root.bind_all("<Control-s>", lambda e: self.save_current())
        self.root.bind_all("<Control-S>", lambda e: self.save_all())  # Ctrl+Shift+S
        self.root.bind_all("<Control-C>", lambda e: self.copy_markdown())  # Ctrl+Shift+C
        self.root.bind_all("<F1>", lambda e: self.show_about())

    # ------------------------------------------------------------ worker
    def _worker(self) -> None:
        while True:
            item = self._work.get()
            if item is None:
                return
            key, path = item
            if key == "__warmup__":
                core.warm_up()
                continue
            self._results.put(("started", key))
            try:
                result = core.convert_file(path)
            except core.ConversionError as exc:
                self._results.put(("failed", key, exc.user_message, exc.detail))
            except Exception as exc:  # noqa: BLE001
                self._results.put(("failed", key, "Unexpected internal error.", core.format_exception(exc)))
            else:
                self._results.put(("done", key, result))

    def _poll(self) -> None:
        for batch in self.drop.drain():
            self.add_files(batch)
        try:
            while True:
                self._handle_result(self._results.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                text, level = self.log_handler.queue.get_nowait()
                self._append_log(text, level)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle_result(self, msg: tuple) -> None:
        kind, key = msg[0], msg[1]
        job = self.jobs.get(key)
        if job is None:
            return  # removed meanwhile
        if kind == "started":
            job.status = Status.CONVERTING
            log.info("Converting %s …", job.path.name)
        elif kind == "done":
            result = msg[2]
            job.status, job.markdown, job.elapsed, job.dirty = Status.DONE, result.markdown, result.elapsed, True
            if result.markdown.strip():
                log.info("Converted %s in %.2fs (%s characters).", job.path.name, result.elapsed,
                         f"{len(result.markdown):,}")
            else:
                log.warning("%s converted but contained no extractable text.", job.path.name)
        elif kind == "failed":
            job.status, job.error = Status.FAILED, msg[2]
            log.error("Failed to convert %s: %s", job.path.name, msg[2])
            if msg[3] and msg[3] != msg[2]:
                log.error("Details for %s:\n%s", job.path, msg[3], extra={"file_only": True})
        self._refresh_row(key)
        if key == self.current:
            self._show_job(key)
        self._update_controls()

    # ------------------------------------------------------------- queue
    def browse_files(self) -> None:
        all_exts = " ".join(f"*{e}" for g in LITE_EXTENSIONS.values() for e in g)
        types = [("All supported files", all_exts)]
        types += [(name, " ".join(f"*{e}" for e in exts)) for name, exts in LITE_EXTENSIONS.items()]
        types.append(("All files", "*.*"))
        files = filedialog.askopenfilenames(
            parent=self.root, title="Choose files to convert", initialdir=self._last_open_dir, filetypes=types
        )
        if files:
            self._last_open_dir = str(Path(files[0]).parent)
            self.add_files(list(files))

    def add_files(self, paths: list) -> None:
        added = skipped_dirs = 0
        last = None
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                skipped_dirs += 1
                continue
            key = os.path.normcase(str(path.resolve()))
            last = key
            job = self.jobs.get(key)
            if job is not None:
                if job.status is Status.FAILED:
                    self._enqueue(key)
                continue
            self.jobs[key] = Job(path=path)
            self.tree.insert("", "end", iid=key, text=f"  {path.name}")
            self._enqueue(key)
            added += 1
        if skipped_dirs:
            log.warning("Skipped %d folder(s) - drop individual files instead.", skipped_dirs)
            self._toast(f"Skipped {skipped_dirs} folder(s). Please choose files, not folders.")
        if added:
            log.info("Added %d file(s) to the queue.", added)
        if last:
            self.tree.selection_set(last)
            self.tree.see(last)
        self._update_controls()

    def _enqueue(self, key: str) -> None:
        job = self.jobs[key]
        job.status, job.error = Status.QUEUED, ""
        self._refresh_row(key)
        self._work.put((key, job.path))

    def _refresh_row(self, key: str) -> None:
        job = self.jobs.get(key)
        if job is None or not self.tree.exists(key):
            return
        symbol, tag = STATUS_STYLE[job.status]
        label = job.status.value
        if job.status is Status.DONE and not job.markdown.strip():
            symbol, tag, label = "⚠", "empty", "No text"
        name = f"  {job.path.name}{' •' if job.status is Status.DONE and job.dirty else ''}"
        self.tree.item(key, text=name, values=(f"{symbol} {label}",), tags=(tag,))

    def remove_current(self) -> None:
        if self.current:
            self._remove(self.current)

    def _remove(self, key: str) -> None:
        job = self.jobs.get(key)
        if job is None:
            return
        if job.status in (Status.QUEUED, Status.CONVERTING):
            self._toast("Wait until the file has finished converting before removing it.")
            return
        del self.jobs[key]
        self.tree.delete(key)
        if key == self.current:
            self.current = None
            self._show_empty()
        self._update_controls()

    def clear_finished(self) -> None:
        finished = [k for k, j in self.jobs.items() if j.status in (Status.DONE, Status.FAILED)]
        unsaved = [k for k in finished if self.jobs[k].status is Status.DONE and self.jobs[k].dirty]
        if unsaved and not messagebox.askyesno(
            "Clear list?", f"{len(unsaved)} converted file(s) have not been exported. Clear them anyway?",
            parent=self.root, icon="warning",
        ):
            return
        for key in finished:
            self._remove(key)

    def _tree_menu(self, event) -> None:
        key = self.tree.identify_row(event.y)
        if not key:
            return
        self.tree.selection_set(key)
        job = self.jobs[key]
        menu = tk.Menu(self.root, tearoff=False, bg="#2c2c2c", fg=TEXT, activebackground="#3a3a3a",
                       activeforeground=TEXT, disabledforeground="#5d5d5d", bd=1, relief="solid")
        done = job.status is Status.DONE
        menu.add_command(label="Export .md…", command=self.save_current, state="normal" if done else "disabled")
        menu.add_command(label="Convert again", command=lambda: self._enqueue(key),
                         state="normal" if job.status in (Status.DONE, Status.FAILED) else "disabled")
        menu.add_command(label="Open containing folder", command=lambda: os.startfile(job.path.parent))
        menu.add_separator()
        menu.add_command(label="Remove from list", command=lambda: self._remove(key))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------ viewer
    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        self.current = sel[0] if sel else None
        if self.current:
            self._show_job(self.current)
        else:
            self._show_empty()
        self._update_controls()

    def _show_message(self, glyph: str, color: str, title: str, body: str = "", button: str | None = None) -> None:
        self.msg_glyph.configure(text=GLYPH[glyph], fg=color)
        self.msg_title.configure(text=title)
        self.msg_body.configure(text=body)
        if button:
            self.msg_button.configure(text=button)
            self.msg_button.pack(pady=(14, 0))
        else:
            self.msg_button.pack_forget()
        self.message.tkraise()

    def _show_empty(self) -> None:
        self.file_label.configure(text="No file selected")
        self.meta_label.configure(text="Add files on the left to get started.")
        self._show_message(
            "doc", TEXT_3, "Your Markdown will appear here",
            "Drop files onto this window or press Ctrl+O. Files are converted locally "
            "with Microsoft MarkItDown - nothing leaves your PC.",
        )

    def _show_job(self, key: str) -> None:
        job = self.jobs[key]
        self.file_label.configure(text=job.path.name)
        if job.status is Status.DONE:
            meta = (f"{len(job.markdown):,} characters · {len(job.markdown.split()):,} words · "
                    f"converted in {job.elapsed:.2f}s")
            if job.saved_to:
                meta += f" · saved to {job.saved_to}"
            self.meta_label.configure(text=meta)
            if not job.markdown.strip():
                self._show_message("warning", CAUTION, "No text found",
                                   "The file contains no extractable text. Scanned PDFs and photos need OCR, "
                                   "which MarkItDown does not perform locally.", "Convert again")
                return
            self._loading_editor = True
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", job.markdown)
            self.editor.edit_reset()
            self.editor.edit_modified(False)
            self._loading_editor = False
            self.editor_frame.tkraise()
        elif job.status is Status.FAILED:
            self.meta_label.configure(text=str(job.path.parent))
            self._show_message("error", CRITICAL, "Conversion failed", job.error, "Try again")
        else:
            self.meta_label.configure(text=str(job.path.parent))
            busy = job.status is Status.CONVERTING
            self._show_message("sync" if busy else "clock", ACCENT if busy else TEXT_3,
                               "Converting…" if busy else "Waiting in queue")

    def _on_editor_modified(self, _event=None) -> None:
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        if self._loading_editor or not self.current:
            return
        job = self.jobs.get(self.current)
        if job and job.status is Status.DONE:
            job.markdown = self.editor.get("1.0", "end-1c")
            if not job.dirty:
                job.dirty = True
                self._refresh_row(self.current)

    def _retry_current(self) -> None:
        if self.current:
            self._enqueue(self.current)
            self._show_job(self.current)
            self._update_controls()

    # ------------------------------------------------------------ export
    def _current_done(self) -> Job | None:
        job = self.jobs.get(self.current) if self.current else None
        return job if job and job.status is Status.DONE and job.markdown.strip() else None

    def copy_markdown(self) -> None:
        job = self._current_done()
        if job:
            self.root.clipboard_clear()
            self.root.clipboard_append(job.markdown)
            self._toast(f"Copied {len(job.markdown):,} characters to the clipboard.")

    def save_current(self) -> None:
        job = self._current_done()
        if not job:
            return
        target = filedialog.asksaveasfilename(
            parent=self.root, title="Export Markdown", defaultextension=".md",
            initialdir=self._last_save_dir or str(job.path.parent), initialfile=f"{job.path.stem}.md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if not target:
            return
        path = Path(target)
        error = core.write_text(path, job.markdown)
        if error:
            log.error(error.replace("\n", " "))
            messagebox.showerror("Export failed", error, parent=self.root)
            return
        self._last_save_dir = str(path.parent)
        job.dirty, job.saved_to = False, path
        self._refresh_row(self.current)
        self._show_job(self.current)
        self._toast(f"Saved {path.name}")

    def save_all(self) -> None:
        done = [(k, j) for k, j in self.jobs.items() if j.status is Status.DONE and j.markdown.strip()]
        if not done:
            return
        folder = filedialog.askdirectory(parent=self.root, title="Export all Markdown files to…",
                                         initialdir=self._last_save_dir or self._last_open_dir)
        if not folder:
            return
        out_dir = Path(folder)
        self._last_save_dir = folder
        used: set[str] = set()
        saved = failed = 0
        for key, job in done:
            target = core.unique_path(out_dir, job.path.stem, used)
            error = core.write_text(target, job.markdown)
            if error:
                log.error(error.replace("\n", " "))
                failed += 1
            else:
                job.dirty, job.saved_to = False, target
                saved += 1
            self._refresh_row(key)
        if self.current:
            self._show_job(self.current)
        if failed:
            messagebox.showwarning("Export finished with errors",
                                   f"Saved {saved} file(s). {failed} could not be written - see the log.",
                                   parent=self.root)
        else:
            self._toast(f"Exported {saved} file(s) to {out_dir}")

    # ------------------------------------------------------------- about
    def show_about(self) -> None:
        if getattr(self, "_about", None) is not None and self._about.winfo_exists():
            self._about.lift()
            return
        dlg = tk.Toplevel(self.root)
        self._about = dlg
        dlg.title(f"About {APP_NAME}")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)

        body = ttk.Frame(dlg, padding=(self.px(28), self.px(24), self.px(28), self.px(20)))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        icon = resource_path("assets/app.ico")
        logo = tk.Label(body, bg=BG)
        try:
            self._about_logo = tk.PhotoImage(file=str(resource_path("assets/app.png")))
            logo.configure(image=self._about_logo)
        except tk.TclError:
            logo.configure(text="M↓", font=(UI_DISPLAY, 22, "bold"), fg="#0b1a26", bg=ACCENT,
                           width=3, height=1)
        logo.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, self.px(16)))

        tk.Label(body, text=APP_NAME, font=(UI_DISPLAY, 16, "bold"), fg=TEXT, bg=BG).grid(
            row=0, column=1, sticky="w")
        tk.Label(body, text=f"Version {__version__} · Lite edition", font=(UI_FONT, 10), fg=TEXT_2,
                 bg=BG).grid(row=1, column=1, sticky="nw")
        tk.Label(body, text=COPYRIGHT, font=(UI_FONT, 10), fg=TEXT, bg=BG, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(self.px(18), 0))
        tk.Label(body, text=CREDITS, font=(UI_FONT, 9), fg=TEXT_3, bg=BG, justify="left",
                 wraplength=self.px(380)).grid(row=3, column=0, columnspan=2, sticky="w",
                                               pady=(self.px(10), 0))
        ok = ttk.Button(body, text="OK", style="Accent.TButton", width=10, command=dlg.destroy)
        ok.grid(row=4, column=0, columnspan=2, sticky="e", pady=(self.px(20), 0))

        if icon.exists():
            try:
                dlg.iconbitmap(str(icon))
            except tk.TclError:
                pass
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

        # Centre over the main window, then make modal.
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        apply_dark_title_bar(int(dlg.wm_frame(), 16))
        ok.focus_set()
        dlg.grab_set()

    # -------------------------------------------------------------- misc
    def _update_controls(self) -> None:
        has = self._current_done() is not None
        for btn in (self.copy_btn, self.save_btn):
            btn.state(["!disabled"] if has else ["disabled"])
        any_done = any(j.status is Status.DONE and j.markdown.strip() for j in self.jobs.values())
        self.save_all_btn.state(["!disabled"] if any_done else ["disabled"])
        done = sum(j.status is Status.DONE for j in self.jobs.values())
        failed = sum(j.status is Status.FAILED for j in self.jobs.values())
        pending = sum(j.status in (Status.QUEUED, Status.CONVERTING) for j in self.jobs.values())
        self.clear_btn.state(["!disabled"] if done + failed else ["disabled"])
        parts = [f"{done} converted"] + ([f"{failed} failed"] if failed else []) + (
            [f"{pending} pending"] if pending else [])
        self.stats.configure(text=" · ".join(parts) if self.jobs else "")
        if pending:
            if not self.progress.winfo_ismapped():
                self.progress.grid(row=0, column=1, padx=12)
                self.progress.start(12)
            self.status_label.configure(text=f"Converting… {pending} file(s) remaining")
        else:
            if self.progress.winfo_ismapped():
                self.progress.stop()
                self.progress.grid_remove()
            if self._status_after is None:
                self.status_label.configure(text="Ready")

    def _toast(self, text: str) -> None:
        self.status_label.configure(text=text)
        if self._status_after:
            self.root.after_cancel(self._status_after)
        self._status_after = self.root.after(5000, self._end_toast)

    def _end_toast(self) -> None:
        self._status_after = None
        self.status_label.configure(text="Ready")
        self._update_controls()

    def _append_log(self, text: str, level: int) -> None:
        tag = "error" if level >= logging.ERROR else "warn" if level >= logging.WARNING else ()
        self.log_view.configure(state="normal")
        self.log_view.insert("end", text + "\n", tag)
        if int(self.log_view.index("end-1c").split(".")[0]) > 2000:
            self.log_view.delete("1.0", "500.0")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _toggle_log(self) -> None:
        if str(self.log_card) in self.vpane.panes():
            self.vpane.forget(self.log_card)
            self.log_toggle.configure(text="Show log")
        else:
            self.vpane.add(self.log_card, weight=1)
            self.log_toggle.configure(text="Hide log")

    def _open_log_folder(self) -> None:
        os.startfile(self.log_file.parent)

    def on_close(self) -> None:
        busy = any(j.status in (Status.QUEUED, Status.CONVERTING) for j in self.jobs.values())
        unsaved = [j for j in self.jobs.values() if j.status is Status.DONE and j.dirty]
        if busy or unsaved:
            parts = (["Some files are still being converted."] if busy else []) + (
                [f"{len(unsaved)} converted file(s) have not been exported."] if unsaved else [])
            if not messagebox.askyesno("Quit MarkItDown Studio Lite?",
                                       " ".join(parts) + "\n\nDo you want to quit anyway?",
                                       parent=self.root, icon="warning"):
                return
        self._work.put(None)
        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    set_app_user_model_id(APP_ID + ".Lite")
    enable_dpi_awareness()
    log_file = setup_logging()
    log.info("%s %s starting (Python %s)", APP_TITLE, __version__, sys.version.split()[0])
    core.set_engine_factory(create_engine)

    root = tk.Tk()
    root.title(APP_TITLE)
    scale = root.winfo_fpixels("1i") / 96.0
    width = min(int(1180 * scale), int(root.winfo_screenwidth() * 0.9))
    height = min(int(760 * scale), int(root.winfo_screenheight() * 0.85))
    root.geometry(f"{width}x{height}")
    root.minsize(int(900 * scale), int(560 * scale))
    icon = resource_path("assets/app.ico")
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass

    import sv_ttk

    sv_ttk.set_theme("dark")

    def report_callback_exception(exc_type, exc, tb) -> None:
        import traceback

        log.critical("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)),
                     extra={"file_only": True})
        log.error("Unexpected error: %s", exc)
        messagebox.showerror("Something went wrong",
                             f"An unexpected error occurred. The app will keep running.\n\n{exc_type.__name__}: {exc}",
                             parent=root)

    root.report_callback_exception = report_callback_exception

    app = LiteApp(root, log_file)
    root.update_idletasks()
    apply_dark_title_bar(int(root.wm_frame(), 16))

    files = [a for a in argv[1:] if Path(a).exists()]
    if files:
        root.after(200, app.add_files, files)

    root.mainloop()
    return 0
