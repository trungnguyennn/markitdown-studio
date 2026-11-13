@echo off
rem This script lives in windows\ ; everything runs from the project root.
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Running setup first...
    call "%~dp0setup.bat" || exit /b 1
)
rem pythonw = no console window behind the GUI
start "" ".venv\Scripts\pythonw.exe" main.py %*
