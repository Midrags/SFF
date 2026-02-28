@echo off
cd /d "%~dp0"

echo ========================================
echo Building SteaMidra GUI Executable
echo ========================================
echo.

echo Cleaning old GUI build files...
if exist "build\build_sff_gui" rmdir /s /q "build\build_sff_gui"

echo.
echo Building GUI executable...
echo This may take 5-10 minutes...
echo.

REM Suppress pkg_resources deprecation from PyInstaller/build deps so log stays clean
set PYTHONWARNINGS=ignore::UserWarning
python -m PyInstaller build_sff_gui.spec

if errorlevel 1 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo Make sure PyInstaller, PyQt6 and PyQt6-WebEngine are installed:
    echo   pip install pyinstaller PyQt6 PyQt6-WebEngine
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Executable: dist\SteaMidra_GUI.exe
echo.

if exist "dist\SteaMidra_GUI.exe" (
    python -c "import os; size = os.path.getsize('dist/SteaMidra_GUI.exe'); print(f'Size: {size / (1024*1024):.1f} MB')"
    echo.
    echo Refreshing icon for SteaMidra_GUI.exe...
    move /y "dist\SteaMidra_GUI.exe" "dist\SteaMidra_GUI_temp.exe" >nul
    move /y "dist\SteaMidra_GUI_temp.exe" "dist\SteaMidra_GUI.exe" >nul
)

echo.
echo You can now run: dist\SteaMidra_GUI.exe
echo Settings will be saved in: dist\settings.bin
echo.
pause
