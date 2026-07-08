// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/LicenseHooks.h"

#include "hooks/Macros.h"
#include "hooks/capture/RuntimeCapture.h"
#include "core/entry.h"
#include "config/LuaLoader.h"
#include "runtime/HookStatus.h"

#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <string_view>
#include <unordered_set>
#include <vector>

// LicenseHooks owns two steamclient surfaces:
//
//   * OptedInMask         -> CSteamController opt-in mask. The game asks
//                            through 480 on route launches, but controller
//                            setup still belongs to the real app.
//
//   * RequiresLegacyCDKey -> Steam asks the wrapper for a CD key on a small
//                            set of pre-2010 titles when ownership crosses
//                            certain code paths. For Lua-tracked appids the
//                            owner doesn't have a real key, so returning
//                            false short-circuits the legacy-key prompt.
//
//   * IsCloudEnabledForApp -> managed Lua apps keep Steam's native cloud
//                             out of the save path. Family-shared Lua roots
//                             get cloud back because Steam already provides
//                             the license and saves belong to that account.
//
// DLC ownership / install / license-update / ownership-ticket queries
// (BIsDlcEnabled, IsAppDlcInstalled, BUpdateLicenses,
// BUpdateAppOwnershipTicket) are still NOT hooked here. Steam already
// returns the right answer for Lua-tracked appids through CheckAppOwnership,
// so detouring those surfaces is redundant and risks x64 fastcall crashes.
//
// The unused patterns still ride in the per-build TOML so a future narrow
// hook can resolve them without changing the cache layout.

namespace {

    std::mutex g_cloudLogLock;
    std::unordered_set<AppId_t> g_cloudBlockedLoggedApps;
    std::unordered_set<AppId_t> g_cloudFamilyAllowedLoggedApps;
    std::unordered_set<std::uint64_t> g_cloudSyncBlockedLogged;

    struct CloudPolicy {
        bool tracked = false;
        bool managed = false;
        bool owned = false;
        bool familyShared = false;
        bool block = false;
        const char* ownershipClass = "untracked";
    };

    const char* CloudOwnershipClass(bool tracked, bool managed, bool owned, bool familyShared) {
        if (familyShared) return "family-shared";
        if (owned) return "steam-provided";
        if (managed) return "managed-unowned";
        if (tracked) return "lua-tracked";
        return "untracked";
    }

    CloudPolicy GetCloudPolicy(AppId_t appId) {
        CloudPolicy policy{};
        policy.managed = LuaLoader::HasDepot(appId);
        policy.tracked = LuaLoader::IsLuaTrackedApp(appId);
        policy.owned = LuaLoader::IsOwned(appId);
        policy.familyShared = LuaLoader::IsFamilySharedApp(appId);
        policy.block = policy.managed && !policy.owned && !policy.familyShared;
        policy.ownershipClass = CloudOwnershipClass(policy.tracked, policy.managed,
                                                    policy.owned, policy.familyShared);
        return policy;
    }

    std::uint64_t CloudSyncLogKey(AppId_t appId, const char* stage) {
        std::uint64_t h = static_cast<std::uint64_t>(appId) << 32;
        if (!stage) return h;
        while (*stage) {
            h = (h * 131u) + static_cast<unsigned char>(*stage++);
        }
        return h;
    }

    bool ShouldBlockCloudSync(AppId_t appId, const char* stage) {
        const CloudPolicy policy = GetCloudPolicy(appId);
        if (!policy.block) {
            if (policy.tracked || policy.managed || policy.owned || policy.familyShared) {
                HookStatus::RecordCloudSyncGate(appId, stage ? stage : "unknown",
                                                "passthrough",
                                                policy.ownershipClass,
                                                true);
            }
            return false;
        }

        HookStatus::RecordCloudSyncGate(appId, stage ? stage : "unknown",
                                        "blocked", "managed-block", true);
        {
            std::lock_guard<std::mutex> hold(g_cloudLogLock);
            if (g_cloudSyncBlockedLogged.insert(CloudSyncLogKey(appId, stage)).second) {
                LOG_LICENSECH_INFO(
                    "AutoCloudSyncGate: appid={} stage={} tracked={} managed=true owned=false familyShared={} ownershipClass={} result=blocked reason=managed-block",
                    appId, stage ? stage : "unknown", policy.tracked,
                    policy.familyShared, policy.ownershipClass);
            }
        }
        return true;
    }

