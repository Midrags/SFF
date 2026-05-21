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
#include <regex>
#include <memory>
#include <atomic>
#include <format>

#include "Steam/Types.h"
#include "Steam/Enums.h"
#include "Steam/Structs.h"
#include "Steam/Callback.h"
#include "utils/LuaLoader.h"
#include "utils/Logger.h"
#include "utils/Settings.h"


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
inline char DiversionPath[MAX_PATH]   = {};  // <SteamInstallPath>\bin\lcoverlay.dll (hooked copy)
inline char LuaDir[MAX_PATH]          = {};  // <SteamInstallPath>\config\stplug-in
inline char ConfigPath[MAX_PATH]      = {};  // <SteamInstallPath>\lumacore.toml

// Steam build number read at startup from steam.exe!GetBootstrapperVersion.
// ByteSearch uses this string to select the best-matching Signature entry in PatternDb.h
// before falling back to trying every other entry in order.
// Stays empty if steam.exe is not loaded or does not export GetBootstrapperVersion.
inline std::string g_steamBuildId;

// The fake AppId substituted when -onlinefix is active (Valve's SpaceWar lobby app).
constexpr AppId_t kOnlineFixAppId = 480;

#endif // ENTRY_H
