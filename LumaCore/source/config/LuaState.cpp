// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.
//
// Owns the lua_State lifecycle and the binding registry.
//
// Each Lua C-function we expose to .lua files is registered under its
// lowercase canonical name. The .lua files that ship in the wild use a
// mix of casings (addappid, AddAppId, setManifestid, setAppTicket, ...);
// to make every variant resolve to the same handler we install a fallback
// resolver on the _G metatable that lowercases any missed global lookup
// and hands back the matching binding from `g_caseFoldedBindings`. Without
// that fallback, scripts written in camelCase or PascalCase silently fail
// at the first call site with "attempt to call a nil value".

#include "config/LuaLoaderInternal.h"

#include <lua.hpp>
#include <array>
#include <cctype>
#include <cstring>
#include <string>
#include <unordered_map>
#include <utility>

namespace LuaLoader::Internal {

    // ── Global state definitions ──────────────────────────────────────────
    lua_State* g_lua_state = nullptr;

    std::unordered_map<AppId_t, std::string> DepotKeySet{};
    std::unordered_set<AppId_t>              LibraryAppIdSet{};
    std::unordered_set<AppId_t>              StatsAppIdSet{};
    std::unordered_map<AppId_t, uint64_t>    AccessTokenSet{};
    std::unordered_set<AppId_t>              PinnedApps{};
    std::unordered_map<uint64_t, ManifestOverride> ManifestOverrides{};
    std::unordered_map<AppId_t, uint64_t>    StatSteamIdSet{};
    std::unordered_set<AppId_t>              OwnedAppIdSet{};
    std::unordered_set<AppId_t>              FamilySharedAppIdSet{};
    std::unordered_map<AppId_t, int64_t>     LuaMtimeMap{};

    std::unordered_map<std::string, std::unordered_set<AppId_t>> g_fileDepots;
    std::unordered_map<std::string, std::unordered_set<AppId_t>> g_fileLibraryApps;
    std::unordered_map<std::string, std::unordered_set<AppId_t>> g_fileStatsApps;
    std::unordered_map<std::string, std::unordered_map<AppId_t, uint64_t>> g_fileStatSteamIds;
    std::unordered_map<AppId_t, uint32_t> g_depotRefCount;
    std::unordered_map<AppId_t, uint32_t> g_libraryRefCount;
    std::unordered_map<AppId_t, uint32_t> g_statsRefCount;
    std::vector<AppId_t> g_pendingRemovals;
    std::vector<AppId_t> g_pendingAdditions;
    ParseSession* g_activeSession = nullptr;
    std::string g_eticketUrl;
    std::unordered_set<AppId_t> g_forcedDenuvoApps;
    std::unordered_map<std::string, AppId_t> g_processAppMap;

    // Achievement ringfence: pool used by the wire-level UserStats spoofer
    // when no explicit setStat() is configured for an appId. PacketRouter
    // reads from GetStatSteamIdPool() (defined in LuaQuery.cpp) which hands
    // a span over this array. Keep byte-identical.
    const uint64_t kStatSteamIdPool[15] = {
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
        76561198028121353ULL,
    };

    // ── ParseSession helper ──────────────────────────────────────────────
    void ParseSession::recordDepot(AppId_t id) {
        if (currentFile.empty()) return;
        if (!g_fileDepots[currentFile].insert(id).second) return;
        if (++g_depotRefCount[id] == 1) {
            g_pendingAdditions.push_back(id);
        }
    }

    void ParseSession::recordLibraryApp(AppId_t id) {
        if (currentFile.empty()) return;
        if (!g_fileLibraryApps[currentFile].insert(id).second) return;
        if (++g_libraryRefCount[id] == 1) {
            LibraryAppIdSet.insert(id);
        }
    }

    void ParseSession::recordStatsApp(AppId_t id) {
        if (currentFile.empty()) return;
        if (!g_fileStatsApps[currentFile].insert(id).second) return;
        if (++g_statsRefCount[id] == 1) {
            StatsAppIdSet.insert(id);
        }
    }

