// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/ManifestBind.h"
#include "hooks/Macros.h"
#include "core/entry.h"
#include <format>
#include <mutex>
#include <string>

// hook that patches depot gid/size in the output vector after Steam builds it.
// we don't hook BIsDlcEnabled / IsAppDlcInstalled / IsCloudEnabledForApp —
// CheckAppOwnership already covers those, adding em would be redundant.

namespace ManifestBind::Internal {

    constexpr uint32_t kDepotHardCap = 8192;

    // safe window over CUtlVector<DepotEntry> — Steam's internal layout
    class DepotBank {
        CUtlVector<DepotEntry>* m_store = nullptr;
        uint32_t m_items = 0;

    public:
        explicit DepotBank(CUtlVector<DepotEntry>* store) : m_store(store) {
            if (!m_store || !m_store->m_Size) return;
            m_items = m_store->m_Size;
            if (m_items > kDepotHardCap) {
                LOG_MANBND_WARN("BuildDepotDependency: clipping count {} to {}", m_items, kDepotHardCap);
                m_items = kDepotHardCap;
            }
            if (!m_store->m_Memory.m_pMemory) {
                LOG_MANBND_ERROR("BuildDepotDependency: backing memory is null");
                m_items = 0;
            }
        }

        bool HasEntries() const { return m_items > 0; }
        uint32_t Len() const { return m_items; }
        const DepotEntry& Get(uint32_t ix) const { return m_store->m_Memory.m_pMemory[ix]; }
        DepotEntry& Mut(uint32_t ix) { return m_store->m_Memory.m_pMemory[ix]; }

        std::string DumpEntry(uint32_t ix) const {
            const auto& e = Get(ix);
            return std::format("[DepotId={} | AppId={} | Gid={} | Size={} | Dlc={} | Lcs={} | Carry={} | Shared={}]",
                e.DepotId, e.AppId, e.ManifestGid, e.ManifestSize, e.DlcAppId,
                (int)e.LcsRequired, (int)e.bNotNewTarget, (int)e.SharedInstall);
        }
    };

    // walk the depot list and slap in any overrides from lua config
    static void SlapManifestOverrides(DepotBank& bank) {
        if (!bank.HasEntries()) return;
        const auto& overrides = LuaLoader::GetManifestOverrides();
        if (overrides.empty()) return;

        static std::once_flag s_once;
        std::call_once(s_once, [&]() {
            LOG_MANBND_INFO("manifest-map-dump size={}", static_cast<uint32_t>(overrides.size()));
            for (const auto& [k, v] : overrides)
                LOG_MANBND_INFO("manifest-map-entry depot={} gid={}", k, v.gid);
        });

        uint32_t idx = 0;
        while (idx < bank.Len()) {
            uint64_t key = static_cast<uint64_t>(bank.Get(idx).DepotId);
            auto it = overrides.find(key);
            if (it != overrides.end()) {
                uint64_t newSz = it->second.size ? it->second.size : bank.Get(idx).ManifestSize;
                LOG_MANBND_INFO("manifest-override depot={} gid={}->{} size={}->{}",
                    bank.Get(idx).DepotId, bank.Get(idx).ManifestGid, it->second.gid,
                    bank.Get(idx).ManifestSize, newSz);
                bank.Mut(idx).ManifestGid  = it->second.gid;
                bank.Mut(idx).ManifestSize = newSz;
            } else {
                LOG_MANBND_INFO("manifest-scan depot={} gid={} appid={} size={} mapSize={}",
                    bank.Get(idx).DepotId, bank.Get(idx).ManifestGid,
                    bank.Get(idx).AppId, bank.Get(idx).ManifestSize,
                    static_cast<uint32_t>(overrides.size()));
            }
            ++idx;
        }
    }

} // namespace ManifestBind::Internal

namespace {
    using ManifestBind::Internal::DepotBank;
    using ManifestBind::Internal::SlapManifestOverrides;

    LM_HOOK(BuildDepotDependency, bool, void* pUserAppMgr, AppId_t AppId,
              void* pUserConfig, CUtlVector<DepotEntry>* pDepotInfo,
              CUtlVector<DepotEntry>* pSharedDepotInfo, void* pSteamApp,
              uint32_t* pBuildId, bool* pbBetaFallback)
    {
        bool ok = oBuildDepotDependency(pUserAppMgr, AppId, pUserConfig,
            pDepotInfo, pSharedDepotInfo, pSteamApp, pBuildId, pbBetaFallback);

        if (pDepotInfo) {
            DepotBank db(pDepotInfo);
            LOG_MANBND_TRACE("BuildDepotDependency appid={} depots={} ok={}", AppId, db.Len(), ok);
            if (ok) SlapManifestOverrides(db);
        }
        return ok;
    }

} // anonymous namespace

namespace ManifestBind {

    void Install() {
        LM_TX_BEGIN();
        LM_INSTALL(BuildDepotDependency);
        LM_TX_COMMIT();
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(BuildDepotDependency);
        LM_TX_COMMIT();
    }
}
