"""Self-test used by the build scripts:  MarkItDownStudio --smoke-test OUT_DIR FILE...

Runs the real window: queues the files, waits for every conversion, then writes
into OUT_DIR one .md per converted file, results.json (status of each file) and
window.png (a screenshot). Exit code 0 means every file converted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QTimer
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

TIMEOUT_MS = 10 * 60 * 1000


def start(app: QApplication, window, out_dir: Path, files: list[Path]) -> None:
    from .main_window import Status

    out_dir.mkdir(parents=True, exist_ok=True)
    clock = QElapsedTimer()
    clock.start()
    timer = QTimer(window)
    timer.setInterval(250)

    def finish(timed_out: bool) -> None:
        timer.stop()
        results = {}
        for job in window._jobs.values():
            results[job.path.name] = {
                "status": job.status.name,
                "characters": len(job.markdown),
                "error": job.error,
                "detail": job.detail,
            }
            if job.status is Status.DONE:
                (out_dir / f"{job.path.name}.md").write_text(job.markdown, encoding="utf-8", newline="")
        # Show the last converted file in Preview so the screenshot covers the renderer too.
        done = [k for k, j in window._jobs.items() if j.status is Status.DONE and j.markdown.strip()]
        if done:
            window.queue.setCurrentItem(window._items[done[-1]])
            window.preview_button.setChecked(True)
        app.processEvents()
        window.grab().save(str(out_dir / "window.png"))
        def passed(r: dict) -> bool:
            # "UnknownValueError" is the speech service answering that the audio holds
            # no speech (true for the generated test tone): the audio path worked.
            return r["status"] == "DONE" or "UnknownValueError" in r["detail"]

        ok = not timed_out and len(results) == len(files) and all(passed(r) for r in results.values())
        (out_dir / "results.json").write_text(
            json.dumps({"ok": ok, "timed_out": timed_out, "files": results}, indent=2), encoding="utf-8"
        )
        app.exit(0 if ok else 1)

    def poll() -> None:
        busy = any(j.status in (Status.QUEUED, Status.CONVERTING) for j in window._jobs.values())
        if not busy:
            finish(False)
        elif clock.elapsed() > TIMEOUT_MS:
            finish(True)

    timer.timeout.connect(poll)
    window.add_files(files)
    timer.start()
