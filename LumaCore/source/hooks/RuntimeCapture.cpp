#include "RuntimeCapture.h"
#include "Macros.h"
#include "PackagePatch.h"
#include "SteamUI.h"
#include "utils/VehUtil.h"
#include "utils/Ticket.h"
#include "entry.h"

namespace {
    // ── function type aliases (alphabetical) ─────────────────────────────────
    using BuildSpawnEnvBlock_t           = __int64(*)(void*, uint64_t*, void*, void*, uint64_t*, void*, int, void*, void*, unsigned int, char);
    using OptedInMask_t                  = __int64(*)(void*, unsigned int);
    using CUtlBufferEnsureCapacity_t     = void*(*)(CUtlBuffer*, int);
    using CUtlMemoryGrow_t               = void*(*)(CUtlVector<AppId_t>*, int);
    using GetAppDataFromAppInfo_t        = int64(*)(void*, AppId_t, const char*, uint8*, int32);
    using GetAppIDForCurrentPipe_t       = AppId_t(*)(void*);
    using GetPackageInfo_t               = PackageInfo*(*)(void*, uint32, int64);
    using MarkLicenseAsChanged_t         = int64(*)(void*, uint32, bool);
    using ProcessPendingLicenseUpdates_t = bool(*)(void*);

    // ── X-macro lists ────────────────────────────────────────────────────────
    // One-shot int3: on hit, ctx->Rcx stored to the named output variable.
    #define VEH_GRAB_LIST(X)                         \
        X(GetAppIDForCurrentPipe, g_steamEngine)     \
        X(GetAppDataFromAppInfo,  g_pCAppInfoCache)

    // Resolve-only (no int3).
    #define VEH_TRACK_LIST(X)            \
        X(CUtlBufferEnsureCapacity)      \
        X(CUtlMemoryGrow)               \
        X(ProcessPendingLicenseUpdates)

    // ── generated declarations ───────────────────────────────────────────────
    VEH_GRAB_LIST(VEH_DECL_CAPTURE)
    VEH_TRACK_LIST(VEH_DECL_RESOLVE)

    // ── Detours-captured pointers (set on first call, never cleared) ─────────
    // These replace the old VEH int3 captures for MarkLicenseAsChanged and
    // GetPackageInfo. Detours hooks fire on every call regardless of when they
    // were installed, so we capture pCUser and pCPackageInfo on the first
    // natural Steam call after login — even if that happens after startup.
    void* g_pCUser        = nullptr;
    void* g_pCPackageInfo = nullptr;
    std::atomic<bool> g_startupInjectionDone{false};

    // Forward declaration
    void DoStartupInjection();

    // ── per-session state ─────────────────────────────────────────────────────
    uint8_t*              g_spawnProcessTarget = nullptr;
    PVOID                 g_vehHandle          = nullptr;
    std::atomic<AppId_t>  g_OnlineFixRealAppId{0};
    std::unordered_map<AppId_t, std::string> g_GameNameCache;
    static std::vector<CaptureEntry> g_captures;

