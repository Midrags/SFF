@echo off
echo ========================================
echo Installing SteaMidra Requirements
echo ========================================
echo.
echo This installs all dependencies including CLI, GUI, and
echo multiplayer fix (online-fix.me). One install for everything.
echo.
echo For multiplayer fix: Chrome browser must be installed.
echo.
pause

pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo requirements.txt failed. Try runtime-only:
    pip install -r requirements-consumer.txt
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo You can run SteaMidra with: python Main.py or python Main_gui.py
echo.
pause
