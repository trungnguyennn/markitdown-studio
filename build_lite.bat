@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-lite\Scripts\python.exe" (
    call "%~dp0setup_lite.bat" || exit /b 1
)

if not exist "assets\app.png" (
    echo ERROR: assets\app.ico / app.png missing. Generate them once with:  .venv\Scripts\python.exe tools\make_icon.py
    exit /b 1
)

echo Building single-file Lite exe (markitdown_lite.spec)...
.venv-lite\Scripts\python.exe -m PyInstaller --noconfirm --clean ^
    --distpath dist\lite --workpath build\lite ^
    markitdown_lite.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo.
echo Done: dist\lite\MarkItDownStudio-Lite.exe
endlocal
