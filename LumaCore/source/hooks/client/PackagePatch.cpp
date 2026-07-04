// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/PackagePatch.h"
#include "hooks/Macros.h"
#include "hooks/capture/RuntimeCapture.h"
#include "core/entry.h"
#include "Steam/Callback.h"
#include "runtime/HookStatus.h"
#include "runtime/Ticket.h"

#include <limits>
#include <mutex>
#include <unordered_set>

namespace {

    using CUtlMemoryGrow_t = void* (*)(CUtlVector<AppId_t>* pVec, int grow_size);
    CUtlMemoryGrow_t oCUtlMemoryGrow = nullptr;
    std::mutex g_stubWarnLock;
    std::unordered_set<AppId_t> g_stubWarnedApps;
    std::unordered_set<AppId_t> g_ownershipPatchLoggedApps;

    // ── OnlineFix achievement-callback rewrite helpers ──────────────────────
    //
    // Steam dispatches user-stats callbacks (UserStatsReceived, UserStatsStored,
    // UserAchievementStored, UserAchievementIconFetched) keyed on the real
    // appid. Hidden-480 route games register their callback handlers under
    // appid 480 because LumaCore rewrites the spawn CGameID to 480, so the
    // game never sees those callbacks until we rewrite m_nGameID back to 480.
    //
    // The rewrite path is gated five ways:
    //   1. route   -- active manual OnlineFix or SteamStub auto route
    //   2. coarse  -- thread-local depth counter g_userStatsAppIdOverrideDepth
    //   3. fine    -- pipe-scoped g_StatsScopePipe stamped by IPCBus on the
    //                 IClientUserStats dispatch bracket
    //   4. session -- g_OnlineFixRealAppId != 0
    //   5. payload -- low 24 bits of m_nGameID equal the real appid

    constexpr int kAchievementCallbackIds[] = {
        UserStatsReceived_t::k_iCallback,
        UserStatsStored_t::k_iCallback,
        UserAchievementStored_t::k_iCallback,
        UserAchievementIconFetched_t::k_iCallback,
    };

    static bool IsAchievementCallback(int iCallback) {
        for (int id : kAchievementCallbackIds)
            if (id == iCallback) return true;
        return false;
    }

    // Rewrites m_nGameID low-24-bits from real appid back to kOnlineFixAppId
    // when the payload genuinely carries the real appid. Leaves the high 40
    // bits untouched. Returns false (without mutation) on any mismatch so the
    // caller's gating chain can short-circuit cleanly.
    static bool RewriteAchievementCallbackGameId(int iCallback, void* pCallbackData,
                                                 int cubCallbackData)
    {
        AppId_t real = SteamCapture::ActiveRouteRealAppId();
        if (real == 0 || real == kOnlineFixAppId) return false;
        if (cubCallbackData < static_cast<int>(sizeof(uint64_t))) return false;
        if (pCallbackData == nullptr) return false;

        auto* pGameId = static_cast<uint64_t*>(pCallbackData);
        AppId_t current = static_cast<AppId_t>(*pGameId & 0xFFFFFF);
        if (current != real) return false;

        *pGameId = (*pGameId & ~static_cast<uint64_t>(0xFFFFFF))
                 | static_cast<uint64_t>(kOnlineFixAppId);
        LOG_ONLINEFIX_DEBUG("achievement callback {} m_nGameID {} -> {}",
                            iCallback, real, kOnlineFixAppId);
        return true;
    }

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

    LM_HOOK(LoadPackage, bool, PackageInfo* pInfo, uint8* sha1, int32 cn, void* p4) {
        bool result = oLoadPackage(pInfo, sha1, cn, p4);

        LOG_PACKAGE_DEBUG("LoadPackage: PackageId={} AppIdVec.m_Size={}", pInfo->PackageId, pInfo->AppIdVec.m_Size);

        if (pInfo->PackageId == 0) {
            // PR-style guard: skip injection unless Steam reports the
            // package usable. injecting into a non-Available package gets
            // the vector clobbered when Steam re-loads it, and we lose
            // every fake appid. better to bail and let the post-login
            // re-injection from RuntimeCapture pick it up cleanly.
            if (pInfo->Status != EPackageStatus::Available) {
                LOG_PACKAGE_WARN("LoadPackage(PackageId=0): status={} not Available; deferring injection",
                                  static_cast<int>(pInfo->Status));
                g_pPackage0 = pInfo;
                return result;
            }
            // Save the pointer for later use by startup injection
            g_pPackage0 = pInfo;

            // Don't inject if already seeded — prevents double-injection on
            // package reload after login.
            if (g_package0Seeded.load(std::memory_order_acquire)) {
                LOG_PACKAGE_DEBUG("LoadPackage(PackageId=0): already seeded, skipping injection");
                return result;
            }

            std::vector<AppId_t> appIds = LuaLoader::GetAllDepotIds();
            if (!appIds.empty()) {
                uint32 oldSize = pInfo->AppIdVec.m_Size;
                uint32 numToAdd = static_cast<uint32>(appIds.size());
                LOG_PACKAGE_INFO("LoadPackage(PackageId=0): adding {} apps, oldSize={}", numToAdd, oldSize);
                oCUtlMemoryGrow(&pInfo->AppIdVec, numToAdd);
                AppId_t* dst = pInfo->AppIdVec.m_Memory.m_pMemory + oldSize;
                for (uint32 i = 0; i < numToAdd; i++)
                    *dst++ = appIds[i];
                pInfo->AppIdVec.m_Size = oldSize + numToAdd;
                g_package0Seeded.store(true, std::memory_order_release);
                HookStatus::SetPackageState(true, true, false, false);
            } else {
                LOG_PACKAGE_WARN("LoadPackage(PackageId=0): no Lua depots loaded yet! Lua parsing happens after hook install.");
            }
        }

        return result;
    }

