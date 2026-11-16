"""Offline OCR using the operating system's own engine (no extra download, no cloud).

* Windows 10/11: Windows.Media.Ocr  (recognises the languages installed in Windows)
* macOS 10.15+:  Vision framework

An image converter is registered with MarkItDown so every image file (and the text in
it) is converted to Markdown. Nothing leaves the computer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from typing import Any, BinaryIO

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp")


class OcrUnavailable(Exception):
    """OCR cannot run on this computer (message is user-friendly)."""


def _prepare_png(data: bytes, max_dim: int) -> str:
    """Decode with Pillow (any format), shrink if needed, save as a temp PNG."""
    import io

    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    img = img.convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))
    fd, name = tempfile.mkstemp(suffix=".png", prefix="mds_ocr_")
    os.close(fd)
    img.save(name, "PNG")
    return name


async def _windows_ocr(data: bytes) -> str:
    try:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import FileAccessMode, StorageFile
    except ImportError as exc:  # pragma: no cover
        raise OcrUnavailable("OCR components are missing from this build.") from exc

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable(
            "Windows has no OCR language installed. Add one in Settings > Time & language > Language & region."
        )
    path = _prepare_png(data, int(OcrEngine.max_image_dimension))
    try:
        file = await StorageFile.get_file_from_path_async(path)
        stream = await file.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)
        stream.close()
        return "\n".join(line.text for line in result.lines)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _mac_ocr(data: bytes) -> str:
    try:
        import Vision
        from Foundation import NSURL
    except ImportError as exc:  # pragma: no cover
        raise OcrUnavailable("OCR components are missing from this build.") from exc

    path = _prepare_png(data, 8000)
    try:
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
        ok, err = handler.performRequests_error_([request], None)
        if not ok:
            raise OcrUnavailable(f"The macOS text recogniser failed: {err}")
        lines = []
        for obs in request.results() or []:
            cands = obs.topCandidates_(1)
            if cands:
                lines.append(str(cands[0].string()))
        return "\n".join(lines)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def recognize(data: bytes) -> str:
    """Return the text found in the image bytes ('' if none)."""
    if sys.platform == "win32":
        return asyncio.run(_windows_ocr(data)).strip()
    if sys.platform == "darwin":
        return _mac_ocr(data).strip()
    raise OcrUnavailable("OCR is available on Windows and macOS only.")


def register(md: Any) -> None:
    """Add the OCR image converter to a MarkItDown instance (tried before the stock one)."""
    from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo

    class OcrImageConverter(DocumentConverter):
        def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
            ext = (stream_info.extension or "").lower()
            mime = (stream_info.mimetype or "").lower()
            return ext in IMAGE_EXTENSIONS or mime.startswith("image/")

        def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any):
            try:
                text = recognize(file_stream.read())
            except OcrUnavailable as exc:
                log.warning("OCR unavailable: %s", exc)
                text = ""
                note = f"*OCR unavailable: {exc}*"
            else:
                note = "*No text was detected in this image.*"
            return DocumentConverterResult(markdown=text or note)

    md.register_converter(OcrImageConverter(), priority=-1.0)
