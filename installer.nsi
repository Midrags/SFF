; SteaMidra Windows Installer
; NSIS MUI2 script — 64-bit, user-level, LZMA compression

!define APPNAME    "SteaMidra"
!define COMPANY    "Midrags"
!ifndef VERSION
  !define VERSION  "6.5.2"
!endif
!define EXENAME    "SteaMidra_GUI.exe"
!define PUBLISHER  "Midrags"

Name "${APPNAME}"
OutFile "SteaMidra-${VERSION}-Setup.exe"

InstallDir "$LOCALAPPDATA\${APPNAME}"
InstallDirRegKey HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${APPNAME} ${VERSION}"

; ============================================================
; MUI2
; ============================================================
!include "MUI2.nsh"
!include "x64.nsh"
!include "Sections.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON    "SFF.ico"
!define MUI_UNICON  "SFF.ico"

!define MUI_WELCOMEPAGE_TITLE     "Install ${APPNAME} ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT      "This will install ${APPNAME} ${VERSION} on your computer.$\r$\n$\r$\nClick Next to continue."

!define MUI_FINISHPAGE_RUN        "$INSTDIR\${EXENAME}"
!define MUI_FINISHPAGE_RUN_TEXT   "Launch ${APPNAME}"
!define MUI_FINISHPAGE_LINK       "Visit GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/Midrags/SFF"

; Installer pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ============================================================
; .onInit — require 64-bit Windows
; ============================================================
Function .onInit
    ${Unless} ${RunningX64}
        MessageBox MB_OK|MB_ICONSTOP "This installer requires a 64-bit version of Windows."
        Abort
    ${EndUnless}
FunctionEnd

; ============================================================
; Main install section
; ============================================================
Section "SteaMidra (required)" SEC_MAIN
    SectionIn RO

    SetOutPath "$INSTDIR"
    File /r "dist\SteaMidra_GUI\*"

    ; Bundle the icon at root so shortcuts and ARP show it
    File /oname=SteaMidra.ico "SFF.ico"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Add/Remove Programs (64-bit registry hive)
    SetRegView 64
    WriteRegStr  HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName"      "${APPNAME}"
    WriteRegStr  HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion"   "${VERSION}"
    WriteRegStr  HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher"        "${PUBLISHER}"
    WriteRegStr  HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon"      "$INSTDIR\SteaMidra.ico"
    WriteRegStr  HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString"  '"$INSTDIR\Uninstall.exe"'
    WriteRegStr  HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegStr  HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir" "$INSTDIR"


SectionEnd

; ============================================================
; Optional: .NET 9 Runtime
; ============================================================
Section ".NET 9 Runtime (required for downloads)" SEC_DOTNET
    FindFirst $0 $1 "$PROGRAMFILES64\dotnet\shared\Microsoft.NETCore.App\9.*"
    FindClose $0
    StrCmp $1 "" check_user_dotnet dotnet_ok

    check_user_dotnet:
        ; Per-user install at %LOCALAPPDATA%\Microsoft\dotnet — SteaMidra
        ; itself drops .NET 9 here on first launch when the system-wide
        ; install is missing. If we already see it there, skip the
        ; re-download so the installer doesn't waste 30 MB.
        FindFirst $0 $1 "$LOCALAPPDATA\Microsoft\dotnet\shared\Microsoft.NETCore.App\9.*"
        FindClose $0
        StrCmp $1 "" dotnet_get dotnet_ok

    dotnet_ok:
        DetailPrint ".NET 9 Runtime is already installed - skipping."
        Goto dotnet_end

    dotnet_get:
        DetailPrint "Downloading .NET 9 Runtime (x64)..."
        ClearErrors
        nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri ''https://aka.ms/dotnet/9.0/dotnet-runtime-win-x64.exe'' -OutFile ''$TEMP\dotnet9-installer.exe'' -UseBasicParsing"'
        Pop $0
        IfFileExists "$TEMP\dotnet9-installer.exe" 0 dotnet_dl_failed
        ExecWait '"$TEMP\dotnet9-installer.exe" /install /quiet /norestart' $0
        Delete "$TEMP\dotnet9-installer.exe"
        IntCmp $0 0 dotnet_end dotnet_install_failed dotnet_install_failed

    dotnet_dl_failed:
        DetailPrint "Could not download .NET 9 Runtime (no internet, AV block, or firewall)."
        DetailPrint "Skipping. SteaMidra will offer to install it again on first launch."
        Goto dotnet_end

    dotnet_install_failed:
        DetailPrint ".NET 9 Runtime installer returned exit code $0 (skipping)."
        DetailPrint "SteaMidra will offer to install it again on first launch."

    dotnet_end:
SectionEnd