    LM_HOOK(OptedInMask, __int64, void* pThis, unsigned int appId) {
        AppId_t realAppId = SteamCapture::ActiveRouteRealAppId();
        const char* routeName = SteamCapture::OnlineFixRouteIsSteamStubAuto()
            ? "steamstub-auto"
            : SteamCapture::OnlineFixRouteModeName(SteamCapture::OnlineFixMode());
        if (appId == kOnlineFixAppId && realAppId) {
            LOG_MISC_INFO("OptedInMask: routeMode={} appid {} -> {}",
                          routeName, appId, realAppId);
            return oOptedInMask(pThis, realAppId);
        }
        LOG_MISC_TRACE("OptedInMask: routeMode={} appid {} (realAppId={}, no redirect)",
                       routeName, appId, realAppId);
        return oOptedInMask(pThis, appId);
    }

    LM_HOOK(IsCloudEnabledForApp, bool, void* pRemoteStorage, AppId_t appId) {
        const CloudPolicy policy = GetCloudPolicy(appId);

        if (policy.tracked && policy.familyShared) {
            const bool original = oIsCloudEnabledForApp(pRemoteStorage, appId);
            HookStatus::RecordCloudDecision(appId, policy.tracked, policy.managed,
                                            policy.owned, policy.familyShared,
                                            original, true,
                                            "family-shared-allow");
            {
                std::lock_guard<std::mutex> hold(g_cloudLogLock);
                if (g_cloudFamilyAllowedLoggedApps.insert(appId).second) {
                    LOG_LICENSECH_INFO(
                        "IsCloudEnabledForApp: appid={} tracked=true familyShared=true native-cloud={} final=true reason=family-shared-allow",
                        appId, original);
                }
            }
            return true;
        }

        if (policy.block) {
            constexpr const char* closeState = "disabled";
            const bool original = oIsCloudEnabledForApp(pRemoteStorage, appId);
            HookStatus::RecordCloudCloseState(appId, closeState, false, false);
            HookStatus::RecordCloudDecision(appId, policy.tracked, policy.managed,
                                            policy.owned, policy.familyShared,
                                            original, false,
                                            "managed-block");
            {
                std::lock_guard<std::mutex> hold(g_cloudLogLock);
                if (g_cloudBlockedLoggedApps.insert(appId).second) {
                    LOG_LICENSECH_INFO(
                        "IsCloudEnabledForApp: appid={} tracked={} managed=true owned=false familyShared={} ownershipClass={} native-cloud={} final=false reason=managed-block closeAppCloud={}",
                        appId, policy.tracked, policy.familyShared,
                        policy.ownershipClass, original,
                        closeState);
                }
            }
            return false;
        }

        const bool enabled = oIsCloudEnabledForApp(pRemoteStorage, appId);
        if (policy.tracked || policy.managed || policy.owned || policy.familyShared) {
            HookStatus::RecordCloudDecision(appId, policy.tracked, policy.managed,
                                            policy.owned, policy.familyShared,
                                            enabled, enabled,
                                            "passthrough");
            LOG_LICENSECH_TRACE(
                "IsCloudEnabledForApp: appid={} tracked={} managed={} owned={} familyShared={} native-cloud={} final={} reason=passthrough",
                appId, policy.tracked, policy.managed, policy.owned,
                policy.familyShared, enabled, enabled);
        }
        return enabled;
    }

    LM_HOOK(EvaluateRemoteStorageSyncState, std::uint64_t,
            void* pRemoteStorage, AppId_t appId, bool force) {
        if (ShouldBlockCloudSync(appId, "evaluate")) return 0;
        return oEvaluateRemoteStorageSyncState(pRemoteStorage, appId, force);
    }

    LM_HOOK(RunAutoCloudOnAppLaunch, std::uint64_t,
            void* pRemoteStorage, AppId_t appId) {
        if (ShouldBlockCloudSync(appId, "launch")) return 0;
        return oRunAutoCloudOnAppLaunch(pRemoteStorage, appId);
    }

    LM_HOOK(RunAutoCloudOnAppExit, std::uint64_t,
            void* pRemoteStorage, AppId_t appId) {
        if (ShouldBlockCloudSync(appId, "exit")) return 0;
        return oRunAutoCloudOnAppExit(pRemoteStorage, appId);
    }

    LM_HOOK(GetRemoteStorageSyncState, std::int32_t,
            void* pRemoteStorage, AppId_t appId) {
        if (ShouldBlockCloudSync(appId, "state")) return 1;
        return oGetRemoteStorageSyncState(pRemoteStorage, appId);
    }

