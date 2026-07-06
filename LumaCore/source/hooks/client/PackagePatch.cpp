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

#include <atomic>
#include <limits>
#include <mutex>
#include <unordered_set>

namespace {

    using CUtlMemoryGrow_t = void* (*)(CUtlVector<AppId_t>* pVec, int grow_size);
    CUtlMemoryGrow_t oCUtlMemoryGrow = nullptr;
    std::mutex g_stubWarnLock;
    std::unordered_set<AppId_t> g_stubWarnedApps;
    std::unordered_set<AppId_t> g_ownershipPatchLoggedApps;
    std::atomic<bool> g_package0Seeded{false};
    std::atomic<bool> g_packagePatchInstalled{false};

    struct PackageContainmentResult {
        uint64_t expected = 0;
        uint64_t present = 0;
        uint64_t missing = 0;
        uint64_t appended = 0;
        uint32_t total = 0;
        bool ok = false;
    };

    bool PackageVectorContains(PackageInfo* pPkg, AppId_t appId) {
        if (!pPkg || !pPkg->AppIdVec.m_Memory.m_pMemory) return false;
        AppId_t* data = pPkg->AppIdVec.m_Memory.m_pMemory;
        for (uint32_t i = 0; i < pPkg->AppIdVec.m_Size; ++i) {
            if (data[i] == appId) return true;
        }
        return false;
    }

    PackageContainmentResult EnsurePackageContains(PackageInfo* pPkg,
                                                   const std::vector<AppId_t>& appIds,
                                                   const char* reason) {
        PackageContainmentResult out{};
        out.total = pPkg ? pPkg->AppIdVec.m_Size : 0;
        const char* safeReason = reason ? reason : "package0";

        std::unordered_set<AppId_t> seen;
        std::vector<AppId_t> missingIds;
        seen.reserve(appIds.size());
        missingIds.reserve(appIds.size());

        for (AppId_t id : appIds) {
            if (!id || !seen.insert(id).second) continue;
            ++out.expected;
            if (PackageVectorContains(pPkg, id)) {
                ++out.present;
            } else {
                missingIds.push_back(id);
            }
        }

        if (!pPkg) {
            out.missing = missingIds.size();
            LOG_PACKAGE_WARN("Package0Containment: reason={} package0=null expected={} present={} missing={} appended=0 status=-1",
                             safeReason, out.expected, out.present, out.missing);
            HookStatus::RecordPackageContainment(-1, 0, out.expected, out.present,
                                                 out.missing, 0, safeReason);
            return out;
        }

        if (pPkg->Status != EPackageStatus::Available) {
            out.missing = missingIds.size();
            LOG_PACKAGE_WARN(
                "Package0Containment: reason={} status={} expected={} present={} missing={} appended=0 total={} not-available",
                safeReason, static_cast<int>(pPkg->Status), out.expected,
                out.present, out.missing, pPkg->AppIdVec.m_Size);
            HookStatus::RecordPackageContainment(static_cast<int32_t>(pPkg->Status),
                                                 pPkg->AppIdVec.m_Size, out.expected,
                                                 out.present, out.missing, 0,
                                                 safeReason);
            return out;
        }

        if (!missingIds.empty()) {
            if (!oCUtlMemoryGrow) {
                out.missing = missingIds.size();
                LOG_PACKAGE_WARN(
                    "Package0Containment: reason={} status={} expected={} present={} missing={} appended=0 total={} grow-missing",
                    safeReason, static_cast<int>(pPkg->Status), out.expected,
                    out.present, out.missing, pPkg->AppIdVec.m_Size);
                HookStatus::RecordPackageContainment(static_cast<int32_t>(pPkg->Status),
                                                     pPkg->AppIdVec.m_Size, out.expected,
                                                     out.present, out.missing, 0,
                                                     safeReason);
                return out;
            }

            const uint32_t oldSize = pPkg->AppIdVec.m_Size;
            const uint32_t numToAdd = static_cast<uint32_t>(missingIds.size());
            oCUtlMemoryGrow(&pPkg->AppIdVec, numToAdd);
            AppId_t* dst = pPkg->AppIdVec.m_Memory.m_pMemory + oldSize;
            for (AppId_t id : missingIds) {
                *dst++ = id;
            }
            pPkg->AppIdVec.m_Size = oldSize + numToAdd;
            out.appended = numToAdd;
            out.total = pPkg->AppIdVec.m_Size;
        }

        out.missing = missingIds.size() - out.appended;
        out.ok = out.missing == 0;
        g_package0Seeded.store(out.ok, std::memory_order_release);
        LOG_PACKAGE_INFO(
            "Package0Containment: reason={} status={} expected={} present={} missing={} appended={} total={}",
            safeReason, static_cast<int>(pPkg->Status), out.expected,
            out.present, out.missing, out.appended, pPkg->AppIdVec.m_Size);
        HookStatus::RecordPackageContainment(static_cast<int32_t>(pPkg->Status),
                                             pPkg->AppIdVec.m_Size, out.expected,
                                             out.present, out.missing,
                                             out.appended, safeReason);
        return out;
    }

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
    // Used by retryable startup injection after hooks are fully installed.
    static PackageInfo* g_pPackage0 = nullptr;

