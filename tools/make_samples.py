"""Create one small sample file per supported format, for the build self-test.

Run:  python tools/make_samples.py OUT_DIR
Then: MarkItDownStudio --smoke-test RESULT_DIR OUT_DIR/*

Only libraries that the Full edition already installs are used.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import wave
import zipfile
from pathlib import Path


def make_pdf(path: Path) -> None:
    """A minimal one-page PDF with a text line, written by hand."""
    stream = b"BT /F1 18 Tf 72 720 Td (Sample PDF heading) Tj 0 -28 Td (Quarterly revenue was 1234 units.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))


def make_docx(path: Path) -> None:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{w}"><w:body>'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Sample Word heading</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>First paragraph with </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>bold text</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>Alpha</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>42</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    styles = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{w}">'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style></w:styles>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)


def make_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr(
            "content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">sample</dc:identifier>'
            "<dc:title>Sample Book</dc:title><dc:language>en</dc:language><dc:creator>Test Author</dc:creator></metadata>"
            '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c1"/></spine></package>',
        )
        z.writestr(
            "chapter1.xhtml",
            '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter 1</title></head>'
            "<body><h1>Chapter One</h1><p>It was a sample chapter.</p></body></html>",
        )


def make_wav(path: Path) -> None:
    rate = 16000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate))
        )


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sample.txt").write_text("Plain text sample.\nSecond line with unicode: café, 日本語.\n", encoding="utf-8")
    (out / "sample.md").write_text("# Markdown sample\n\n- one\n- two\n", encoding="utf-8")
    (out / "sample.html").write_text(
        "<html><head><title>HTML sample</title></head><body><h1>Heading</h1><p>A <a href='https://example.com'>link</a>.</p>"
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table></body></html>",
        encoding="utf-8",
    )
    (out / "sample.csv").write_text("name,qty,price\nwidget,3,1.50\ngadget,10,22.00\n", encoding="utf-8")
    (out / "sample.json").write_text(json.dumps({"title": "JSON sample", "items": [1, 2, 3]}, indent=2), encoding="utf-8")
    (out / "sample.xml").write_text('<?xml version="1.0"?><root><item id="1">XML sample</item></root>', encoding="utf-8")
    (out / "sample.ipynb").write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": ["# Notebook sample"]},
                    {"cell_type": "code", "metadata": {}, "execution_count": 1, "outputs": [], "source": ["print('hi')"]},
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    make_pdf(out / "sample.pdf")
    make_docx(out / "sample.docx")
    make_epub(out / "sample.epub")
    make_wav(out / "sample.wav")

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Region", "Units", "Revenue"])
    ws.append(["North", 12, 340.5])
    ws.append(["South", 7, 199.0])
    wb.create_sheet("Notes").append(["Excel sample note"])
    wb.save(out / "sample.xlsx")

    from pptx import Presentation

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "PowerPoint sample"
    slide.placeholders[1].text = "First bullet\nSecond bullet"
    slide.notes_slide.notes_text_frame.text = "Speaker note text"
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    chart_slide = deck.slides.add_slide(deck.slide_layouts[5])
    chart_slide.shapes.title.text = "Chart slide"
    chart_data = CategoryChartData()
    chart_data.categories = ["Q1", "Q2", "Q3"]
    chart_data.add_series("Sales", (10, 20, 30))
    chart_slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.5), Inches(6), Inches(4), chart_data
    )
    deck.save(out / "sample.pptx")

    from PIL import Image

    image = Image.new("RGB", (64, 48), (44, 143, 214))
    image.save(out / "sample.png")
    image.save(out / "sample.jpg", quality=85)

    with zipfile.ZipFile(out / "sample.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out / "sample.csv", "inner/sample.csv")
        z.write(out / "sample.docx", "inner/sample.docx")
        z.write(out / "sample.xlsx", "inner/sample.xlsx")

    print(f"Wrote {len(list(out.iterdir()))} sample files to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build/samples"))
