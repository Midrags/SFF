#include "RuntimeCapture.h"
#include "Macros.h"
#include "utils/VehUtil.h"
#include "entry.h"
#include <cstdio>

namespace {
    // ── function type aliases (alphabetical) ─────────────────────────────────
    using BuildSpawnEnvBlock_t           = bool(*)(void*, char**, uint32*);
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
        X(GetAppDataFromAppInfo,  g_pCAppInfoCache)  \
        X(MarkLicenseAsChanged,   g_pCUser)          \
        X(GetPackageInfo,         g_pCPackageInfo)

    // Resolve-only (no int3).
    #define VEH_TRACK_LIST(X)            \
        X(CUtlBufferEnsureCapacity)      \
        X(CUtlMemoryGrow)               \
        X(ProcessPendingLicenseUpdates)

    // ── generated declarations ───────────────────────────────────────────────
    VEH_GRAB_LIST(VEH_DECL_CAPTURE)
    VEH_TRACK_LIST(VEH_DECL_RESOLVE)

    // ── per-session state ─────────────────────────────────────────────────────
    uint8_t*              g_spawnProcessTarget = nullptr;
    PVOID                 g_vehHandle          = nullptr;
    std::atomic<AppId_t>  g_OnlineFixRealAppId{0};
    std::unordered_map<AppId_t, std::string> g_GameNameCache;
    static std::vector<CaptureEntry> g_captures;

