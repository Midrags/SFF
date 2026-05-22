@echo off
setlocal

set NSIS=C:\Program Files (x86)\NSIS\makensis.exe

:: Extract version from sff/strings.py
for /f "tokens=3" %%v in ('findstr "^VERSION" sff\strings.py') do set APP_VERSION=%%v
set APP_VERSION=%APP_VERSION:"=%
if "%APP_VERSION%"=="" (
    echo Could not read VERSION from sff\strings.py
    pause
    exit /b 1
)
echo Version: %APP_VERSION%

:: Patch installer.nsi fallback version to match strings.py
python -c "import re,sys; c=open('installer.nsi').read(); c=re.sub(r'(!define VERSION\s+\")[^\"]+\"', r'\g<1>%APP_VERSION%\"', c); open('installer.nsi','w').write(c)"
echo Patched installer.nsi to version %APP_VERSION%

:: Allow NSI-only mode: pass "nsi" as first argument to skip PyInstaller
if /i "%~1"=="nsi" goto compile_nsi

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

:compile_nsi
echo [2/2] Compiling NSIS installer...
if not exist "%NSIS%" goto nsis_missing
goto nsis_found
:nsis_missing
    echo NSIS not found at "%NSIS%"
    echo Install NSIS from https://nsis.sourceforge.io/Download
    pause
    exit /b 1
:nsis_found
"%NSIS%" /DVERSION=%APP_VERSION% installer.nsi
if %errorlevel% neq 0 (
    echo NSIS compile failed.
    pause
    exit /b 1
)

echo Done. Installer written to SteaMidra-%APP_VERSION%-Setup.exe
pause
