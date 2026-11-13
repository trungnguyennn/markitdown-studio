"""UI-independent conversion core shared by the Full (Qt) and Lite (Tk) editions.

Every failure is translated into a ConversionError that carries a short,
user-friendly message plus technical detail for the log file.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Extensions MarkItDown handles (Full edition, markitdown[all]).
SUPPORTED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "Documents": (".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".epub", ".msg"),
    "Web & data": (".html", ".htm", ".csv", ".json", ".jsonl", ".xml", ".ipynb", ".rss", ".atom"),
    "Text": (".txt", ".md", ".markdown", ".rst"),
    "Images": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"),
    "Audio": (".wav", ".mp3", ".m4a", ".mp4"),
    "Archives": (".zip",),
}


def file_dialog_filter(groups: dict[str, tuple[str, ...]] = SUPPORTED_EXTENSIONS) -> str:
    """Qt file-dialog filter string."""
    all_exts = " ".join(f"*{e}" for group in groups.values() for e in group)
    parts = [f"All supported files ({all_exts})"]
    for name, exts in groups.items():
        parts.append(f"{name} ({' '.join(f'*{e}' for e in exts)})")
    parts.append("All files (*.*)")
    return ";;".join(parts)


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    markdown: str
    title: str | None
    elapsed: float


class ConversionError(Exception):
    """A conversion failure with a message that is safe to show to users."""

    def __init__(self, user_message: str, detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail or user_message


def _default_factory():
    from markitdown import MarkItDown

    return MarkItDown(enable_plugins=False)


# MarkItDown is expensive to construct, so a single instance is shared. The
# RLock serialises access because the library does not document thread safety.
_engine = None
_engine_factory: Callable[[], object] = _default_factory
_engine_lock = threading.RLock()


def set_engine_factory(factory: Callable[[], object]) -> None:
    """Let an edition customise MarkItDown (e.g. register extra converters)."""
    global _engine_factory, _engine
    with _engine_lock:
        _engine_factory = factory
        _engine = None


def _get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            try:
                log.info("Initialising MarkItDown engine…")
                _engine = _engine_factory()
            except ImportError as exc:
                raise ConversionError(
                    "The MarkItDown library is not installed. Run the setup script again.",
                    repr(exc),
                ) from exc
        return _engine


def warm_up() -> None:
    """Create the engine ahead of time (call from a worker thread at start-up)."""
    try:
        _get_engine()
        log.info("MarkItDown engine ready.")
    except ConversionError as exc:
        log.error("%s (%s)", exc.user_message, exc.detail)
    except Exception as exc:  # noqa: BLE001
        log.error("MarkItDown failed to start: %s", exc)


def convert_file(path: Path) -> ConversionResult:
    """Convert *path* to Markdown. Raises ConversionError on any failure."""
    path = Path(path)
    if not path.exists():
        raise ConversionError("The file could not be found. It may have been moved or deleted.")
    if not path.is_file():
        raise ConversionError("This item is a folder, not a file.")
    try:
        if path.stat().st_size == 0:
            raise ConversionError("The file is empty (0 bytes).")
    except OSError as exc:
        system = "macOS" if sys.platform == "darwin" else "Windows"
        raise ConversionError(f"{system} did not allow reading this file.", repr(exc)) from exc

    from markitdown import (
        FileConversionException,
        MissingDependencyException,
        UnsupportedFormatException,
    )

    start = time.perf_counter()
    try:
        with _engine_lock:
            result = _get_engine().convert(str(path))
    except ConversionError:
        raise
    except UnsupportedFormatException as exc:
        raise ConversionError(
            f"The '{path.suffix or 'unknown'}' format is not supported.", repr(exc)
        ) from exc
    except MissingDependencyException as exc:
        raise ConversionError(
            "A component needed for this file type is not included in this edition.",
            str(exc),
        ) from exc
    except FileConversionException as exc:
        raise ConversionError(
            "The file could not be read. It may be corrupted, encrypted or password-protected.",
            format_exception(exc),
        ) from exc
    except PermissionError as exc:
        raise ConversionError(
            "Access denied. Close the file if it is open in another program and try again.", repr(exc)
        ) from exc
    except MemoryError as exc:
        raise ConversionError("The file is too large to convert with the available memory.") from exc
    except OSError as exc:
        raise ConversionError("A system error occurred while reading the file.", repr(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort guard, details go to the log
        raise ConversionError(
            "An unexpected error occurred during conversion. See the log for details.",
            format_exception(exc),
        ) from exc

    elapsed = time.perf_counter() - start
    markdown = getattr(result, "markdown", None) or getattr(result, "text_content", "") or ""
    title = getattr(result, "title", None)
    return ConversionResult(source=path, markdown=markdown, title=title, elapsed=elapsed)


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc)).strip()


def unique_path(folder: Path, stem: str, used: set[str]) -> Path:
    """'name.md', then 'name (1).md', ... skipping existing and already-used names."""
    import os

    candidate = folder / f"{stem}.md"
    n = 1
    while candidate.exists() or os.path.normcase(str(candidate)) in used:
        candidate = folder / f"{stem} ({n}).md"
        n += 1
    used.add(os.path.normcase(str(candidate)))
    return candidate


def write_text(target: Path, text: str) -> str | None:
    """Write UTF-8 text. Returns None on success or a user-friendly error message."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" keeps the converter's line endings exactly as produced.
        with target.open("w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    except PermissionError:
        return (
            f"Permission denied while writing:\n{target}\n\n"
            "Choose another folder or close the file if it is open elsewhere."
        )
    except OSError as exc:
        return f"Could not write:\n{target}\n\n{exc.strerror or exc}"
    log.info("Saved %s", target)
    return None