    // ── BuildSpawnEnvBlock Detours hook ──────────────────────────────────────
    // Patches pOverlayCGameID from 480 to the real appid before delegating.
    // This fixes the overlay identity (screenshots, community hub) for -onlinefix games.
    // pCGameID is left at 480 so the lobby/matchmaking redirection still holds.
    // OST approach: patch the overlay CGameID argument, not the env block string.
    LC_HOOK_DEF(BuildSpawnEnvBlock, __int64,
                void* pThis, uint64_t* pCGameID, void* a3, void* env,
                uint64_t* pOverlayCGameID, void* a6, int a7,
                void* a8, void* a9, unsigned int a10, char a11)
    {
        AppId_t realAppId = g_OnlineFixRealAppId.load(std::memory_order_acquire);
        AppId_t overlayAppId = pOverlayCGameID
            ? static_cast<AppId_t>(*pOverlayCGameID & 0xFFFFFF) : 0;
        AppId_t cgameAppId = pCGameID
            ? static_cast<AppId_t>(*pCGameID & 0xFFFFFF) : 0;

        if (realAppId && pOverlayCGameID && overlayAppId == kOnlineFixAppId) {
            uint64_t prev = *pOverlayCGameID;
            *pOverlayCGameID = (prev & ~static_cast<uint64_t>(0xFFFFFF))
                             | static_cast<uint64_t>(realAppId);
            LOG_MISC_INFO("BuildSpawnEnvBlock: overlay CGameID {:#x} -> {:#x} (realAppId={}, cgame={})",
                          prev, *pOverlayCGameID, realAppId, cgameAppId);
        } else {
            LOG_MISC_TRACE("BuildSpawnEnvBlock: cgame={} overlay={} realAppId={} (no patch)",
                           cgameAppId, overlayAppId, realAppId);
        }
        return oBuildSpawnEnvBlock(pThis, pCGameID, a3, env,
                                    pOverlayCGameID, a6, a7, a8, a9, a10, a11);
    }

    // ── OptedInMask Detours hook ──────────────────────────────────────────────
    // CSteamController::OptedInMask(appid) returns the Steam Input opt-in mask
    // and sets SDL_GAMECONTROLLER_* env vars for the spawned process.
    // When -onlinefix rewrites the game's CGameID to 480 (Spacewar), this function
    // gets called with appid=480 and returns Spacewar's empty mask — no controller,
    // no SDL env vars. We redirect to the real appid so controllers work correctly.
    LC_HOOK_DEF(OptedInMask, __int64, void* pThis, unsigned int appId)
    {
        AppId_t realAppId = g_OnlineFixRealAppId.load(std::memory_order_acquire);
        if (appId == kOnlineFixAppId && realAppId) {
            LOG_MISC_INFO("OptedInMask: appid {} -> {}", appId, realAppId);
            return oOptedInMask(pThis, realAppId);
        }
        LOG_MISC_TRACE("OptedInMask: appid {} (realAppId={}, no redirect)", appId, realAppId);
        return oOptedInMask(pThis, appId);
    }

    // ── MarkLicenseAsChanged Detours hook ────────────────────────────────────
    // Captures pCUser (RCX = this) on first call, then triggers startup injection.
    // This replaces the old VEH int3 capture — Detours fires on every call
    // regardless of when the hook was installed, so we always get pCUser.
    LC_HOOK_DEF(MarkLicenseAsChanged, int64, void* pThis, uint32 packageId, bool bReloadAll) {
        if (!g_pCUser) {
            g_pCUser = pThis;
            LOG_PACKAGE_INFO("MarkLicenseAsChanged: captured pCUser=0x{:X}",
                             reinterpret_cast<uint64_t>(pThis));
            // Trigger startup injection now that we have pCUser
            DoStartupInjection();
        }
        return oMarkLicenseAsChanged(pThis, packageId, bReloadAll);
    }

    // ── GetPackageInfo Detours hook ───────────────────────────────────────────
    // Captures pCPackageInfo (RCX = this) on first call — kept for NotifyLicenseChanged.
    LC_HOOK_DEF(GetPackageInfo, PackageInfo*, void* pThis, uint32 packageId, int64 p3) {
        if (!g_pCPackageInfo) {
            g_pCPackageInfo = pThis;
            LOG_PACKAGE_INFO("GetPackageInfo: captured pCPackageInfo=0x{:X}",
                             reinterpret_cast<uint64_t>(pThis));
        }
        return oGetPackageInfo(pThis, packageId, p3);
    }

