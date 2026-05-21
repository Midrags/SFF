#include "ManifestBind.h"
#include "Macros.h"
#include "entry.h"
#include <format>
#include <string>

// ═══════════════════════════════════════════════════════════════════
//  Manifest override hooks:
//    BuildDepotDependency — patches depot entries' gid/size directly
//      in the output vector.
// ═══════════════════════════════════════════════════════════════════
namespace {

    // ── helper ─────────────────────────────────────────────────────

    std::string DepotStr(const DepotEntry& e) {
        return std::format("[DepotId={} | AppId={} | Gid={} | Size={} | Dlc={} | Lcs={} | Carry={} | Shared={}]",
            e.DepotId, e.AppId, e.ManifestGid, e.ManifestSize, e.DlcAppId,
            (int)e.LcsRequired, (int)e.bNotNewTarget, (int)e.SharedInstall);
    }

    // ── BuildDepotDependency hook ──────────────────────────────────
    // After Steam builds the depot list for an app, patch ManifestGid
    // and ManifestSize for any depots we have overrides for.

    LC_HOOK_DEF(BuildDepotDependency, bool, void* pUserAppMgr, AppId_t AppId,
              void* pUserConfig, CUtlVector<DepotEntry>* pDepotInfo,
              CUtlVector<DepotEntry>* pSharedDepotInfo, void* pSteamApp,
              uint32* pBuildId, bool* pbBetaFallback)
    {
        bool result = oBuildDepotDependency(pUserAppMgr, AppId, pUserConfig,
            pDepotInfo, pSharedDepotInfo, pSteamApp, pBuildId, pbBetaFallback);

        LOG_MANIFEST_TRACE("BuildDepotDependency: AppId={} pUserConfig=0x{:X} result={} pSteamApp=0x{:X} pBuildId={} pbBetaFallback={}",
            AppId, (uintptr_t)pUserConfig, result, (uintptr_t)pSteamApp,
            pBuildId ? *pBuildId : 0, pbBetaFallback ? *pbBetaFallback : false);
        if (pDepotInfo) {
            LOG_MANIFEST_TRACE("pDepotInfo->nCount={}", pDepotInfo->m_Size);
            const DepotEntry* dBase = pDepotInfo->m_Memory.m_pMemory;
            for (uint32 n = 0; n < pDepotInfo->m_Size; ++n)
                LOG_MANIFEST_TRACE("  [{}] {}", n, DepotStr(dBase[n]));
        }
        if (pSharedDepotInfo) {
            LOG_MANIFEST_TRACE("pSharedDepotInfo->nCount={}", pSharedDepotInfo->m_Size);
            const DepotEntry* sBase = pSharedDepotInfo->m_Memory.m_pMemory;
            for (uint32 n = 0; n < pSharedDepotInfo->m_Size; ++n)
                LOG_MANIFEST_TRACE("  shared[{}] {}", n, DepotStr(sBase[n]));
        }

        if (!result) return result;

        const auto& overrides = LuaLoader::GetManifestOverrides();
        if (overrides.empty()) return result;

        if (pDepotInfo && pDepotInfo->m_Size) {
            DepotEntry* pBegin = pDepotInfo->m_Memory.m_pMemory;
            DepotEntry* pEnd   = pBegin + pDepotInfo->m_Size;
            for (DepotEntry* ep = pBegin; ep != pEnd; ++ep) {
                auto it = overrides.find(ep->DepotId);
                if (it != overrides.end()) {
                    // if size=0 in the override, keep the original size(affects download display but not the actual download)
                    uint64_t newSize = it->second.size ? it->second.size : ep->ManifestSize;
                    LOG_MANIFEST_INFO("BuildDepotDependency: patching depot {} gid={}->{} size={}->{}",
                        ep->DepotId, ep->ManifestGid, it->second.gid,
                        ep->ManifestSize, newSize);
                    ep->ManifestGid  = it->second.gid;
                    ep->ManifestSize = newSize;
                }
            }
        }
        return result;
    }

} // anonymous namespace

namespace ManifestBind {

    void Install() {
        LC_TX_OPEN();
        LC_ATTACH_D(BuildDepotDependency);
        LC_TX_COMMIT();
    }

    void Uninstall() {
        LC_TX_OPEN();
        LC_DETACH(BuildDepotDependency);
        LC_TX_COMMIT();
    }
}
