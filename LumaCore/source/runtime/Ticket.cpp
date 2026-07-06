// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "Ticket.h"
#include "config/LuaLoader.h"
#include "hooks/client/DecryptionKeyHook.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <string_view>

namespace Ticket {

    namespace {
        constexpr const char* kSteamIdValue = "SteamID";
        constexpr const char* kAppTicketValue = "AppTicket";
        constexpr const char* kEncryptedTicketValue = "ETicket";
        constexpr DWORD kMaxTicketRegistryBytes = 1024 * 1024;
        constexpr size_t kForgedTailGap = kAppTicketSignatureSize + sizeof(AppId_t);

        std::string AppRegistryPath(AppId_t appId) {
            return "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        }

        bool IsAppManagedByLua(AppId_t appId, const char* caller) {
            if (LuaLoader::HasDepot(appId)) return true;
            LOG_DEBUG("{} for AppId {}: not in addappid, skip", caller, appId);
            return false;
        }

        std::vector<uint8_t> ReadBinaryValue(AppId_t appId, const char* valueName) {
            const std::string regPath = AppRegistryPath(appId);
            DWORD valueType = 0;
            DWORD valueSize = 0;
            LSTATUS status = RegGetValueA(
                HKEY_CURRENT_USER,
                regPath.c_str(),
                valueName,
                RRF_RT_REG_BINARY,
                &valueType,
                nullptr,
                &valueSize);
            if (status != ERROR_SUCCESS || valueSize == 0) {
                LOG_DEBUG("ReadBinaryValue: AppId={} value={} unavailable status={} size={}",
                          appId, valueName, status, valueSize);
                return {};
            }
            if (valueSize > kMaxTicketRegistryBytes) {
                LOG_WARN("ReadBinaryValue: AppId={} value={} too large size={}",
                         appId, valueName, valueSize);
                return {};
            }

            std::vector<uint8_t> value(valueSize);
            status = RegGetValueA(
                HKEY_CURRENT_USER,
                regPath.c_str(),
                valueName,
                RRF_RT_REG_BINARY,
                &valueType,
                value.data(),
                &valueSize);
            if (status != ERROR_SUCCESS || valueType != REG_BINARY) {
                LOG_WARN("ReadBinaryValue: AppId={} value={} read failed status={} type={}",
                         appId, valueName, status, valueType);
                return {};
            }

            value.resize(valueSize);
            LOG_INFO("ReadBinaryValue: AppId={} value={} bytes={}", appId, valueName, value.size());
            return value;
        }

        bool ParseAppIdName(const char* text, AppId_t& appId) {
            if (!text || !*text)
                return false;

            char* end = nullptr;
            unsigned long long parsed = std::strtoull(text, &end, 10);
            if (!end || *end != '\0' || parsed == 0 || parsed > 0xFFFFFFFFull)
                return false;

            appId = static_cast<AppId_t>(parsed);
            return true;
        }

        std::vector<uint8_t> ReadRegistryTicketCandidate(AppId_t appId) {
            const std::string regPath = AppRegistryPath(appId);
            DWORD valueType = 0;
            DWORD valueSize = 0;
            LSTATUS status = RegGetValueA(
                HKEY_CURRENT_USER,
                regPath.c_str(),
                kAppTicketValue,
                RRF_RT_REG_BINARY,
                &valueType,
                nullptr,
                &valueSize);
            if (status != ERROR_SUCCESS || valueSize == 0)
                return {};
            if (valueSize > kMaxTicketRegistryBytes) {
                LOG_WARN("SteamStub source scan: AppId={} AppTicket too large size={}", appId, valueSize);
                return {};
            }

            std::vector<uint8_t> value(valueSize);
            status = RegGetValueA(
                HKEY_CURRENT_USER,
                regPath.c_str(),
                kAppTicketValue,
                RRF_RT_REG_BINARY,
                &valueType,
                value.data(),
                &valueSize);
            if (status != ERROR_SUCCESS || valueType != REG_BINARY)
                return {};

            value.resize(valueSize);
            return value;
        }

        bool WriteRegistryValue(AppId_t appId, const char* valueName, DWORD type,
                                const uint8_t* data, DWORD size) {
            HKEY hKey = nullptr;
            const std::string regPath = AppRegistryPath(appId);
            DWORD disposition = 0;
            LSTATUS status = RegCreateKeyExA(
                HKEY_CURRENT_USER,
                regPath.c_str(),
                0,
                nullptr,
                REG_OPTION_NON_VOLATILE,
                KEY_SET_VALUE,
                nullptr,
                &hKey,
                &disposition);
            if (status != ERROR_SUCCESS) {
                LOG_ERROR("WriteRegistryValue: failed to open {} status={}", regPath, status);
                return false;
            }

            status = RegSetValueExA(hKey, valueName, 0, type, data, size);
            RegCloseKey(hKey);
            if (status != ERROR_SUCCESS) {
                LOG_ERROR("WriteRegistryValue: AppId={} value={} status={}", appId, valueName, status);
                return false;
            }
            return true;
        }

        bool DeleteRegistryValue(AppId_t appId, const char* valueName) {
            HKEY hKey = nullptr;
            const std::string regPath = AppRegistryPath(appId);
            LSTATUS status = RegOpenKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, KEY_SET_VALUE, &hKey);
            if (status != ERROR_SUCCESS) {
                LOG_WARN("DeleteRegistryValue: AppId={} value={} open failed status={}",
                         appId, valueName, status);
                return false;
            }

            status = RegDeleteValueA(hKey, valueName);
            RegCloseKey(hKey);
            if (status != ERROR_SUCCESS && status != ERROR_FILE_NOT_FOUND) {
                LOG_WARN("DeleteRegistryValue: AppId={} value={} delete failed status={}",
                         appId, valueName, status);
                return false;
            }

            LOG_INFO("DeleteRegistryValue: AppId={} value={} removed", appId, valueName);
            return true;
        }

