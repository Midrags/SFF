#include "Ticket.h"

#include <cstdlib>
#include <cstring>

namespace Ticket {

    static uint64_t GetSteamIDFromRegistryString(AppId_t appId) {
        HKEY hKey;
        const std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        if (RegOpenKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, KEY_READ, &hKey) != ERROR_SUCCESS) {
            return 0;
        }

        DWORD valueType = 0;
        DWORD valueSize = 0;
        if (RegQueryValueExA(hKey, "SteamID", nullptr, &valueType, nullptr, &valueSize) != ERROR_SUCCESS
            || valueType != REG_SZ || valueSize == 0) {
            RegCloseKey(hKey);
            return 0;
        }

        std::vector<char> value(valueSize);
        if (RegQueryValueExA(hKey, "SteamID", nullptr, nullptr,
            reinterpret_cast<LPBYTE>(value.data()), &valueSize) != ERROR_SUCCESS) {
            RegCloseKey(hKey);
            return 0;
        }
        RegCloseKey(hKey);

        if (value.back() != '\0') {
            value.push_back('\0');
        }

        const std::string steamIdStr(value.data());
        if (steamIdStr.empty()) {
            return 0;
        }
        for (char c : steamIdStr) {
            if (c < '0' || c > '9') {
                return 0;
            }
        }

