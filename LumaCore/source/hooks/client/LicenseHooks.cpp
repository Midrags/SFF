// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/LicenseHooks.h"

#include "hooks/Macros.h"
#include "hooks/capture/RuntimeCapture.h"
#include "core/entry.h"
#include "config/LuaLoader.h"

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
// DLC ownership / install / cloud / license-update / ownership-ticket
// queries (BIsDlcEnabled, IsAppDlcInstalled, IsCloudEnabledForApp,
// BUpdateLicenses, BUpdateAppOwnershipTicket) were intentionally NOT
// hooked here. Steam
// already returns the right answer for Lua-tracked appids through the
// existing CheckAppOwnership patch, so installing detours on top of those
// surfaces is redundant. Detouring them with hand-rolled signatures also
// risks stack corruption on x64 fastcall when an argument count or type
// is even slightly off, which is what surfaced as a random Steam crash a
// few minutes into a session and as cloud-save toggles flipping on for
// every tracked game.
//
// The patterns for those five functions still ride in the per-build TOML
// (the analyzer keeps detecting them) so any future hook code that needs
// them can resolve their addresses without changing the pattern publisher
// or the cache layout.

namespace {

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
        LM_INSTALL(RequiresLegacyCDKey);
        LM_INSTALL(ConfigStoreGetBinary);
        LM_TX_COMMIT();

        LOG_LICENSECH_INFO(
            "LicenseHooks::Install: OptedInMask={} RequiresLegacyCDKey={} ConfigStoreGetBinary={}",
            oOptedInMask         ? "attached" : "skipped (TOML entry missing)",
            oRequiresLegacyCDKey ? "attached" : "skipped (TOML entry missing)",
            oConfigStoreGetBinary ? "attached" : "skipped (TOML entry missing)");
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(RequiresLegacyCDKey);
        LM_REMOVE(OptedInMask);
        LM_TX_COMMIT();
        LOG_LICENSECH_INFO("LicenseHooks::Uninstall: complete");
    }

}
