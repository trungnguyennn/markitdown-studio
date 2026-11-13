@echo off
setlocal
cd /d "%~dp0"

rem Locate the Inno Setup 6 compiler
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo ERROR: Inno Setup 6 not found. Install it with:
    echo     winget install --id JRSoftware.InnoSetup -e
    exit /b 1
)

rem Build the app first if needed (or always, with: make_installer.bat rebuild)
if /i "%~1"=="rebuild" goto build
if exist "dist\MarkItDownStudio\MarkItDownStudio.exe" goto package
:build
call "%~dp0build.bat" || exit /b 1

:package
for /f "usebackq delims=" %%v in (`.venv\Scripts\python.exe -c "from markitdown_app import __version__; print(__version__)"`) do set "APPVER=%%v"
echo Creating installer for version %APPVER%...
"%ISCC%" /Q /DAppVersion=%APPVER% "installer\MarkItDownStudio.iss"
if errorlevel 1 (
    echo ERROR: Inno Setup compilation failed.
    exit /b 1
)

echo.
echo Done: dist\installer\MarkItDownStudio-Setup-%APPVER%.exe
endlocal
