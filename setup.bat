@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Creating virtual environment (.venv)...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 (
    echo ERROR: Could not create the virtual environment. Install Python 3.10+ from python.org first.
    exit /b 1
)

echo [2/3] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo [3/3] Installing dependencies (this can take a few minutes)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed. See the messages above.
    exit /b 1
)

echo.
echo Setup complete. Start the app with run.bat
endlocal
