#include "entry.h"
#include "LuaLoader.h"
#include "utils/Ticket.h"
#include <lua.hpp>
#include <cctype>
#include <fstream>
#include <string>

extern "C" {
    struct lua_State;
}

namespace LuaLoader {
    static lua_State* g_lua_state = nullptr;
    std::unordered_map<AppId_t, std::string>DepotKeySet{};
    std::unordered_map<AppId_t, uint64_t>AccessTokenSet{};
    std::unordered_set<AppId_t> PinnedApps{};
    std::unordered_map<uint64_t, ManifestOverride> ManifestOverrides{};
    std::unordered_map<AppId_t, uint64_t> StatSteamIdSet{};
    std::unordered_set<AppId_t> OwnedAppIdSet{};

    // Per-file tracking: which depots each .lua file contributed.
    static std::string g_currentFile;
    static std::unordered_map<std::string, std::unordered_set<AppId_t>> g_fileDepots;
    // Reference count: how many files provide each depot.
    static std::unordered_map<AppId_t, uint32_t> g_depotRefCount;
    // Depot IDs removed by UnloadFile / added by ParseFile, consumed by NotifyLicenseChanged.
    static std::vector<AppId_t> g_pendingRemovals;
    static std::vector<AppId_t> g_pendingAdditions;
    constexpr uint64_t kDefaultStatSteamId = 76561198028121353ULL;

    // Fallback SteamID pool for achievement schema fetching.
    // These are accounts that own a wide variety of games.
    // Used in order when no setStat() is configured for an appId.
    static constexpr uint64_t kStatSteamIdPool[] = {
        76561198017975643ULL,
        76561198001678750ULL,
        76561198355953202ULL,
        76561197979911851ULL,
        76561198040673812ULL,
        76561198367471798ULL,
        76561198028125071ULL,
        76561198012616627ULL,
        76561197971398453ULL,
        76561197977849691ULL,
        76561198019373005ULL,
        76561198155124847ULL,
        76561198063534772ULL,
        76561198072711049ULL,
        76561198028121353ULL,  // original default kept at end
    };

    // Case-insensitive function registry: lowercase name → C function
    static std::unordered_map<std::string, lua_CFunction> g_func_registry;

    // ── Case-insensitive global function lookup ─────────────────
    // __index metamethod on _G: when a global name isn't found,
    // lower-case the name and look it up in g_func_registry.
    static int case_insensitive_global_index(lua_State* L) {
        const char* name = lua_tostring(L, 2);
        if (!name) {
            lua_pushnil(L);
            return 1;
        }
        std::string lower;
        for (const char* p = name; *p; ++p) {
            lower += static_cast<char>(std::tolower(static_cast<unsigned char>(*p)));
        }
        auto it = g_func_registry.find(lower);
        if (it != g_func_registry.end()) {
            lua_pushcfunction(L, it->second);
            return 1;
        }
        lua_pushnil(L);
        return 1;
    }

    // Register a C function both in _G (lowercase name) and in the
    // case-insensitive lookup table so any case variant resolves.
    static void register_func(lua_State* L, const char* lowercase_name, lua_CFunction fn) {
        g_func_registry[lowercase_name] = fn;
        lua_pushcfunction(L, fn);
        lua_setglobal(L, lowercase_name);
    }