    // ── Startup injection ─────────────────────────────────────────────────────
    // Called once when MarkLicenseAsChanged fires (post-login).
    // Injects all startup Lua files into the already-loaded package 0 using
    // the PackageInfo* pointer saved by the LoadPackage hook.
    void DoStartupInjection() {
        if (g_startupInjectionDone.exchange(true)) return;
        LOG_PACKAGE_INFO("DoStartupInjection: injecting startup Lua files into package 0");
        LuaLoader::QueueStartupInjection();
        std::vector<AppId_t> additions = LuaLoader::TakePendingAdditions();
        if (!PackagePatch::InjectIntoPackage0(additions)) {
            LOG_PACKAGE_WARN("DoStartupInjection: package 0 not captured yet, injection failed");
            g_startupInjectionDone.store(false);
            return;
        }
        LOG_PACKAGE_INFO("DoStartupInjection: done, injected {} apps", additions.size());
    }
    // Prevents substring matches like "-onlinefixpatch" triggering the -onlinefix path.
    static bool HasExactFlag(const char* cmd, const char* flag) {
        const char* p = cmd;
        size_t n = strlen(flag);
        while ((p = strstr(p, flag))) {
            bool startOk = (p == cmd || p[-1] == ' ');
            bool endOk   = (p[n] == '\0' || p[n] == ' ');
            if (startOk && endOk) return true;
            p += n;
        }
        return false;
    }

    // ── VEH handler ──────────────────────────────────────────────────────────
    // Scoped to this module's int3 sites only. Foreign RIP ->
    // EXCEPTION_CONTINUE_SEARCH so other VEH handlers still get their turn.
    LONG CALLBACK VehHandler(PEXCEPTION_POINTERS pExInfo) {
        PCONTEXT ctx = pExInfo->ContextRecord;

        if (pExInfo->ExceptionRecord->ExceptionCode == EXCEPTION_BREAKPOINT) {
            for (auto& cap : g_captures) {
                if (*cap.funcPtr && ctx->Rip == reinterpret_cast<uint64_t>(*cap.funcPtr)) {
                    *cap.outPtr = reinterpret_cast<void*>(ctx->Rcx);
                    *reinterpret_cast<uint8_t*>(*cap.funcPtr) = cap.restoreByte;
                    LOG_MISC_INFO("Captured {}: 0x{:X}", cap.label,
                                  reinterpret_cast<uint64_t>(*cap.outPtr));
                    return EXCEPTION_CONTINUE_EXECUTION;
                }
            }

            // CUser_SpawnProcess(pCUser, pExePath, pCommandLine, pWorkingDir,
            //                   pGameID, ...)
            // RCX=pCUser, RDX=pExePath, R8=pCommandLine, R9=pWorkingDir
            // [RSP+0x28]=pGameID (5th arg, pointer to CGameID, low 24 bits = AppId)
            if (g_spawnProcessTarget
                && ctx->Rip == reinterpret_cast<uint64_t>(g_spawnProcessTarget)) {
                auto* pGameID = reinterpret_cast<uint64_t*>(
                    *reinterpret_cast<uint64_t*>(ctx->Rsp + 0x28));
                const char* exePath = reinterpret_cast<const char*>(ctx->Rdx);
                const char* cmdLine = reinterpret_cast<const char*>(ctx->R8);
                const char* workDir = reinterpret_cast<const char*>(ctx->R9);

                if (!pGameID) {
                    LOG_MISC_WARN("SpawnProcess: pGameID is null, exe=\"{}\" cmd=\"{}\"",
                                  exePath ? exePath : "(null)",
                                  cmdLine ? cmdLine : "(null)");
                    *g_spawnProcessTarget = 0x48;
                    ctx->EFlags |= 0x100;
                    return EXCEPTION_CONTINUE_EXECUTION;
                }
                AppId_t appId = static_cast<AppId_t>(*pGameID & 0xFFFFFF);

                *g_spawnProcessTarget = 0x48;
                ctx->EFlags |= 0x100;

                bool hasDepot = LuaLoader::HasDepot(appId);
                bool hasFlag  = (cmdLine != nullptr) && HasExactFlag(cmdLine, "-onlinefix");

                LOG_MISC_INFO("SpawnProcess: hit appid={} hasDepot={} hasFlag={} exe=\"{}\" cmd=\"{}\"",
                              appId, hasDepot, hasFlag,
                              exePath ? exePath : "(null)",
                              cmdLine ? cmdLine : "(null)");

                // Ensure the registry has tickets baked with the active user's
                // SteamID before the game's DRM wrapper reads them. Wipes any
                // stale ticket from a previous account, and writes a minimal
                // unsigned blob if nothing is cached. For Steam-DRM (Steam
                // Stub) v2.2+ titles like Teardown the unsigned blob still
                // fails the wrapper signature check — the fix there is
                // Steamless from SteaMidra. For older v1.5 / early-v2
                // wrappers and tools that only read the SteamID/AppID
                // fields this is enough on its own.
                if (hasDepot) {
                    Ticket::EnsureRegistryTicketsForApp(appId);
                }

                if (hasDepot && hasFlag) {
                    g_OnlineFixRealAppId.store(appId, std::memory_order_release);
                    *pGameID = kOnlineFixAppId;
                    LOG_MISC_INFO("SpawnProcess: ONLINEFIX ACTIVE — appid {} -> {}, real stored",
                                  appId, kOnlineFixAppId);
                } else {
                    g_OnlineFixRealAppId.store(0, std::memory_order_release);
                    LOG_MISC_DEBUG("SpawnProcess: onlinefix NOT activated for appid={} "
                                   "(reason: {}{}{})",
                                   appId,
                                   !hasDepot ? "no-depot " : "",
                                   !hasFlag  ? "no-flag "  : "",
                                   (hasDepot && hasFlag) ? "(internal)" : "");
                }
                return EXCEPTION_CONTINUE_EXECUTION;
            }
        }

        if (pExInfo->ExceptionRecord->ExceptionCode == EXCEPTION_SINGLE_STEP) {
            if (g_spawnProcessTarget
                && ctx->Rip == reinterpret_cast<uint64_t>(g_spawnProcessTarget + 5)) {
                *g_spawnProcessTarget = 0xCC;
                return EXCEPTION_CONTINUE_EXECUTION;
            }
        }

        return EXCEPTION_CONTINUE_SEARCH;
    }
}

