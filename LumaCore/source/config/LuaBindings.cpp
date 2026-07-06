// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.
//
// Implementation of the Lua C functions we expose to .lua scripts.
//
// Each binding goes through CheckAppId / CheckString / DecodeHex helpers
// instead of inlining the type / range checks. Errors raise a Lua error
// with a "where: what" message so script authors actually see what went
// wrong, rather than the empty-string error the older code threw.
//
// Bind_setStat stays achievement-ringfenced. setStat(appid) marks a stats
// root; the optional SteamID arg is the old override path.

#include "LuaLoaderInternal.h"
#include "runtime/Logger.h"
#include "runtime/Ticket.h"
#include "runtime/RuntimeHttp.h"
#include "hooks/client/DecryptionKeyHook.h"
#include "config/Settings.h"

#include <lua.hpp>
#include <algorithm>
#include <charconv>
#include <cstring>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {
    // Truncate to keep log lines bounded when a script ships a huge string.
    std::string_view TruncForLog(std::string_view s) {
        constexpr size_t kMax = 32;
        return s.size() > kMax ? s.substr(0, kMax) : s;
    }
}

namespace LuaLoader::Internal {

    // ── HTTP allowlist helpers ──────────────────────────────────────────
    // Hostile .lua files are a real concern. A malicious script dropped
    // into stplug-in could pair lcHttpGet with the addappid/setStat read
    // surface and silently exfil to whatever URL the attacker controls.
    // The host gate below kills that vector. The hardcoded set covers the
    // hosts SteaMidra's official update flows actually need, and the user
    // can extend through `[lua] http_allowlist` if they're using a private
    // mirror. Anything not on the combined list returns 403/empty without
    // the network ever being reached.
    namespace {
        // Hardcoded baseline. Anyone trying to run an official LumaCore
        // workflow needs these regardless of config. Lowercased once on
        // declaration so the comparison loop is plain memcmp.
        constexpr std::string_view kHttpBaselineHosts[] = {
            "manifesthub1.filegear-sg.me",
            "raw.githubusercontent.com",
            "cdn.jsdelivr.net",
            "gitflic.ru",
            "api.github.com",
        };

        // Strip "http(s)://" from the front of a URL and grab everything up
        // to the first `/`, `?`, `#`, or `:`. Returns empty on a malformed
        // URL (no scheme prefix, no host body).
        std::string_view ExtractHost(std::string_view url) {
            constexpr std::string_view https = "https://";
            constexpr std::string_view http  = "http://";
            std::string_view rest = url;
            if (rest.size() >= https.size() &&
                std::equal(https.begin(), https.end(), rest.begin(),
                           [](char a, char b) {
                               return std::tolower(static_cast<unsigned char>(a)) ==
                                      std::tolower(static_cast<unsigned char>(b));
                           })) {
                rest.remove_prefix(https.size());
            } else if (rest.size() >= http.size() &&
                       std::equal(http.begin(), http.end(), rest.begin(),
                                  [](char a, char b) {
                                      return std::tolower(static_cast<unsigned char>(a)) ==
                                             std::tolower(static_cast<unsigned char>(b));
                                  })) {
                rest.remove_prefix(http.size());
            } else {
                return {};
            }
            std::size_t end = rest.size();
            for (std::size_t i = 0; i < rest.size(); ++i) {
                char c = rest[i];
                if (c == '/' || c == '?' || c == '#' || c == ':') { end = i; break; }
            }
            return rest.substr(0, end);
        }

        bool HostMatchesIgnoreCase(std::string_view a, std::string_view b) {
            if (a.size() != b.size()) return false;
            for (std::size_t i = 0; i < a.size(); ++i) {
                if (std::tolower(static_cast<unsigned char>(a[i])) !=
                    std::tolower(static_cast<unsigned char>(b[i])))
                    return false;
            }
            return true;
        }

        bool IsHostAllowed(std::string_view host) {
            if (host.empty()) return false;
            for (auto h : kHttpBaselineHosts) {
                if (HostMatchesIgnoreCase(host, h)) return true;
            }
            for (const auto& h : Settings::luaHttpAllowlistExtra) {
                if (HostMatchesIgnoreCase(host, h)) return true;
            }
            return false;
        }
    }

