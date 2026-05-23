@echo off
setlocal EnableDelayedExpansion

set "SOURCE_DIR=%~dp0source"
set "BUILD_DIR=%~dp0build"
set "OUT_DIR=%~dp0Releases"

:: --- Argument parsing ----------------------------------------------------
:: --no-pause   skip the trailing 'pause' (use when running from a script/agent)
:: --debug-only / --release-only restrict the build to one config
set "NO_PAUSE=0"
set "BUILD_RELEASE=1"
set "BUILD_DEBUG=1"
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--no-pause"     ( set "NO_PAUSE=1"      & shift & goto parse_args )
if /I "%~1"=="--debug-only"   ( set "BUILD_RELEASE=0" & shift & goto parse_args )
if /I "%~1"=="--release-only" ( set "BUILD_DEBUG=0"   & shift & goto parse_args )
echo [WARN] Unknown argument: %~1
shift
goto parse_args
:args_done

echo.
echo ============================================================
echo  LumaCore Build (ALWAYS CLEAN)
echo  Source  : %SOURCE_DIR%
echo  Build   : %BUILD_DIR%
echo  Output  : %OUT_DIR%
echo  Release : %BUILD_RELEASE%   Debug: %BUILD_DEBUG%
echo ============================================================
echo.

:: --- ALWAYS delete build directory to prevent stale cache issues ---
:: This guarantees that source edits ALWAYS produce updated DLLs — no stale
:: incremental link, no cached object files. Slower but always correct.
if exist "%BUILD_DIR%" (
    echo [STEP] Deleting old build directory...
    rmdir /S /Q "%BUILD_DIR%"
    if exist "%BUILD_DIR%" (
        echo [ERROR] Failed to delete %BUILD_DIR% (file in use?)
        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
)

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
        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
    echo [INFO] Using cmake from VS Build Tools: !CMAKE_EXE!
)

:: --- Pick generator: prefer Ninja Multi-Config (fast, parallel, multi-config),
::     fall back to Visual Studio 17 2022.
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

:: --- Configure ---
echo [STEP] Configuring...
mkdir "%BUILD_DIR%" 2>nul
"!CMAKE_EXE!" -S "%SOURCE_DIR%" -B "%BUILD_DIR%" -G "!GENERATOR!" !GEN_ARGS!
if !errorlevel! neq 0 (
    echo [ERROR] Configure failed.
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

:: --- Build Release and Debug ---
:: Build Release first so a partial Debug failure doesn't hide a working
:: Release DLL. Each build step is independent — a Release error does not
:: stop the Debug build, and vice versa.
set "BUILD_FAILED=0"

if "%BUILD_RELEASE%"=="1" (
    echo.
    echo [STEP] Building Release...
    "!CMAKE_EXE!" --build "%BUILD_DIR%" --config Release --parallel
    if !errorlevel! neq 0 (
        echo [WARN] Release build failed.
        set "BUILD_FAILED=1"
    )
)

if "%BUILD_DEBUG%"=="1" (
    echo.
    echo [STEP] Building Debug...
    "!CMAKE_EXE!" --build "%BUILD_DIR%" --config Debug --parallel
    if !errorlevel! neq 0 (
        echo [WARN] Debug build failed.
        set "BUILD_FAILED=1"
    )
)

:: --- Copy DLLs to Releases\<Config>\ ---
echo.
echo [STEP] Copying DLLs to %OUT_DIR%...

if "%BUILD_RELEASE%"=="1" (
    if exist "%BUILD_DIR%\Release\LumaCore.dll" (
        mkdir "%OUT_DIR%\Release" 2>nul
        copy /Y "%BUILD_DIR%\Release\LumaCore.dll" "%OUT_DIR%\Release\" >nul
        if exist "%BUILD_DIR%\Release\dwmapi.dll" (
            copy /Y "%BUILD_DIR%\Release\dwmapi.dll" "%OUT_DIR%\Release\" >nul
        )
        echo [OK] Release DLLs copied to %OUT_DIR%\Release
    ) else (
        echo [SKIP] Release LumaCore.dll not produced.
    )
)

if "%BUILD_DEBUG%"=="1" (
    if exist "%BUILD_DIR%\Debug\LumaCore.dll" (
        mkdir "%OUT_DIR%\Debug" 2>nul
        copy /Y "%BUILD_DIR%\Debug\LumaCore.dll" "%OUT_DIR%\Debug\" >nul
        if exist "%BUILD_DIR%\Debug\dwmapi.dll" (
            copy /Y "%BUILD_DIR%\Debug\dwmapi.dll" "%OUT_DIR%\Debug\" >nul
        )
        echo [OK] Debug DLLs copied to %OUT_DIR%\Debug
    ) else (
        echo [SKIP] Debug LumaCore.dll not produced.
    )
)

echo.
echo ============================================================
echo  Done. DLLs are in:
if "%BUILD_RELEASE%"=="1" echo    %OUT_DIR%\Release
if "%BUILD_DEBUG%"=="1"   echo    %OUT_DIR%\Debug
echo ============================================================
echo.

if "%NO_PAUSE%"=="0" pause
endlocal
exit /b %BUILD_FAILED%
