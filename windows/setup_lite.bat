@echo off
setlocal
rem This script lives in windows\ ; everything runs from the project root.
cd /d "%~dp0.."

echo [1/3] Creating virtual environment (.venv-lite)...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv-lite
) else (
    python -m venv .venv-lite
)
if errorlevel 1 (
    echo ERROR: Could not create the virtual environment. Install Python 3.10+ from python.org first.
    exit /b 1
)
set PY=.venv-lite\Scripts\python.exe

echo [2/3] Installing small dependencies...
%PY% -m pip install --upgrade pip || exit /b 1
%PY% -m pip install -r requirements-lite.txt || exit /b 1

echo [3/3] Installing markitdown and pdfminer.six without heavy dependencies...
%PY% -m pip install --no-deps markitdown==0.1.9 pdfminer.six==20260107 || exit /b 1

echo.
echo Lite setup complete. Run with:   .venv-lite\Scripts\python.exe main_lite.py
echo Build the small exe with:        windows\build_lite.bat
endlocal
