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

echo [2/2] Building dist\MarkItDownStudio with PyInstaller...
%PY% -m PyInstaller ^
    --noconfirm --clean ^
    --windowed ^
    --name MarkItDownStudio ^
    --icon "%CD%\assets\app.ico" ^
    --version-file "%CD%\windows\installer\version_info.txt" ^
    --specpath build ^
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
echo Done: dist\MarkItDownStudio\MarkItDownStudio.exe
echo Next: run windows\make_installer.bat to create the setup .exe
endlocal