    // ── Bind_lcHttpPost(url, body [, headers]) -> body, status ────────────
// Synchronous HTTP POST exposed to Lua. Same allowlist gate as lcHttpGet.
// Headers is an optional table of key-value pairs.
int Bind_lcHttpPost(lua_State* L) {
    if (lua_gettop(L) < 2) {
        return luaL_error(L, "lcHttpPost: need url and body");
    }
    std::string_view url = CheckString(L, 1, "lcHttpPost");
    std::string_view body = CheckString(L, 2, "lcHttpPost");

    // same allowlist gate as lcHttpGet
    std::string_view host = ExtractHost(url);
    if (!IsHostAllowed(host)) {
        lua_pushlstring(L, "", 0);
        lua_pushinteger(L, 403);
        return 2;
    }

    // optional headers table
    std::vector<std::string> extraHeaders;
    if (lua_gettop(L) >= 3 && lua_istable(L, 3)) {
        lua_pushnil(L);
        while (lua_next(L, 3) != 0) {
            if (lua_isstring(L, -2) && lua_isstring(L, -1)) {
                std::string h;
                h += lua_tostring(L, -2);
                h += ": ";
                h += lua_tostring(L, -1);
                extraHeaders.push_back(std::move(h));
            }
            lua_pop(L, 1);
        }
    }

    const auto resp = RuntimeHttp::Post(url, body, extraHeaders);
    if (resp.networkError) {
        LOG_LUA_DEBUG("lcHttpPost: net error '{}' for url='{}'",
                      resp.diagnostic, TruncForLog(url));
    }
    lua_pushlstring(L, resp.body.data(), resp.body.size());
    lua_pushinteger(L, static_cast<lua_Integer>(resp.status));
    return 2;
}

// ── fetchManifestCode(gid) -> code ─────────────────────────────────────
// Calls the Lua manifest code fetch function installed by the plugin.
// Returns 0 if no function is installed or it fails.
int Bind_fetchManifestCode(lua_State* L) {
    if (lua_gettop(L) < 1) {
        return luaL_error(L, "fetchManifestCode: need gid string");
    }
    std::string_view gid = CheckString(L, 1, "fetchManifestCode");

    uint64_t parsedGid = 0;
    if (!TryParseUInt64Decimal(gid, parsedGid)) {
        return luaL_error(L, "fetchManifestCode: gid must be decimal uint64");
    }

    // Look up the registered fetch_manifest_code function
    lua_getglobal(L, "fetch_manifest_code");
    if (!lua_isfunction(L, -1)) {
        lua_pop(L, 1);
        lua_pushinteger(L, 0);
        return 1;
    }

    lua_pushinteger(L, static_cast<lua_Integer>(parsedGid));
    if (lua_pcall(L, 1, 1, 0) != LUA_OK) {
        const char* err = lua_tostring(L, -1);
        LOG_LUA_WARN("fetchManifestCode: lua error: {}", err ? err : "unknown");
        lua_pop(L, 1);
        lua_pushinteger(L, 0);
        return 1;
    }

    if (!lua_isinteger(L, -1) && !lua_isnumber(L, -1)) {
        lua_pop(L, 1);
        lua_pushinteger(L, 0);
        return 1;
    }

    lua_Integer code = lua_tointeger(L, -1);
    lua_pop(L, 1);
    lua_pushinteger(L, code);
    return 1;
}

// ── fetchManifestCodeEx(appId, depotId, gid) -> code ──────────────────
int Bind_fetchManifestCodeEx(lua_State* L) {
    if (lua_gettop(L) < 3) {
        return luaL_error(L, "fetchManifestCodeEx: need appId, depotId, gid");
    }
    AppId_t appId = CheckAppId(L, 1, "fetchManifestCodeEx");
    AppId_t depotId = CheckAppId(L, 2, "fetchManifestCodeEx");
    std::string_view gid = CheckString(L, 3, "fetchManifestCodeEx");

    uint64_t parsedGid = 0;
    if (!TryParseUInt64Decimal(gid, parsedGid)) {
        return luaL_error(L, "fetchManifestCodeEx: gid must be decimal uint64");
    }

    lua_getglobal(L, "fetch_manifest_code_ex");
    if (!lua_isfunction(L, -1)) {
        lua_pop(L, 1);
        lua_pushinteger(L, 0);
        return 1;
    }

    lua_pushinteger(L, static_cast<lua_Integer>(appId));
    lua_pushinteger(L, static_cast<lua_Integer>(depotId));
    lua_pushinteger(L, static_cast<lua_Integer>(parsedGid));
    if (lua_pcall(L, 3, 1, 0) != LUA_OK) {
        const char* err = lua_tostring(L, -1);
        LOG_LUA_WARN("fetchManifestCodeEx: lua error: {}", err ? err : "unknown");
        lua_pop(L, 1);
        lua_pushinteger(L, 0);
        return 1;
    }

    if (!lua_isinteger(L, -1) && !lua_isnumber(L, -1)) {
        lua_pop(L, 1);
        lua_pushinteger(L, 0);
        return 1;
    }

    lua_Integer code = lua_tointeger(L, -1);
    lua_pop(L, 1);
    lua_pushinteger(L, code);
    return 1;
}

// ── Typed argument helpers ───────────────────────────────────────────
    AppId_t CheckAppId(lua_State* L, int idx, const char* where) {
        if (!lua_isinteger(L, idx)) {
            luaL_error(L, "%s: arg #%d must be an integer", where, idx);
        }
        lua_Integer raw = lua_tointeger(L, idx);
        if (raw < 0 || raw > UINT32_MAX) {
            luaL_error(L, "%s: arg #%d out of uint32 range", where, idx);
        }
        return static_cast<AppId_t>(raw);
    }

