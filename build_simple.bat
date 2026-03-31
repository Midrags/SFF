@echo off
cd /d "%~dp0"

echo ========================================
echo Building SteaMidra Executable
echo ========================================
echo.

echo Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

if exist "third_party\SteamAuto Code\SteamAuto\SteamAutoCrack.CLI\SteamAutoCrack.CLI.csproj" (
    where dotnet >nul 2>&1
    if not errorlevel 1 (
        echo.
        echo Building SteamAutoCrack CLI...
        dotnet build "third_party\SteamAuto Code\SteamAuto\SteamAutoCrack.CLI\SteamAutoCrack.CLI.csproj" -c Release
        if exist "third_party\SteamAuto Code\SteamAuto\SteamAutoCrack.CLI\bin\Release\net9.0-windows\SteamAutoCrack.CLI.dll" (
            if not exist "third_party\SteamAutoCrack\cli" mkdir "third_party\SteamAutoCrack\cli"
            copy /y "third_party\SteamAuto Code\SteamAuto\SteamAutoCrack.CLI\bin\Release\net9.0-windows\SteamAutoCrack.CLI.*" "third_party\SteamAutoCrack\cli" >nul
            if exist "third_party\SteamAuto Code\SteamAuto\SteamAutoCrack.Core\bin\Release\net9.0-windows\SteamAutoCrack.Core.dll" (
                copy /y "third_party\SteamAuto Code\SteamAuto\SteamAutoCrack.Core\bin\Release\net9.0-windows\SteamAutoCrack.Core.*" "third_party\SteamAutoCrack\cli" >nul
            )
        )
        echo.
    )
)

echo.
echo Building executable...
echo This may take 5-10 minutes...
echo.

REM Suppress pkg_resources deprecation from PyInstaller/build deps so log stays clean
set PYTHONWARNINGS=ignore::UserWarning
python -m PyInstaller build_sff.spec

if errorlevel 1 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Install requirements first (two steps):
    echo   1. pip install -r requirements.txt
    echo   2. pip install steam==1.4.4 --no-deps
    echo.
    echo Or just run: install_online_fix_requirements.bat
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Executable: dist\SteaMidra.exe
echo.

if exist "dist\SteaMidra.exe" (
    python -c "import os; size = os.path.getsize('dist/SteaMidra.exe'); print(f'Size: {size / (1024*1024):.1f} MB')"
    echo.
    echo Refreshing icon for SteaMidra.exe (so Windows shows the new icon)...
    move /y "dist\SteaMidra.exe" "dist\SteaMidra_temp.exe" >nul
    move /y "dist\SteaMidra_temp.exe" "dist\SteaMidra.exe" >nul
)

echo.
echo You can now run: dist\SteaMidra.exe
echo Settings will be saved in: dist\settings.bin
echo.
pause
