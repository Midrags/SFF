@echo off
cd /d "%~dp0"

echo ========================================
echo Building SteaMidra Executable
echo ========================================
echo.

echo Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

if exist "third_party\SteamAutoCrack\Steam-auto-crack-3.5.0.3\Steam-auto-crack-3.5.0.3\SteamAutoCrack.CLI\SteamAutoCrack.CLI.csproj" (
    where dotnet >nul 2>&1
    if not errorlevel 1 (
        echo.
        echo Building SteamAutoCrack CLI v3.5.0.3...
        dotnet publish "third_party\SteamAutoCrack\Steam-auto-crack-3.5.0.3\Steam-auto-crack-3.5.0.3\SteamAutoCrack.CLI\SteamAutoCrack.CLI.csproj" -c Release -r win-x86 --self-contained true -p:PublishSingleFile=false -p:ErrorOnDuplicatePublishOutputFiles=false
        if exist "third_party\SteamAutoCrack\Steam-auto-crack-3.5.0.3\Steam-auto-crack-3.5.0.3\SteamAutoCrack.CLI\bin\Release\net10.0-windows\win-x86\publish\SteamAutoCrack.CLI.exe" (
            if not exist "third_party\SteamAutoCrack\cli" mkdir "third_party\SteamAutoCrack\cli"
            xcopy /E /Y /I "third_party\SteamAutoCrack\Steam-auto-crack-3.5.0.3\Steam-auto-crack-3.5.0.3\SteamAutoCrack.CLI\bin\Release\net10.0-windows\win-x86\publish\*" "third_party\SteamAutoCrack\cli" >nul
            echo SteamAutoCrack CLI v3.5.0.3 built successfully.
        ) else (
            echo WARNING: SteamAutoCrack CLI build did not produce expected output.
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
