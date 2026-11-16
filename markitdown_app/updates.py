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
