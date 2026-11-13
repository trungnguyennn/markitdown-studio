@echo off
setlocal
rem This script lives in windows\ ; everything runs from the project root.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    call "%~dp0setup.bat" || exit /b 1
)
set PY=.venv\Scripts\python.exe

echo [1/2] Generating icon...
%PY% tools\make_icon.py || exit /b 1

echo [2/2] Building single-file portable exe (takes a few minutes)...
rem Full edition, every feature kept. Size comes from tools\size_trim.py (files the
rem app can never load) and LZMA packing (tools\lzma_onefile.py, tools\portable_boot.py).
%PY% -m PyInstaller --noconfirm --clean ^
    --distpath dist\portable --workpath build\portable ^
    windows\MarkItDownStudio-portable.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo.
echo Done: dist\portable\MarkItDownStudio-Portable.exe
endlocal