    std::string_view CheckString(lua_State* L, int idx, const char* where) {
        if (!lua_isstring(L, idx)) {
            luaL_error(L, "%s: arg #%d must be a string", where, idx);
        }
        size_t len = 0;
        const char* p = lua_tolstring(L, idx, &len);
        return {p, len};
    }

    bool IsDecimalDigits(std::string_view s) {
        if (s.empty()) return false;
        for (char c : s) {
            if (c < '0' || c > '9') return false;
        }
        return true;
    }

    std::optional<std::vector<uint8_t>> DecodeHex(std::string_view hex) {
        std::vector<uint8_t> out;
        out.reserve((hex.size() + 1) / 2);

        for (size_t i = 0; i < hex.size(); i += 2) {
            char chunk[2];
            chunk[0] = hex[i];
            chunk[1] = (i + 1 < hex.size()) ? hex[i + 1] : '0';

            uint8_t byte = 0;
            auto [ptr, ec] = std::from_chars(chunk, chunk + 2, byte, 16);
            if (ec != std::errc{} || ptr != chunk + 2) {
                return std::nullopt;
            }
            out.push_back(byte);
        }
        return out;
    }

    // ── addappid(depotId [, _, key]) ─────────────────────────────────────
    int Bind_addappid(lua_State* L) {
        const int argc = lua_gettop(L);
        if (argc < 1) {
            return luaL_error(L, "addappid: need at least depotId");
        }

        AppId_t depotId = CheckAppId(L, 1, "addappid");

        // Optional 3rd arg is a 64-char hex key. Empty string keeps the
        // existing key (if any). Non-empty keys overwrite an empty key.
        std::string key;
        if (argc > 2) {
            std::string_view raw = CheckString(L, 3, "addappid");
            if (raw.size() == 64) {
                key.assign(raw.data(), raw.size());
            }
        }
        if (!key.empty() || !DepotKeySet.count(depotId)) {
            DepotKeySet[depotId] = key;
        }

        // Multi-account fix: clearing Steam-provided flags on every addappid
        // means a secondary account re-patches correctly through ownership.
        OwnedAppIdSet.erase(depotId);
        FamilySharedAppIdSet.erase(depotId);

        if (g_activeSession) {
            g_activeSession->recordDepot(depotId);
        }
        return 0;
    }

    // ── addtoken(appId, tokenString) ─────────────────────────────────────
    int Bind_addtoken(lua_State* L) {
        const int argc = lua_gettop(L);
        if (argc < 1) {
            return luaL_error(L, "addtoken: need appId");
        }

        AppId_t appId = CheckAppId(L, 1, "addtoken");

        if (argc > 1) {
            std::string_view tok = CheckString(L, 2, "addtoken");
            uint64_t parsed = 0;
            if (!TryParseUInt64Decimal(tok, parsed)) {
                LOG_LUA_WARN("addtoken: rejected token '{}' (must be decimal uint64)",
                             TruncForLog(tok));
                return luaL_error(L, "addtoken: token must be a decimal uint64");
            }
            AccessTokenSet[appId] = parsed;
        }
        return 0;
    }

