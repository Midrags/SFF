// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

// Tracks which hook installers landed and which couldn't resolve their target
// through the runtime TOML. The result lands in <Steam>\lumacore\status.json
// so SteaMidra can surface a banner when the running Steam build doesn't have
// a pattern emitted yet.
//
// Threading: every public function takes the same internal mutex, so call
// sites don't have to coordinate. Mutator calls made after init completes
// (signalled by the first WriteToDisk) re-publish the file in place so the
// banner reflects the latest counts.
//
// Schema produced by WriteToDisk (top-level keys only, exact set):
//   build_id            string
//   lumacore_build_stamp string (__DATE__ + __TIME__ from the DLL)
//   build_config        string (Debug or Release)
//   logging_enabled     boolean (false in shipped Release)
//   diagnostics_enabled boolean (true in standard builds)
//   protobuf_runtime    string (full or lite)
//   startup_capture_revision string (purchase-race fix marker)
//   toml_found          object with exactly steamclient and steamui booleans
//   hooks_installed     non-negative integer (count of RecordInstalled calls)
//   hooks_missed        array of strings (names from RecordMissed)
//   steamclient_sha     string (empty when unknown)
//   steamui_sha         string (empty when unknown)
//   loader              string (proxy that loaded LumaCore)
//   hook_target         string (diversion or active_steamclient)
//   hook_module         string (path used for steamclient hook resolution)

#include <cstdint>
#include <string>
#include <string_view>

namespace HookStatus {

    void SetBuildId(std::string buildId);
    void SetBinarySnapshot(std::string steamExePath,
                           std::string steamclientPath,
                           std::string steamuiPath,
                           std::string diversionPath,
                           std::string steamclientFileSha,
                           std::string steamuiFileSha,
                           std::string diversionFileSha);
    void SetLoaderState(std::string loader, std::string hookTarget, std::string hookModule);
    void SetPackageState(bool package0Captured, bool package0Seeded,
                         bool startupInjectionDone, bool licenseRefreshDone);
    void SetLuaCounts(std::uint64_t files, std::uint64_t depots,
                      std::uint64_t libraryRoots, std::uint64_t statsRoots);
    void RecordPackage0Seen(std::int32_t status, std::uint32_t appVecSize,
                            std::uint32_t luaAddCount);
    void RecordPackage0Capture(std::string source, bool luaReady);
    void RecordStartupPackageRetry(std::string reason);
    void RecordPackageContainment(std::int32_t status, std::uint32_t appVecSize,
                                  std::uint64_t expected, std::uint64_t present,
                                  std::uint64_t missing, std::uint64_t appended,
                                  std::string reason);
    void RecordHotReload(std::uint32_t additions, std::uint32_t removals,
                         std::uint32_t uiTouches, std::uint32_t uiRemovals,
                         std::string reason);
    void RecordOwnershipCheck(std::uint32_t appId, bool patched,
                              bool directOwned, bool familyShared,
                              std::int32_t releaseState,
                              std::uint32_t existInPackageNums,
                              bool borrowedFlag, bool familySharedFlag);
    void RecordSubscribedApps(std::uint32_t original, std::uint64_t roots,
                              std::uint32_t written, std::uint32_t advertised,
                              std::uint32_t buffer);
    void RecordCloudDecision(std::uint32_t appId, bool tracked, bool managed,
                             bool owned, bool familyShared, bool original,
                             bool finalValue, std::string reason);
    void RecordCloudCloseState(std::uint32_t appId, std::string result,
                               bool ownerCaptured, bool sehDisabled);
    void RecordCloudSyncGate(std::uint32_t appId, std::string stage,
                             std::string result, std::string reason,
                             bool attached);
    void RecordPatternStatus(std::string moduleName, std::string source,
                             bool cacheHit, std::string networkResult,
                             std::string lastError);
    void RecordSteamUiLateRetry(std::string result);
    void RecordSteamStubDetection(std::uint32_t appId, std::string source,
                                  std::string method, std::string image,
                                  std::uint64_t candidates,
                                  bool routeAccepted, std::string routeReason);
    void RecordOnlineFixPayload(std::uint32_t appId, std::uint32_t pid,
                                std::string image, std::string state,
                                std::string detail);
    void RecordStatsState(std::uint32_t appId, std::string protocol,
                          std::uint64_t poolIndex, std::uint64_t poolCount,
                          std::string matchSource, std::int32_t originalResult,
                          std::string finalResult);
    void SetStartupPhase(std::string phase);
    void SetStartupRefreshState(std::string state);
    void SetStartupSafety(std::string phase, bool safe, std::string deferredReason);
    void SetMappedLoaders(std::string mappedLoaders);
    void SetDiversionState(bool validated, std::string reason);
    void SetDiversionDetails(bool fileReady, bool loadReady,
                             std::string strategy, std::string lastError);
    void SetSteamUiAttachState(std::string state, int attempts, bool activeFallbackUsed);

    // Module names accepted: "steamclient" and "steamui". Anything else is
    // ignored with a warning log line.
    void SetTomlAvailability(std::string_view moduleName, bool found);

    void SetShas(std::string steamclientSha, std::string steamuiSha);

    void RecordInstalled();
    void RecordMissed(std::string hookName);

    // Writes the current snapshot to <Steam>\lumacore\status.json via a
    // tmp + MoveFileExA(MOVEFILE_REPLACE_EXISTING) swap. Best-effort: failures
    // log a warning and never throw. The first successful or attempted write
    // marks init as complete, after which every mutator re-publishes.
    void WriteToDisk();

}  // namespace HookStatus