    // ── BuildSpawnEnvBlock Detours hook ──────────────────────────────────────
    // Patches SteamOverlayGameId=480 and SteamAppId=480 in the env block that
    // Steam passes to CreateProcess when launching a game with -onlinefix.
    // The original function sets those to 480 (kOnlineFixAppId) because
    // the SpawnProcess VEH already rewrote *pGameID. We rebuild the block
    // with the real appid so controllers and the Steam overlay attach correctly.
    LC_HOOK_DEF(BuildSpawnEnvBlock, bool, void* pThis, char** ppEnvBlock, uint32* pcbEnvBlock)
    {
        bool result = oBuildSpawnEnvBlock(pThis, ppEnvBlock, pcbEnvBlock);
        AppId_t realId = g_OnlineFixRealAppId.load(std::memory_order_acquire);
        if (!result || !realId || !ppEnvBlock || !*ppEnvBlock) return result;

        char realStr[16];
        int  realLen = sprintf_s(realStr, sizeof(realStr), "%u", realId);
        char fakeStr[16];
        int  fakeLen = sprintf_s(fakeStr, sizeof(fakeStr), "%u",
                                 static_cast<uint32>(kOnlineFixAppId));
        (void)fakeLen;

        static const char* kPatch[] = { "SteamOverlayGameId=", "SteamAppId=" };

        // First pass: check if anything needs patching.
        bool needsPatch = false;
        const char* scan = *ppEnvBlock;
        while (*scan) {
            for (const char* pfx : kPatch) {
                size_t pl = strlen(pfx);
                if (strncmp(scan, pfx, pl) == 0 && strcmp(scan + pl, fakeStr) == 0) {
                    needsPatch = true;
                    break;
                }
            }
            if (needsPatch) break;
            scan += strlen(scan) + 1;
        }
        if (!needsPatch) return result;

        // Second pass: rebuild with patched entries.
        // +64 bytes headroom covers the difference between "480" (3 chars) and
        // any realistic appid (up to 10 chars), multiplied by the 2 target keys.
        uint32 cbNew = *pcbEnvBlock + 64;
        char*  newEnv = static_cast<char*>(VirtualAlloc(nullptr, cbNew,
                            MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
        if (!newEnv) return result;

        char* src = *ppEnvBlock;
        char* dst = newEnv;
        while (*src) {
            size_t entryLen = strlen(src);
            bool replaced = false;
            for (const char* pfx : kPatch) {
                size_t pl = strlen(pfx);
                if (strncmp(src, pfx, pl) == 0 && strcmp(src + pl, fakeStr) == 0) {
                    memcpy(dst, pfx, pl);
                    dst += pl;
                    memcpy(dst, realStr, realLen + 1);
                    dst += realLen + 1;
                    replaced = true;
                    break;
                }
            }
            if (!replaced) {
                memcpy(dst, src, entryLen + 1);
                dst += entryLen + 1;
            }
            src += entryLen + 1;
        }
        *dst = '\0';

        *ppEnvBlock  = newEnv;
        *pcbEnvBlock = static_cast<uint32>(dst - newEnv + 1);
        LOG_MISC_INFO("BuildSpawnEnvBlock: patched SteamOverlayGameId/SteamAppId {} -> {}",
                      kOnlineFixAppId, realId);
        return result;
    }

    // Returns true when flag appears as a whole word in cmd (space- or end-delimited).
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
                if (!pGameID) {
                    *g_spawnProcessTarget = 0x48;
                    ctx->EFlags |= 0x100;
                    return EXCEPTION_CONTINUE_EXECUTION;
                }
                AppId_t appId = static_cast<AppId_t>(*pGameID & 0xFFFFFF);

                *g_spawnProcessTarget = 0x48;
                ctx->EFlags |= 0x100;

                const char* cmdLine = reinterpret_cast<const char*>(ctx->R8);

                if (LuaLoader::HasDepot(appId) && cmdLine
                    && HasExactFlag(cmdLine, "-onlinefix")) {
                    g_OnlineFixRealAppId.store(appId, std::memory_order_release);
                    *pGameID = kOnlineFixAppId;
                    LOG_MISC_INFO("SpawnProcess: appid {} -> {}, cmd=\"{}\"",
                                  appId, kOnlineFixAppId, cmdLine);
                } else {
                    g_OnlineFixRealAppId.store(0, std::memory_order_release);
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
        ARM_CAPTURE_D(MarkLicenseAsChanged, g_pCUser);
        ARM_CAPTURE_D(GetPackageInfo, g_pCPackageInfo);

        if (auto* _sp_ = FIND_SIG(diversion_hModule, SpawnProcess)) {
            g_spawnProcessTarget = static_cast<uint8_t*>(_sp_);
            VehUtil::ArmInt3(_sp_);
        }

        if (!g_captures.empty() || g_spawnProcessTarget)
            g_vehHandle = AddVectoredExceptionHandler(1, VehHandler);

        // BuildSpawnEnvBlock hook disabled — string XRef resolves to wrong
        // function on this Steam build, corrupting env block for all launches.
        // LC_TX_OPEN();
        // LC_ATTACH_STR_ONLY_D(BuildSpawnEnvBlock, BuildSpawnEnvBlockStrSigs);
        // LC_TX_COMMIT();
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

        // LC_TX_OPEN();
        // LC_DETACH(BuildSpawnEnvBlock);
        // LC_TX_COMMIT();

        VEH_TRACK_LIST(VEH_ZERO_RESOLVE)
        g_OnlineFixRealAppId.store(0, std::memory_order_relaxed);
        g_GameNameCache.clear();
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

        // ── Remove depots that were unloaded ──
        std::vector<AppId_t> removals = LuaLoader::TakePendingRemovals();
        uint32_t removedCount = 0;
        for (AppId_t id : removals) {
            if (pPkg->AppIdVec.FindAndFastRemove(id)) {
                ++removedCount;
                LOG_PACKAGE_DEBUG("NotifyLicenseChanged: removed AppId {}", id);
            }
        }

        // ── Add depots that are newly loaded ──
        std::vector<AppId_t> additions = LuaLoader::TakePendingAdditions();
        if (!additions.empty()) {
            uint32_t oldSize = pPkg->AppIdVec.m_Size;
            oCUtlMemoryGrow(&pPkg->AppIdVec, static_cast<uint32>(additions.size()));
            for (size_t i = 0; i < additions.size(); ++i) {
                pPkg->AppIdVec.m_Memory.m_pMemory[oldSize + i] = additions[i];
                LOG_PACKAGE_DEBUG("NotifyLicenseChanged: inserted AppId {} at [{}]", additions[i], oldSize + i);
            }

        }

        if (additions.empty() && removedCount == 0) {
            LOG_PACKAGE_DEBUG("NotifyLicenseChanged: no changes");
            return;
        }

        // Mark package 0 as changed and trigger library refresh.
        oMarkLicenseAsChanged(g_pCUser, 0, true);
        oProcessPendingLicenseUpdates(g_pCUser);
        LOG_PACKAGE_INFO("NotifyLicenseChanged: {} added, {} removed", additions.size(), removedCount);
    }
}