        template <typename T>
        bool ReadTicketValue(const std::vector<uint8_t>& data, size_t offset, T& out) {
            if (offset > data.size() || sizeof(T) > data.size() - offset)
                return false;
            std::memcpy(&out, data.data() + offset, sizeof(T));
            return true;
        }

        void FillOwnershipTicketMetadata(AppOwnershipTicket& ticket,
                                         const AppTicketInspection& inspection) {
            ticket.steamIdOffset = kAppTicketSteamIdOffset;
            ticket.signatureSize = kAppTicketSignatureSize;
            if (inspection.status == AppTicketStatus::OkForged) {
                ticket.totalSize = static_cast<uint32>(ticket.data.size() - sizeof(AppId_t));
                ticket.appIdOffset = inspection.forgedAppIdOffset;
                ticket.signatureOffset = ticket.appIdOffset + sizeof(AppId_t);
                return;
            }

            ticket.totalSize = static_cast<uint32>(ticket.data.size());
            ticket.appIdOffset = kAppTicketAppIdOffset;
            ticket.signatureOffset = inspection.signatureOffset;
        }

        std::string ReadRegistryString(HKEY root, const char* keyPath, const char* valueName) {
            DWORD valueType = 0;
            DWORD valueSize = 0;
            LSTATUS status = RegGetValueA(
                root, keyPath, valueName, RRF_RT_REG_SZ,
                &valueType, nullptr, &valueSize);
            if (status != ERROR_SUCCESS) {
                LOG_DEBUG("ReadRegistryString: {}\\{} missing status={}", keyPath, valueName, status);
                return {};
            }
            if (valueSize == 0 || valueType != REG_SZ) {
                LOG_DEBUG("ReadRegistryString: {}\\{} invalid size={} type={}",
                          keyPath, valueName, valueSize, valueType);
                return {};
            }

            std::vector<char> value(valueSize + 1, '\0');
            status = RegGetValueA(
                root, keyPath, valueName, RRF_RT_REG_SZ,
                &valueType, value.data(), &valueSize);
            if (status != ERROR_SUCCESS || valueType != REG_SZ) {
                LOG_WARN("ReadRegistryString: {}\\{} read failed status={} type={}",
                         keyPath, valueName, status, valueType);
                return {};
            }

            std::string result(value.data());
            while (!result.empty() && result.back() == '\0')
                result.pop_back();
            return result;
        }

        bool ParseDecimalU64(std::string_view text, uint64_t& out) {
            if (text.empty())
                return false;
            uint64_t value = 0;
            for (char c : text) {
                if (c < '0' || c > '9')
                    return false;
                uint64_t digit = static_cast<uint64_t>(c - '0');
                if (value > (UINT64_MAX - digit) / 10)
                    return false;
                value = value * 10 + digit;
            }
            if (value == 0)
                return false;
            out = value;
            return true;
        }

        uint64_t ComposeSteamID64(uint32_t accountId, uint32_t universe) {
            if (accountId == 0)
                return 0;
            if (universe == 0)
                universe = 1; // Public
            constexpr uint64_t kIndividual = 1;
            constexpr uint64_t kDesktopInstance = 1;
            return (static_cast<uint64_t>(universe) << 56) |
                   (kIndividual << 52) |
                   (kDesktopInstance << 32) |
                   static_cast<uint64_t>(accountId);
        }