    LM_HOOK(CheckAppOwnership, bool, void* pObj, AppId_t appId, AppOwnership* pOwn) {
        bool result = oCheckAppOwnership(pObj, appId, pOwn);
        if (pOwn && LuaLoader::HasDepot(appId)) {
            if (result && pOwn->ExistInPackageNums > 1
                && pOwn->ReleaseState == EAppReleaseState::Released) {
                // Actually owned — record so HasDepot excludes it going forward
                LuaLoader::MarkOwned(appId);
                LOG_PACKAGE_DEBUG("CheckAppOwnership: appId={} actually owned, marking", appId);
            } else {
                pOwn->PackageId     = 0;
                pOwn->ReleaseState  = EAppReleaseState::Released;
                pOwn->bFreeLicense  = false;
                pOwn->bOwnsLicense  = true;
                bool firstPatchLog = false;
                {
                    std::lock_guard lock(g_stubWarnLock);
                    firstPatchLog = g_ownershipPatchLoggedApps.insert(appId).second;
                }
                if (firstPatchLog) {
                    LOG_PACKAGE_INFO("CheckAppOwnership: appId={} patched -> owned (was result={} ExistInPkg={})",
                                     appId, result, pOwn->ExistInPackageNums);
                } else {
                    LOG_PACKAGE_TRACE("CheckAppOwnership: appId={} patched -> owned (repeat)",
                                      appId);
                }
                if (Ticket::IsKnownSteamDrmApp(appId)) {
                    bool first = false;
                    {
                        std::lock_guard lock(g_stubWarnLock);
                        first = g_stubWarnedApps.insert(appId).second;
                    }
                    if (first) {
                        LOG_PACKAGE_INFO("CheckAppOwnership: appId={} is a known Steam Stub title; "
                                         "normal launches use the dedicated SteamStub auto route "
                                         "when the preflight AppTicket is OK. If Steam still "
                                         "reports error 54 after that, try Remove SteamStub from SteaMidra.",
                                         appId);
                    }
                }

                return true;
            }
        }
        return result;
    }

    LM_HOOK(GetSubscribedApps, uint32_t, void* pThis, uint32_t* pAppList, uint32_t size, uint8_t unknownFlag) {
        uint32_t count = oGetSubscribedApps(pThis, pAppList, size, unknownFlag);
        std::vector<AppId_t> roots = LuaLoader::GetLibraryAppIds();
        if (roots.empty()) return count;

        uint32_t written = 0;
        uint32_t advertisedAdds = 0;
        const bool canScanOriginal = pAppList && count <= size;

        for (AppId_t appId : roots) {
            bool alreadyInList = false;
            if (canScanOriginal) {
                for (uint32_t i = 0; i < count; i++) {
                    if (pAppList[i] == appId) {
                        alreadyInList = true;
                        break;
                    }
                }
            }

            if (alreadyInList) continue;

            advertisedAdds++;
            if (pAppList && count + written < size) {
                pAppList[count + written] = appId;
                written++;
            }
        }

        uint32_t advertisedTotal = count + advertisedAdds;
        if (advertisedTotal < count) {
            advertisedTotal = (std::numeric_limits<uint32_t>::max)();
        }

        LOG_PACKAGE_INFO("GetSubscribedApps: original={}, roots={}, written={}, advertised={}, buffer={}",
                         count, roots.size(), written, advertisedTotal, size);
        return advertisedTotal;
    }

