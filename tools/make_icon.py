"""Render the app icon to assets/app.ico (used by the .exe and the installer).

Run:  .venv\\Scripts\\python.exe tools\\make_icon.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402  (Pillow is installed with markitdown[all])
from PySide6.QtCore import QBuffer, QIODevice, QSize  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from markitdown_app.icons import app_icon, app_icon_pixmap  # noqa: E402

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - painting needs a GUI app
    icon = app_icon()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    icon.pixmap(QSize(256, 256)).save(buffer, "PNG")
    master = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")

    out = ROOT / "assets" / "app.ico"
    out.parent.mkdir(exist_ok=True)
    master.save(out, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"Wrote {out}")

    # Logo for the Lite edition's About dialog (Tk reads PNG natively).
    png = ROOT / "assets" / "app.png"
    master.resize((80, 80), Image.Resampling.LANCZOS).save(png, format="PNG", optimize=True)
    print(f"Wrote {png}")

    # macOS icon: Apple's template leaves ~10% transparent padding around the tile.
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    app_icon_pixmap(1024, margin=100 / 1024).save(buffer, "PNG")
    icns = ROOT / "assets" / "app.icns"
    Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA").save(icns, format="ICNS")
    print(f"Wrote {icns}")


if __name__ == "__main__":
    main()