namespace SteamCapture {
    void Install() {
        if (g_vehHandle) return;

        VEH_TRACK_LIST(VEH_LOCATE)

        ARM_CAPTURE_D(GetAppIDForCurrentPipe, g_steamEngine);
        ARM_CAPTURE_STR_D(GetAppDataFromAppInfo, g_pCAppInfoCache,
                          GetAppDataFromAppInfoStrSigs, GetAppDataFromAppInfoSigs);

        if (auto* _sp_ = FIND_SIG(diversion_hModule, SpawnProcess)) {
            g_spawnProcessTarget = static_cast<uint8_t*>(_sp_);
            VehUtil::ArmInt3(_sp_);
        }

        if (!g_captures.empty() || g_spawnProcessTarget)
            g_vehHandle = AddVectoredExceptionHandler(1, VehHandler);

        // Hook MarkLicenseAsChanged and GetPackageInfo with Detours to capture
        // pCUser and pCPackageInfo on first call. This replaces the old VEH int3
        // approach which missed the first call (happened before hooks were installed).
        LC_TX_OPEN();
        LC_ATTACH_D(MarkLicenseAsChanged);
        LC_ATTACH_D(GetPackageInfo);
        LC_ATTACH_D(OptedInMask);
        LC_ATTACH_D(BuildSpawnEnvBlock);
        LC_TX_COMMIT();
    }

