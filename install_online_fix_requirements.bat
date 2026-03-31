@echo off
echo ========================================
echo  Installing SteaMidra Requirements
echo ========================================
echo.
echo  Installs all dependencies: CLI, GUI (PyQt6), online-fix
echo  (Selenium/Chrome), and Tor fallback support.
echo.
echo  For multiplayer fix: Chrome browser must be installed.
echo.
pause

pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  pip install failed. Check the error above.
    echo  Common fix: make sure Python 3.12 is installed and on PATH.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Step 2: Installing steam (no-deps)
echo ========================================
echo.
echo  steam==1.4.4 has a stale urllib3 ^<2 constraint that conflicts
echo  with Selenium. Installing with --no-deps bypasses this check.
echo  steam works fine with urllib3 2.x at runtime.
echo.
pip install steam==1.4.4 --no-deps
if errorlevel 1 (
    echo.
    echo  Warning: steam install failed. Check the error above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  OPTIONAL: Tor Expert Bundle
echo ========================================
echo.
echo  Tor Expert Bundle lets SteaMidra automatically fall back to
echo  the Tor network when the primary GMRC endpoint is down.
echo  Without it, the tool falls back to ManifestHub API / manual
echo  code entry instead. It is NOT required to use SteaMidra.
echo.
echo  If installed: unzip anywhere and run tor.exe before using
echo  the tool. It listens on port 9050 automatically.
echo.
set /p TOR_CHOICE= Open Tor download page now? [Y/N]: 
if /i "%TOR_CHOICE%"=="Y" (
    echo  Opening https://www.torproject.org/download/#tor-downloads ...
    start https://www.torproject.org/download/#tor-downloads
    echo.
    echo  Download "Expert Bundle" ^(Windows, no browser needed^).
    echo  Unzip anywhere, then run tor.exe once to start the daemon.
    echo  Leave it running while using SteaMidra.
)

echo.
echo ========================================
echo  Installation Complete!
echo ========================================
echo.
echo  Run SteaMidra:
echo    CLI:  python Main.py
echo    GUI:  python Main_gui.py
echo.
pause