    // ── Lua: addappid / addtoken / pinApp / setManifestid ────────
    static int lua_addappid(lua_State* L) {
        // addappid(integer, integer, string)
        int argc = lua_gettop(L);
        // Validate argument count and required argument types.
        if (argc == 0) {
            return luaL_error(L, "");
        }
        if (!lua_isinteger(L, 1)) {
            return luaL_error(L, "");
        }

        // Read the first argument as app/depot id.
        lua_Integer value = lua_tointeger(L, 1);
        // Ensure the value fits into uint32_t range.
        if (value < 0 || value > UINT32_MAX)
            return luaL_error(L, "");
        AppId_t DepotId = (uint32_t)value;
        // Read the optional third argument as a key.
        std::string Key = "";
        if (argc > 2) {
            if (!lua_isstring(L, 3))
                return luaL_error(L, "");
            const char* key = lua_tostring(L, 3);
            // Keep only keys with exactly 64 characters.
            if (strlen(key) == 64) {
                Key = std::string(key);
            }
        }
        // Non-empty keys have priority over existing empty keys.
        if (!Key.empty() || !DepotKeySet.count(DepotId)) {
            DepotKeySet[DepotId] = Key;
        }

        if (!g_currentFile.empty()) {
            if (g_fileDepots[g_currentFile].insert(DepotId).second) {
                if (++g_depotRefCount[DepotId] == 1)
                    g_pendingAdditions.push_back(DepotId);
            }
        }

        return 0;
    }

    static int lua_addtoken(lua_State* L) {
        // addtoken(integer, string(uint64_t))
        int argc = lua_gettop(L);
        // Validate argument count and required argument types.
        if (argc == 0) {
            return luaL_error(L, "");
        }
        if (!lua_isinteger(L, 1)) {
            return luaL_error(L, "");
        }

        // Read the first argument as app/depot id.
        lua_Integer value = lua_tointeger(L, 1);
        // Ensure the value fits into uint32_t range.
        if (value < 0 || value > UINT32_MAX)
            return luaL_error(L, "");
        AppId_t AppId = (uint32_t)value;
        // Read the second argument as a token.
        if (argc > 1) {
            if (!lua_isstring(L, 2))
                return luaL_error(L, "");
            const char* token = lua_tostring(L, 2);
            // Convert the string token to a uint64_t value.
            if(!std::all_of(token, token + strlen(token), ::isdigit)) {
                return luaL_error(L, "");
            }
            AccessTokenSet[AppId] = std::stoull(token);
        }

        return 0;
    }

    static int lua_pinApp(lua_State* L) {
        // pinApp(integer)
        int argc = lua_gettop(L);
        // Validate argument count and required argument types.
        if (argc == 0) {
            return luaL_error(L, "");
        }
        if (!lua_isinteger(L, 1)) {
            return luaL_error(L, "");
        }

        // Read the first argument as appid.
        lua_Integer value = lua_tointeger(L, 1);
        // Ensure the value fits into uint32_t range.
        if (value < 0 || value > UINT32_MAX)
            return luaL_error(L, "");
        AppId_t AppId = (uint32_t)value;

        PinnedApps.insert(AppId);

        return 0;
    }

    static int lua_setManifestid(lua_State* L)
    {
        // setManifestid(depotId, gid_string [, size])
        // size is always forced to 0 to prevent incorrect size from breaking Steam.
        int argc = lua_gettop(L);
        if (argc < 2)
            return luaL_error(L, "setManifestid: need depotId, gid");

        if (!lua_isinteger(L, 1))
            return luaL_error(L, "setManifestid: depotId must be integer");
        if (!lua_isstring(L, 2))
            return luaL_error(L, "setManifestid: gid must be decimal string");

        lua_Integer val = lua_tointeger(L, 1);
        if (val < 0 || val > UINT32_MAX)
            return luaL_error(L, "setManifestid: depotId out of range");

        uint64_t depotId = (uint64_t)(uint32_t)val;
        const char* gidStr = lua_tostring(L, 2);

        if (!std::all_of(gidStr, gidStr + strlen(gidStr), ::isdigit))
            return luaL_error(L, "setManifestid: gid must be all digits");

        ManifestOverrides[depotId] = { std::stoull(gidStr), 0 };
        return 0;
    }

