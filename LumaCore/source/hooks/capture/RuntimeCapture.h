// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include "core/entry.h"

// Captures runtime Steam object pointers and handles lightweight hooks that
// don't belong in a dedicated category:
//   * GetAppIDForCurrentPipe  -> Detours hook; captures the SteamEngine
//                                pointer on first call and applies the
//                                scoped real-appid override for IClientUserStats
//                                traffic (see SetUserStatsContext)
//   * SpawnProcess            -> online-fix / SteamStub launch routing
//   * GetAppDataFromAppInfo   -> int3 trap; captures the CAppInfoCache pointer
//   * MarkLicenseAsChanged    -> captures pCUser; resolved for NotifyLicenseChanged
//   * GetPackageInfo          -> captures pCPackageInfo; used by NotifyLicenseChanged to append AppIds
//   * ProcessPendingLicenseUpdates -> resolved for NotifyLicenseChanged
namespace SteamCapture {
    enum class OnlineFixRouteMode : uint32 {
        None = 0,
        ManualFlag = 1,
    };

    void Install();
    void Uninstall();

    // Returns the AppId for the current Steam pipe via the captured engine
    // pointer, or 0 if we haven't yet observed the host calling
    // GetAppIDForCurrentPipe.
    AppId_t GetAppIDForCurrentPipe();

    // Grow a CUtlBuffer to at least 'size' bytes and set m_Put = size.
    // Uses CUtlBuffer::EnsureCapacity from steamclient, resolved on first call.
    void EnsureBufferSize(CUtlBuffer* pWrite, int32 size);

    // Resolve the real appid: if a manual OnlineFix or dedicated SteamStub
    // route is active return its real appid, otherwise fall back to
    // GetAppIDForCurrentPipe().
    AppId_t ResolveAppId();

    // Returns the active route real appid for either manual OnlineFix or the
    // dedicated SteamStub route. Returns 0 when neither route is active.
    AppId_t ActiveRouteRealAppId();

    // Returns the captured OnlineFix real appid (0 when no OnlineFix session
    // is active). The callback rewrite path keys on the raw value because the
    // pipe-fallback semantics of ResolveAppId would mask a non-active session.
    AppId_t OnlineFixRealAppId();
    OnlineFixRouteMode OnlineFixMode();
    bool OnlineFixRouteIsSteamStubAuto();
    const char* OnlineFixRouteModeName(OnlineFixRouteMode mode);

    // Scoped real-appid override for IClientUserStats traffic. Increments
    // a thread-local depth counter on active=true and decrements on
    // active=false (underflow guarded). The GetAppIDForCurrentPipe detour
    // returns the real appid only while depth > 0 AND OnlineFix is active
    // AND the original engine call returned the Spacewar masquerade.
    void SetUserStatsContext(bool active);

    // Pipe-scoped fine gate paired with the thread-local depth counter.
    // EnterStatsScope stamps g_StatsScopePipe with the dispatching pipe on
    // entry to an IClientUserStats IPC; LeaveStatsScope clears it back to 0
    // on exit. The achievement-callback rewrite path keys on the stamp so
    // worker threads sharing an HSteamPipe value cannot bleed rewrites
    // across pipes that did not originate the user-stats call. StatsScopePipe
    // returns the current stamp under acquire ordering.
    void EnterStatsScope(HSteamPipe pipe);
    void LeaveStatsScope();
    HSteamPipe StatsScopePipe();

    // Get localized game name via GetAppDataFromAppInfo (cached).
    std::string GetGameNameByAppID(AppId_t appId);

    // Mark package 0 as changed and trigger CClientAppManager_ProcessPendingLicenseUpdates
    // Requires pCUser to have been captured (happens on first natural call to
    // MarkLicenseAsChanged, which Steam makes during license load on startup).
    void NotifyLicenseChanged();

    // Returns true when all captures needed by NotifyLicenseChanged are ready.
    // Used by the startup injection thread to know when it's safe to call NotifyLicenseChanged.
    bool IsReadyForNotify();
}