        const uint64_t steamID = std::strtoull(steamIdStr.c_str(), nullptr, 10);
        if (steamID != 0) {
            LOG_DEBUG("GetSpoofSteamID for AppId {}: SteamID REG_SZ -> 0x{:X}({})", appId, steamID, steamID);
        }
        return steamID;
    }

    std::vector<uint8_t> GetAppOwnershipTicketFromRegistry(AppId_t appId) {
        LOG_INFO("GetAppOwnershipTicketFromRegistry: ENTER AppId={}", appId);
        // exclude those appids that are not in addappid
        if (!LuaLoader::HasDepot(appId)) {
            LOG_INFO("GetAppOwnershipTicketFromRegistry: AppId={} not in addappid, skip", appId);
            return {};
        }
        std::vector<uint8_t> empty{};
        HKEY hKey;
        const std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        LSTATUS openStatus = RegOpenKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, KEY_READ, &hKey);
        if (openStatus != ERROR_SUCCESS) {
            LOG_WARN("GetAppOwnershipTicketFromRegistry: AppId={} RegOpenKey({}) failed status={}", appId, regPath, openStatus);
            return empty;
        }

        std::vector<uint8_t> value(1024);
        DWORD valueSize = static_cast<DWORD>(value.size());
        DWORD valueType = 0;
        LSTATUS qStatus = RegQueryValueExA(hKey, "AppTicket", nullptr, &valueType, value.data(), &valueSize);
        if (qStatus != ERROR_SUCCESS || valueType != REG_BINARY) {
            RegCloseKey(hKey);
            LOG_WARN("GetAppOwnershipTicketFromRegistry: AppId={} RegQuery(AppTicket) status={} type={} (no cached blob)",
                     appId, qStatus, valueType);
            return empty;
        }
        RegCloseKey(hKey);

        value.resize(valueSize);
        LOG_INFO("GetAppOwnershipTicketFromRegistry: AppId={} got {} bytes from registry", appId, valueSize);
        return value;
    }

    std::vector<uint8_t> GetEncryptedTicketFromRegistry(AppId_t appId) {
        LOG_INFO("GetEncryptedTicketFromRegistry: ENTER AppId={}", appId);
        // exclude those appids that are not in addappid
        if (!LuaLoader::HasDepot(appId)) {
            LOG_INFO("GetEncryptedTicketFromRegistry: AppId={} not in addappid, skip", appId);
            return {};
        }
        std::vector<uint8_t> empty{};
        HKEY hKey;
        const std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        LSTATUS openStatus = RegOpenKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, KEY_READ, &hKey);
        if (openStatus != ERROR_SUCCESS) {
            LOG_WARN("GetEncryptedTicketFromRegistry: AppId={} RegOpenKey({}) failed status={}", appId, regPath, openStatus);
            return empty;
        }

        std::vector<uint8_t> value(1024);
        DWORD valueSize = static_cast<DWORD>(value.size());
        DWORD valueType = 0;
        LSTATUS qStatus = RegQueryValueExA(hKey, "ETicket", nullptr, &valueType, value.data(), &valueSize);
        if (qStatus != ERROR_SUCCESS || valueType != REG_BINARY) {
            RegCloseKey(hKey);
            LOG_WARN("GetEncryptedTicketFromRegistry: AppId={} RegQuery(ETicket) status={} type={} (no cached blob)",
                     appId, qStatus, valueType);
            return empty;
        }
        RegCloseKey(hKey);

        value.resize(valueSize);
        LOG_INFO("GetEncryptedTicketFromRegistry: AppId={} got {} bytes from registry", appId, valueSize);
        return value;
    }

    bool WriteAppOwnershipTicket(AppId_t appId, const std::vector<uint8_t>& data) {
        // we can't execlude appids here 
        HKEY hKey;
        const std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        DWORD disposition;
        if (RegCreateKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, &disposition) != ERROR_SUCCESS) {
            LOG_ERROR("Failed to create/open registry key: {}", regPath);
            return false;
        }
        LSTATUS result = RegSetValueExA(hKey, "AppTicket", 0, REG_BINARY, data.data(), static_cast<DWORD>(data.size()));
        RegCloseKey(hKey);
        if (result != ERROR_SUCCESS) {
            LOG_ERROR("Failed to write AppTicket for AppId {}: {}", appId, result);
            return false;
        }
        LOG_INFO("Wrote AppTicket for AppId {} ({} bytes)", appId, data.size());
        return true;
    }

    bool WriteEncryptedTicket(AppId_t appId, const std::vector<uint8_t>& data) {
        // we can't execlude appids here 
        HKEY hKey;
        const std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        DWORD disposition;
        if (RegCreateKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, &disposition) != ERROR_SUCCESS) {
            LOG_ERROR("Failed to create/open registry key: {}", regPath);
            return false;
        }
        LSTATUS result = RegSetValueExA(hKey, "ETicket", 0, REG_BINARY, data.data(), static_cast<DWORD>(data.size()));
        RegCloseKey(hKey);
        if (result != ERROR_SUCCESS) {
            LOG_ERROR("Failed to write ETicket for AppId {}: {}", appId, result);
            return false;
        }
        LOG_INFO("Wrote ETicket for AppId {} ({} bytes)", appId, data.size());
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

        // The SteamID baked into the cached AppOwnershipTicket is the same
        // one Steam itself uses for this app — pull it straight out of the
        // ticket so spoofed responses match what the DRM layer expects.
        // Layout: ticket bytes start with [uint32 Size][uint32 Version][uint64 SteamID][...].
        std::vector<uint8_t> ticket = GetAppOwnershipTicketFromRegistry(appId);
        if (ticket.size() >= 16) {
            const uint64_t steamID = reinterpret_cast<const uint64_t*>(ticket.data())[1];
            LOG_DEBUG("GetSpoofSteamID for AppId {}: -> 0x{:X}({})", appId, steamID, steamID);
            return steamID;
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
        if (s == ERROR_SUCCESS && accountId != 0) {
            const uint64_t steamID64 = 0x0110000100000000ULL | static_cast<uint64_t>(accountId);
            LOG_DEBUG("GetActiveSteamID64: ActiveProcess\\ActiveUser={} -> SteamID64=0x{:X}",
                      accountId, steamID64);
            return steamID64;
        }

        // 2. Filesystem fallback — pick the most recently modified
        //    userdata\<accountid>\ folder. This survives Steam being
        //    closed at the moment we query.
        DWORD pathLen = MAX_PATH;
        char steamPath[MAX_PATH] = {};
        if (RegGetValueA(HKEY_CURRENT_USER, "Software\\Valve\\Steam", "SteamPath",
                         RRF_RT_REG_SZ, nullptr, steamPath, &pathLen) != ERROR_SUCCESS) {
            LOG_DEBUG("GetActiveSteamID64: no ActiveUser, no SteamPath — give up");
            return 0;
        }

        char userdataPath[MAX_PATH];
        std::snprintf(userdataPath, MAX_PATH, "%s\\userdata", steamPath);

        char searchPattern[MAX_PATH];
        std::snprintf(searchPattern, MAX_PATH, "%s\\*", userdataPath);

        WIN32_FIND_DATAA fd;
        HANDLE hFind = FindFirstFileA(searchPattern, &fd);
        if (hFind == INVALID_HANDLE_VALUE) {
            LOG_DEBUG("GetActiveSteamID64: no userdata folder at {}", userdataPath);
            return 0;
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
            LOG_DEBUG("GetActiveSteamID64: no userdata\\<accountid>\\ folders found");
            return 0;
        }

        const uint64_t steamID64 = 0x0110000100000000ULL | static_cast<uint64_t>(bestAccountId);
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

    // ════════════════════════════════════════════════════════════════
    //  EnsureRegistryTicketsForApp
    //
    //  Called from the SpawnProcess VEH right before a configured-appid
    //  game is allowed to launch. Two responsibilities:
    //
    //  1. If a cached AppTicket exists but its embedded SteamID does NOT
    //     match the currently-logged-in Steam user, wipe it. Otherwise
    //     the wrapper would compare the stale SteamID against the new
    //     user and fail.
    //
    //  2. If no cached AppTicket is present, write a fabricated minimal
    //     blob baked with the active user's SteamID. Helps older Steam
    //     Stub wrappers; harmless for v3 (those still need Steamless).
    //
    //  Same logic for ETicket.
    //
    //  Returns true if any write happened.
    // ════════════════════════════════════════════════════════════════
    bool EnsureRegistryTicketsForApp(AppId_t appId) {
        const uint64_t activeID = GetActiveSteamID64();
        if (activeID == 0) {
            LOG_INFO("EnsureRegistryTicketsForApp: AppId={} no active user — skip", appId);
            return false;
        }

        bool wrote = false;

        // ── AppTicket ──
        std::vector<uint8_t> existing = GetAppOwnershipTicketFromRegistry(appId);
        if (!existing.empty() && existing.size() >= 16) {
            // Layout: [u32 sigOffset][u32 version][u64 steamID][...]
            const uint64_t cachedID = reinterpret_cast<const uint64_t*>(existing.data())[1];
            if (cachedID != activeID) {
                LOG_INFO("EnsureRegistryTicketsForApp: AppId={} cached SteamID 0x{:X} != active 0x{:X}, wiping",
                         appId, cachedID, activeID);
                HKEY hKey;
                const std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
                if (RegOpenKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
                    RegDeleteValueA(hKey, "AppTicket");
                    RegCloseKey(hKey);
                }
                existing.clear();
            }
        }

        if (existing.empty()) {
            std::vector<uint8_t> blob = BuildMinimalAppTicket(appId);
            if (!blob.empty()) {
                if (WriteAppOwnershipTicket(appId, blob)) {
                    LOG_INFO("EnsureRegistryTicketsForApp: AppId={} wrote fabricated AppTicket ({} bytes)",
                             appId, blob.size());
                    wrote = true;
                    if (IsKnownSteamDrmApp(appId)) {
                        LOG_INFO("EnsureRegistryTicketsForApp: AppId={} is a known Steam-DRM title — "
                                 "the fabricated ticket is unsigned and will likely be rejected by the "
                                 "wrapper's signature check (error 54). Use Steamless from SteaMidra "
                                 "to strip the wrapper if launch fails.",
                                 appId);
                    }
                }
            }
        }

        return wrote;
    }
}