    // ── Lua: setAppTicket / setETicket ──────────────────────────
    static int lua_setAppticket(lua_State* L) {
        int argc = lua_gettop(L);
        if (argc < 2)
            return luaL_error(L, "setAppTicket: need appId and hex string");
        if (!lua_isinteger(L, 1))
            return luaL_error(L, "setAppTicket: appId must be integer");
        if (!lua_isstring(L, 2))
            return luaL_error(L, "setAppTicket: ticket must be hex string");

        lua_Integer val = lua_tointeger(L, 1);
        if (val < 0 || val > UINT32_MAX)
            return luaL_error(L, "setAppTicket: appId out of range");
        AppId_t appId = static_cast<uint32_t>(val);

        size_t hexLen;
        const char* hex = lua_tolstring(L, 2, &hexLen);

        std::vector<uint8_t> binary;
        binary.reserve((hexLen + 1) / 2);
        for (size_t i = 0; i < hexLen; i += 2) {
            char byteStr[3] = {
                hex[i],
                i + 1 < hexLen ? hex[i + 1] : '0',
                '\0'
            };
            binary.push_back(static_cast<uint8_t>(strtoul(byteStr, nullptr, 16)));
        }

        if (!Ticket::WriteAppOwnershipTicket(appId, binary))
            return luaL_error(L, "setAppTicket: failed to write to registry");

        return 0;
    }

    static int lua_setEticket(lua_State* L) {
        int argc = lua_gettop(L);
        if (argc < 2)
            return luaL_error(L, "setETicket: need appId and hex string");
        if (!lua_isinteger(L, 1))
            return luaL_error(L, "setETicket: appId must be integer");
        if (!lua_isstring(L, 2))
            return luaL_error(L, "setETicket: ticket must be hex string");

        lua_Integer val = lua_tointeger(L, 1);
        if (val < 0 || val > UINT32_MAX)
            return luaL_error(L, "setETicket: appId out of range");
        AppId_t appId = static_cast<uint32_t>(val);

        size_t hexLen;
        const char* hex = lua_tolstring(L, 2, &hexLen);

        std::vector<uint8_t> binary;
        binary.reserve((hexLen + 1) / 2);
        for (size_t i = 0; i < hexLen; i += 2) {
            char byteStr[3] = {
                hex[i],
                i + 1 < hexLen ? hex[i + 1] : '0',
                '\0'
            };
            binary.push_back(static_cast<uint8_t>(strtoul(byteStr, nullptr, 16)));
        }

        if (!Ticket::WriteEncryptedTicket(appId, binary))
            return luaL_error(L, "setETicket: failed to write to registry");

        return 0;
    }

    
    // ── Lua: setStat ────────────────────────────────────────────
    static int lua_setStat(lua_State* L) {
        // setStat(appid, "steamid")
        int argc = lua_gettop(L);
        if (argc < 2)
            return luaL_error(L, "setStat: need appId and steamId string");
        if (!lua_isinteger(L, 1))
            return luaL_error(L, "setStat: appId must be integer");
        if (!lua_isstring(L, 2))
            return luaL_error(L, "setStat: steamId must be string");

        lua_Integer val = lua_tointeger(L, 1);
        if (val < 0 || val > UINT32_MAX)
            return luaL_error(L, "setStat: appId out of range");
        AppId_t appId = static_cast<uint32_t>(val);

        const char* sidStr = lua_tostring(L, 2);
        if (!std::all_of(sidStr, sidStr + strlen(sidStr), ::isdigit))
            return luaL_error(L, "setStat: steamId must be all digits");

        StatSteamIdSet[appId] = std::stoull(sidStr);
        return 0;
    }

