#ifndef LUALOADER_H
#define LUALOADER_H

#include <cstdint>
#include <unordered_map>
#include <string>
#include <vector>

namespace LuaLoader {
    bool HasDepot(AppId_t appId);
    void MarkOwned(AppId_t appId);
    std::vector<AppId_t> GetAllDepotIds();
    std::vector<uint8> GetDecryptionKey(AppId_t appId);
    uint64_t GetAccessToken(AppId_t appId);
    uint64_t GetStatSteamId(AppId_t appId);
    // Returns the full fallback pool of SteamIDs for achievement schema fetching.
    // If setStat() was configured for appId, outCount=1 and returns pointer to that ID.
    // Otherwise returns the built-in pool. PacketRouter tries each in order.
    const uint64_t* GetStatSteamIdPool(AppId_t appId, size_t& outCount);
    bool pinApp(AppId_t appId);

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

}

#endif // LUALOADER_H
