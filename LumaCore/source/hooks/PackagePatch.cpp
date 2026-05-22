#include "PackagePatch.h"
#include "Macros.h"
#include "entry.h"

namespace {
    using CUtlMemoryGrow_t = void* (*)(CUtlVector<AppId_t>* pVec, int grow_size);
    CUtlMemoryGrow_t oCUtlMemoryGrow = nullptr;

    LC_HOOK_DEF(LoadPackage, bool, PackageInfo* pInfo, uint8* sha1, int32 cn, void* p4) {
        bool result = oLoadPackage(pInfo, sha1, cn, p4);

        if (pInfo->PackageId == 0) {
            std::vector<AppId_t> appIds = LuaLoader::GetAllDepotIds();
            if (!appIds.empty()) {
                uint32 oldSize = pInfo->AppIdVec.m_Size;
                uint32 numToAdd = static_cast<uint32>(appIds.size());
                LOG_PACKAGE_INFO("LoadPackage(PackageId=0): adding {} apps, oldSize={}", numToAdd, oldSize);
                oCUtlMemoryGrow(&pInfo->AppIdVec, numToAdd);
                for (uint32 i = 0; i < numToAdd; i++)
                    pInfo->AppIdVec.m_Memory.m_pMemory[oldSize + i] = appIds[i];
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
            } else {
                pOwn->PackageId    = 0;
                pOwn->ReleaseState = EAppReleaseState::Released;
                pOwn->bFreeLicense = false;
                return true;
            }
        }
        return result;
    }

    LC_HOOK_DEF(SendCallbackToPipe, bool, void* pSteamEngine, HSteamPipe hSteamPipe,
              HSteamUser iClientUser, int iCallback, void* pCallbackData, int cubCallbackData) {
        if (iCallback == AppLicensesChanged_t::k_iCallback) {
            auto* p = static_cast<AppLicensesChanged_t*>(pCallbackData);
            LOG_PACKAGE_DEBUG("SendCallbackToPipe: AppLicensesChanged m_bReloadAll={}",
                           p->m_bReloadAll);
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
    }
}