    // ── init / cleanup ───────────────────────────────────────────
    static bool Initialize() {
        if (g_lua_state)
            return true;
        g_lua_state = luaL_newstate();
        if (!g_lua_state)
            return false;
        // Load standard Lua libraries.
        luaL_openlibs(g_lua_state);

        // Set up case-insensitive global lookup via __index on _G's metatable.
        lua_getglobal(g_lua_state, "_G");
        if (!lua_getmetatable(g_lua_state, -1)) {
            lua_newtable(g_lua_state);
        }
        lua_pushcfunction(g_lua_state, case_insensitive_global_index);
        lua_setfield(g_lua_state, -2, "__index");
        lua_setmetatable(g_lua_state, -2);
        lua_pop(g_lua_state, 1);  // pop _G

        // Register custom helper functions for scripts.
        // All functions use register_func() so any case variant works
        // (e.g. setAppTICKET, addAppId, SETManifestid, etc.).
        register_func(g_lua_state, "addappid", lua_addappid);
        register_func(g_lua_state, "addtoken", lua_addtoken);
        // we don't need it?
        // register_func(g_lua_state, "pinapp", lua_pinApp);
        register_func(g_lua_state, "setmanifestid", lua_setManifestid);
        register_func(g_lua_state, "setappticket", lua_setAppticket);
        register_func(g_lua_state, "seteticket", lua_setEticket);
        register_func(g_lua_state, "setstat", lua_setStat);
        return true;
    }

    static void Cleanup() {
        if (g_lua_state) {
            lua_close(g_lua_state);
            g_lua_state = nullptr;
        }
    }

    // ── public query API ─────────────────────────────────────────
    bool HasDepot(AppId_t DepotId) {
        return DepotKeySet.count(DepotId) && !OwnedAppIdSet.count(DepotId);
    }

    void MarkOwned(AppId_t AppId) {
        if(!OwnedAppIdSet.count(AppId)) {
            LOG_PACKAGE_INFO("Marking app {} as owned", AppId);
            OwnedAppIdSet.insert(AppId);
        }
    }

    std::vector<AppId_t> GetAllDepotIds() {
        std::vector<AppId_t> DepotIds;
        for (const auto& pair : DepotKeySet) {
            DepotIds.push_back(pair.first);
        }
        return DepotIds;
    }

    std::vector<uint8> GetDecryptionKey(AppId_t DepotId) {
        std::vector<uint8> keyBytes;
        if (DepotKeySet.count(DepotId)) {
            const std::string& keyStr = DepotKeySet[DepotId];
            // Convert hex string to byte vector.
            for (size_t i = 0; i < keyStr.length(); i += 2) {
                std::string byteString = keyStr.substr(i, 2);
                uint8 byte = (uint8)strtoul(byteString.c_str(), nullptr, 16);
                keyBytes.push_back(byte);
            }
        }
        return keyBytes;
    }

    uint64_t GetAccessToken(AppId_t AppId) {
        if (AccessTokenSet.count(AppId)) {
            return AccessTokenSet[AppId];
        }
        return 0;
    }

    bool pinApp(AppId_t AppId) {
        return PinnedApps.count(AppId);
    }

    uint64_t GetStatSteamId(AppId_t AppId) {
        if (StatSteamIdSet.count(AppId))
            return StatSteamIdSet[AppId];
        return kDefaultStatSteamId;
    }

    const uint64_t* GetStatSteamIdPool(AppId_t AppId, size_t& outCount) {
        auto it = StatSteamIdSet.find(AppId);
        if (it != StatSteamIdSet.end()) {
            outCount = 1;
            return &it->second;
        }
        outCount = sizeof(kStatSteamIdPool) / sizeof(kStatSteamIdPool[0]);
        return kStatSteamIdPool;
    }

    const std::unordered_map<uint64_t, ManifestOverride>& GetManifestOverrides() {
      return ManifestOverrides;
    }

    // ── per-file unload ────────────────────────────────────────
    void UnloadFile(const std::string& filePath) {
        auto it = g_fileDepots.find(filePath);
        if (it == g_fileDepots.end()) return;

        for (AppId_t id : it->second) {
            LOG_PACKAGE_DEBUG("UnloadFile:Ref count for AppId {} is {}", id, g_depotRefCount[id]);
            if (--g_depotRefCount[id] == 0) {
                g_depotRefCount.erase(id);
                DepotKeySet.erase(id);
                g_pendingRemovals.push_back(id);
            }
        }

        LOG_PACKAGE_INFO("UnloadFile: removed {} depots from {}", it->second.size(), filePath);
        g_fileDepots.erase(it);
    }

