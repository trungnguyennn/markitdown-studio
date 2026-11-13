"""Build-side helpers for the LZMA-packed portable exe (see tools/portable_boot.py).

Used by MarkItDownStudio-portable.spec:

    needed = probe(folder_build_exe)          # which files Python loads before the boot hook
    keep_bin, keep_data, payload = split(a.binaries, a.datas, needed)
    ...EXE(..., keep_bin, keep_data, ...)     # PyInstaller one-file exe with only those files
    append_payload(exe_path, payload)         # everything else, LZMA-compressed, appended
"""

from __future__ import annotations

import fnmatch
import json
import lzma
import os
import struct
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

MAGIC = b"MDSLZMA1"
FOOTER = struct.Struct("<8sQQ")

# Always left in PyInstaller's own archive, whatever the probe says: the Python
# and C run-time libraries have to be on disk before Python can start at all.
# (On the build PC the C run-time may load from System32 and so not show up in
# the probe; on a PC without it, the bundled copy is what gets used.)
ALWAYS_KEEP = (
    "python3*.dll", "vcruntime*.dll", "msvcp*.dll", "ucrtbase.dll", "api-ms-win-*.dll", "libffi*.dll",
    "encodings/*",  # text codecs can be looked up at any moment
)

CODE_SUFFIXES = (".dll", ".pyd", ".exe")
CODE_STREAMS = 3  # + 1 stream for everything else = 4 unpack threads
MAX_DICT = 64 << 20


def _norm(name: str) -> str:
    return name.replace("\\", "/").lower()


def probe(exe_path: str, log=print) -> set[str]:
    """Run the folder build with the boot hook in probe mode; return the files it had loaded."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "probe.json")
        env = dict(os.environ, MDS_BOOT_PROBE=out)
        subprocess.run([exe_path], env=env, check=False, timeout=120)
        if not os.path.exists(out):
            raise SystemExit("lzma_onefile: the probe run produced no file list")
        with open(out, encoding="utf-8") as fh:
            names = {_norm(n) for n in json.load(fh)}
    log(f"lzma_onefile: Python loads {len(names)} files before the boot hook")
    return names


def split(binaries, datas, needed: set[str], log=print):
    """Partition the TOC: (binaries to keep, datas to keep, payload [(dest, source path)])."""

    def keep(dest: str) -> bool:
        d = _norm(dest)
        return d in needed or any(fnmatch.fnmatch(d, pattern) for pattern in ALWAYS_KEEP)

    keep_bin, keep_data, payload = [], [], []
    for source, kept in ((binaries, keep_bin), (datas, keep_data)):
        for entry in source:
            if keep(entry[0]) or (len(entry) > 2 and entry[2] == "SYMLINK"):
                kept.append(entry)
            else:
                payload.append((entry[0], entry[1]))
    size = lambda items: sum(os.path.getsize(e[1]) for e in items) / 1e6  # noqa: E731
    log(f"lzma_onefile: kept in PyInstaller archive: {len(keep_bin) + len(keep_data)} files, "
        f"{size(keep_bin) + size(keep_data):.1f} MB; LZMA payload: {len(payload)} files, {size(payload):.1f} MB")
    return keep_bin, keep_data, payload


def _compress(group: list[tuple[str, str]], is_code: bool) -> tuple[bytes, list]:
    raw = bytearray()
    files = []
    for dest, src in group:
        with open(src, "rb") as fh:
            data = fh.read()
        files.append([dest.replace("\\", "/"), len(data)])
        raw += data
    dict_size = 1 << 20
    while dict_size < min(len(raw), MAX_DICT):
        dict_size <<= 1
    chain = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME, "dict_size": dict_size}]
    if is_code:
        chain.insert(0, {"id": lzma.FILTER_X86})  # makes machine code more compressible
    return lzma.compress(bytes(raw), format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, filters=chain), files


def append_payload(exe_path: str, payload: list[tuple[str, str]], log=print) -> None:
    started = time.perf_counter()

    def order(item):  # similar files next to each other compress better
        dest = _norm(item[0])
        return (os.path.splitext(dest)[1], os.path.basename(dest), dest)

    code = sorted((p for p in payload if _norm(p[0]).endswith(CODE_SUFFIXES)), key=order)
    other = sorted((p for p in payload if not _norm(p[0]).endswith(CODE_SUFFIXES)), key=order)

    # Split the code into streams of roughly equal size so they unpack in parallel.
    groups: list[tuple[list, bool]] = []
    total = sum(os.path.getsize(src) for _dest, src in code)
    target = total / CODE_STREAMS if total else 0
    current, filled = [], 0
    for item in code:
        current.append(item)
        filled += os.path.getsize(item[1])
        if filled >= target and len(groups) < CODE_STREAMS - 1:
            groups.append((current, True))
            current, filled = [], 0
    if current:
        groups.append((current, True))
    if other:
        groups.append((other, False))

    with ThreadPoolExecutor(len(groups)) as pool:  # lzma releases the GIL
        packed = list(pool.map(lambda g: _compress(*g), groups))

    dirs = sorted({os.path.dirname(dest.replace("\\", "/")) for dest, _src in payload} - {""})
    streams = []
    with open(exe_path, "ab") as out:
        out.seek(0, os.SEEK_END)
        for blob, files in packed:
            streams.append({"offset": out.tell(), "size": len(blob), "files": files})
            out.write(blob)
        index = json.dumps({"dirs": dirs, "streams": streams}, separators=(",", ":")).encode("utf-8")
        index_offset = out.tell()
        out.write(index)
        out.write(FOOTER.pack(MAGIC, index_offset, len(index)))

    packed_mb = sum(len(blob) for blob, _files in packed) / 1e6
    log(f"lzma_onefile: appended {len(payload)} files in {len(packed)} LZMA streams, {packed_mb:.1f} MB "
        f"({time.perf_counter() - started:.0f}s); exe is now {os.path.getsize(exe_path) / 1e6:.1f} MB")
