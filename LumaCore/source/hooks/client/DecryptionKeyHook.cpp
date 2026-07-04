// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "DecryptionKeyHook.h"
#include "hooks/Macros.h"
#include "core/entry.h"
#include "config/LuaLoader.h"

namespace {

    void* g_configStoreObj = nullptr;

    static void CaptureStoreObj(void* pObject, EConfigStore storeType) {
        if (pObject && !g_configStoreObj && storeType == k_EConfigStoreUserLocal) {
            g_configStoreObj = pObject;
            LOG_DECRYPTIONKEYCH_INFO("captured user-local ConfigStore store={} object=0x{:X}",
                                     static_cast<int32>(storeType),
                                     reinterpret_cast<uint64_t>(pObject));
        }
    }

    // intercept depot decryption key fetches. if steam asks for a key we
    // know about, slap the hex blob directly into the output buffer.
    LM_HOOK(ConfigStoreGetBinary, int32, void* pObject, EConfigStore eConfigStore, const char* KeyName, char* Key, uint32 KeySize)
    {
        CaptureStoreObj(pObject, eConfigStore);

        if (!KeyName)
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, Key, KeySize);

        const char* marker = strstr(KeyName, "\\DecryptionKey");
        if (!marker)
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, Key, KeySize);

        // walk backwards to find the depot number segment
        const char* seg = marker;
        while (seg > KeyName && seg[-1] != '\\')
            --seg;
        if (seg == KeyName)
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, Key, KeySize);

        char* end = nullptr;
        AppId_t depotId = static_cast<AppId_t>(strtoull(seg, &end, 10));
        if (!end || end != marker || depotId == 0)
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, Key, KeySize);

        const auto& hexKey = LuaLoader::GetDecryptionKey(depotId);
        if (hexKey.empty())
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, Key, KeySize);

        if (hexKey.size() > KeySize) {
            LOG_DECRYPTIONKEYCH_WARN("depot {} key won't fit ({} > {})", depotId, hexKey.size(), KeySize);
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, Key, KeySize);
        }

        memcpy(Key, hexKey.data(), hexKey.size());
        LOG_DECRYPTIONKEYCH_INFO("fed key for depot {} ({} bytes)", depotId, hexKey.size());
        return static_cast<int32>(hexKey.size());
    }

    std::vector<uint8_t> PullConfigStoreBlob(const std::string& keyName) {
        if (!g_configStoreObj || !oConfigStoreGetBinary) {
            LOG_DECRYPTIONKEYCH_WARN("PullConfigStoreBlob: no object or original, can't read binary");
            return {};
        }

        std::vector<uint8_t> blob(1024);
        int32 got = oConfigStoreGetBinary(g_configStoreObj, k_EConfigStoreUserLocal,
                                          keyName.c_str(),
                                          reinterpret_cast<char*>(blob.data()),
                                          static_cast<uint32>(blob.size()));
        if (got <= 0) {
            LOG_DECRYPTIONKEYCH_DEBUG("PullConfigStoreBlob: empty read for '{}'", keyName);
            return {};
        }

        blob.resize(got);
        LOG_DECRYPTIONKEYCH_DEBUG("PullConfigStoreBlob: '{}' -> {} bytes", keyName, got);
        return blob;
    }

}

namespace DecryptionKeyHook {

    void Install() {
        LM_TX_BEGIN();
        LM_INSTALL(ConfigStoreGetBinary);
        LM_TX_COMMIT();
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(ConfigStoreGetBinary);
        LM_TX_COMMIT();
        g_configStoreObj = nullptr;
    }

    std::vector<uint8_t> GetCachedAppTicket(AppId_t appId) {
        // try ConfigStore first (fast when hook is live)
        std::string csKey = "apptickets\\" + std::to_string(appId);
        std::vector<uint8_t> ticket = PullConfigStoreBlob(csKey);
        if (!ticket.empty()) {
            LOG_DECRYPTIONKEYCH_DEBUG("cached ticket for AppId {} via CS ({} bytes)", appId, ticket.size());
            return ticket;
        }

        // ConfigStore can miss early in boot. Registry is the backup for
        // tickets Steam already wrote under the user.
        HKEY hKey;
        std::string regPath = "Software\\Valve\\Steam\\Apps\\" + std::to_string(appId);
        if (RegOpenKeyExA(HKEY_CURRENT_USER, regPath.c_str(), 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
            std::vector<uint8_t> regVal(1024 * 1024);
            DWORD cb = static_cast<DWORD>(regVal.size());
            DWORD vt = 0;
            LSTATUS st = RegQueryValueExA(hKey, "AppTicket", nullptr, &vt, regVal.data(), &cb);
            RegCloseKey(hKey);
            if (st == ERROR_SUCCESS && vt == REG_BINARY && cb > 0) {
                regVal.resize(cb);
                LOG_DECRYPTIONKEYCH_INFO("cached ticket for AppId {} from registry ({} bytes)", appId, cb);
                return regVal;
            }
        }

        LOG_DECRYPTIONKEYCH_DEBUG("no cached ticket for AppId {}", appId);
        return {};
    }

}
