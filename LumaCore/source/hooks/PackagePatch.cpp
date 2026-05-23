#include "PackagePatch.h"
#include "Macros.h"
#include "entry.h"
#include "utils/Ticket.h"

namespace {
    using CUtlMemoryGrow_t = void* (*)(CUtlVector<AppId_t>* pVec, int grow_size);
    CUtlMemoryGrow_t oCUtlMemoryGrow = nullptr;

    // Saved pointer to package 0's PackageInfo — captured from LoadPackage hook.
    // Used by DoStartupInjection to inject apps after hooks are fully installed.
    static PackageInfo* g_pPackage0 = nullptr;

    // Set to true once LoadPackage has injected our depot list into package 0.
    // Used by InjectIntoPackage0 to suppress redundant re-injection from
    // DoStartupInjection — re-injecting causes each AppId to appear twice in
    // package 0's vector, which makes Steam report ExistInPackageNums >= 2 for
    // fake-owned apps, which makes CheckAppOwnership think the user genuinely
    // owns them, which makes HasDepot return false, which breaks every
    // downstream feature (achievements, ownership patching, manifest binding).
    static std::atomic<bool> g_package0Seeded{false};

    LC_HOOK_DEF(LoadPackage, bool, PackageInfo* pInfo, uint8* sha1, int32 cn, void* p4) {
        bool result = oLoadPackage(pInfo, sha1, cn, p4);

        LOG_PACKAGE_DEBUG("LoadPackage: PackageId={} AppIdVec.m_Size={}", pInfo->PackageId, pInfo->AppIdVec.m_Size);

        if (pInfo->PackageId == 0) {
            // Save the pointer for later use by startup injection
            g_pPackage0 = pInfo;

            std::vector<AppId_t> appIds = LuaLoader::GetAllDepotIds();
            if (!appIds.empty()) {
                uint32 oldSize = pInfo->AppIdVec.m_Size;
                uint32 numToAdd = static_cast<uint32>(appIds.size());
                LOG_PACKAGE_INFO("LoadPackage(PackageId=0): adding {} apps, oldSize={}", numToAdd, oldSize);
                oCUtlMemoryGrow(&pInfo->AppIdVec, numToAdd);
                for (uint32 i = 0; i < numToAdd; i++)
                    pInfo->AppIdVec.m_Memory.m_pMemory[oldSize + i] = appIds[i];
                pInfo->AppIdVec.m_Size = oldSize + numToAdd;
                g_package0Seeded.store(true, std::memory_order_release);
            } else {
                LOG_PACKAGE_WARN("LoadPackage(PackageId=0): no Lua depots loaded yet! Lua parsing happens after hook install.");
            }
        }

        return result;
    }

    LC_HOOK_DEF(CheckAppOwnership, bool, void* pObj, AppId_t appId, AppOwnership* pOwn) {
        bool result = oCheckAppOwnership(pObj, appId, pOwn);
        if (pOwn && LuaLoader::HasDepot(appId)) {
            if (result && pOwn->ExistInPackageNums > 1
                && pOwn->ReleaseState == EAppReleaseState::Released) {
                // Actually owned — record so HasDepot excludes it going forward
                LuaLoader::MarkOwned(appId);
                LOG_PACKAGE_DEBUG("CheckAppOwnership: appId={} actually owned, marking", appId);
            } else {
                pOwn->PackageId    = 0;
                pOwn->ReleaseState = EAppReleaseState::Released;
                pOwn->bFreeLicense = false;
                LOG_PACKAGE_INFO("CheckAppOwnership: appId={} patched -> owned (was result={} ExistInPkg={})",
                                  appId, result, pOwn->ExistInPackageNums);
                // Diagnostic only: titles known to use Steam DRM (Steam Stub)
                // can still fail at launch with error 54 even after we patch
                // ownership, because the wrapper does its own registry-based
                // ticket check. Log once per patch so users with launch
                // failures know what to try.
                if (Ticket::IsKnownSteamDrmApp(appId)) {
                    LOG_PACKAGE_INFO("CheckAppOwnership: appId={} is a known Steam-DRM (Steam Stub) "
                                     "title. If launch fails with error 54, try Remove SteamStub "
                                     "(Steamless) from SteaMidra — ownership patching alone is not "
                                     "enough for the wrapper's local ticket check.",
                                     appId);
                }
                return true;
            }
        }
        return result;
    }

    LC_HOOK_DEF(SendCallbackToPipe, bool, void* pSteamEngine, HSteamPipe hSteamPipe,
              HSteamUser iClientUser, int iCallback, void* pCallbackData, int cubCallbackData) {
        if (iCallback == AppLicensesChanged_t::k_iCallback) {
            auto* p = static_cast<AppLicensesChanged_t*>(pCallbackData);
            LOG_PACKAGE_DEBUG("SendCallbackToPipe: AppLicensesChanged m_bReloadAll={} -> true",
                           p->m_bReloadAll);
            p->m_bReloadAll = true;
        }

        return oSendCallbackToPipe(pSteamEngine, hSteamPipe, iClientUser,
                                   iCallback, pCallbackData, cubCallbackData);
    }
}

namespace PackagePatch {
    void Install() {
        LC_RESOLVE_D(CUtlMemoryGrow);

        LC_TX_OPEN();
        LC_ATTACH_D(LoadPackage);
        LC_ATTACH_D(CheckAppOwnership);
        LC_ATTACH_D(SendCallbackToPipe);
        LC_TX_COMMIT();
    }

    void Uninstall() {
        LC_TX_OPEN();
        LC_DETACH(LoadPackage);
        LC_DETACH(CheckAppOwnership);
        LC_DETACH(SendCallbackToPipe);
        LC_TX_COMMIT();
        oCUtlMemoryGrow = nullptr;
        g_pPackage0 = nullptr;
        g_package0Seeded.store(false, std::memory_order_release);
    }

    // Inject all currently loaded Lua app IDs into package 0.
    // Called from RuntimeCapture after MarkLicenseAsChanged fires (post-login).
    // At that point g_pPackage0 is set and oCUtlMemoryGrow is resolved.
    //
    // Early-out when LoadPackage already seeded the vector at process start —
    // injecting the same set twice doubles ExistInPackageNums for every app
    // and breaks ownership detection.  This branch only matters when Lua
    // parsing finished after the LoadPackage hook fired (race at startup).
    bool InjectIntoPackage0(const std::vector<AppId_t>& appIds) {
        if (!g_pPackage0 || !oCUtlMemoryGrow || appIds.empty()) return false;
        if (g_package0Seeded.load(std::memory_order_acquire)) {
            LOG_PACKAGE_DEBUG("InjectIntoPackage0: package 0 already seeded by LoadPackage; skipping {} apps", appIds.size());
            return true;
        }
        PackageInfo* pPkg = g_pPackage0;
        uint32 oldSize = pPkg->AppIdVec.m_Size;
        uint32 numToAdd = static_cast<uint32>(appIds.size());
        oCUtlMemoryGrow(&pPkg->AppIdVec, numToAdd);
        for (uint32 i = 0; i < numToAdd; i++)
            pPkg->AppIdVec.m_Memory.m_pMemory[oldSize + i] = appIds[i];
        pPkg->AppIdVec.m_Size = oldSize + numToAdd;
        g_package0Seeded.store(true, std::memory_order_release);
        LOG_PACKAGE_INFO("InjectIntoPackage0: injected {} apps (total now {})", numToAdd, pPkg->AppIdVec.m_Size);
        return true;
    }

    PackageInfo* GetPackage0() { return g_pPackage0; }
}