    void ParseSession::recordStatSteamId(AppId_t id, uint64_t steamId) {
        if (currentFile.empty()) return;
        g_fileStatSteamIds[currentFile][id] = steamId;
    }

    namespace {
        // Lowercase-name to handler map populated at Initialize() time.
        // Read from the case-folded resolver below.
        std::unordered_map<std::string, lua_CFunction> g_caseFoldedBindings;

        // Registry of canonical bindings.
        // setStat is achievement-ringfenced — never rename or change its
        // signature.
        struct Binding {
            const char*   name;
            lua_CFunction fn;
        };

        constexpr Binding kBindings[] = {
            {"addappid",             &Bind_addappid},
            {"addtoken",             &Bind_addtoken},
            // pinapp intentionally unregistered at runtime today (matches
            // the older "we don't need it?" comment). The handler stays
            // compiled in case scripts start using it.
            // {"pinapp",            &Bind_pinApp},
            {"setmanifestid",        &Bind_setManifestid},
            {"setappticket",         &Bind_setAppticket},
            {"seteticket",           &Bind_setEticket},
            {"setstat",              &Bind_setStat},
            {"lchttpget",            &Bind_lcHttpGet},
            {"lchttppost",           &Bind_lcHttpPost},
            {"fetchmanifestcode",    &Bind_fetchManifestCode},
            {"fetchmanifestcodeex",  &Bind_fetchManifestCodeEx},
            {"getcachedappticket",   &Bind_getCachedAppTicket},
            {"getdecryptionkey",     &Bind_getDecryptionKey},
            {"seteticketurl",        &Bind_seteticketurl},
            {"forcedenuvo",          &Bind_forcedenuvo},
            {"addprocess",           &Bind_addprocess},
        };

        // _G.__index resolver: any global that isn't directly defined gets
        // its name lowercased and matched against g_caseFoldedBindings.
        // That makes addAppId, AddAppId, ADDAPPID, setManifestid,
        // SetAppTicket all dispatch to the same canonical handler.
        int CaseFoldedGlobalResolver(lua_State* L) {
            const char* requested = lua_tostring(L, 2);
            if (!requested) {
                lua_pushnil(L);
                return 1;
            }

            std::string folded;
            folded.reserve(std::strlen(requested));
            for (const char* p = requested; *p; ++p) {
                folded.push_back(
                    static_cast<char>(std::tolower(static_cast<unsigned char>(*p))));
            }

            auto match = g_caseFoldedBindings.find(folded);
            if (match == g_caseFoldedBindings.end()) {
                lua_pushnil(L);
            } else {
                lua_pushcfunction(L, match->second);
            }
            return 1;
        }

        // Stdlib sandbox. We deliberately do NOT call luaL_openlibs because
        // it pulls in io, os, package, debug, coroutine — every one of those
        // gives a hostile .lua file a way to read/write files, shell out, or
        // load arbitrary bytecode. Plugin scripts only need pure-data
        // primitives so we open exactly four libs by hand.
        struct StdLib {
            const char*  name;
            lua_CFunction loader;
        };
        constexpr StdLib kAllowedStdLibs[] = {
            {"_G",            luaopen_base},
            {LUA_TABLIBNAME,  luaopen_table},
            {LUA_STRLIBNAME,  luaopen_string},
            {LUA_MATHLIBNAME, luaopen_math},
        };

        // After luaopen_base runs the base lib still hands us dofile,
        // loadfile, load, loadstring, require. Any one of those lets a
        // plugin pull external code into the VM so wipe them. collectgarbage
        // gets nuked too because a malicious script can pause the GC and
        // starve Steam's process. Everything else (pairs, ipairs, pcall,
        // tostring, type, error, assert) stays because legitimate .lua
        // files use them.
        constexpr const char* kStripFromBase[] = {
            "dofile",
            "loadfile",
            "load",
            "loadstring",
            "require",
            "collectgarbage",
        };
    }