    // Hook for ConfigStore::GetBinary — intercepts depot decryption key fetches.
    // The real binary signature is int32 f(void*, EConfigStore, const char*, char*, uint32)
    // verified from the published prologue at RVA 0x5B3870: "48 63 FA" = movsxd rdi, edx
    // confirms the second param is a 32-bit enum, not a pointer.
    LM_HOOK(ConfigStoreGetBinary, int32, void* pObject, EConfigStore eConfigStore, const char* KeyName, char* pBuffer, uint32 cbBuffer) {
        if (!KeyName) return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, pBuffer, cbBuffer);

        std::string_view keyPath(KeyName);
        constexpr std::string_view kDepotPrefix = "Software\\Valve\\Steam\\depots\\";
        if (keyPath.find(kDepotPrefix) != 0)
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, pBuffer, cbBuffer);

        std::string seg(keyPath.substr(kDepotPrefix.size()));
        if (auto slash = seg.find('\\'); slash != std::string::npos)
            seg.resize(slash);

        char* end = nullptr;
        AppId_t depotId = static_cast<AppId_t>(strtoul(seg.c_str(), &end, 10));
        if (end == seg.c_str() || depotId == 0)
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, pBuffer, cbBuffer);

        std::vector<uint8_t> depotKey = LuaLoader::GetDecryptionKey(depotId);
        if (depotKey.empty())
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, pBuffer, cbBuffer);

        LOG_LICENSECH_INFO("ConfigStoreGetBinary: slapped key for depot={} len={}", depotId, depotKey.size());

        if (cbBuffer < depotKey.size())
            return oConfigStoreGetBinary(pObject, eConfigStore, KeyName, pBuffer, cbBuffer);

        memcpy(pBuffer, depotKey.data(), depotKey.size());
        return static_cast<int32>(depotKey.size());
    }

    LM_HOOK(RequiresLegacyCDKey, bool, void* pUser, AppId_t appId, uint32_t* pOut) {
        if (LuaLoader::HasDepot(appId)) {
            LOG_LICENSECH_INFO("RequiresLegacyCDKey: appId={} suppressed (Lua-tracked)", appId);
            if (pOut) *pOut = 0;
            return false;
        }
        return oRequiresLegacyCDKey(pUser, appId, pOut);
    }

}

namespace LicenseHooks {

    void Install() {
        LM_BIND(ConfigStoreGetBinary);

        LM_TX_BEGIN();
        LM_INSTALL(OptedInMask);
        LM_INSTALL(IsCloudEnabledForApp);
        LM_INSTALL(EvaluateRemoteStorageSyncState);
        LM_INSTALL(RunAutoCloudOnAppLaunch);
        LM_INSTALL(RunAutoCloudOnAppExit);
        LM_INSTALL(GetRemoteStorageSyncState);
        LM_INSTALL(RequiresLegacyCDKey);
        LM_INSTALL(ConfigStoreGetBinary);
        LM_TX_COMMIT();

        const int cloudGateCount =
            (oEvaluateRemoteStorageSyncState ? 1 : 0) +
            (oRunAutoCloudOnAppLaunch ? 1 : 0) +
            (oRunAutoCloudOnAppExit ? 1 : 0) +
            (oGetRemoteStorageSyncState ? 1 : 0);
        HookStatus::RecordCloudSyncGate(
            0, "install",
            cloudGateCount == 4 ? "attached" : (cloudGateCount > 0 ? "partial" : "missing"),
            cloudGateCount == 4 ? "ok" : "cloud-sync-gate-missing",
            cloudGateCount > 0);

        LOG_LICENSECH_INFO(
            "LicenseHooks::Install: OptedInMask={} IsCloudEnabledForApp={} AutoCloudSyncGate={}/4 RequiresLegacyCDKey={} ConfigStoreGetBinary={}",
            oOptedInMask         ? "attached" : "skipped (TOML entry missing)",
            oIsCloudEnabledForApp ? "attached" : "skipped (TOML entry missing)",
            cloudGateCount,
            oRequiresLegacyCDKey ? "attached" : "skipped (TOML entry missing)",
            oConfigStoreGetBinary ? "attached" : "skipped (TOML entry missing)");
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(GetRemoteStorageSyncState);
        LM_REMOVE(RunAutoCloudOnAppExit);
        LM_REMOVE(RunAutoCloudOnAppLaunch);
        LM_REMOVE(EvaluateRemoteStorageSyncState);
        LM_REMOVE(IsCloudEnabledForApp);
        LM_REMOVE(RequiresLegacyCDKey);
        LM_REMOVE(OptedInMask);
        LM_REMOVE(ConfigStoreGetBinary);
        LM_TX_COMMIT();
        LOG_LICENSECH_INFO("LicenseHooks::Uninstall: complete");
    }

}
