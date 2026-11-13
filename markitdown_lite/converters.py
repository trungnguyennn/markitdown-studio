"""Lightweight converters that replace markitdown's heavy built-ins in the Lite
edition. They plug into MarkItDown's own converter registry, so everything
else (HTML, DOCX, CSV, JSON, EPUB, ZIP, MSG, ...) still runs through markitdown.

  PDF  : pdfminer.six only (markitdown's own fallback path) - no pdfplumber,
         pypdfium2 or Pillow.
  PPTX : Python standard library (zipfile + XML) - no python-pptx, lxml, Pillow.
  XLSX : openpyxl - no pandas/numpy.
  XLS  : xlrd     - no pandas/numpy.
"""

from __future__ import annotations

import datetime as _dt
import io
import posixpath
import re
import zipfile
from typing import Any, BinaryIO, Iterable

from defusedxml import ElementTree as SafeET

from .shims import install as _install_shims

_install_shims()  # must run before markitdown is imported

from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo  # noqa: E402

# Tried before markitdown's built-ins (PRIORITY_SPECIFIC_FILE_FORMAT == 0.0).
LITE_PRIORITY = -1.0


def _accepts(stream_info: StreamInfo, extensions: tuple[str, ...], mimetypes: tuple[str, ...]) -> bool:
    ext = (stream_info.extension or "").lower()
    mime = (stream_info.mimetype or "").lower()
    return ext in extensions or any(mime.startswith(m) for m in mimetypes)


# ------------------------------------------------------------------ tables
def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, _dt.datetime):
        value = value.date() if value.time() == _dt.time(0) else value.isoformat(sep=" ")
    if isinstance(value, (_dt.date, _dt.time)):
        value = value.isoformat()
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("|", "\\|").replace("\n", "<br>").strip()


