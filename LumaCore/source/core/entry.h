// LumaCore — Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#ifndef ENTRY_H
#define ENTRY_H

#include <windows.h>
#include <string>
#include <fstream>
#include <filesystem>
#include <array>
#include <vector>
#include <unordered_set>
#include <unordered_map>
#include <memory>
#include <atomic>
#include <format>

#include "Steam/Types.h"
#include "Steam/Enums.h"
#include "Steam/Structs.h"
#include "Steam/Callback.h"
#include "config/LuaLoader.h"
#include "runtime/Logger.h"
#include "config/Settings.h"


// Handle to lcoverlay.dll once LoadDiversion() copies and loads it.
// All hook targets in steamclient64.dll are resolved through this module.
// Null until LoadDiversion() succeeds.
inline HMODULE diversion_hModule = nullptr;

// InitThread handle retained so DLL_PROCESS_DETACH can wait for init to finish
// before unhooking. Closed after the wait completes.
inline HANDLE g_InitThread = nullptr;

// Set to true by InitThread after every hook has been installed.
// SteamUI.cpp's LoadModuleWithPath hook polls this before returning diversion_hModule
// to the caller, so all hooks are in place before Steam starts using the module.
inline std::atomic<bool> g_HooksInstalled{false};

// Runtime paths filled in by LoadDiversion() from the process working directory.
inline char SteamInstallPath[MAX_PATH] = {};  // Steam root: the folder containing steam.exe
inline char SteamclientPath[MAX_PATH] = {};  // <SteamInstallPath>\steamclient64.dll
// Hooked copy of steamclient64.dll that this session loads.
// Multi-instance mode ([diversion] multiinstance): bin\lcoverlay-<sha16>.dll,
// an immutable content-addressed artifact shared read-only by every session.
// Legacy mode: the fixed <SteamInstallPath>\bin\lcoverlay.dll.
inline char DiversionPath[MAX_PATH]   = {};
inline char LuaDir[MAX_PATH]          = {};  // <SteamInstallPath>\config\stplug-in
inline char ConfigPath[MAX_PATH]      = {};  // <SteamInstallPath>\lumacore.toml
inline char PayloadPath[MAX_PATH]    = {};  // <SteamInstallPath>\LumaCorePayload.dll

// Steam build number read at startup from steam.exe!GetBootstrapperVersion.
// ByteSearch uses this string to select the best-matching Signature entry in PatternDb.h
// before falling back to trying every other entry in order.
// Stays empty if steam.exe is not loaded or does not export GetBootstrapperVersion.
inline std::string g_steamBuildId;

// The fake AppId substituted when -onlinefix is active (Valve's SpaceWar lobby app).
constexpr AppId_t kOnlineFixAppId = 480;

// Dispatches the PatternFetcher worker for steamui.dll on a detached thread.
// Defined in entry.cpp. Idempotent: subsequent calls after the first are no-ops.
// Called from InitThread when steamui.dll is already mapped, and from the
// SteamUI::LoadModuleWithPath hook when Steam's loader maps it later.
void DispatchSteamUiPatternFetch();

#endif // ENTRY_H
