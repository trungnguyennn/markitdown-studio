"""Native Windows file drag-and-drop for Tk (WM_DROPFILES via ctypes).

Tkinter has no built-in drop support, and the usual add-on (tkdnd) ships extra
binaries. Subclassing the top-level window procedure costs nothing in size.

IMPORTANT: the window procedure runs *inside* Tk's event dispatch. Calling any
Tk/tkinter API from it (even `after()`) corrupts tkinter's saved thread state
and crashes the interpreter. So the WndProc only records the paths in a
thread-safe deque; the app drains it from its own periodic `after()` loop.
"""

from __future__ import annotations

import collections
import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class FileDropTarget:
    """Collects files dropped on the window; call drain() from the Tk thread."""

    def __init__(self, toplevel) -> None:
        self._toplevel = toplevel
        self._pending: collections.deque[list[str]] = collections.deque()
        self._old_proc = None
        self._proc = None
        self.hwnd = 0
        if sys.platform != "win32":
            return
        try:
            self._install()
        except (AttributeError, OSError, ValueError) as exc:
            log.warning("Drag-and-drop unavailable: %s", exc)

    def drain(self) -> list[list[str]]:
        batches = []
        while self._pending:
            batches.append(self._pending.popleft())
        return batches

    def _install(self) -> None:
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = (
            ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        )
        shell32.DragQueryFileW.restype = wintypes.UINT
        shell32.DragQueryFileW.argtypes = (ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT)
        shell32.DragFinish.argtypes = (ctypes.c_void_p,)
        shell32.DragAcceptFiles.argtypes = (wintypes.HWND, wintypes.BOOL)

        # Everything the WndProc touches must exist BEFORE it is installed:
        # Windows starts calling it immediately.
        self._user32, self._shell32 = user32, shell32
        self._toplevel.update_idletasks()
        self.hwnd = int(self._toplevel.wm_frame(), 16)
        self._proc = WNDPROC(self._wndproc)  # keep a reference: it must outlive the window
        self._old_proc = user32.GetWindowLongPtrW(self.hwnd, GWLP_WNDPROC)
        user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, ctypes.cast(self._proc, ctypes.c_void_p))
        shell32.DragAcceptFiles(self.hwnd, True)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            paths = []
            try:
                count = self._shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                for i in range(count):
                    length = self._shell32.DragQueryFileW(wparam, i, None, 0)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    self._shell32.DragQueryFileW(wparam, i, buf, length + 1)
                    paths.append(buf.value)
            finally:
                self._shell32.DragFinish(wparam)
            if paths:
                self._pending.append(paths)  # no Tk calls here - see module docstring
            return 0
        return self._user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)