    bool Initialize() {
        if (g_lua_state) return true;
        g_lua_state = luaL_newstate();
        if (!g_lua_state) return false;

        // Whitelist load instead of luaL_openlibs.
        for (const auto& lib : kAllowedStdLibs) {
            luaL_requiref(g_lua_state, lib.name, lib.loader, 1);
            lua_pop(g_lua_state, 1);
        }

        // Strip code-loading and GC-control hooks from the base lib.
        for (const char* victim : kStripFromBase) {
            lua_pushnil(g_lua_state);
            lua_setglobal(g_lua_state, victim);
        }

        // Register every binding under its canonical lowercase name AND
        // remember it for the case-folded resolver below.
        g_caseFoldedBindings.clear();
        g_caseFoldedBindings.reserve(std::size(kBindings));
        for (const auto& b : kBindings) {
            g_caseFoldedBindings.emplace(b.name, b.fn);
            lua_pushcfunction(g_lua_state, b.fn);
            lua_setglobal(g_lua_state, b.name);
        }

        // Publish an _originals table so user-supplied .lua files can
        // wrap a binding without losing the C handler. The 00_LetUpdate
        // override pattern is:
        //
        //   local original = _originals.setManifestid
        //   function setManifestid(d, m, s)
        //       print(("override: depot=%d gid=%s"):format(d, m))
        //       return original(d, m, s)
        //   end
        //
        // The user reassigns the global slot, but the C handler stays
        // reachable through _originals so the override can chain through
        // it. _originals is populated case-insensitively (both lowercase
        // canonical AND CamelCase aliases) so the user doesn't have to
        // care about which casing the binding was registered under.
        lua_createtable(g_lua_state,
                        0, static_cast<int>(std::size(kBindings) * 2));
        for (const auto& b : kBindings) {
            lua_pushcfunction(g_lua_state, b.fn);
            lua_setfield(g_lua_state, -2, b.name);
        }
        // Camel-style aliases the existing scripts in the wild expect.
        // Hardcoded set; if we ever rename a binding update both lists.
        constexpr std::pair<const char*, const char*> kCamelAliases[] = {
            {"addAppId",      "addappid"},
            {"addToken",      "addtoken"},
            {"setManifestid", "setmanifestid"},
            {"setAppTicket",  "setappticket"},
            {"setEticket",    "seteticket"},
            {"setStat",       "setstat"},
            {"lcHttpGet",     "lchttpget"},
            {"lcHttpPost",    "lchttppost"},
            {"fetchManifestCode",    "fetchmanifestcode"},
            {"fetchManifestCodeEx",  "fetchmanifestcodeex"},
            {"getCachedAppTicket",   "getcachedappticket"},
            {"getDecryptionKey",     "getdecryptionkey"},
            {"setEticketUrl",        "seteticketurl"},
            {"forceDenuvo",          "forcedenuvo"},
            {"addProcess",           "addprocess"},
        };
        for (const auto& alias : kCamelAliases) {
            for (const auto& b : kBindings) {
                if (std::strcmp(b.name, alias.second) == 0) {
                    lua_pushcfunction(g_lua_state, b.fn);
                    lua_setfield(g_lua_state, -2, alias.first);
                    break;
                }
            }
        }
        lua_setglobal(g_lua_state, "_originals");

        // Install the case-folded resolver on _G's metatable as __index.
        // Lua's protocol calls __index whenever a direct global lookup
        // misses, which is exactly when we need to map e.g. "setManifestid"
        // back to the lowercase "setmanifestid" handler.
        lua_getglobal(g_lua_state, "_G");
        if (!lua_getmetatable(g_lua_state, -1)) {
            lua_newtable(g_lua_state);
        }
        lua_pushcfunction(g_lua_state, CaseFoldedGlobalResolver);
        lua_setfield(g_lua_state, -2, "__index");
        lua_setmetatable(g_lua_state, -2);
        lua_pop(g_lua_state, 1);  // pop _G

        return true;
    }

    void Cleanup() {
        if (g_lua_state) {
            lua_close(g_lua_state);
            g_lua_state = nullptr;
        }
        g_caseFoldedBindings.clear();
    }
}