    void Uninstall() {
        if (g_vehHandle) {
            RemoveVectoredExceptionHandler(g_vehHandle);
            g_vehHandle = nullptr;
        }

        VEH_CLEANUP_CAPTURES(g_captures);

        if (g_spawnProcessTarget && *g_spawnProcessTarget == 0xCC)
            VehUtil::RestoreByte(g_spawnProcessTarget, 0x48);
        g_spawnProcessTarget = nullptr;

        LC_TX_OPEN();
        LC_DETACH(MarkLicenseAsChanged);
        LC_DETACH(GetPackageInfo);
        LC_DETACH(OptedInMask);
        LC_DETACH(BuildSpawnEnvBlock);
        LC_TX_COMMIT();

        VEH_TRACK_LIST(VEH_ZERO_RESOLVE)
        g_OnlineFixRealAppId.store(0, std::memory_order_relaxed);
        g_GameNameCache.clear();
        g_pCUser        = nullptr;
        g_pCPackageInfo = nullptr;
        g_startupInjectionDone.store(false);
    }

    AppId_t GetAppIDForCurrentPipe() {
        if (!g_steamEngine || !oGetAppIDForCurrentPipe) {
            LOG_MISC_WARN("GetAppIDForCurrentPipe called before capture — returning 0");
            return 0;
        }
        auto appid = oGetAppIDForCurrentPipe(g_steamEngine);
        if (!appid) {
            LOG_MISC_TRACE("GetAppIDForCurrentPipe: AppId=0(Not GamePipe)");
        } else {
            LOG_MISC_DEBUG("GetAppIDForCurrentPipe: AppId={}", appid);
        }
        return appid;
    }

    AppId_t ResolveAppId() {
        AppId_t onlineFix = g_OnlineFixRealAppId.load(std::memory_order_acquire);
        if (onlineFix) return onlineFix;
        return GetAppIDForCurrentPipe();
    }

    void EnsureBufferSize(CUtlBuffer* pWrite, int32 size)
    {
        if (oCUtlBufferEnsureCapacity) {
            LOG_MISC_DEBUG("Before ensuring CUtlBuffer capacity: {}", pWrite->DebugString());
            oCUtlBufferEnsureCapacity(pWrite, size);
            LOG_MISC_DEBUG("After ensuring CUtlBuffer capacity: {}", pWrite->DebugString());
        }
        pWrite->m_Put = size;
    }

    // ── Game name ────────────────────────────────────────────────
    std::string GetGameNameByAppID(AppId_t appId)
    {
        auto it = g_GameNameCache.find(appId);
        if (it != g_GameNameCache.end()) return it->second;

        std::string name;

        if (g_pCAppInfoCache && oGetAppDataFromAppInfo) {
            char buf[256] = {};
            // "common/name" triggers auto-localization: the function detects
            // prefix "common" (keyType=2) + key "name", then tries
            // "name_localized/<current_lang>" before falling back to "name".
            // Returns strlen+1 on success, -1 on failure.
            int64 len = oGetAppDataFromAppInfo(
                g_pCAppInfoCache, appId, "common/name",
                reinterpret_cast<uint8*>(buf), sizeof(buf));
            if (len > 1)
                name.assign(buf, static_cast<size_t>(len - 1));
        }

        LOG_MISC_DEBUG("GetGameNameByAppID({}): {}", appId, name);
        g_GameNameCache[appId] = name;
        return name;
    }

    // ── License refresh (no-restart) ────────────────────────────────
    bool IsReadyForNotify() {
        return g_pCUser != nullptr && g_pCPackageInfo != nullptr
            && oGetPackageInfo != nullptr && oMarkLicenseAsChanged != nullptr
            && oProcessPendingLicenseUpdates != nullptr && oCUtlMemoryGrow != nullptr;
    }

