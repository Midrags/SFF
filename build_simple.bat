@echo off
cd /d "%~dp0"

echo ========================================
echo Building SteamForge Fetcher (SFF) Executable
echo ========================================
echo.

echo Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

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
    echo Make sure PyInstaller is installed: pip install pyinstaller
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Executable: dist\SFF.exe
echo.

if exist "dist\SFF.exe" (
    python -c "import os; size = os.path.getsize('dist/SFF.exe'); print(f'Size: {size / (1024*1024):.1f} MB')"
    echo.
    echo Refreshing icon for SFF.exe (so Windows shows the new icon)...
    move /y "dist\SFF.exe" "dist\SFF_temp.exe" >nul
    move /y "dist\SFF_temp.exe" "dist\SFF.exe" >nul
)

echo.
echo You can now run: dist\SFF.exe
echo Settings will be saved in: dist\settings.bin
echo.
pause
