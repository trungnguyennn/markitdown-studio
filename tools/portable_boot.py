"""First code to run inside MarkItDownStudio-Portable.exe (a PyInstaller run-time hook).

The portable exe is an ordinary PyInstaller one-file program, except that most of
its files are not stored in PyInstaller's own (zlib) archive. They sit in a few
LZMA streams appended to the end of the exe, which compress far better. This hook
unpacks them into the same temporary folder PyInstaller already uses, before any
other part of the app is imported. From then on the program is identical to a
normal one-file build: same files, same folder, and PyInstaller removes the
folder when the app closes.

Layout of the appended data (written by tools/lzma_onefile.py):

    [xz stream 0][xz stream 1]...[index: JSON][footer: magic, index offset, index size]

Each stream holds the plain concatenation of its files; the index lists, per
stream, where it starts and the (path, size) of every file in order. Streams are
unpacked in parallel threads. xz verifies a CRC-64 of everything it unpacks.

Set MDS_BOOT_PROBE=<file> to make the hook write the list of files Python has
loaded so far and exit; the build uses that to decide which files must stay in
PyInstaller's archive so that Python can start and run this hook.
"""

import ctypes
import importlib
import json
import lzma
import os
import struct
import sys
import threading

MAGIC = b"MDSLZMA1"
FOOTER = struct.Struct("<8sQQ")
READ_SIZE = 1 << 20


def _write_probe(target: str) -> None:
    from ctypes import wintypes

    root = os.path.normcase(os.path.abspath(sys._MEIPASS)) + os.sep
    found = set()
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and os.path.normcase(os.path.abspath(path)).startswith(root):
            found.add(os.path.abspath(path)[len(root):])
    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetModuleFileNameW.argtypes = (wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
    psapi.EnumProcessModules.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    )
    handles = (wintypes.HMODULE * 4096)()
    used = wintypes.DWORD()
    if psapi.EnumProcessModules(kernel32.GetCurrentProcess(), handles, ctypes.sizeof(handles), ctypes.byref(used)):
        for handle in handles[: used.value // ctypes.sizeof(wintypes.HMODULE)]:
            buf = ctypes.create_unicode_buffer(2048)
            if kernel32.GetModuleFileNameW(wintypes.HMODULE(handle), buf, len(buf)):
                path = os.path.abspath(buf.value)
                if os.path.normcase(path).startswith(root):
                    found.add(path[len(root):])
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(sorted(found), fh)


def _unpack_stream(exe: str, root: str, stream: dict, errors: list) -> None:
    try:
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
        files = iter(stream["files"])
        out = None
        left = 0

        def next_file():
            # Opens the next file that has content; empty files are created on the way.
            nonlocal out, left
            for name, size in files:
                handle = open(os.path.join(root, name), "wb")
                if size:
                    out, left = handle, size
                    return True
                handle.close()
            out, left = None, 0
            return False

        more = next_file()
        with open(exe, "rb") as src:
            src.seek(stream["offset"])
            remaining = stream["size"]
            while remaining and not decoder.eof:
                chunk = src.read(min(READ_SIZE, remaining))
                if not chunk:
                    raise EOFError("the program file is cut short")
                remaining -= len(chunk)
                data = memoryview(decoder.decompress(chunk))
                while len(data):
                    if not more:
                        raise ValueError("more data than the index describes")
                    part = data[:left]
                    out.write(part)
                    left -= len(part)
                    data = data[len(part):]
                    if left == 0:
                        out.close()
                        more = next_file()
        if more or not decoder.eof:
            raise EOFError("the packed data ended early")
    except BaseException as exc:  # noqa: BLE001 - reported on the main thread
        errors.append(exc)
        if out is not None and not out.closed:
            out.close()


def _boot() -> None:
    probe = os.environ.get("MDS_BOOT_PROBE")
    if probe:
        _write_probe(probe)
        os._exit(0)

    exe = sys.executable
    try:
        with open(exe, "rb") as fh:
            fh.seek(-FOOTER.size, os.SEEK_END)
            magic, index_offset, index_size = FOOTER.unpack(fh.read(FOOTER.size))
            if magic != MAGIC:
                return  # an ordinary build without appended data
            fh.seek(index_offset)
            index = json.loads(fh.read(index_size).decode("utf-8"))
    except OSError:
        return

    root = sys._MEIPASS
    for folder in index["dirs"]:
        os.makedirs(os.path.join(root, folder), exist_ok=True)

    errors: list = []
    threads = [
        threading.Thread(target=_unpack_stream, args=(exe, root, stream, errors)) for stream in index["streams"]
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if errors:
        reason = errors[0]
        if isinstance(reason, OSError) and getattr(reason, "winerror", None) in (39, 112):
            hint = "The disk holding your temporary folder is full."
        elif isinstance(reason, (lzma.LZMAError, EOFError, ValueError)):
            hint = "The program file is damaged or incomplete. Please download or copy it again."
        else:
            hint = "The program could not unpack its files into your temporary folder."
        ctypes.windll.user32.MessageBoxW(
            None, f"{hint}\n\nDetails: {type(reason).__name__}: {reason}", "MarkItDown Studio", 0x10
        )
        sys.exit(1)

    importlib.invalidate_caches()  # the import system must notice the new files


_boot()