        uint32_t ParseUniverseName(std::string value) {
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
                return static_cast<char>(std::tolower(ch));
            });
            if (value == "public") return 1;
            if (value == "beta") return 2;
            if (value == "internal") return 3;
            if (value == "dev") return 4;
            return 1;
        }
    }

    const char* AppTicketStatusName(AppTicketStatus status) {
        switch (status) {
        case AppTicketStatus::Empty:           return "empty";
        case AppTicketStatus::TooSmall:        return "too-small";
        case AppTicketStatus::SteamIdMismatch: return "steamid-mismatch";
        case AppTicketStatus::AppIdMismatch:   return "appid-mismatch";
        case AppTicketStatus::OkStandard:      return "ok-standard";
        case AppTicketStatus::OkForged:        return "ok-forged";
        }
        return "unknown";
    }

    const char* TicketPreflightActionName(TicketPreflightAction action) {
        switch (action) {
        case TicketPreflightAction::Skipped:       return "skipped";
        case TicketPreflightAction::Kept:          return "kept";
        case TicketPreflightAction::Replaced:      return "replaced";
        case TicketPreflightAction::Deleted:       return "deleted";
        case TicketPreflightAction::ForgeFailed:   return "forge-failed";
        case TicketPreflightAction::WroteMinimal:  return "wrote-minimal";
        case TicketPreflightAction::MinimalFailed: return "minimal-failed";
        }
        return "unknown";
    }

    const char* TicketPreflightSourceName(TicketPreflightSource source) {
        switch (source) {
        case TicketPreflightSource::None:                 return "none";
        case TicketPreflightSource::Standard:             return "standard";
        case TicketPreflightSource::App7Forged:           return "app7-forged";
        case TicketPreflightSource::LocalSignedSource:    return "local-signed-source";
        case TicketPreflightSource::TargetForgedFallback: return "target-forged-fallback";
        case TicketPreflightSource::Missing:              return "missing";
        }
        return "unknown";
    }

    bool IsAppTicketStatusOk(AppTicketStatus status) {
        return status == AppTicketStatus::OkStandard || status == AppTicketStatus::OkForged;
    }

    AppTicketInspection InspectAppTicket(const std::vector<uint8_t>& data,
                                         AppId_t appId,
                                         uint64_t expectedSteamId) {
        AppTicketInspection out{};
        if (data.empty()) {
            out.status = AppTicketStatus::Empty;
            return out;
        }

        if (data.size() <= kForgedTailGap ||
            data.size() < kAppTicketAppIdOffset + sizeof(AppId_t) ||
            data.size() < kAppTicketSteamIdOffset + sizeof(uint64_t) ||
            data.size() < sizeof(uint32)) {
            out.status = AppTicketStatus::TooSmall;
            return out;
        }

        ReadTicketValue(data, 0, out.signatureOffset);
        if (out.signatureOffset > data.size() ||
            kAppTicketSignatureSize > data.size() - out.signatureOffset) {
            out.status = AppTicketStatus::TooSmall;
            return out;
        }
        ReadTicketValue(data, kAppTicketSteamIdOffset, out.steamId);
        ReadTicketValue(data, kAppTicketAppIdOffset, out.standardAppId);

        out.forgedAppIdOffset = static_cast<uint32>(data.size() - kForgedTailGap);
        if (out.forgedAppIdOffset != kAppTicketAppIdOffset)
            ReadTicketValue(data, out.forgedAppIdOffset, out.forgedAppId);
        else
            out.forgedAppId = out.standardAppId;

        if (expectedSteamId != 0 && out.steamId != expectedSteamId) {
            out.status = AppTicketStatus::SteamIdMismatch;
            return out;
        }

        if (out.standardAppId == appId) {
            out.status = AppTicketStatus::OkStandard;
            return out;
        }

        if (out.forgedAppId == appId) {
            out.status = AppTicketStatus::OkForged;
            return out;
        }

        out.status = AppTicketStatus::AppIdMismatch;
        return out;
    }

    namespace {
        bool IsSignedSourceTicket(AppId_t sourceAppId,
                                  AppId_t targetAppId,
                                  uint64_t activeSteamId,
                                  const std::vector<uint8_t>& ticket,
                                  AppTicketInspection& inspection) {
            if (sourceAppId == 0 || sourceAppId == targetAppId)
                return false;

            inspection = InspectAppTicket(ticket, sourceAppId, activeSteamId);
            return inspection.status == AppTicketStatus::OkStandard
                && inspection.standardAppId == sourceAppId;
        }

        bool FindLocalSignedAppTicketSource(AppId_t targetAppId,
                                            uint64_t activeSteamId,
                                            AppId_t& sourceAppId) {
            sourceAppId = 0;
            if (activeSteamId == 0)
                return false;

            HKEY hRoot = nullptr;
            LSTATUS status = RegOpenKeyExA(HKEY_CURRENT_USER,
                                           "Software\\Valve\\Steam\\Apps",
                                           0,
                                           KEY_ENUMERATE_SUB_KEYS | KEY_QUERY_VALUE,
                                           &hRoot);
            if (status != ERROR_SUCCESS) {
                LOG_WARN("SteamStub source scan: open failed status={}", status);
                return false;
            }

            bool found = false;
            DWORD scanned = 0;
            DWORD usable = 0;
            for (DWORD index = 0;; ++index) {
                char name[64] = {};
                DWORD nameLen = static_cast<DWORD>(sizeof(name));
                FILETIME ignored{};
                status = RegEnumKeyExA(hRoot,
                                       index,
                                       name,
                                       &nameLen,
                                       nullptr,
                                       nullptr,
                                       nullptr,
                                       &ignored);
                if (status == ERROR_NO_MORE_ITEMS)
                    break;
                if (status != ERROR_SUCCESS)
                    continue;

                AppId_t candidateAppId = 0;
                if (!ParseAppIdName(name, candidateAppId) || candidateAppId == targetAppId)
                    continue;

                ++scanned;
                std::vector<uint8_t> ticket = ReadRegistryTicketCandidate(candidateAppId);
                AppTicketInspection inspection{};
                if (!IsSignedSourceTicket(candidateAppId, targetAppId, activeSteamId, ticket, inspection))
                    continue;

                ++usable;
                if (!found || candidateAppId < sourceAppId) {
                    found = true;
                    sourceAppId = candidateAppId;
                }
            }

            RegCloseKey(hRoot);
            if (!found) {
                LOG_WARN("SteamStub source scan: target={} scanned={} usable=0", targetAppId, scanned);
                return false;
            }

            LOG_INFO("SteamStub source scan: target={} ticketSource=local-signed-source sourceAppId={} scanned={} usable={}",
                     targetAppId, sourceAppId, scanned, usable);
            return true;
        }
    }

    static uint64_t GetSteamIDFromRegistryString(AppId_t appId) {
        const std::string regPath = AppRegistryPath(appId);
        const std::string steamIdStr = ReadRegistryString(HKEY_CURRENT_USER,
                                                          regPath.c_str(),
                                                          kSteamIdValue);
        uint64_t steamID = 0;
        if (!ParseDecimalU64(steamIdStr, steamID)) {
            return 0;
        }

        LOG_DEBUG("GetSpoofSteamID for AppId {}: SteamID REG_SZ -> 0x{:X}({})", appId, steamID, steamID);
        return steamID;
    }

    std::vector<uint8_t> GetAppOwnershipTicketFromRegistry(AppId_t appId) {
        LOG_INFO("GetAppOwnershipTicketFromRegistry: ENTER AppId={}", appId);
        if (!IsAppManagedByLua(appId, "GetAppOwnershipTicketFromRegistry")) return {};
        return ReadBinaryValue(appId, kAppTicketValue);
    }

    std::vector<uint8_t> GetEncryptedTicketFromRegistry(AppId_t appId) {
        LOG_INFO("GetEncryptedTicketFromRegistry: ENTER AppId={}", appId);
        if (!IsAppManagedByLua(appId, "GetEncryptedTicketFromRegistry")) return {};
        return ReadBinaryValue(appId, kEncryptedTicketValue);
    }

    bool WriteAppOwnershipTicket(AppId_t appId, const std::vector<uint8_t>& data) {
        if (!WriteRegistryValue(appId, kAppTicketValue, REG_BINARY,
                                data.data(), static_cast<DWORD>(data.size())))
            return false;
        LOG_INFO("Wrote AppTicket for AppId {} ({} bytes)", appId, data.size());
        return true;
    }

    bool WriteEncryptedTicket(AppId_t appId, const std::vector<uint8_t>& data) {
        if (!WriteRegistryValue(appId, kEncryptedTicketValue, REG_BINARY,
                                data.data(), static_cast<DWORD>(data.size())))
            return false;
        LOG_INFO("Wrote ETicket for AppId {} ({} bytes)", appId, data.size());
        return true;
    }

    bool WriteSteamID(AppId_t appId, uint64_t steamId) {
        if (appId == 0 || appId == k_uAppIdInvalid || steamId == 0)
            return false;
        const std::string value = std::to_string(steamId);
        if (!WriteRegistryValue(appId, kSteamIdValue, REG_SZ,
                                reinterpret_cast<const uint8_t*>(value.c_str()),
                                static_cast<DWORD>(value.size() + 1)))
            return false;
        LOG_INFO("Wrote SteamID for AppId {} ({})", appId, steamId);
        return true;
    }

    uint64_t GetSpoofSteamID(AppId_t appId) {
        // exclude those appids that are not in addappid
        if (!LuaLoader::HasDepot(appId)) {
            LOG_DEBUG("GetSpoofSteamID for AppId {}: not in addappid, skip spoofing", appId);
            return 0;
        }
        const uint64_t registrySteamID = GetSteamIDFromRegistryString(appId);
        if (registrySteamID != 0) {
            return registrySteamID;
        }

        std::vector<uint8_t> ticket = GetAppOwnershipTicketFromRegistry(appId);
        const AppTicketInspection inspection = InspectAppTicket(ticket, appId, 0);
        if (IsAppTicketStatusOk(inspection.status)) {
            const uint64_t steamID = inspection.steamId;
            LOG_DEBUG("GetSpoofSteamID for AppId {}: -> 0x{:X}({})", appId, steamID, steamID);
            return steamID;
        }
        if (!ticket.empty()) {
            LOG_WARN("GetSpoofSteamID for AppId {}: rejecting AppTicket status={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                     appId, AppTicketStatusName(inspection.status), inspection.steamId,
                     inspection.standardAppId, inspection.forgedAppId);
        }
        return 0;
    }

    // ════════════════════════════════════════════════════════════════
    //  Active SteamID lookup — used for fabricating tickets and for
    //  detecting "user switched accounts since the cached ticket was
    //  written" cases.
    //
    //  Lookup order:
    //   1. HKCU\Software\Valve\Steam\ActiveProcess\ActiveUser (DWORD).
    //      Set by Steam at runtime, reset to 0 when Steam isn't running.
    //   2. Walk %SteamPath%\userdata\<accountid>\ folders. Steam keeps
    //      one folder per account that's ever logged in. If exactly one
    //      exists we use it; if multiple, we pick the most recently
    //      modified (best heuristic for "current user").
    // ════════════════════════════════════════════════════════════════
    uint64_t GetActiveSteamID64() {
        auto ReadCached = []() -> uint64_t {
            char buf[32] = {};
            DWORD sz = sizeof(buf);
            if (RegGetValueA(HKEY_CURRENT_USER, "Software\\Valve\\Steam\\lumacore",
                             "LastActiveSteamId", RRF_RT_REG_SZ, nullptr, buf, &sz) == ERROR_SUCCESS) {
                char* end = nullptr;
                uint64_t v = strtoull(buf, &end, 16);
                if (end && *end == '\0' && v != 0) return v;
            }
            return 0;
        };
        auto WriteCache = [](uint64_t sid) {
            if (sid == 0) return;
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%llX", static_cast<unsigned long long>(sid));
            HKEY hk = nullptr;
            if (RegCreateKeyExA(HKEY_CURRENT_USER, "Software\\Valve\\Steam\\lumacore",
                                0, nullptr, 0, KEY_WRITE, nullptr, &hk, nullptr) == ERROR_SUCCESS) {
                RegSetValueExA(hk, "LastActiveSteamId", 0, REG_SZ,
                               reinterpret_cast<const BYTE*>(buf),
                               static_cast<DWORD>(std::strlen(buf) + 1));
                RegCloseKey(hk);
            }
        };

        // 1. ActiveProcess\ActiveUser (live value while Steam is running)
        DWORD accountId = 0;
        DWORD size = sizeof(accountId);
        DWORD type = 0;
        LSTATUS s = RegGetValueA(
            HKEY_CURRENT_USER,
            "Software\\Valve\\Steam\\ActiveProcess",
            "ActiveUser",
            RRF_RT_REG_DWORD,
            &type,
            &accountId,
            &size);
        if (s == ERROR_SUCCESS && size == sizeof(accountId) && type == REG_DWORD && accountId != 0) {
            std::string universe = ReadRegistryString(
                HKEY_CURRENT_USER,
                "Software\\Valve\\Steam\\ActiveProcess",
                "Universe");
            const uint64_t steamID64 = ComposeSteamID64(accountId, ParseUniverseName(universe));
            WriteCache(steamID64);
            LOG_DEBUG("GetActiveSteamID64: ActiveProcess\\ActiveUser={} universe={} -> SteamID64=0x{:X}",
                      accountId, universe.empty() ? "Public" : universe, steamID64);
            return steamID64;
        }
        if (s == ERROR_SUCCESS && (size != sizeof(accountId) || type != REG_DWORD)) {
            LOG_WARN("GetActiveSteamID64: ActiveUser invalid size={} type={}", size, type);
        }

        // 2. Filesystem fallback — pick the most recently modified
        //    userdata\<accountid>\ folder. This survives Steam being
        //    closed at the moment we query.
        DWORD pathLen = MAX_PATH;
        char steamPath[MAX_PATH] = {};
        if (RegGetValueA(HKEY_CURRENT_USER, "Software\\Valve\\Steam", "SteamPath",
                         RRF_RT_REG_SZ, nullptr, steamPath, &pathLen) != ERROR_SUCCESS) {
            uint64_t cached = ReadCached();
            LOG_DEBUG("GetActiveSteamID64: no ActiveUser, no SteamPath — fallback to cache=0x{:X}", cached);
            return cached;
        }

        char userdataPath[MAX_PATH];
        std::snprintf(userdataPath, MAX_PATH, "%s\\userdata", steamPath);

        char searchPattern[MAX_PATH];
        std::snprintf(searchPattern, MAX_PATH, "%s\\*", userdataPath);

        WIN32_FIND_DATAA fd;
        HANDLE hFind = FindFirstFileA(searchPattern, &fd);
        if (hFind == INVALID_HANDLE_VALUE) {
            uint64_t cached = ReadCached();
            LOG_DEBUG("GetActiveSteamID64: no userdata folder at {} — fallback to cache=0x{:X}",
                      userdataPath, cached);
            return cached;
        }

        DWORD bestAccountId = 0;
        FILETIME bestMtime = {};
        do {
            if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
            if (fd.cFileName[0] == '.') continue;

            char* end = nullptr;
            unsigned long aid = strtoul(fd.cFileName, &end, 10);
            if (!end || *end != '\0' || aid == 0) continue;

            // Pick the most recently written folder.
            if (bestAccountId == 0
                || CompareFileTime(&fd.ftLastWriteTime, &bestMtime) > 0) {
                bestAccountId = static_cast<DWORD>(aid);
                bestMtime = fd.ftLastWriteTime;
            }
        } while (FindNextFileA(hFind, &fd));

        FindClose(hFind);

        if (bestAccountId == 0) {
            uint64_t cached = ReadCached();
            LOG_DEBUG("GetActiveSteamID64: no userdata\\<accountid>\\ folders found — fallback to cache=0x{:X}",
                      cached);
            return cached;
        }

        const uint64_t steamID64 = ComposeSteamID64(bestAccountId, 1);
        WriteCache(steamID64);
        LOG_DEBUG("GetActiveSteamID64: userdata\\{}\\ -> SteamID64=0x{:X} (filesystem fallback)",
                  bestAccountId, steamID64);
        return steamID64;
    }

    // ════════════════════════════════════════════════════════════════
    //  Known Steam DRM (Steam Stub) appid table.
    //
    //  This is a hand-curated, deliberately-small list. We only flag
    //  titles where we have direct evidence of error-54 reports against
    //  LumaCore. The list is not security-sensitive — it only changes
    //  the wording of the diagnostic log line so users get a "try
    //  Steamless" hint instead of generic "ownership patched" output.
    // ════════════════════════════════════════════════════════════════
    bool IsKnownSteamDrmApp(AppId_t appId) {
        switch (appId) {
        case 1167630:  // Teardown
        case 782330:   // DOOM Eternal
        case 17390:    // Spore (legacy v2 wrapper)
        case 21660:    // Mirror's Edge (legacy v1.5 wrapper)
            return true;
        default:
            return false;
        }
    }

    // ════════════════════════════════════════════════════════════════
    //  Build a minimal AppTicket-shaped blob.
    //
    //  Layout matches what Steam's wrapper writes into the registry:
    //    [uint32 sigOffset]
    //    [uint32 version=4]
    //    [uint64 steamID]
    //    [uint32 appId]
    //    [uint32 ticketGenerated (Unix epoch)]
    //    [uint32 ticketExpires]
    //    [uint32 licenseFlags]
    //    [uint32 licenseCount=0]    // empty license list
    //    [uint32 dlcCount=0]        // empty DLC list
    //    [uint16 reserved=0]
    //    [128 bytes of zeros]       // signature placeholder
    //
    //  This is unsigned. Steam Stub v2.2+ verifies the signature against
    //  Valve's public key so this blob alone does NOT bypass error 54
    //  on modern Steam DRM titles. It does help older v1.5 / early v2
    //  wrappers and tools that only inspect the SteamID/AppID fields.
    //  Steamless on the .exe is the actual fix for v3 titles like
    //  Teardown — this is just a best-effort fallback.
    // ════════════════════════════════════════════════════════════════
    std::vector<uint8_t> BuildMinimalAppTicket(AppId_t appId) {
        const uint64_t steamID = GetActiveSteamID64();
        if (steamID == 0) {
            LOG_DEBUG("BuildMinimalAppTicket: AppId={} no active SteamID — skip", appId);
            return {};
        }

        // Header before signature: 4 + 4 + 8 + 4 + 4 + 4 + 4 + 4 + 4 + 2 = 42 bytes.
        constexpr size_t kHeaderBytes = 42;
        constexpr size_t kSignatureBytes = 128;
        const size_t total = kHeaderBytes + kSignatureBytes;

        std::vector<uint8_t> blob(total, 0);
        uint8_t* p = blob.data();

        const uint32_t sigOffset = static_cast<uint32_t>(kHeaderBytes);
        std::memcpy(p +  0, &sigOffset, 4);
        const uint32_t version = 4;
        std::memcpy(p +  4, &version, 4);
        std::memcpy(p +  8, &steamID, 8);
        std::memcpy(p + 16, &appId, 4);
        const uint32_t now = static_cast<uint32_t>(time(nullptr));
        std::memcpy(p + 20, &now, 4);
        const uint32_t expires = now + (60u * 60u * 24u * 30u);  // +30 days
        std::memcpy(p + 24, &expires, 4);
        // licenseFlags=0, licenseCount=0, dlcCount=0, reserved=0 are already zero-init.

        LOG_INFO("BuildMinimalAppTicket: AppId={} steamID=0x{:X} -> {} bytes (unsigned)",
                 appId, steamID, total);
        return blob;
    }

    constexpr AppId_t kLocalAppTicketSourceAppId = 7;

    // SpawnProcess preflight. Steam Stub wrappers read the registry early,
    // before IPC ticket hooks can help, so stale AppTicket blobs get fixed here.
    TicketPreflightResult EnsureRegistryTicketsForApp(AppId_t appId, bool forceSteamStub) {
        TicketPreflightResult result{};
        result.knownSteamStub = IsKnownSteamDrmApp(appId) || forceSteamStub;

        const uint64_t activeID = GetActiveSteamID64();
        if (activeID == 0) {
            LOG_INFO("EnsureRegistryTicketsForApp: AppId={} no active user — skip", appId);
            result.action = TicketPreflightAction::Skipped;
            return result;
        }

        if (GetSteamIDFromRegistryString(appId) != activeID) {
            result.changed = WriteSteamID(appId, activeID) || result.changed;
        }

        std::vector<uint8_t> existing = GetAppOwnershipTicketFromRegistry(appId);
        AppTicketInspection inspection = InspectAppTicket(existing, appId, activeID);
        result.ticketStatus = inspection.status;

        bool acceptableExisting = IsAppTicketStatusOk(inspection.status);
        TicketPreflightSource existingSource = TicketPreflightSource::None;
        if (inspection.status == AppTicketStatus::OkStandard) {
            existingSource = TicketPreflightSource::Standard;
        } else if (inspection.status == AppTicketStatus::OkForged
                   && inspection.standardAppId == kLocalAppTicketSourceAppId
                   && inspection.forgedAppId == appId) {
            existingSource = TicketPreflightSource::App7Forged;
        } else if (inspection.status == AppTicketStatus::OkForged
                   && inspection.forgedAppId == appId) {
            std::vector<uint8_t> sourceTicket =
                ReadRegistryTicketCandidate(inspection.standardAppId);
            AppTicketInspection sourceInspection{};
            existingSource =
                IsSignedSourceTicket(inspection.standardAppId, appId, activeID,
                                     sourceTicket, sourceInspection)
                    ? TicketPreflightSource::LocalSignedSource
                    : TicketPreflightSource::TargetForgedFallback;
        }
        const bool knownSteamStubFallback =
            result.knownSteamStub
            && inspection.status == AppTicketStatus::OkForged
            && inspection.forgedAppId == appId
            && inspection.standardAppId != kLocalAppTicketSourceAppId
            && (existingSource == TicketPreflightSource::LocalSignedSource
                || existingSource == TicketPreflightSource::TargetForgedFallback);

        if (knownSteamStubFallback) {
            LOG_WARN("EnsureRegistryTicketsForApp: AppId={} treating non-app7 forged ticket as fallback while app7 source is checked ticketSource={} status={} bytes={} steamId=0x{:X} requiredSourceAppId={} standardAppId={} forgedAppId={} target={}",
                     appId, TicketPreflightSourceName(existingSource),
                     AppTicketStatusName(inspection.status), existing.size(),
                     inspection.steamId, kLocalAppTicketSourceAppId,
                     inspection.standardAppId, inspection.forgedAppId, appId);
        }

        if (acceptableExisting && !result.knownSteamStub) {
            result.ticketSource = existingSource;
            result.sourceAppId = inspection.standardAppId;
            LOG_INFO("EnsureRegistryTicketsForApp: AppId={} AppTicket kept status={} ticketSource={} bytes={} steamId=0x{:X} sourceAppId={} standardAppId={} forgedAppId={} sigOffset={} forgedOffset={}",
                     appId, AppTicketStatusName(inspection.status),
                     TicketPreflightSourceName(result.ticketSource), existing.size(),
                     inspection.steamId, result.sourceAppId,
                     inspection.standardAppId, inspection.forgedAppId,
                     inspection.signatureOffset, inspection.forgedAppIdOffset);
            result.action = TicketPreflightAction::Kept;
            return result;
        }

        if (acceptableExisting
            && result.knownSteamStub
            && (existingSource == TicketPreflightSource::Standard
                || existingSource == TicketPreflightSource::App7Forged)) {
            result.ticketSource = existingSource;
            result.sourceAppId = inspection.standardAppId;
            LOG_INFO("EnsureRegistryTicketsForApp: AppId={} AppTicket kept status={} ticketSource={} bytes={} steamId=0x{:X} sourceAppId={} standardAppId={} forgedAppId={} sigOffset={} forgedOffset={}",
                     appId, AppTicketStatusName(inspection.status),
                     TicketPreflightSourceName(result.ticketSource), existing.size(),
                     inspection.steamId, result.sourceAppId,
                     inspection.standardAppId, inspection.forgedAppId,
                     inspection.signatureOffset, inspection.forgedAppIdOffset);
            result.action = TicketPreflightAction::Kept;
            return result;
        }

        const bool keepFallbackUntilReplacement =
            acceptableExisting && knownSteamStubFallback;

        if (!existing.empty() && !keepFallbackUntilReplacement) {
            LOG_WARN("EnsureRegistryTicketsForApp: AppId={} rejecting AppTicket status={} bytes={} steamId=0x{:X} active=0x{:X} standardAppId={} forgedAppId={} target={}",
                     appId, AppTicketStatusName(inspection.status), existing.size(),
                     inspection.steamId, activeID, inspection.standardAppId,
                     inspection.forgedAppId, appId);
            result.changed = DeleteRegistryValue(appId, kAppTicketValue) || result.changed;
            result.action = TicketPreflightAction::Deleted;
        }

        if (result.knownSteamStub) {
            const AppId_t forgedSourceAppId = kLocalAppTicketSourceAppId;
            std::vector<uint8_t> forged = ForgeAppTicket(forgedSourceAppId, appId);
            AppTicketInspection forgedInspection = InspectAppTicket(forged, appId, activeID);
            TicketPreflightSource forgedSource = TicketPreflightSource::App7Forged;
            if (!IsAppTicketStatusOk(forgedInspection.status)) {
                if (keepFallbackUntilReplacement) {
                    LOG_WARN("EnsureRegistryTicketsForApp: AppId={} forge failed, keeping fallback ticketSource={} status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={} fallbackSourceAppId={}",
                             appId,
                             TicketPreflightSourceName(existingSource),
                             AppTicketStatusName(forgedInspection.status), forged.size(),
                             inspection.steamId, inspection.standardAppId,
                             inspection.forgedAppId, inspection.standardAppId);
                    result.action = TicketPreflightAction::Kept;
                    result.ticketStatus = inspection.status;
                    result.ticketSource = existingSource;
                    result.sourceAppId = inspection.standardAppId;
                    return result;
                }
                LOG_WARN("EnsureRegistryTicketsForApp: AppId={} forge failed ticketSource={} status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                         appId, TicketPreflightSourceName(TicketPreflightSource::Missing),
                         AppTicketStatusName(forgedInspection.status), forged.size(),
                         forgedInspection.steamId, forgedInspection.standardAppId,
                         forgedInspection.forgedAppId);
                result.action = TicketPreflightAction::ForgeFailed;
                result.ticketStatus = forgedInspection.status;
                result.ticketSource = TicketPreflightSource::Missing;
                return result;
            }

            if (WriteAppOwnershipTicket(appId, forged)) {
                LOG_INFO("EnsureRegistryTicketsForApp: AppId={} wrote forged AppTicket status={} ticketSource={} bytes={} steamId=0x{:X} sourceAppId={} standardAppId={} forgedAppId={} forgedOffset={}",
                         appId, AppTicketStatusName(forgedInspection.status),
                         TicketPreflightSourceName(forgedSource), forged.size(),
                         forgedInspection.steamId, forgedSourceAppId,
                         forgedInspection.standardAppId,
                         forgedInspection.forgedAppId, forgedInspection.forgedAppIdOffset);
                result.action = TicketPreflightAction::Replaced;
                result.ticketStatus = forgedInspection.status;
                result.ticketSource = forgedSource;
                result.sourceAppId = forgedSourceAppId;
                result.changed = true;
                return result;
            }

            if (keepFallbackUntilReplacement) {
                LOG_WARN("EnsureRegistryTicketsForApp: AppId={} forged AppTicket write failed sourceAppId={}, keeping fallback ticketSource={}",
                         appId, forgedSourceAppId,
                         TicketPreflightSourceName(existingSource));
                result.action = TicketPreflightAction::Kept;
                result.ticketStatus = inspection.status;
                result.ticketSource = existingSource;
                result.sourceAppId = inspection.standardAppId;
                return result;
            }

            LOG_WARN("EnsureRegistryTicketsForApp: AppId={} forged AppTicket write failed ticketSource={} sourceAppId={}",
                     appId, TicketPreflightSourceName(TicketPreflightSource::Missing),
                     forgedSourceAppId);
            result.action = TicketPreflightAction::ForgeFailed;
            result.ticketStatus = forgedInspection.status;
            result.ticketSource = TicketPreflightSource::Missing;
            return result;
        }

        std::vector<uint8_t> blob = BuildMinimalAppTicket(appId);
        if (!blob.empty() && WriteAppOwnershipTicket(appId, blob)) {
            AppTicketInspection minimalInspection = InspectAppTicket(blob, appId, activeID);
            LOG_INFO("EnsureRegistryTicketsForApp: AppId={} wrote minimal AppTicket status={} bytes={}",
                     appId, AppTicketStatusName(minimalInspection.status), blob.size());
            result.action = TicketPreflightAction::WroteMinimal;
            result.ticketStatus = minimalInspection.status;
            result.changed = true;
            return result;
        }

        if (blob.empty()) {
            LOG_WARN("EnsureRegistryTicketsForApp: AppId={} minimal ticket build failed", appId);
        } else {
            LOG_WARN("EnsureRegistryTicketsForApp: AppId={} minimal ticket write failed", appId);
        }
        result.action = TicketPreflightAction::MinimalFailed;
        return result;
    }

    std::vector<uint8_t> ForgeAppTicket(AppId_t sourceAppId, AppId_t targetAppId) {
        std::vector<uint8_t> source = DecryptionKeyHook::GetCachedAppTicket(sourceAppId);
        if (source.empty()) {
            LOG_DEBUG("ForgeAppTicket for AppId {}: no cached ticket source appId={}",
                      targetAppId, sourceAppId);
            return {};
        }

        const uint64_t activeID = GetActiveSteamID64();
        AppTicketInspection sourceInspection = InspectAppTicket(source, sourceAppId, activeID);
        if (sourceInspection.status != AppTicketStatus::OkStandard) {
            LOG_DEBUG("ForgeAppTicket for AppId {}: source ticket invalid sourceAppId={} status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                      targetAppId, sourceAppId,
                      AppTicketStatusName(sourceInspection.status),
                      source.size(), sourceInspection.steamId,
                      sourceInspection.standardAppId,
                      sourceInspection.forgedAppId);
            return {};
        }

        const size_t bodyLen = source.size() - 128;
        std::vector<uint8_t> ticket;
        ticket.reserve(source.size() + sizeof(AppId_t));
        std::copy_n(source.begin(), bodyLen, std::back_inserter(ticket));
        const uint8_t* idBytes = reinterpret_cast<const uint8_t*>(&targetAppId);
        std::copy_n(idBytes, sizeof(AppId_t), std::back_inserter(ticket));
        std::copy(source.begin() + bodyLen, source.end(), std::back_inserter(ticket));

        LOG_INFO("Forged App Ownership Ticket, AppId: {}, SourceAppId: {}, Physical Size: {}, Source Size: {}",
                 targetAppId, sourceAppId, ticket.size(), source.size());
        return ticket;
    }

    std::vector<uint8_t> ForgeAppTicketFromBestSource(AppId_t targetAppId, AppId_t& sourceAppId) {
        sourceAppId = 0;
        const uint64_t activeID = GetActiveSteamID64();

        std::vector<uint8_t> forged = ForgeAppTicket(kLocalAppTicketSourceAppId, targetAppId);
        AppTicketInspection forgedInspection = InspectAppTicket(forged, targetAppId, activeID);
        if (IsAppTicketStatusOk(forgedInspection.status)) {
            sourceAppId = kLocalAppTicketSourceAppId;
            return forged;
        }

        LOG_WARN("ForgeAppTicketFromBestSource: app-7 unavailable target={} status={} bytes={}",
                 targetAppId, AppTicketStatusName(forgedInspection.status), forged.size());

        AppId_t localSourceAppId = 0;
        if (!FindLocalSignedAppTicketSource(targetAppId, activeID, localSourceAppId))
            return {};

        forged = ForgeAppTicket(localSourceAppId, targetAppId);
        forgedInspection = InspectAppTicket(forged, targetAppId, activeID);
        if (!IsAppTicketStatusOk(forgedInspection.status)) {
            LOG_WARN("ForgeAppTicketFromBestSource: local source failed target={} sourceAppId={} status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                     targetAppId, localSourceAppId,
                     AppTicketStatusName(forgedInspection.status),
                     forged.size(), forgedInspection.steamId,
                     forgedInspection.standardAppId, forgedInspection.forgedAppId);
            return {};
        }

        sourceAppId = localSourceAppId;
        LOG_INFO("ForgeAppTicketFromBestSource: target={} ticketSource=local-signed-source sourceAppId={} bytes={}",
                 targetAppId, sourceAppId, forged.size());
        return forged;
    }

    bool GetAppOwnershipTicket(AppId_t appId, AppOwnershipTicket& ticket) {
        ticket = {};
        const uint64_t activeID = GetActiveSteamID64();

        ticket.data = GetAppOwnershipTicketFromRegistry(appId);
        AppTicketInspection registryInspection = InspectAppTicket(ticket.data, appId, activeID);
        if (IsAppTicketStatusOk(registryInspection.status)) {
            FillOwnershipTicketMetadata(ticket, registryInspection);
            return true;
        }
        if (!ticket.data.empty()) {
            LOG_WARN("GetAppOwnershipTicket: AppId={} rejecting registry AppTicket status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                     appId, AppTicketStatusName(registryInspection.status),
                     ticket.data.size(), registryInspection.steamId,
                     registryInspection.standardAppId, registryInspection.forgedAppId);
        }

        AppId_t sourceAppId = 0;
        ticket.data = ForgeAppTicketFromBestSource(appId, sourceAppId);
        if (ticket.data.empty()) {
            LOG_DEBUG("GetAppOwnershipTicket: AppId={} forge failed, no ticket available", appId);
            return false;
        }

        AppTicketInspection forgedInspection = InspectAppTicket(ticket.data, appId, activeID);
        if (!IsAppTicketStatusOk(forgedInspection.status)) {
            LOG_WARN("GetAppOwnershipTicket: AppId={} rejecting forged AppTicket status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                     appId, AppTicketStatusName(forgedInspection.status),
                     ticket.data.size(), forgedInspection.steamId,
                     forgedInspection.standardAppId, forgedInspection.forgedAppId);
            ticket = {};
            return false;
        }

        FillOwnershipTicketMetadata(ticket, forgedInspection);
        return true;
    }
}

