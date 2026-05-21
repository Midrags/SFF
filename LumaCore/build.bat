@echo off
setlocal EnableDelayedExpansion

title LumaCore Build

set "SOURCE_DIR=%~dp0source"
set "BUILD_DIR=%~dp0build"
set "OUT_DIR=%~dp0Releases"

echo.
echo ============================================================
echo  LumaCore Build
echo  Source  : %SOURCE_DIR%
echo  Build   : %BUILD_DIR%
echo  Output  : %OUT_DIR%
echo ============================================================
echo.

:: --- Locate cmake: try PATH first, then the VS Build Tools default install ---
set "CMAKE_EXE=cmake"
where cmake >nul 2>&1
if !errorlevel! neq 0 (
    set "CMAKE_EXE=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    if not exist "!CMAKE_EXE!" (
        set "CMAKE_EXE=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    )
    if not exist "!CMAKE_EXE!" (
        echo [ERROR] cmake not found. Add cmake to PATH or install VS Build Tools 2022.
        pause
        exit /b 1
    )
    echo [INFO] Using cmake from VS Build Tools: !CMAKE_EXE!
)

:: --- Detect generator: Ninja Multi-Config if ninja is available, else VS 2022 ---
set "GENERATOR=Visual Studio 17 2022"
set "GEN_ARGS=-A x64"
where ninja >nul 2>&1
if !errorlevel! == 0 (
    set "GENERATOR=Ninja Multi-Config"
    set "GEN_ARGS="
    echo [INFO] Using Ninja Multi-Config generator
) else (
    echo [INFO] Using Visual Studio 17 2022 generator
)

:: --- Configure (first-time only) ---
if not exist "%BUILD_DIR%\CMakeCache.txt" (
    echo [STEP] Configuring...
    if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
    "!CMAKE_EXE!" -S "%SOURCE_DIR%" -B "%BUILD_DIR%" -G "!GENERATOR!" !GEN_ARGS!
    if !errorlevel! neq 0 (
        echo [ERROR] Configure failed.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Build dir already configured, skipping configure.
)

:: --- Build Release ---
echo.
echo [STEP] Building Release (clean)...
"!CMAKE_EXE!" --build "%BUILD_DIR%" --config Release --parallel
if !errorlevel! neq 0 (
    echo [WARN] Release build failed ^(non-fatal^).
)

:: --- Build Debug ---
echo.
echo [STEP] Building Debug (clean)...
"!CMAKE_EXE!" --build "%BUILD_DIR%" --config Debug --parallel
if !errorlevel! neq 0 (
    echo [WARN] Debug build failed ^(non-fatal^).
)

:: --- Copy DLLs to LumaCore\Releases\ (main output next to build.bat) ---
echo.
echo [STEP] Copying DLLs to %OUT_DIR%...
mkdir "%OUT_DIR%\Release" 2>nul
mkdir "%OUT_DIR%\Debug"   2>nul

if exist "%BUILD_DIR%\Release\LumaCore.dll" (
    copy /Y "%BUILD_DIR%\Release\LumaCore.dll" "%OUT_DIR%\Release\LumaCore.dll"
    copy /Y "%BUILD_DIR%\Release\dwmapi.dll"   "%OUT_DIR%\Release\dwmapi.dll"
    echo [OK] Release DLLs copied to %OUT_DIR%\Release
) else (
    echo [SKIP] Release LumaCore.dll not found, skipping.
)

if exist "%BUILD_DIR%\Debug\LumaCore.dll" (
    copy /Y "%BUILD_DIR%\Debug\LumaCore.dll" "%OUT_DIR%\Debug\LumaCore.dll"
    copy /Y "%BUILD_DIR%\Debug\dwmapi.dll"   "%OUT_DIR%\Debug\dwmapi.dll"
    echo [OK] Debug DLLs copied to %OUT_DIR%\Debug
) else (
    echo [SKIP] Debug LumaCore.dll not found, skipping.
)

echo.
echo ============================================================
echo  Done. DLLs are in:
echo    %OUT_DIR%\Release
echo    %OUT_DIR%\Debug
echo ============================================================
echo.
pause
endlocal
