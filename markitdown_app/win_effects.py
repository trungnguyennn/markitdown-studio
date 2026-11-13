"""Small Win32 helpers (no-ops on non-Windows platforms)."""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 10 20H1+ / Windows 11
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # Windows 10 1809-1909
_DWMWA_WINDOW_CORNER_PREFERENCE = 33  # Windows 11
_DWMWCP_ROUND = 2


def set_app_user_model_id(app_id: str) -> None:
    """Give the process its own taskbar identity (correct icon/grouping)."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError) as exc:
        log.debug("SetCurrentProcessExplicitAppUserModelID failed: %s", exc)


def apply_dark_title_bar(hwnd: int) -> None:
    """Ask DWM for a dark caption bar and rounded corners."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi
    except (AttributeError, OSError):
        return
    value = ctypes.c_int(1)
    hr = dwm.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
    )
    if hr != 0:
        dwm.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(value), ctypes.sizeof(value)
        )
    corner = ctypes.c_int(_DWMWCP_ROUND)
    dwm.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), ctypes.sizeof(corner)
    )