    // ── pinApp(appId) — currently unregistered; left compiled-in. ────────
    int Bind_pinApp(lua_State* L) {
        if (lua_gettop(L) < 1) {
            return luaL_error(L, "pinApp: need appId");
        }
        AppId_t appId = CheckAppId(L, 1, "pinApp");
        PinnedApps.insert(appId);
        return 0;
    }

    // ── setManifestid(depotId, gidString [, size]) ──────────────────────
    // The optional `size` is intentionally ignored — Steam rejects manifests
    // when the size doesn't line up with what the depot reports, so we force
    // 0 and let Steam fill it in.
    int Bind_setManifestid(lua_State* L) {
        if (lua_gettop(L) < 2) {
            return luaL_error(L, "setManifestid: need depotId, gid");
        }

        const AppId_t depotIdRaw = CheckAppId(L, 1, "setManifestid");
        const uint64_t depotId = static_cast<uint64_t>(depotIdRaw);

        std::string_view gid = CheckString(L, 2, "setManifestid");
        uint64_t parsedGid = 0;
        if (!TryParseUInt64Decimal(gid, parsedGid)) {
            LOG_LUA_WARN("setManifestid: rejected gid '{}' (must be decimal uint64)",
                         TruncForLog(gid));
            return luaL_error(L, "setManifestid: gid must be a decimal uint64");
        }

        ManifestOverrides[depotId] = { parsedGid, 0 };
        return 0;
    }

    // ── setAppTicket(appId, hexTicket) ───────────────────────────────────
    int Bind_setAppticket(lua_State* L) {
        if (lua_gettop(L) < 2) {
            return luaL_error(L, "setAppTicket: need appId and hex string");
        }

        AppId_t appId = CheckAppId(L, 1, "setAppTicket");
        std::string_view hex = CheckString(L, 2, "setAppTicket");

        auto decoded = DecodeHex(hex);
        if (!decoded) {
            return luaL_error(L, "setAppTicket: ticket must be hex");
        }

        if (!Ticket::WriteAppOwnershipTicket(appId, *decoded)) {
            return luaL_error(L, "setAppTicket: registry write failed");
        }
        return 0;
    }

    // ── setETicket(appId, hexTicket) ─────────────────────────────────────
    int Bind_setEticket(lua_State* L) {
        if (lua_gettop(L) < 2) {
            return luaL_error(L, "setETicket: need appId and hex string");
        }

        AppId_t appId = CheckAppId(L, 1, "setETicket");
        std::string_view hex = CheckString(L, 2, "setETicket");

        auto decoded = DecodeHex(hex);
        if (!decoded) {
            return luaL_error(L, "setETicket: ticket must be hex");
        }

        if (!Ticket::WriteEncryptedTicket(appId, *decoded)) {
            return luaL_error(L, "setETicket: registry write failed");
        }
        return 0;
    }

    // ── setStat(appId [, "steamid"]) ─────────────────────────────────────
    int Bind_setStat(lua_State* L) {
        const int argc = lua_gettop(L);
        if (argc < 1) {
            return luaL_error(L, "setStat: need appId");
        }

        AppId_t appId = CheckAppId(L, 1, "setStat");
        if (g_activeSession) {
            g_activeSession->recordStatsApp(appId);
        }

        if (argc < 2 || lua_isnil(L, 2)) {
            LOG_LUA_DEBUG("setStat: app {} marked for auto stats pool", appId);
            return 0;
        }

        if (!lua_isstring(L, 2)) {
            LOG_LUA_WARN("setStat: ignored SteamID override for app {} (arg #2 must be a decimal string)",
                         appId);
            return 0;
        }

        std::string_view sid = CheckString(L, 2, "setStat");

        uint64_t parsedSid = 0;
        if (!TryParseUInt64Decimal(sid, parsedSid)) {
            LOG_LUA_WARN("setStat: ignored SteamID override '{}' for app {}",
                         TruncForLog(sid), appId);
            return 0;
        }

        StatSteamIdSet[appId] = parsedSid;
        if (g_activeSession) {
            g_activeSession->recordStatSteamId(appId, parsedSid);
        }
        return 0;
    }

