"""Check whether Microsoft MarkItDown has published a newer release than the one bundled.

Only an anonymous, read-only request to PyPI / GitHub is made (no personal data sent).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

PYPI_URL = "https://pypi.org/pypi/markitdown/json"
GITHUB_API = "https://api.github.com/repos/microsoft/markitdown/releases/latest"


@dataclass(frozen=True)
class UpdateInfo:
    installed: str
    latest: str
    newer: bool
    notes_url: str


def installed_version() -> str:
    try:
        from markitdown.__about__ import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        from importlib.metadata import version

        return version("markitdown")


def _key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v.split("+")[0].split("rc")[0])[:4])


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "MarkItDownStudio-update-check", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https URLs
        return json.load(resp)


def latest_upstream() -> tuple[str, str]:
    """(version, release-notes URL) of the newest stable markitdown."""
    try:
        data = _get_json(PYPI_URL)
        ver = data["info"]["version"]
        return ver, f"https://github.com/microsoft/markitdown/releases/tag/v{ver}"
    except Exception as exc:  # noqa: BLE001 - fall back to GitHub
        log.debug("PyPI check failed (%s); trying GitHub", exc)
        data = _get_json(GITHUB_API)
        return str(data["tag_name"]).lstrip("v"), data.get("html_url", "https://github.com/microsoft/markitdown/releases")


def check() -> UpdateInfo:
    """Raises OSError/ValueError-like errors when offline; callers show a friendly message."""
    current = installed_version()
    latest, url = latest_upstream()
    return UpdateInfo(current, latest, _key(latest) > _key(current), url)


# ------------------------------------------------------------------ self-update
APP_API = "https://api.github.com/repos/trungnguyennn/markitdown-studio/releases/latest"


@dataclass(frozen=True)
class AppUpdate:
    version: str
    notes_url: str
    asset_name: str
    asset_url: str
    sha256: str
    size: int
    mode: str  # "portable" | "installer" | "manual"


def install_mode() -> str:
    """How this copy of the app can be updated."""
    import sys
    from pathlib import Path

    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return "manual"
    folder = Path(sys.executable).parent
    return "installer" if (folder / "unins000.exe").exists() else "portable"


def check_app(current: str) -> AppUpdate | None:
    """Newest MarkItDown Studio release if it is newer than *current*, else None."""
    import os

    current = os.environ.get("MDS_FAKE_VERSION", current)  # lets tests simulate an old build
    data = _get_json(APP_API)
    version = str(data["tag_name"]).lstrip("v")
    if _key(version) <= _key(current):
        return None
    mode = install_mode()
    want = "-Windows-Setup.exe" if mode == "installer" else "-Windows-Portable.exe"
    asset = next(
        (a for a in data.get("assets", []) if a["name"].endswith(want) and "Lite" not in a["name"]), None
    )
    if asset is None:
        return AppUpdate(version, data.get("html_url", ""), "", "", "", 0, "manual")
    digest = str(asset.get("digest") or "")
    sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
    if not sha:
        mode = "manual"
    return AppUpdate(
        version, data.get("html_url", ""), asset["name"], asset["browser_download_url"], sha, int(asset["size"]), mode
    )


def download(update: AppUpdate, progress=None, cancelled=lambda: False) -> str:
    """Download the asset to a temp folder, verify SHA-256, return the file path."""
    import hashlib
    import tempfile
    from pathlib import Path

    folder = Path(tempfile.mkdtemp(prefix="mds_update_"))
    target = folder / update.asset_name
    h = hashlib.sha256()
    req = urllib.request.Request(update.asset_url, headers={"User-Agent": "MarkItDownStudio-update"})
    done = 0
    with urllib.request.urlopen(req, timeout=30) as resp, target.open("wb") as out:  # noqa: S310
        while chunk := resp.read(1 << 20):
            if cancelled():
                raise OSError("Download cancelled.")
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, update.size)
    if h.hexdigest().lower() != update.sha256.lower():
        target.unlink(missing_ok=True)
        raise OSError("The downloaded file failed its integrity check and was discarded.")
    return str(target)


def start_apply(update: AppUpdate, downloaded: str) -> None:
    """Start a detached helper that finishes the update after this process exits."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    if update.mode == "installer":
        subprocess.Popen(  # noqa: S603
            [downloaded, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/NORESTART"],
            creationflags=flags, close_fds=True,
        )
        return
    target = sys.executable
    script = Path(tempfile.mkdtemp(prefix="mds_swap_")) / "swap.bat"
    script.write_text(
        "@echo off\r\n"
        "set n=0\r\n"
        ":retry\r\n"
        "set /a n+=1\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        f'move /y "{downloaded}" "{target}" >nul 2>&1\r\n'
        "if errorlevel 1 if %n% lss 60 goto retry\r\n"
        f'start "" "{target}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n',
        encoding="ascii",
    )
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)  # noqa: S603,S607