    // Set to true once LoadPackage has injected our depot list into package 0.
    // Used by InjectIntoPackage0 to suppress redundant re-injection from
    // startup retry. Re-injecting causes each AppId to appear twice in
    // package 0's vector, which makes Steam report ExistInPackageNums >= 2 for
    // fake-owned apps, which makes CheckAppOwnership think the user genuinely
    // owns them, which makes HasDepot return false, which breaks every
    // downstream feature (achievements, ownership patching, manifest binding).
    LM_HOOK(LoadPackage, bool, PackageInfo* pInfo, uint8* sha1, int32 cn, void* p4) {
        bool result = oLoadPackage(pInfo, sha1, cn, p4);

        LOG_PACKAGE_DEBUG("LoadPackage: PackageId={} AppIdVec.m_Size={}", pInfo->PackageId, pInfo->AppIdVec.m_Size);

        if (pInfo->PackageId == 0) {
            std::vector<AppId_t> appIds = LuaLoader::GetAllDepotIds();
            HookStatus::RecordPackage0Seen(static_cast<int32_t>(pInfo->Status),
                                           pInfo->AppIdVec.m_Size,
                                           static_cast<uint32_t>(appIds.size()));
            // Save the pointer for later use by startup injection
            g_pPackage0 = pInfo;
            HookStatus::RecordPackage0Capture("loadpackage", !appIds.empty());

            if (!appIds.empty()) {
                const auto containment = EnsurePackageContains(pInfo, appIds, "loadpackage");
                HookStatus::SetPackageState(true, containment.ok, false, false);
            } else {
                LOG_PACKAGE_WARN("LoadPackage(PackageId=0): no Lua depots loaded yet! Lua parsing happens after hook install.");
            }
        }

        return result;
    }

