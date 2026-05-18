@echo off
setlocal

set NSIS=C:\Program Files (x86)\NSIS\makensis.exe

:: Extract version from sff/strings.py (mirrors the Linux build script)
for /f "tokens=2 delims=^"" %%v in ('findstr /R "^VERSION = " sff\strings.py') do set APP_VERSION=%%v
if "%APP_VERSION%"=="" (
    echo Could not read VERSION from sff\strings.py
    pause
    exit /b 1
)
echo Version: %APP_VERSION%

echo [1/2] Building PyInstaller distribution...
call .venv\Scripts\activate.bat 2>nul || (
    echo Activating venv failed — trying system Python
)
python -m PyInstaller build_sff_gui.spec --noconfirm
if %errorlevel% neq 0 (
    echo PyInstaller build failed.
    pause
    exit /b 1
)

echo [2/2] Compiling NSIS installer...
if not exist "%NSIS%" (
    echo NSIS not found at %NSIS%
    echo Install NSIS from https://nsis.sourceforge.io/Download
    pause
    exit /b 1
)
"%NSIS%" /DVERSION=%APP_VERSION% installer.nsi
if %errorlevel% neq 0 (
    echo NSIS compile failed.
    pause
    exit /b 1
)

echo Done. Installer written to SteaMidra-*-Setup.exe
pause
