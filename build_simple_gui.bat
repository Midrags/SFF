@echo off
cd /d "%~dp0"

echo ========================================
echo Building SFF GUI Executable
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
    echo Make sure PyInstaller and PyQt6 are installed:
    echo   pip install pyinstaller PyQt6
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Executable: dist\SFF_GUI.exe
echo.

if exist "dist\SFF_GUI.exe" (
    python -c "import os; size = os.path.getsize('dist/SFF_GUI.exe'); print(f'Size: {size / (1024*1024):.1f} MB')"
    echo.
    echo Refreshing icon for SFF_GUI.exe...
    move /y "dist\SFF_GUI.exe" "dist\SFF_GUI_temp.exe" >nul
    move /y "dist\SFF_GUI_temp.exe" "dist\SFF_GUI.exe" >nul
)

echo.
echo You can now run: dist\SFF_GUI.exe
echo Settings will be saved in: dist\settings.bin
echo.
pause