    void NotifyLicenseChanged() {
        if (!g_pCUser || !g_pCPackageInfo) {
            LOG_PACKAGE_WARN("NotifyLicenseChanged: pCUser or pCPackageInfo not captured yet, skipping");
            return;
        }
        if (!oGetPackageInfo || !oMarkLicenseAsChanged
            || !oProcessPendingLicenseUpdates || !oCUtlMemoryGrow) {
            LOG_PACKAGE_WARN("NotifyLicenseChanged: functions not resolved, skipping");
            return;
        }

        PackageInfo* pPkg = oGetPackageInfo(g_pCPackageInfo, 0, 0);
        if (!pPkg) {
            LOG_PACKAGE_WARN("NotifyLicenseChanged: GetPackageInfo returned null");
            return;
        }

        // Two-phase order — copies the OST flow exactly.
        //   1. Mutate the package vector (drop removals, append additions)
        //   2. Trigger Steam's MarkLicenseAsChanged + ProcessPendingLicenseUpdates
        //   3. THEN evict UI cards via RemoveAppOverviewBatch
        //
        // Mixing UI eviction inside the package-vector loop crashed Steam:
        // the per-id RemoveAppOverview synchronously dispatches a
        // CAppOverview_Change to every webhelper subscriber while Steam
        // itself is still rendering the same card, racing the AppIdVec
        // mutations on another thread. Doing all vector work first, then
        // a single batched UI dispatch at the end, eliminates that race.

        // ── Phase 1a: drop removals from the package vector ──
        std::vector<AppId_t> removals = LuaLoader::TakePendingRemovals();
        uint32_t removedCount = 0;
        for (AppId_t id : removals) {
            if (pPkg->AppIdVec.FindAndFastRemove(id)) {
                ++removedCount;
                LOG_PACKAGE_DEBUG("NotifyLicenseChanged: removed AppId {} from vector", id);
            } else {
                LOG_PACKAGE_DEBUG("NotifyLicenseChanged: AppId {} not in vector (hot-reload)", id);
            }
        }

        // ── Phase 1b: append additions to the package vector ──
        std::vector<AppId_t> additions = LuaLoader::TakePendingAdditions();
        if (!additions.empty()) {
            uint32_t oldSize = pPkg->AppIdVec.m_Size;
            oCUtlMemoryGrow(&pPkg->AppIdVec, static_cast<uint32>(additions.size()));
            for (size_t i = 0; i < additions.size(); ++i) {
                pPkg->AppIdVec.m_Memory.m_pMemory[oldSize + i] = additions[i];
                LOG_PACKAGE_DEBUG("NotifyLicenseChanged: inserted AppId {} at [{}]", additions[i], oldSize + i);
            }
            pPkg->AppIdVec.m_Size = static_cast<uint32>(oldSize + additions.size());
        }

        if (additions.empty() && removals.empty()) {
            LOG_PACKAGE_DEBUG("NotifyLicenseChanged: no changes");
            return;
        }

        // ── Phase 2: license refresh (Steam re-evaluates package state) ──
        oMarkLicenseAsChanged(g_pCUser, 0, true);
        oProcessPendingLicenseUpdates(g_pCUser);
        LOG_PACKAGE_INFO("NotifyLicenseChanged: {} added, {} removed ({} from vector)",
                         additions.size(), removals.size(), removedCount);

        // NO Phase 3 / RemoveAppOverview eviction.
        //
        // Three separate attempts to evict library cards via SteamUI's
        // CAppOverview_Change dispatch all crashed Steam at different points:
        //   1. Per-id INSIDE the AppIdVec mutation loop — race with Steam's
        //      reads on the same vector.
        //   2. Batched after the loop — webhelper choked on a 20-id removal
        //      burst in one packet.
        //   3. Per-id AFTER the license refresh, no batching, identical to
        //      OST's published code — STILL crashed in user testing.
        //
        // OldLumaCore shipped without this step and only had the visual
        // side-effect of cards lingering as "Purchase" until Steam restarted.
        // We're back to that behavior here. The eviction primitives
        // (RemoveAppOverview, RemoveAppOverviewBatch) stay available in the
        // public SteamUI API for future call sites once a safe trigger is
        // found, just not in the hot-reload path.
        //
        // User-visible workaround: restart Steam to drop the lingering card.
    }
}