    std::vector<AppId_t> TakePendingRemovals() {
        std::vector<AppId_t> result;
        result.swap(g_pendingRemovals);
        return result;
    }

    std::vector<AppId_t> TakePendingAdditions() {
        std::vector<AppId_t> result;
        result.swap(g_pendingAdditions);
        return result;
    }

    // ── single-file parser ──────────────────────────────────────
    void ParseFile(const std::string& filePath) {
        if (!Initialize()) return;

        // Remove old entries from this file before re-parsing.
        UnloadFile(filePath);
        g_currentFile = filePath;

        std::filesystem::path path(filePath);

        // ── Auto-register app ID from filename ──────────────────
        // If the filename stem is all digits (e.g. "3764200.lua"),
        // treat it as the base app ID and register it automatically.
        // This ensures HasDepot(baseAppId) returns true even when the
        // Lua content only calls addappid() for depot IDs.
        {
            const std::string stem = path.stem().string();
            if (!stem.empty() && std::all_of(stem.begin(), stem.end(), ::isdigit)) {
                char* endPtr = nullptr;
                unsigned long long val = std::strtoull(stem.c_str(), &endPtr, 10);
                if (endPtr && *endPtr == '\0' && val > 0 && val <= UINT32_MAX) {
                    AppId_t fileAppId = static_cast<AppId_t>(val);
                    // Only register if not already present (don't overwrite a key set by addappid)
                    if (!DepotKeySet.count(fileAppId)) {
                        DepotKeySet[fileAppId] = "";
                        if (g_fileDepots[g_currentFile].insert(fileAppId).second) {
                            if (++g_depotRefCount[fileAppId] == 1)
                                g_pendingAdditions.push_back(fileAppId);
                        }
                        LOG_DEBUG("ParseFile: auto-registered appid={} from filename {}", fileAppId, stem);
                    }
                }
            }
        }

        std::ifstream file(path);
        if (!file) {
            LOG_WARN("ParseFile: failed to open {}", path.filename().string());
            return;
        }

        std::string chunk, line;
        int lineNo = 0;
        while (std::getline(file, line)) {
            ++lineNo;
            if (!chunk.empty()) chunk += '\n';
            chunk += line;

            lua_settop(g_lua_state, 0);
            int rc = luaL_loadstring(g_lua_state, chunk.c_str());
            if (rc == LUA_OK) {
                if (lua_pcall(g_lua_state, 0, 0, 0) != LUA_OK) {
                    const char* err = lua_tostring(g_lua_state, -1);
                    LOG_WARN("{}:{}: {}", path.filename().string(), lineNo,
                             err ? err : "unknown");
                }
                chunk.clear();
            } else if (rc == LUA_ERRSYNTAX) {
                lua_pop(g_lua_state, 1);
            } else {
                const char* err = lua_tostring(g_lua_state, -1);
                LOG_WARN("{}:{}: {}", path.filename().string(), lineNo, err ? err : "unknown");
                lua_pop(g_lua_state, 1);
                chunk.clear();
            }
        }
        if (!chunk.empty()) {
            LOG_WARN("{}: incomplete statement at end of file", path.filename().string());
        }

        g_currentFile.clear();
    }

    // ── directory scanner ────────────────────────────────────────
    void ParseDirectory(const std::string& directory) {
        if (!Initialize()) return;

        std::error_code ec;
        if (!std::filesystem::exists(directory, ec))
            std::filesystem::create_directories(directory, ec);
        if (!std::filesystem::exists(directory, ec) || !std::filesystem::is_directory(directory, ec))
            return;

        for (const auto& entry : std::filesystem::directory_iterator(directory, ec)) {
            if (ec) break;
            if (!entry.is_regular_file()) continue;
            if (entry.path().extension() != ".lua") continue;
            ParseFile(entry.path().string());
        }

        // Initial parse — discard pending additions so NotifyLicenseChanged
        // only sees changes that happen after startup.
        g_pendingAdditions.clear();
    }

}