; ============================================================
; Optional: Visual C++ 2022 Redistributable
; ============================================================
Section "Visual C++ 2022 Redistributable" SEC_VCREDIST
    ; x64
    SetRegView 64
    ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
    IntCmp $0 1 vcx64_ok vcx64_get vcx64_get

    vcx64_ok:
        DetailPrint "VC++ 2022 x64 already installed - skipping."
        Goto vcx64_end

    vcx64_get:
        DetailPrint "Downloading Visual C++ 2022 Redistributable (x64)..."
        ClearErrors
        nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri ''https://aka.ms/vs/17/release/vc_redist.x64.exe'' -OutFile ''$TEMP\vcredist_x64.exe'' -UseBasicParsing"'
        IfFileExists "$TEMP\vcredist_x64.exe" 0 vcx64_dl_failed
        ExecWait '"$TEMP\vcredist_x64.exe" /install /quiet /norestart' $0
        Delete "$TEMP\vcredist_x64.exe"
        Goto vcx64_end

    vcx64_dl_failed:
        DetailPrint "Could not download VC++ 2022 x64 (no internet, AV block, or firewall). Skipping."

    vcx64_end:
    ; x86
    SetRegView 32
    ReadRegDWORD $1 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86" "Installed"
    IntCmp $1 1 vcx86_ok vcx86_get vcx86_get

    vcx86_ok:
        DetailPrint "VC++ 2022 x86 already installed - skipping."
        Goto vcx86_end

    vcx86_get:
        DetailPrint "Downloading Visual C++ 2022 Redistributable (x86)..."
        ClearErrors
        nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri ''https://aka.ms/vs/17/release/vc_redist.x86.exe'' -OutFile ''$TEMP\vcredist_x86.exe'' -UseBasicParsing"'
        IfFileExists "$TEMP\vcredist_x86.exe" 0 vcx86_dl_failed
        ExecWait '"$TEMP\vcredist_x86.exe" /install /quiet /norestart' $0
        Delete "$TEMP\vcredist_x86.exe"
        Goto vcx86_end

    vcx86_dl_failed:
        DetailPrint "Could not download VC++ 2022 x86 (no internet, AV block, or firewall). Skipping."

    vcx86_end:
    SetRegView 64
SectionEnd

; ============================================================
; Optional: Desktop shortcut
; ============================================================
Section "Desktop Shortcut" SEC_DESKTOP
    CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\SteaMidra.ico"
SectionEnd

; ============================================================
; Optional: Start Menu shortcut
; ============================================================
Section "Start Menu Shortcut" SEC_STARTMENU
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortcut  "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"  "$INSTDIR\${EXENAME}" "" "$INSTDIR\SteaMidra.ico"
    CreateShortcut  "$SMPROGRAMS\${APPNAME}\Uninstall.lnk"   "$INSTDIR\Uninstall.exe"
SectionEnd

; ============================================================
; Section descriptions shown in the Components page
; ============================================================
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN}      "Core application files. Required."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DOTNET}    "Required for the DepotDownloaderMod download tool. Skipped automatically if .NET 9 is already installed."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_VCREDIST}  "Visual C++ runtime libraries used by SteaMidra and bundled tools. Skipped automatically if already present."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP}   "Add a shortcut on your Desktop."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} "Add a shortcut in the Start Menu."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ============================================================
; Uninstaller
; ============================================================
Section "Uninstall"
    ; Terminate the app before deleting files
    nsExec::ExecToLog 'taskkill /F /IM "${EXENAME}" /T'

    ; Remove files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\Uninstall.lnk"
    RMDir  "$SMPROGRAMS\${APPNAME}"

    ; Remove registry keys (64-bit registry hive)
    SetRegView 64
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
    DeleteRegKey HKCU "Software\${COMPANY}\${APPNAME}"

    ; Prompt to clean LumaCore DLLs from Steam folder
    ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Valve\Steam" "InstallPath"
    StrCmp $0 "" try_hkcu_steam
    Goto ask_clean_dlls
try_hkcu_steam:
    ReadRegStr $0 HKCU "Software\Valve\Steam" "SteamPath"
    StrCmp $0 "" done_clean_dlls ask_clean_dlls
ask_clean_dlls:
    IfFileExists "$0\steam.exe" 0 try_steamapps
    MessageBox MB_YESNO "Remove LumaCore files from Steam folder ($0)?$\nThis will delete:$\n  - LumaCore.dll$\n  - LumaCorePayload.dll$\n  - dwmapi.dll$\n  - xinput1_4.dll$\n  - version.dll$\n  - bin\lcoverlay.dll$\n$\nSelect Yes to clean these files." IDNO done_clean_dlls
    Delete "$0\LumaCore.dll"
    Delete "$0\LumaCorePayload.dll"
    Delete "$0\dwmapi.dll"
    Delete "$0\xinput1_4.dll"
    Delete "$0\version.dll"
    Delete "$0\bin\lcoverlay.dll"
    RMDir "$0\bin"
    Goto done_clean_dlls
try_steamapps:
    ; try common alternate paths
    IfFileExists "$PROGRAMFILES64\Steam\steam.exe" 0 try_programfiles
    StrCpy $0 "$PROGRAMFILES64\Steam"
    MessageBox MB_YESNO "Remove LumaCore files from Steam folder ($0)?$\n...$\nSelect Yes to clean." IDNO done_clean_dlls
    Delete "$0\LumaCore.dll"
    Delete "$0\LumaCorePayload.dll"
    Delete "$0\dwmapi.dll"
    Delete "$0\xinput1_4.dll"
    Delete "$0\version.dll"
    Delete "$0\bin\lcoverlay.dll"
    RMDir "$0\bin"
    Goto done_clean_dlls
try_programfiles:
    IfFileExists "$PROGRAMFILES\Steam\steam.exe" 0 done_clean_dlls
    StrCpy $0 "$PROGRAMFILES\Steam"
    MessageBox MB_YESNO "Remove LumaCore files from Steam folder ($0)?$\n...$\nSelect Yes to clean." IDNO done_clean_dlls
    Delete "$0\LumaCore.dll"
    Delete "$0\LumaCorePayload.dll"
    Delete "$0\dwmapi.dll"
    Delete "$0\xinput1_4.dll"
    Delete "$0\version.dll"
    Delete "$0\bin\lcoverlay.dll"
    RMDir "$0\bin"
done_clean_dlls:
SectionEnd
