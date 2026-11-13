# MarkItDown Studio for Windows

Everything specific to the Windows version. Run these from the project root.

| Script | What it does |
|---|---|
| `windows\setup.bat` | create `.venv` and install dependencies |
| `windows\run.bat` | run the app from source |
| `windows\make_installer.bat rebuild` | build the installer: `dist\installer\MarkItDownStudio-Setup-1.0.0.exe` |
| `windows\build_portable.bat` | build the one-file portable exe: `dist\portable\MarkItDownStudio-Portable.exe` |
| `windows\setup_lite.bat`, `windows\build_lite.bat` | set up and build the Lite edition: `dist\lite\MarkItDownStudio-Lite.exe` |

Other files here:

- `installer/` holds the Inno Setup script, the exe version details and the third-party notices.
- `MarkItDownStudio-portable.spec` and `markitdown_lite.spec` are the PyInstaller build recipes.

Details, sizes and limitations are in the [main README](../README.md).