    // ── getCachedAppTicket(appId) -> hexString or nil ────────────────────
    // Reads the cached app ownership ticket from Steam's config store for the
    // given appId. Returns the binary ticket as a hex string, or nil if no
    // ticket is cached. Used by plugin .lua files to inspect or forward tickets.
    int Bind_getCachedAppTicket(lua_State* L) {
        if (lua_gettop(L) < 1) {
            return luaL_error(L, "getCachedAppTicket: need appId");
        }
        AppId_t appId = CheckAppId(L, 1, "getCachedAppTicket");
        auto ticket = DecryptionKeyHook::GetCachedAppTicket(appId);
        if (ticket.empty()) {
            lua_pushnil(L);
            return 1;
        }
        std::string hex;
        hex.reserve(ticket.size() * 2);
        static constexpr char kHex[] = "0123456789abcdef";
        for (uint8_t b : ticket) {
            hex.push_back(kHex[b >> 4]);
            hex.push_back(kHex[b & 0xf]);
        }
        lua_pushlstring(L, hex.data(), hex.size());
        return 1;
    }

    // ── getDecryptionKey(depotId) -> hexString or empty string ──────────
    // Returns the depot decryption key configured in the .lua file for the
    // given depotId, as a hex string. Returns empty string when no key is set.
    int Bind_getDecryptionKey(lua_State* L) {
        if (lua_gettop(L) < 1) {
            return luaL_error(L, "getDecryptionKey: need depotId");
        }
        AppId_t depotId = CheckAppId(L, 1, "getDecryptionKey");
        auto key = LuaLoader::GetDecryptionKey(depotId);
        if (key.empty()) {
            lua_pushlstring(L, "", 0);
            return 1;
        }
        std::string hex;
        hex.reserve(key.size() * 2);
        static constexpr char kHex[] = "0123456789abcdef";
        for (uint8_t b : key) {
            hex.push_back(kHex[b >> 4]);
            hex.push_back(kHex[b & 0xf]);
        }
        lua_pushlstring(L, hex.data(), hex.size());
        return 1;
    }

    // ── lcHttpGet(url) -> body, status ───────────────────────────────────
    int Bind_lcHttpGet(lua_State* L) {
        if (lua_gettop(L) < 1) {
            return luaL_error(L, "lcHttpGet: need url string");
        }
        std::string_view url = CheckString(L, 1, "lcHttpGet");

        // Gate enforcement before the URL ever reaches WinHTTP. A blocked
        // URL surfaces as status=403, body="" so the caller's flow looks
        // like a real "host said no" response, no script can branch on
        // "did the gate fire" vs "did the upstream server reject me".
        std::string_view host = ExtractHost(url);
        if (!IsHostAllowed(host)) {
            LOG_LUA_WARN("lcHttpGet: host '{}' blocked by allowlist for url='{}'",
                         host.empty() ? std::string_view("<unparseable>") : host,
                         TruncForLog(url));
            lua_pushlstring(L, "", 0);
            lua_pushinteger(L, 403);
            return 2;
        }

        const auto resp = RuntimeHttp::Get(url);
        if (resp.networkError) {
            LOG_LUA_DEBUG("lcHttpGet: net error '{}' for url='{}'",
                          resp.diagnostic, TruncForLog(url));
        }
        lua_pushlstring(L, resp.body.data(), resp.body.size());
        lua_pushinteger(L, static_cast<lua_Integer>(resp.status));
        return 2;
    }

    int Bind_seteticketurl(lua_State* L) {
        std::string_view url = CheckString(L, 1, "seteticketurl");
        LuaLoader::SetEticketUrl(std::string(url));
        return 0;
    }

    int Bind_forcedenuvo(lua_State* L) {
        AppId_t appId = CheckAppId(L, 1, "forcedenuvo");
        g_forcedDenuvoApps.insert(appId);
        return 0;
    }

    int Bind_addprocess(lua_State* L) {
        AppId_t appId = CheckAppId(L, 1, "addprocess");
        std::string_view exeName = CheckString(L, 2, "addprocess");
        g_processAppMap[std::string(exeName)] = appId;
        return 0;
    }
}
