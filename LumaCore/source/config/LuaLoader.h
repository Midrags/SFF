// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#ifndef LUALOADER_H
#define LUALOADER_H

#include <cstddef>
#include <cstdint>
#include "Steam/Types.h"
#include <unordered_map>
#include <string>
#include <vector>

namespace LuaLoader {
    bool HasDepot(AppId_t appId);
    bool IsOwned(AppId_t appId);
    bool IsStatsManagedApp(AppId_t appId);
    void MarkOwned(AppId_t appId);
    std::vector<AppId_t> GetAllDepotIds();
    std::vector<AppId_t> GetLibraryAppIds();
    std::vector<uint8> GetDecryptionKey(AppId_t appId);
    uint64_t GetAccessToken(AppId_t appId);
    uint64_t GetStatSteamId(AppId_t appId);
    // Backend URL for on-demand eticket minting, set via seteticketurl() in Lua.
    // Empty string means disabled, callers fall back to credential store.
    const std::string& GetEticketUrl();
    void SetEticketUrl(std::string url);

    // Process-name to AppId mapping, set via addprocess() in Lua.
    // Returns k_uAppIdInvalid when no mapping exists.
    AppId_t GetAppIdForProcess(const std::string& imageName);

    // Check if an appid was force-marked as Denuvo via forcedenuvo() in Lua.
    bool IsForcedDenuvo(AppId_t appId);
    // Returns the full fallback pool of SteamIDs for achievement schema fetching.
    // If setStat(appId, steamId) override exists, outCount=1 and returns that ID.
    // Otherwise returns the built-in pool. PacketRouter tries each in order.
    const uint64_t* GetStatSteamIdPool(AppId_t appId, size_t& outCount);
    bool pinApp(AppId_t appId);

    // .lua mtime indexed per appid so the host can feed Steam's "added"
    // timestamp from when the user dropped the .lua file in. The library
    // "Date Added" sort wants seconds since epoch as int64 RTC time. Zero
    // when the appid wasn't registered through ParseFile (legacy entries
    // captured by addappid in the same process before ParseFile ran).
    int64_t GetLuaMtime(AppId_t appId);

    struct ManifestOverride {
          uint64_t gid;
          uint64_t size;
    };
    const std::unordered_map<uint64_t, ManifestOverride>& GetManifestOverrides();

    void ParseFile(const std::string& filePath);
    void UnloadFile(const std::string& filePath);
    // Returns and clears the list of depot IDs removed/added since last call.
    std::vector<AppId_t> TakePendingRemovals();
    std::vector<AppId_t> TakePendingAdditions();
    void ParseDirectory(const std::string& directory);

    // Re-queue all currently loaded depot IDs as pending additions.
    // Called after startup when hooks are ready but LoadPackage already fired.
    // This allows NotifyLicenseChanged to inject all startup Lua files into
    // the already-loaded package 0.
    void QueueStartupInjection();

    // Lua manifest code fetch: checks if the Lua plugin registered
    // fetch_manifest_code or fetch_manifest_code_ex functions.
    bool HasManifestCodeFunc();
    bool HasManifestCodeFuncEx();

    // Calls fetch_manifest_code(gid) via the Lua state. Returns 0 on failure.
    uint64_t CallManifestFetchCode(uint64_t gid);

    // Calls fetch_manifest_code_ex(appId, depotId, gid) via the Lua state.
    // Returns 0 on failure.
    uint64_t CallManifestFetchCodeEx(AppId_t appId, AppId_t depotId, uint64_t gid);

}

#endif // LUALOADER_H