    LM_HOOK(SendCallbackToPipe, bool, void* pSteamEngine, HSteamPipe hSteamPipe,
              HSteamUser iClientUser, int iCallback, void* pCallbackData, int cubCallbackData) {
        if (iCallback == AppLicensesChanged_t::k_iCallback) {
            auto* p = static_cast<AppLicensesChanged_t*>(pCallbackData);
            LOG_PACKAGE_DEBUG("SendCallbackToPipe: AppLicensesChanged m_bReloadAll={} -> true",
                           p->m_bReloadAll);
            p->m_bReloadAll = true;
            return oSendCallbackToPipe(pSteamEngine, hSteamPipe, iClientUser,
                                       iCallback, pCallbackData, cubCallbackData);
        }

        // Achievement-callback dual-dispatch. Gating order:
        //   * route is active
        //   * iCallback in Achievement_Callback_Ids
        //   * pipe scope matches the dispatching pipe
        //   * payload large enough to carry m_nGameID
        // The first dispatch leaves the real appid in m_nGameID so any
        // real-appid binding still receives the callback. The second
        // dispatch (OnlineFix_Dual_Dispatch) flips m_nGameID's low 24 bits
        // to kOnlineFixAppId and re-emits, which is what reaches the game's
        // appid-480 callback registration. RewriteAchievementCallbackGameId
        // also covers the no-op session and pipe-mismatch paths.
        if (IsAchievementCallback(iCallback)
            && SteamCapture::StatsScopePipe() == hSteamPipe
            && SteamCapture::ActiveRouteRealAppId() != 0)
        {
            const bool firstOk = oSendCallbackToPipe(pSteamEngine, hSteamPipe, iClientUser,
                                                     iCallback, pCallbackData, cubCallbackData);
            if (RewriteAchievementCallbackGameId(iCallback, pCallbackData, cubCallbackData)) {
                LOG_ONLINEFIX_TRACE("OnlineFix_Dual_Dispatch: cb={} pipe=0x{:08X} -> appid {}",
                                    iCallback,
                                    static_cast<uint32_t>(hSteamPipe),
                                    kOnlineFixAppId);
                oSendCallbackToPipe(pSteamEngine, hSteamPipe, iClientUser,
                                    iCallback, pCallbackData, cubCallbackData);
            }
            return firstOk;
        }

        return oSendCallbackToPipe(pSteamEngine, hSteamPipe, iClientUser,
                                   iCallback, pCallbackData, cubCallbackData);
    }
}

namespace PackagePatch {
    void Install() {
        LM_BIND(CUtlMemoryGrow);

        LM_TX_BEGIN();
        LM_INSTALL(LoadPackage);
        LM_INSTALL(CheckAppOwnership);
        LM_INSTALL(GetSubscribedApps);
        LM_INSTALL(SendCallbackToPipe);
        LM_TX_COMMIT();
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(CheckAppOwnership);
        LM_REMOVE(GetSubscribedApps);
        LM_REMOVE(SendCallbackToPipe);
        LM_TX_COMMIT();
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
    //
    // Post-login MarkLicenseAsChanged reloads package 0 from server license
    // data, which clears the AppIdVec while leaving g_package0Seeded=true.
    // Check the vector size to detect this case; if it dropped below our
    // expected count, reset the flag so the injection below actually runs.
    bool InjectIntoPackage0(const std::vector<AppId_t>& appIds) {
        if (!g_pPackage0 || !oCUtlMemoryGrow || appIds.empty()) return false;
        if (g_package0Seeded.load(std::memory_order_acquire)) {
            if (g_pPackage0->AppIdVec.m_Size >= appIds.size()) {
                LOG_PACKAGE_DEBUG("InjectIntoPackage0: package 0 already seeded; skipping {} apps", appIds.size());
                return true;
            }
            LOG_PACKAGE_INFO("InjectIntoPackage0: vector was reset (size={}), re-injecting {} apps",
                             g_pPackage0->AppIdVec.m_Size, appIds.size());
            g_package0Seeded.store(false, std::memory_order_release);
        }
        PackageInfo* pPkg = g_pPackage0;
        uint32 oldSize = pPkg->AppIdVec.m_Size;
        uint32 numToAdd = static_cast<uint32>(appIds.size());
        oCUtlMemoryGrow(&pPkg->AppIdVec, numToAdd);
        AppId_t* dst = pPkg->AppIdVec.m_Memory.m_pMemory + oldSize;
        for (uint32 i = 0; i < numToAdd; i++)
            *dst++ = appIds[i];
        pPkg->AppIdVec.m_Size = oldSize + numToAdd;
        g_package0Seeded.store(true, std::memory_order_release);
        LOG_PACKAGE_INFO("InjectIntoPackage0: injected {} apps (total now {})", numToAdd, pPkg->AppIdVec.m_Size);
        return true;
    }

    PackageInfo* GetPackage0() { return g_pPackage0; }
}
