@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call "%~dp0setup.bat" || exit /b 1
)
set PY=.venv\Scripts\python.exe

echo [1/2] Generating icon...
%PY% tools\make_icon.py || exit /b 1

echo [2/2] Building single-file portable exe (takes a few minutes)...
%PY% -m PyInstaller ^
    --noconfirm --clean ^
    --onefile ^
    --windowed ^
    --name MarkItDownStudio-Portable ^
    --icon "%~dp0assets\app.ico" ^
    --version-file "%~dp0installer\version_info.txt" ^
    --distpath dist\portable ^
    --workpath build\portable ^
    --specpath build\portable ^
    --collect-all markitdown ^
    --collect-all magika ^
    --collect-data pdfminer ^
    --collect-data pptx ^
    --copy-metadata markitdown ^
    --copy-metadata magika ^
    --exclude-module tkinter ^
    main.py
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo.
echo Done: dist\portable\MarkItDownStudio-Portable.exe
endlocal
