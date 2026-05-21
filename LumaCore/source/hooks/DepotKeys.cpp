#include "DepotKeys.h"
#include "Macros.h"
#include "entry.h"
#include <string>

namespace {
    LC_HOOK_DEF(LoadDepotDecryptionKey, int32, void* pObject, uint32 foo,char* KeyName, char* Key, uint32 KeySize) {
        std::string name(KeyName);
        LOG_DECRYPTIONKEY_DEBUG("LoadDepotDecryptionKey called for KeyName='{}'", name);
        // Expected shape: ".../<DepotId>\DecryptionKey"
        if (size_t last = name.find("\\DecryptionKey"); last != std::string::npos) {
            if (size_t start = name.find_last_of("\\", last - 1); start != std::string::npos) {
                AppId_t depotId = std::stoul(name.substr(start + 1, last - start - 1));
                if (const auto& key = LuaLoader::GetDecryptionKey(depotId); !key.empty()) {
                    if (KeySize >= key.size()) {
                        LOG_DECRYPTIONKEY_INFO("Providing decryption key for depot {}: {}", depotId,
                                               spdlog::to_hex(key.data(), key.data() + key.size()));
                        memcpy(Key, key.data(), key.size());
                        return static_cast<int32>(key.size());
                    }
                    LOG_DECRYPTIONKEY_WARN("Decryption key for depot {} is too large ({} bytes) for buffer ({} bytes)",
                                            depotId, key.size(), KeySize);
                }
            }
        }
        return oLoadDepotDecryptionKey(pObject, foo, KeyName, Key, KeySize);
    }
}

namespace DepotKeys {
    void Install() {
        LC_TX_OPEN();
        LC_ATTACH_D(LoadDepotDecryptionKey);
        LC_TX_COMMIT();
    }

    void Uninstall() {
        LC_TX_OPEN();
        LC_DETACH(LoadDepotDecryptionKey);
        LC_TX_COMMIT();
    }
}