def markdown_table(rows: Iterable[Iterable[Any]]) -> str:
    """Rows of values -> GitHub Markdown table (first row is the header)."""
    grid = [[_cell_text(v) for v in row] for row in rows]
    # Drop fully empty rows, then trailing empty columns.
    grid = [r for r in grid if any(c for c in r)]
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    while width > 0 and not any(len(r) >= width and r[width - 1] for r in grid):
        width -= 1
    if width == 0:
        return ""
    grid = [(r + [""] * width)[:width] for r in grid]
    lines = ["| " + " | ".join(grid[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in grid[1:]]
    return "\n".join(lines)


# --------------------------------------------------------------------- PDF
class PdfMinerConverter(DocumentConverter):
    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _accepts(stream_info, (".pdf",), ("application/pdf", "application/x-pdf"))

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        from pdfminer.high_level import extract_text

        text = extract_text(io.BytesIO(file_stream.read()))
        text = text.replace("\f", "\n\n")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return DocumentConverterResult(markdown=text.strip())


# -------------------------------------------------------------------- XLSX
class XlsxConverter(DocumentConverter):
    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _accepts(
            stream_info, (".xlsx", ".xlsm"), ("application/vnd.openxmlformats-officedocument.spreadsheetml",)
        )

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(file_stream.read()), read_only=True, data_only=True)
        parts: list[str] = []
        try:
            for ws in wb.worksheets:
                table = markdown_table(ws.iter_rows(values_only=True))
                parts.append(f"## {ws.title}\n\n{table}" if table else f"## {ws.title}\n\n*(empty sheet)*")
        finally:
            wb.close()
        return DocumentConverterResult(markdown="\n\n".join(parts))


# --------------------------------------------------------------------- XLS
class XlsConverter(DocumentConverter):
    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _accepts(stream_info, (".xls",), ("application/vnd.ms-excel", "application/excel"))

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        import xlrd

        book = xlrd.open_workbook(file_contents=file_stream.read())
        parts: list[str] = []
        for sheet in book.sheets():
            rows = []
            for r in range(sheet.nrows):
                row = []
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
                        except (ValueError, OverflowError):
                            row.append(cell.value)
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        row.append(bool(cell.value))
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        row.append(xlrd.error_text_from_code.get(cell.value, "#ERR"))
                    else:
                        row.append(cell.value)
                rows.append(row)
            table = markdown_table(rows)
            parts.append(f"## {sheet.name}\n\n{table}" if table else f"## {sheet.name}\n\n*(empty sheet)*")
        return DocumentConverterResult(markdown="\n\n".join(parts))


# -------------------------------------------------------------------- PPTX
_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_R_ID = f"{{{_NS['r']}}}id"


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    """Relationship id -> absolute part name for *part*."""
    folder, name = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", name + ".rels")
    if rels_name not in z.namelist():
        return {}
    root = SafeET.fromstring(z.read(rels_name))
    out = {}
    for rel in root.findall("rel:Relationship", _NS):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        full = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        out[rel.get("Id", "")] = full
    return out


def _paragraphs(tx_body) -> list[tuple[int, str]]:
    """(indent level, text) for each non-empty paragraph in a text body."""
    out = []
    for p in tx_body.findall("a:p", _NS):
        pieces = []
        for node in p.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                pieces.append(node.text)
            elif tag == "br":
                pieces.append("\n")
        text = "".join(pieces).strip()
        if text:
            ppr = p.find("a:pPr", _NS)
            level = int(ppr.get("lvl", "0")) if ppr is not None else 0
            out.append((level, text))
    return out


def _position(shape) -> tuple[int, int]:
    off = shape.find(".//a:off", _NS)
    if off is None:
        return (1 << 40, 1 << 40)
    return (int(off.get("y", "0")), int(off.get("x", "0")))


def _placeholder_type(shape) -> str | None:
    ph = shape.find("./*/p:nvPr/p:ph", _NS)
    if ph is None:
        return None
    return ph.get("type", "body")


def _shape_markdown(shape) -> list[str]:
    tag = shape.tag.rsplit("}", 1)[-1]
    if tag == "grpSp":  # group: recurse in visual order
        children = [c for c in shape if c.tag.rsplit("}", 1)[-1] in ("sp", "grpSp", "graphicFrame", "pic")]
        out: list[str] = []
        for child in sorted(children, key=_position):
            out.extend(_shape_markdown(child))
        return out
    if tag == "pic":
        cnv = shape.find("./p:nvPicPr/p:cNvPr", _NS)
        alt = (cnv.get("descr") or cnv.get("name") or "image") if cnv is not None else "image"
        return [f"![{alt.strip()}](image)"]
    if tag == "graphicFrame":
        tbl = shape.find(".//a:tbl", _NS)
        if tbl is None:
            return []  # charts, SmartArt, ...: not extracted in Lite
        rows = []
        for tr in tbl.findall("a:tr", _NS):
            row = []
            for tc in tr.findall("a:tc", _NS):
                body = tc.find("a:txBody", _NS)
                row.append(" ".join(t for _, t in _paragraphs(body)) if body is not None else "")
            rows.append(row)
        table = markdown_table(rows)
        return [table] if table else []
    if tag == "sp":
        body = shape.find("p:txBody", _NS)
        if body is None:
            return []
        lines = []
        for level, text in _paragraphs(body):
            lines.append(("  " * level) + text if level else text)
        return ["\n".join(lines)] if lines else []
    return []


def _notes_text(z: zipfile.ZipFile, notes_part: str) -> str:
    root = SafeET.fromstring(z.read(notes_part))
    texts = []
    for sp in root.iter(f"{{{_NS['p']}}}sp"):
        if _placeholder_type(sp) == "body":
            body = sp.find("p:txBody", _NS)
            if body is not None:
                texts.extend(t for _, t in _paragraphs(body))
    return "\n".join(texts)


class PptxConverter(DocumentConverter):
    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _accepts(
            stream_info,
            (".pptx", ".pptm"),
            ("application/vnd.openxmlformats-officedocument.presentationml",),
        )

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        with zipfile.ZipFile(io.BytesIO(file_stream.read())) as z:
            pres = "ppt/presentation.xml"
            pres_rels = _rels(z, pres)
            root = SafeET.fromstring(z.read(pres))
            slide_parts = [
                pres_rels[s.get(_R_ID)]
                for s in root.findall("p:sldIdLst/p:sldId", _NS)
                if s.get(_R_ID) in pres_rels
            ]
            out: list[str] = []
            title_of_deck = None
            for number, part in enumerate(slide_parts, start=1):
                slide = SafeET.fromstring(z.read(part))
                tree = slide.find("p:cSld/p:spTree", _NS)
                block = [f"<!-- Slide number: {number} -->"]
                if tree is not None:
                    shapes = [c for c in tree if c.tag.rsplit("}", 1)[-1] in ("sp", "grpSp", "graphicFrame", "pic")]
                    titles = [s for s in shapes if _placeholder_type(s) in ("title", "ctrTitle")]
                    for t in titles:
                        body = t.find("p:txBody", _NS)
                        text = " ".join(x for _, x in _paragraphs(body)) if body is not None else ""
                        if text:
                            block.append(f"# {text}")
                            title_of_deck = title_of_deck or text
                    for shape in sorted((s for s in shapes if s not in titles), key=_position):
                        block.extend(_shape_markdown(shape))
                notes = next(
                    (p for p in _rels(z, part).values() if "notesSlide" in p and p in z.namelist()), None
                )
                if notes:
                    note_text = _notes_text(z, notes)
                    if note_text:
                        block.append(f"### Notes:\n{note_text}")
                out.append("\n\n".join(block))
        return DocumentConverterResult(markdown="\n\n".join(out).strip(), title=title_of_deck)


def create_engine():
    """MarkItDown with Lite stand-ins and converters (used by core.set_engine_factory)."""
    from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=False)
    for converter in (PdfMinerConverter(), PptxConverter(), XlsxConverter(), XlsConverter()):
        md.register_converter(converter, priority=LITE_PRIORITY)
    return md