    LM_HOOK(CheckAppOwnership, bool, void* pObj, AppId_t appId, AppOwnership* pOwn) {
        bool result = oCheckAppOwnership(pObj, appId, pOwn);
        if (pOwn && LuaLoader::HasDepot(appId)) {
            const auto originalReleaseState = pOwn->ReleaseState;
            const auto originalExistInPackageNums = pOwn->ExistInPackageNums;
            const bool originalBorrowed = pOwn->bBorrowed;
            const bool originalFamilyShared = pOwn->bFamilyShared;
            const bool released = originalReleaseState == EAppReleaseState::Released;
            const bool steamProvided = result && originalExistInPackageNums > 1 && released;
            const bool familyShared = steamProvided && (originalBorrowed || originalFamilyShared);
            if (result && originalExistInPackageNums > 1
                && released) {
                if (familyShared) {
                    LuaLoader::MarkFamilyShared(appId);
                } else {
                    LuaLoader::MarkOwned(appId);
                }
                HookStatus::RecordOwnershipCheck(
                    appId, false, !familyShared, familyShared,
                    static_cast<int32_t>(originalReleaseState),
                    originalExistInPackageNums, originalBorrowed, originalFamilyShared);
                LOG_PACKAGE_DEBUG(
                    "CheckAppOwnership: appId={} steam-provided class={} result={} ExistInPkg={} ReleaseState={} borrowed={} familyShared={}",
                    appId, familyShared ? "family-shared" : "owned", result,
                    originalExistInPackageNums, static_cast<int>(originalReleaseState),
                    originalBorrowed, originalFamilyShared);
            } else {
                HookStatus::RecordOwnershipCheck(
                    appId, true, false, false,
                    static_cast<int32_t>(originalReleaseState),
                    originalExistInPackageNums, originalBorrowed, originalFamilyShared);
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
                    LOG_PACKAGE_INFO(
                        "CheckAppOwnership: appId={} patched -> owned (was result={} ExistInPkg={} ReleaseState={} borrowed={} familyShared={})",
                        appId, result, originalExistInPackageNums,
                        static_cast<int>(originalReleaseState),
                        originalBorrowed, originalFamilyShared);
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
        if (roots.empty()) {
            HookStatus::RecordSubscribedApps(count, roots.size(), 0, count, size);
            return count;
        }

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
        HookStatus::RecordSubscribedApps(count, roots.size(), written, advertisedTotal, size);
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
        if (g_packagePatchInstalled.exchange(true, std::memory_order_acq_rel))
            return;

        LM_BIND(CUtlMemoryGrow);

        LM_TX_BEGIN();
        LM_INSTALL(LoadPackage);
        LM_INSTALL(CheckAppOwnership);
        LM_INSTALL(GetSubscribedApps);
        LM_INSTALL(SendCallbackToPipe);
        LM_TX_COMMIT();
    }

    void Uninstall() {
        if (!g_packagePatchInstalled.exchange(false, std::memory_order_acq_rel))
            return;

        LM_TX_BEGIN();
        LM_REMOVE(LoadPackage);
        LM_REMOVE(CheckAppOwnership);
        LM_REMOVE(GetSubscribedApps);
        LM_REMOVE(SendCallbackToPipe);
        LM_TX_COMMIT();
        oCUtlMemoryGrow = nullptr;
        g_pPackage0 = nullptr;
        g_package0Seeded.store(false, std::memory_order_release);
    }

    bool InjectIntoPackage0(const std::vector<AppId_t>& appIds, const char* reason) {
        return InjectIntoPackage0(g_pPackage0, appIds, reason);
    }

    bool InjectIntoPackage0(PackageInfo* pPkg, const std::vector<AppId_t>& appIds,
                            const char* reason) {
        if (!pPkg) {
            LOG_PACKAGE_DEBUG("InjectIntoPackage0: package 0 not captured yet (reason={})",
                              reason ? reason : "package0");
            return false;
        }
        bool firstCapture = g_pPackage0 == nullptr;
        g_pPackage0 = pPkg;
        if (firstCapture)
            HookStatus::RecordPackage0Capture(reason ? reason : "inject", !appIds.empty());
        if (appIds.empty()) {
            HookStatus::RecordPackageContainment(static_cast<int32_t>(pPkg->Status),
                                                 pPkg->AppIdVec.m_Size, 0, 0, 0, 0,
                                                 reason ? reason : "package0-empty");
            LOG_PACKAGE_INFO("InjectIntoPackage0: no Lua app ids to inject (reason={})",
                             reason ? reason : "package0-empty");
            return true;
        }
        return EnsurePackageContains(pPkg, appIds, reason).ok;
    }

    PackageInfo* GetPackage0() { return g_pPackage0; }
}
