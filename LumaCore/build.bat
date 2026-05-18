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
if %errorlevel% neq 0 (
    set "CMAKE_EXE=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    if not exist "!CMAKE_EXE!" (
        set "CMAKE_EXE=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    )
    if not exist "!CMAKE_EXE!" (
        echo [ERROR] cmake not found. Add cmake to PATH or install VS Build Tools 2022.
        pause & exit /b 1
    )
    echo [INFO] Using cmake from VS Build Tools: !CMAKE_EXE!
)

:: --- Detect generator: Ninja Multi-Config if ninja is available, else VS 2022 ---
set "GENERATOR=Visual Studio 17 2022"
set "GEN_ARGS=-A x64"
where ninja >nul 2>&1
if %errorlevel% == 0 (
    set "GENERATOR=Ninja Multi-Config"
    set "GEN_ARGS="
    echo [INFO] Using Ninja Multi-Config generator
) else (
    echo [INFO] Using Visual Studio 17 2022 generator
)

:: --- Clear CMake cache (keeps compiled deps, forces fresh generator detection) ---
echo [STEP] Clearing CMake cache...
if exist "%BUILD_DIR%\CMakeCache.txt" del /f /q "%BUILD_DIR%\CMakeCache.txt"
if exist "%BUILD_DIR%\CMakeFiles"     rd /s /q "%BUILD_DIR%\CMakeFiles"

:: --- Configure ---
echo [STEP] Configuring...
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
"!CMAKE_EXE!" -S "%SOURCE_DIR%" -B "%BUILD_DIR%" -G "!GENERATOR!" !GEN_ARGS!
if %errorlevel% neq 0 (
    echo [ERROR] Configure failed.
    pause & exit /b 1
)

:: --- Build Release ---
echo.
echo [STEP] Building Release (clean)...
"!CMAKE_EXE!" --build "%BUILD_DIR%" --config Release --clean-first --parallel
if %errorlevel% neq 0 (
    echo [ERROR] Release build failed.
    pause & exit /b 1
)

:: --- Build Debug ---
echo.
echo [STEP] Building Debug (clean)...
"!CMAKE_EXE!" --build "%BUILD_DIR%" --config Debug --clean-first --parallel
if %errorlevel% neq 0 (
    echo [WARN] Debug build failed (non-fatal).
)

:: --- Copy DLLs to LumaCore\Releases\ (main output next to build.bat) ---
echo.
echo [STEP] Copying DLLs to %OUT_DIR%...
if not exist "%OUT_DIR%\Release" md "%OUT_DIR%\Release"
if not exist "%OUT_DIR%\Debug"   md "%OUT_DIR%\Debug"

copy /Y "%BUILD_DIR%\Release\LumaCore.dll" "%OUT_DIR%\Release\LumaCore.dll" >nul 2>&1
copy /Y "%BUILD_DIR%\Release\dwmapi.dll"   "%OUT_DIR%\Release\dwmapi.dll"   >nul 2>&1
echo [OK] Release DLLs  ->  %OUT_DIR%\Release

copy /Y "%BUILD_DIR%\Debug\LumaCore.dll" "%OUT_DIR%\Debug\LumaCore.dll" >nul 2>&1
copy /Y "%BUILD_DIR%\Debug\dwmapi.dll"   "%OUT_DIR%\Debug\dwmapi.dll"   >nul 2>&1
echo [OK] Debug DLLs    ->  %OUT_DIR%\Debug

echo.
echo ============================================================
echo  Done. DLLs are in:
echo    %OUT_DIR%\Release   <-- copy to Steam for production
echo    %OUT_DIR%\Debug     <-- copy to Steam for testing (logs)
echo ============================================================
echo.
pause
endlocal
