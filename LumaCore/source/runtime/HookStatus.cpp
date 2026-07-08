// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "HookStatus.h"

#include "runtime/Logger.h"
#include "core/entry.h"

#include <windows.h>

#include <cstdio>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

namespace HookStatus {

    namespace {

        std::mutex g_mu;

        std::string g_buildId;
        std::string g_steamExePath;
        std::string g_steamclientPath;
        std::string g_steamuiPath;
        std::string g_diversionPath;
        std::string g_steamclientFileSha;
        std::string g_steamuiFileSha;
        std::string g_diversionFileSha;
        std::string g_steamclientSha;
        std::string g_steamuiSha;
        std::string g_loader;
        std::string g_hookTarget;
        std::string g_hookModule;
        std::string g_mappedLoaders;
        bool        g_package0Captured = false;
        bool        g_package0Seeded = false;
        bool        g_startupInjectionDone = false;
        bool        g_licenseRefreshDone = false;
        std::string g_startupPhase = "boot";
        std::string g_startupRefreshState = "idle";
        std::string g_steamLoginPhase = "init";
        bool        g_startupSafe = false;
        std::string g_packageMutationDeferredReason = "not_evaluated";
        bool        g_diversionValidated = false;
        std::string g_diversionReason;
        bool        g_diversionFileReady = false;
        bool        g_diversionLoadReady = false;
        std::string g_diversionStrategy;
        std::string g_diversionLastError;
        std::string g_steamUiAttachState;
        int         g_steamUiAttachAttempts = 0;
        bool        g_activeFallbackUsed = false;
        bool        g_steamclientToml = false;
        bool        g_steamuiToml     = false;
        std::uint64_t            g_installed = 0;
        std::vector<std::string> g_missed;
        bool        g_initDone        = false;
        std::uint64_t g_luaFilesLoaded = 0;
        std::uint64_t g_luaDepotIds = 0;
        std::uint64_t g_luaLibraryRoots = 0;
        std::uint64_t g_luaStatsRoots = 0;
        std::uint64_t g_package0SeenCount = 0;
        std::int32_t  g_lastPackage0Status = -1;
        std::uint32_t g_lastPackage0AppVecSize = 0;
        std::uint32_t g_lastPackage0LuaAddCount = 0;
        std::uint64_t g_package0ExpectedIds = 0;
        std::uint64_t g_package0PresentIds = 0;
        std::uint64_t g_package0MissingIds = 0;
        std::uint64_t g_package0AppendedIds = 0;
        std::string   g_lastPackageInjectionReason;
        std::string   g_package0CaptureSource;
        bool          g_package0CapturedBeforeLuaReady = false;
        std::uint64_t g_runFramePackageRetryCount = 0;
        std::string   g_lastStartupRetryReason;
        std::uint32_t g_lastHotReloadAdditions = 0;
        std::uint32_t g_lastHotReloadRemovals = 0;
        std::uint32_t g_lastUiTouchQueued = 0;
        std::uint32_t g_lastUiRemovalQueued = 0;
        std::string   g_lastHotReloadReason;
        std::uint64_t g_ownershipCheckCount = 0;
        std::uint64_t g_ownershipPatchedCount = 0;
        std::uint64_t g_ownershipDirectOwnedCount = 0;
        std::uint64_t g_ownershipFamilySharedCount = 0;
        std::uint32_t g_lastOwnershipAppId = 0;
        bool          g_lastOwnershipPatched = false;
        bool          g_lastOwnershipDirectOwned = false;
        bool          g_lastOwnershipFamilyShared = false;
        std::int32_t  g_lastOwnershipReleaseState = -1;
        std::uint32_t g_lastOwnershipExistInPackageNums = 0;
        bool          g_lastOwnershipBorrowedFlag = false;
        bool          g_lastOwnershipFamilySharedFlag = false;
        std::uint32_t g_getSubscribedOriginal = 0;
        std::uint64_t g_getSubscribedRoots = 0;
        std::uint32_t g_getSubscribedWritten = 0;
        std::uint32_t g_getSubscribedAdvertised = 0;
        std::uint32_t g_getSubscribedBuffer = 0;
        std::uint32_t g_lastCloudAppId = 0;
        bool          g_lastCloudTracked = false;
        bool          g_lastCloudManaged = false;
        bool          g_lastCloudOwned = false;
        bool          g_lastCloudFamilyShared = false;
        bool          g_lastCloudOriginal = false;
        bool          g_lastCloudFinal = false;
        std::string   g_lastCloudReason;
        std::uint32_t g_lastCloudCloseAppId = 0;
        std::string   g_lastCloudCloseResult;
        bool          g_cloudCloseOwnerCaptured = false;
        bool          g_cloudCloseSehDisabled = false;
        std::uint32_t g_lastCloudSyncAppId = 0;
        std::string   g_lastCloudSyncStage;
        std::string   g_lastCloudSyncResult;
        std::string   g_lastCloudSyncReason;
        bool          g_cloudSyncGateAttached = false;
        std::string   g_steamclientPatternSource;
        std::string   g_steamuiPatternSource;
        bool          g_steamclientPatternCacheHit = false;
        bool          g_steamuiPatternCacheHit = false;
        std::string   g_steamclientPatternNetwork;
        std::string   g_steamuiPatternNetwork;
        std::string   g_steamclientPatternError;
        std::string   g_steamuiPatternError;
        std::uint64_t g_steamUiLateRetryCount = 0;
        std::string   g_steamUiLateHookResult;
        std::uint32_t g_lastSteamStubAppId = 0;
        std::string   g_lastSteamStubSource;
        std::string   g_lastSteamStubMethod;
        std::string   g_lastSteamStubImage;
        std::uint64_t g_lastSteamStubCandidates = 0;
        bool          g_lastSteamStubRouteAccepted = false;
        std::string   g_lastSteamStubRouteReason;
        std::uint32_t g_lastOnlineFixPayloadAppId = 0;
        std::uint32_t g_lastOnlineFixPayloadPid = 0;
        std::string   g_lastOnlineFixPayloadImage;
        std::string   g_lastOnlineFixPayloadState;
        std::string   g_lastOnlineFixPayloadDetail;
        std::uint32_t g_lastStatsAppId = 0;
        std::string   g_lastStatsProtocol;
        std::uint64_t g_lastStatsPoolIndex = 0;
        std::uint64_t g_lastStatsPoolCount = 0;
        std::string   g_lastStatsMatchSource;
        std::int32_t  g_lastStatsOriginalResult = -1;
        std::string   g_lastStatsFinalResult;

#ifdef LUMACORE_LOGGING_ENABLED
        constexpr const char* kBuildConfig = "Debug";
        constexpr const char* kProtobufRuntime = "full";
#else
        constexpr const char* kBuildConfig = "Release";
        constexpr const char* kProtobufRuntime = "lite";
#endif

        constexpr const char* kLumaCoreBuildStamp = __DATE__ " " __TIME__;
        constexpr const char* kStartupCaptureRevision = "package0-early-capture-v1";

        // Conservative escaper for JSON string literals. The values we emit are
        // ASCII function names, hex SHAs, and decimal build ids, so anything
        // outside printable ASCII falls through to \uXXXX.
        std::string JsonEscape(std::string_view s) {
            std::string out;
            out.reserve(s.size() + 2);
            for (char ch : s) {
                unsigned char c = static_cast<unsigned char>(ch);
                switch (c) {
                    case '"':  out += "\\\""; break;
                    case '\\': out += "\\\\"; break;
                    case '\b': out += "\\b";  break;
                    case '\f': out += "\\f";  break;
                    case '\n': out += "\\n";  break;
                    case '\r': out += "\\r";  break;
                    case '\t': out += "\\t";  break;
                    default:
                        if (c < 0x20 || c > 0x7E) {
                            char buf[8];
                            std::snprintf(buf, sizeof(buf), "\\u%04X", c);
                            out += buf;
                        } else {
                            out += static_cast<char>(c);
                        }
                        break;
                }
            }
            return out;
        }

        std::string DiagnosticReasonLocked();

        // Caller already owns g_mu.
        std::string SerializeLocked() {
            std::string out;
            out.reserve(256 + g_missed.size() * 32);
            out += "{\n";
            out += "  \"build_id\": \"";
            out += JsonEscape(g_buildId);
            out += "\",\n";
            out += "  \"lumacore_build_stamp\": \"";
            out += JsonEscape(kLumaCoreBuildStamp);
            out += "\",\n";
            out += "  \"build_config\": \"";
            out += JsonEscape(kBuildConfig);
            out += "\",\n";
            out += "  \"logging_enabled\": ";
#ifdef LUMACORE_LOGGING_ENABLED
            out += "true";
#else
            out += "false";
#endif
            out += ",\n";
            out += "  \"diagnostics_enabled\": ";
#ifdef LUMACORE_DIAGNOSTICS_ENABLED
            out += "true";
#else
            out += "false";
#endif
            out += ",\n";
            out += "  \"protobuf_runtime\": \"";
            out += JsonEscape(kProtobufRuntime);
            out += "\",\n";
            out += "  \"startup_capture_revision\": \"";
            out += JsonEscape(kStartupCaptureRevision);
            out += "\",\n";
            out += "  \"steam_exe_path\": \"";
            out += JsonEscape(g_steamExePath);
            out += "\",\n";
            out += "  \"steamclient_path\": \"";
            out += JsonEscape(g_steamclientPath);
            out += "\",\n";
            out += "  \"steamui_path\": \"";
            out += JsonEscape(g_steamuiPath);
            out += "\",\n";
            out += "  \"diversion_path\": \"";
            out += JsonEscape(g_diversionPath);
            out += "\",\n";
            out += "  \"steamclient_file_sha\": \"";
            out += JsonEscape(g_steamclientFileSha);
            out += "\",\n";
            out += "  \"steamui_file_sha\": \"";
            out += JsonEscape(g_steamuiFileSha);
            out += "\",\n";
            out += "  \"diversion_file_sha\": \"";
            out += JsonEscape(g_diversionFileSha);
            out += "\",\n";
            out += "  \"toml_found\": {\n";
            out += "    \"steamclient\": ";
            out += g_steamclientToml ? "true" : "false";
            out += ",\n";
            out += "    \"steamui\": ";
            out += g_steamuiToml ? "true" : "false";
            out += "\n  },\n";
            out += "  \"pattern_status\": {\n";
            out += "    \"steamclient\": {\"source\": \"";
            out += JsonEscape(g_steamclientPatternSource);
            out += "\", \"cache_hit\": ";
            out += g_steamclientPatternCacheHit ? "true" : "false";
            out += ", \"network\": \"";
            out += JsonEscape(g_steamclientPatternNetwork);
            out += "\", \"error\": \"";
            out += JsonEscape(g_steamclientPatternError);
            out += "\"},\n";
            out += "    \"steamui\": {\"source\": \"";
            out += JsonEscape(g_steamuiPatternSource);
            out += "\", \"cache_hit\": ";
            out += g_steamuiPatternCacheHit ? "true" : "false";
            out += ", \"network\": \"";
            out += JsonEscape(g_steamuiPatternNetwork);
            out += "\", \"error\": \"";
            out += JsonEscape(g_steamuiPatternError);
            out += "\"}\n";
            out += "  },\n";
            out += "  \"steamui_late_retry_count\": ";
            out += std::to_string(g_steamUiLateRetryCount);
            out += ",\n";
            out += "  \"steamui_late_hook_result\": \"";
            out += JsonEscape(g_steamUiLateHookResult);
            out += "\",\n";
            out += "  \"hooks_installed\": ";
            out += std::to_string(g_installed);
            out += ",\n";
            out += "  \"hooks_missed\": [";
            for (size_t i = 0; i < g_missed.size(); ++i) {
                if (i) out += ", ";
                out += "\"";
                out += JsonEscape(g_missed[i]);
                out += "\"";
            }
            out += "],\n";
            out += "  \"steamclient_sha\": \"";
            out += JsonEscape(g_steamclientSha);
            out += "\",\n";
            out += "  \"steamui_sha\": \"";
            out += JsonEscape(g_steamuiSha);
            out += "\",\n";
            out += "  \"loader\": \"";
            out += JsonEscape(g_loader);
            out += "\",\n";
            out += "  \"hook_target\": \"";
            out += JsonEscape(g_hookTarget);
            out += "\",\n";
            out += "  \"hook_module\": \"";
            out += JsonEscape(g_hookModule);
            out += "\",\n";
            out += "  \"mapped_loaders\": \"";
            out += JsonEscape(g_mappedLoaders);
            out += "\",\n";
            out += "  \"package0_captured\": ";
            out += g_package0Captured ? "true" : "false";
            out += ",\n";
            out += "  \"package0_seeded\": ";
            out += g_package0Seeded ? "true" : "false";
            out += ",\n";
            out += "  \"startup_injection_done\": ";
            out += g_startupInjectionDone ? "true" : "false";
            out += ",\n";
            out += "  \"license_refresh_done\": ";
            out += g_licenseRefreshDone ? "true" : "false";
            out += ",\n";
            out += "  \"startup_phase\": \"";
            out += JsonEscape(g_startupPhase);
            out += "\",\n";
            out += "  \"startup_refresh_state\": \"";
            out += JsonEscape(g_startupRefreshState);
            out += "\",\n";
            out += "  \"steam_login_phase\": \"";
            out += JsonEscape(g_steamLoginPhase);
            out += "\",\n";
            out += "  \"startup_safe\": ";
            out += g_startupSafe ? "true" : "false";
            out += ",\n";
            out += "  \"package_mutation_deferred_reason\": \"";
            out += JsonEscape(g_packageMutationDeferredReason);
            out += "\",\n";
            out += "  \"diversion_validated\": ";
            out += g_diversionValidated ? "true" : "false";
            out += ",\n";
            out += "  \"diversion_reason\": \"";
            out += JsonEscape(g_diversionReason);
            out += "\",\n";
            out += "  \"diversion_file_ready\": ";
            out += g_diversionFileReady ? "true" : "false";
            out += ",\n";
            out += "  \"diversion_load_ready\": ";
            out += g_diversionLoadReady ? "true" : "false";
            out += ",\n";
            out += "  \"diversion_strategy\": \"";
            out += JsonEscape(g_diversionStrategy);
            out += "\",\n";
            out += "  \"diversion_last_error\": \"";
            out += JsonEscape(g_diversionLastError);
            out += "\",\n";
            out += "  \"steamui_attach_state\": \"";
            out += JsonEscape(g_steamUiAttachState);
            out += "\",\n";
            out += "  \"steamui_attach_attempts\": ";
            out += std::to_string(g_steamUiAttachAttempts);
            out += ",\n";
            out += "  \"active_fallback_used\": ";
            out += g_activeFallbackUsed ? "true" : "false";
            out += ",\n";
            out += "  \"lua_files_loaded\": ";
            out += std::to_string(g_luaFilesLoaded);
            out += ",\n";
            out += "  \"lua_depot_ids\": ";
            out += std::to_string(g_luaDepotIds);
            out += ",\n";
            out += "  \"lua_library_roots\": ";
            out += std::to_string(g_luaLibraryRoots);
            out += ",\n";
            out += "  \"lua_stats_roots\": ";
            out += std::to_string(g_luaStatsRoots);
            out += ",\n";
            out += "  \"package0_seen_count\": ";
            out += std::to_string(g_package0SeenCount);
            out += ",\n";
            out += "  \"last_package0_status\": ";
            out += std::to_string(g_lastPackage0Status);
            out += ",\n";
            out += "  \"last_package0_appvec_size\": ";
            out += std::to_string(g_lastPackage0AppVecSize);
            out += ",\n";
            out += "  \"last_package0_lua_add_count\": ";
            out += std::to_string(g_lastPackage0LuaAddCount);
            out += ",\n";
            out += "  \"package0_expected_ids\": ";
            out += std::to_string(g_package0ExpectedIds);
            out += ",\n";
            out += "  \"package0_present_ids\": ";
            out += std::to_string(g_package0PresentIds);
            out += ",\n";
            out += "  \"package0_missing_ids\": ";
            out += std::to_string(g_package0MissingIds);
            out += ",\n";
            out += "  \"package0_appended_ids\": ";
            out += std::to_string(g_package0AppendedIds);
            out += ",\n";
            out += "  \"last_package_injection_reason\": \"";
            out += JsonEscape(g_lastPackageInjectionReason);
            out += "\",\n";
            out += "  \"package0_capture_source\": \"";
            out += JsonEscape(g_package0CaptureSource);
            out += "\",\n";
            out += "  \"package0_captured_before_lua_ready\": ";
            out += g_package0CapturedBeforeLuaReady ? "true" : "false";
            out += ",\n";
            out += "  \"runframe_package_retry_count\": ";
            out += std::to_string(g_runFramePackageRetryCount);
            out += ",\n";
            out += "  \"last_startup_retry_reason\": \"";
            out += JsonEscape(g_lastStartupRetryReason);
            out += "\",\n";
            out += "  \"last_hot_reload_additions\": ";
            out += std::to_string(g_lastHotReloadAdditions);
            out += ",\n";
            out += "  \"last_hot_reload_removals\": ";
            out += std::to_string(g_lastHotReloadRemovals);
            out += ",\n";
            out += "  \"last_ui_touch_queued\": ";
            out += std::to_string(g_lastUiTouchQueued);
            out += ",\n";
            out += "  \"last_ui_removal_queued\": ";
            out += std::to_string(g_lastUiRemovalQueued);
            out += ",\n";
            out += "  \"last_hot_reload_reason\": \"";
            out += JsonEscape(g_lastHotReloadReason);
            out += "\",\n";
            out += "  \"ownership_check_count\": ";
            out += std::to_string(g_ownershipCheckCount);
            out += ",\n";
            out += "  \"ownership_patched_count\": ";
            out += std::to_string(g_ownershipPatchedCount);
            out += ",\n";
            out += "  \"ownership_direct_owned_count\": ";
            out += std::to_string(g_ownershipDirectOwnedCount);
            out += ",\n";
            out += "  \"ownership_family_shared_count\": ";
            out += std::to_string(g_ownershipFamilySharedCount);
            out += ",\n";
            out += "  \"last_ownership_appid\": ";
            out += std::to_string(g_lastOwnershipAppId);
            out += ",\n";
            out += "  \"last_ownership_patched\": ";
            out += g_lastOwnershipPatched ? "true" : "false";
            out += ",\n";
            out += "  \"last_ownership_direct_owned\": ";
            out += g_lastOwnershipDirectOwned ? "true" : "false";
            out += ",\n";
            out += "  \"last_ownership_family_shared\": ";
            out += g_lastOwnershipFamilyShared ? "true" : "false";
            out += ",\n";
            out += "  \"last_ownership_release_state\": ";
            out += std::to_string(g_lastOwnershipReleaseState);
            out += ",\n";
            out += "  \"last_ownership_exist_in_package_nums\": ";
            out += std::to_string(g_lastOwnershipExistInPackageNums);
            out += ",\n";
            out += "  \"last_ownership_borrowed_flag\": ";
            out += g_lastOwnershipBorrowedFlag ? "true" : "false";
            out += ",\n";
            out += "  \"last_ownership_family_shared_flag\": ";
            out += g_lastOwnershipFamilySharedFlag ? "true" : "false";
            out += ",\n";
            out += "  \"getsubscribed_original\": ";
            out += std::to_string(g_getSubscribedOriginal);
            out += ",\n";
            out += "  \"getsubscribed_roots\": ";
            out += std::to_string(g_getSubscribedRoots);
            out += ",\n";
            out += "  \"getsubscribed_written\": ";
            out += std::to_string(g_getSubscribedWritten);
            out += ",\n";
            out += "  \"getsubscribed_advertised\": ";
            out += std::to_string(g_getSubscribedAdvertised);
            out += ",\n";
            out += "  \"getsubscribed_buffer\": ";
            out += std::to_string(g_getSubscribedBuffer);
            out += ",\n";
            out += "  \"last_cloud_appid\": ";
            out += std::to_string(g_lastCloudAppId);
            out += ",\n";
            out += "  \"last_cloud_tracked\": ";
            out += g_lastCloudTracked ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_managed\": ";
            out += g_lastCloudManaged ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_owned\": ";
            out += g_lastCloudOwned ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_family_shared\": ";
            out += g_lastCloudFamilyShared ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_original\": ";
            out += g_lastCloudOriginal ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_final\": ";
            out += g_lastCloudFinal ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_reason\": \"";
            out += JsonEscape(g_lastCloudReason);
            out += "\",\n";
            out += "  \"last_cloud_close_appid\": ";
            out += std::to_string(g_lastCloudCloseAppId);
            out += ",\n";
            out += "  \"last_cloud_close_result\": \"";
            out += JsonEscape(g_lastCloudCloseResult);
            out += "\",\n";
            out += "  \"cloud_close_owner_captured\": ";
            out += g_cloudCloseOwnerCaptured ? "true" : "false";
            out += ",\n";
            out += "  \"cloud_close_seh_disabled\": ";
            out += g_cloudCloseSehDisabled ? "true" : "false";
            out += ",\n";
            out += "  \"last_cloud_sync_appid\": ";
            out += std::to_string(g_lastCloudSyncAppId);
            out += ",\n";
            out += "  \"last_cloud_sync_stage\": \"";
            out += JsonEscape(g_lastCloudSyncStage);
            out += "\",\n";
            out += "  \"last_cloud_sync_result\": \"";
            out += JsonEscape(g_lastCloudSyncResult);
            out += "\",\n";
            out += "  \"last_cloud_sync_reason\": \"";
            out += JsonEscape(g_lastCloudSyncReason);
            out += "\",\n";
            out += "  \"cloud_sync_gate_attached\": ";
            out += g_cloudSyncGateAttached ? "true" : "false";
            out += ",\n";
            out += "  \"last_steamstub_appid\": ";
            out += std::to_string(g_lastSteamStubAppId);
            out += ",\n";
            out += "  \"last_steamstub_source\": \"";
            out += JsonEscape(g_lastSteamStubSource);
            out += "\",\n";
            out += "  \"last_steamstub_method\": \"";
            out += JsonEscape(g_lastSteamStubMethod);
            out += "\",\n";
            out += "  \"last_steamstub_image\": \"";
            out += JsonEscape(g_lastSteamStubImage);
            out += "\",\n";
            out += "  \"last_steamstub_candidates\": ";
            out += std::to_string(g_lastSteamStubCandidates);
            out += ",\n";
            out += "  \"last_steamstub_route_accepted\": ";
            out += g_lastSteamStubRouteAccepted ? "true" : "false";
            out += ",\n";
            out += "  \"last_steamstub_route_reason\": \"";
            out += JsonEscape(g_lastSteamStubRouteReason);
            out += "\",\n";
            out += "  \"last_onlinefix_payload_appid\": ";
            out += std::to_string(g_lastOnlineFixPayloadAppId);
            out += ",\n";
            out += "  \"last_onlinefix_payload_pid\": ";
            out += std::to_string(g_lastOnlineFixPayloadPid);
            out += ",\n";
            out += "  \"last_onlinefix_payload_image\": \"";
            out += JsonEscape(g_lastOnlineFixPayloadImage);
            out += "\",\n";
            out += "  \"last_onlinefix_payload_state\": \"";
            out += JsonEscape(g_lastOnlineFixPayloadState);
            out += "\",\n";
            out += "  \"last_onlinefix_payload_detail\": \"";
            out += JsonEscape(g_lastOnlineFixPayloadDetail);
            out += "\",\n";
            out += "  \"last_stats_appid\": ";
            out += std::to_string(g_lastStatsAppId);
            out += ",\n";
            out += "  \"last_stats_protocol\": \"";
            out += JsonEscape(g_lastStatsProtocol);
            out += "\",\n";
            out += "  \"last_stats_pool_index\": ";
            out += std::to_string(g_lastStatsPoolIndex);
            out += ",\n";
            out += "  \"last_stats_pool_count\": ";
            out += std::to_string(g_lastStatsPoolCount);
            out += ",\n";
            out += "  \"last_stats_match_source\": \"";
            out += JsonEscape(g_lastStatsMatchSource);
            out += "\",\n";
            out += "  \"last_stats_original_result\": ";
            out += std::to_string(g_lastStatsOriginalResult);
            out += ",\n";
            out += "  \"last_stats_final_result\": \"";
            out += JsonEscape(g_lastStatsFinalResult);
            out += "\",\n";
            out += "  \"diagnostic_reason\": \"";
            out += JsonEscape(DiagnosticReasonLocked());
            out += "\"";
            out += "\n";
            out += "}\n";
            return out;
        }

        bool WriteBodyAtomic(const std::string& body) {
            if (!SteamInstallPath[0]) {
                LOG_WARN("HookStatus: SteamInstallPath unset, skipping write");
                return false;
            }
            std::filesystem::path dir = std::filesystem::path(SteamInstallPath) / "lumacore";
            std::error_code ec;
            std::filesystem::create_directories(dir, ec);
            if (ec) {
                LOG_WARN("HookStatus: create_directories failed: {}", ec.message());
                return false;
            }

            std::filesystem::path target = dir / "status.json";
            std::filesystem::path tmp    = target;
            tmp += ".tmp";

            std::string narrowTmp    = tmp.string();
            std::string narrowTarget = target.string();

            {
                std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
                if (!f) {
                    LOG_WARN("HookStatus: open tmp failed for {}", narrowTarget);
                    DeleteFileA(narrowTmp.c_str());
                    return false;
                }
                f.write(body.data(), static_cast<std::streamsize>(body.size()));
                f.flush();
                if (!f) {
                    LOG_WARN("HookStatus: write tmp failed for {}", narrowTarget);
                    f.close();
                    DeleteFileA(narrowTmp.c_str());
                    return false;
                }
            }

            if (!MoveFileExA(narrowTmp.c_str(), narrowTarget.c_str(),
                             MOVEFILE_REPLACE_EXISTING)) {
                DWORD err = GetLastError();
                LOG_WARN("HookStatus: MoveFileExA failed err={} for {}",
                         err, narrowTarget);
                DeleteFileA(narrowTmp.c_str());
                return false;
            }
            return true;
        }

        // Called from any mutator while holding g_mu. Re-publishes the file
        // only after the first explicit WriteToDisk has flipped g_initDone.
        void MaybeRepublishLocked() {
            if (!g_initDone) return;
            std::string body = SerializeLocked();
            (void)WriteBodyAtomic(body);
        }

        bool CsvHasToken(std::string_view csv, std::string_view token) {
            if (token.empty()) return true;
            size_t start = 0;
            while (start <= csv.size()) {
                const size_t comma = csv.find(',', start);
                const size_t end = comma == std::string_view::npos ? csv.size() : comma;
                if (csv.substr(start, end - start) == token)
                    return true;
                if (comma == std::string_view::npos)
                    break;
                start = comma + 1;
            }
            return false;
        }

        void MergeCsvTokens(std::string& target, std::string_view incoming) {
            size_t start = 0;
            while (start <= incoming.size()) {
                const size_t comma = incoming.find(',', start);
                const size_t end = comma == std::string_view::npos ? incoming.size() : comma;
                const std::string_view token = incoming.substr(start, end - start);
                if (!CsvHasToken(target, token)) {
                    if (!target.empty()) target += ',';
                    target.append(token.data(), token.size());
                }
                if (comma == std::string_view::npos)
                    break;
                start = comma + 1;
            }
        }

        std::string DiagnosticReasonLocked() {
            if (!g_steamclientToml || !g_steamuiToml) {
                const bool clientNoCache =
                    !g_steamclientToml &&
                    (g_steamclientPatternSource.empty() ||
                     g_steamclientPatternSource == "none");
                const bool uiNoCache =
                    !g_steamuiToml &&
                    (g_steamuiPatternSource.empty() ||
                     g_steamuiPatternSource == "none");
                const bool noCache = clientNoCache || uiNoCache;
                if (noCache) return "pattern-missing-no-cache";
                return "pattern-missing";
            }
            if (!g_missed.empty()) return "hooks-missed";
            if (g_luaFilesLoaded == 0 && g_luaDepotIds == 0) return "lua-empty";
            if (g_package0SeenCount == 0) {
                if (g_startupRefreshState == "package0-not-seen-after-retry")
                    return g_startupRefreshState;
                if (g_startupRefreshState == "startup-waiting-packageinfo")
                    return g_startupRefreshState;
                if (g_steamLoginPhase == "init") return "waiting-for-login";
                return "package0-not-seen";
            }
            if (g_lastPackage0Status != 0) return "package0-not-available";
            if (g_package0MissingIds > 0) return "package0-missing-lua-ids";
            if (g_startupRefreshState == "startup-waiting-packageinfo") return g_startupRefreshState;
            if (g_startupRefreshState == "startup-waiting-cuser") return g_startupRefreshState;
            if (g_startupRefreshState == "library-refresh-queued") return g_startupRefreshState;
            if (g_package0Captured && g_package0Seeded) return "startup-injected";
            return "package0-seen-not-seeded";
        }

    }  // namespace

    void SetBuildId(std::string buildId) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_buildId = std::move(buildId);
    }

    void SetBinarySnapshot(std::string steamExePath,
                           std::string steamclientPath,
                           std::string steamuiPath,
                           std::string diversionPath,
                           std::string steamclientFileSha,
                           std::string steamuiFileSha,
                           std::string diversionFileSha) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_steamExePath = std::move(steamExePath);
        g_steamclientPath = std::move(steamclientPath);
        g_steamuiPath = std::move(steamuiPath);
        g_diversionPath = std::move(diversionPath);
        g_steamclientFileSha = std::move(steamclientFileSha);
        g_steamuiFileSha = std::move(steamuiFileSha);
        g_diversionFileSha = std::move(diversionFileSha);
        MaybeRepublishLocked();
    }

    void SetLoaderState(std::string loader, std::string hookTarget, std::string hookModule) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_loader = std::move(loader);
        g_hookTarget = std::move(hookTarget);
        g_hookModule = std::move(hookModule);
        MaybeRepublishLocked();
    }

    void SetPackageState(bool package0Captured, bool package0Seeded,
                         bool startupInjectionDone, bool licenseRefreshDone) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_package0Captured = g_package0Captured || package0Captured;
        g_package0Seeded = g_package0Seeded || package0Seeded;
        g_startupInjectionDone = g_startupInjectionDone || startupInjectionDone;
        g_licenseRefreshDone = g_licenseRefreshDone || licenseRefreshDone;
        MaybeRepublishLocked();
    }

    void SetLuaCounts(std::uint64_t files, std::uint64_t depots,
                      std::uint64_t libraryRoots, std::uint64_t statsRoots) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_luaFilesLoaded = files;
        g_luaDepotIds = depots;
        g_luaLibraryRoots = libraryRoots;
        g_luaStatsRoots = statsRoots;
        MaybeRepublishLocked();
    }

    void RecordPackage0Seen(std::int32_t status, std::uint32_t appVecSize,
                            std::uint32_t luaAddCount) {
        std::lock_guard<std::mutex> lk(g_mu);
        ++g_package0SeenCount;
        g_lastPackage0Status = status;
        g_lastPackage0AppVecSize = appVecSize;
        g_lastPackage0LuaAddCount = luaAddCount;
        MaybeRepublishLocked();
    }

    void RecordPackage0Capture(std::string source, bool luaReady) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_package0Captured = true;
        if (g_package0CaptureSource.empty())
            g_package0CaptureSource = std::move(source);
        if (!luaReady)
            g_package0CapturedBeforeLuaReady = true;
        MaybeRepublishLocked();
    }

    void RecordStartupPackageRetry(std::string reason) {
        std::lock_guard<std::mutex> lk(g_mu);
        if (reason == "steamui-runframe-retry")
            ++g_runFramePackageRetryCount;
        g_lastStartupRetryReason = std::move(reason);
        MaybeRepublishLocked();
    }

    void RecordPackageContainment(std::int32_t status, std::uint32_t appVecSize,
                                  std::uint64_t expected, std::uint64_t present,
                                  std::uint64_t missing, std::uint64_t appended,
                                  std::string reason) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_package0Captured = true;
        g_package0Seeded = expected == 0 || missing == 0;
        g_lastPackage0Status = status;
        g_lastPackage0AppVecSize = appVecSize;
        g_package0ExpectedIds = expected;
        g_package0PresentIds = present;
        g_package0MissingIds = missing;
        g_package0AppendedIds = appended;
        g_lastPackageInjectionReason = std::move(reason);
        MaybeRepublishLocked();
    }

    void RecordHotReload(std::uint32_t additions, std::uint32_t removals,
                         std::uint32_t uiTouches, std::uint32_t uiRemovals,
                         std::string reason) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastHotReloadAdditions = additions;
        g_lastHotReloadRemovals = removals;
        g_lastUiTouchQueued = uiTouches;
        g_lastUiRemovalQueued = uiRemovals;
        g_lastHotReloadReason = std::move(reason);
        MaybeRepublishLocked();
    }

    void RecordOwnershipCheck(std::uint32_t appId, bool patched,
                              bool directOwned, bool familyShared,
                              std::int32_t releaseState,
                              std::uint32_t existInPackageNums,
                              bool borrowedFlag, bool familySharedFlag) {
        std::lock_guard<std::mutex> lk(g_mu);
        ++g_ownershipCheckCount;
        if (patched) ++g_ownershipPatchedCount;
        if (directOwned) ++g_ownershipDirectOwnedCount;
        if (familyShared) ++g_ownershipFamilySharedCount;
        g_lastOwnershipAppId = appId;
        g_lastOwnershipPatched = patched;
        g_lastOwnershipDirectOwned = directOwned;
        g_lastOwnershipFamilyShared = familyShared;
        g_lastOwnershipReleaseState = releaseState;
        g_lastOwnershipExistInPackageNums = existInPackageNums;
        g_lastOwnershipBorrowedFlag = borrowedFlag;
        g_lastOwnershipFamilySharedFlag = familySharedFlag;
        MaybeRepublishLocked();
    }

    void RecordSubscribedApps(std::uint32_t original, std::uint64_t roots,
                              std::uint32_t written, std::uint32_t advertised,
                              std::uint32_t buffer) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_getSubscribedOriginal = original;
        g_getSubscribedRoots = roots;
        g_getSubscribedWritten = written;
        g_getSubscribedAdvertised = advertised;
        g_getSubscribedBuffer = buffer;
        MaybeRepublishLocked();
    }

    void RecordCloudDecision(std::uint32_t appId, bool tracked, bool managed,
                             bool owned, bool familyShared, bool original,
                             bool finalValue, std::string reason) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastCloudAppId = appId;
        g_lastCloudTracked = tracked;
        g_lastCloudManaged = managed;
        g_lastCloudOwned = owned;
        g_lastCloudFamilyShared = familyShared;
        g_lastCloudOriginal = original;
        g_lastCloudFinal = finalValue;
        g_lastCloudReason = std::move(reason);
        MaybeRepublishLocked();
    }

    void RecordCloudCloseState(std::uint32_t appId, std::string result,
                               bool ownerCaptured, bool sehDisabled) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastCloudCloseAppId = appId;
        g_lastCloudCloseResult = std::move(result);
        g_cloudCloseOwnerCaptured = ownerCaptured;
        g_cloudCloseSehDisabled = sehDisabled;
        MaybeRepublishLocked();
    }

    void RecordCloudSyncGate(std::uint32_t appId, std::string stage,
                             std::string result, std::string reason,
                             bool attached) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastCloudSyncAppId = appId;
        g_lastCloudSyncStage = std::move(stage);
        g_lastCloudSyncResult = std::move(result);
        g_lastCloudSyncReason = std::move(reason);
        g_cloudSyncGateAttached = attached;
        MaybeRepublishLocked();
    }

    void RecordPatternStatus(std::string moduleName, std::string source,
                             bool cacheHit, std::string networkResult,
                             std::string lastError) {
        std::lock_guard<std::mutex> lk(g_mu);
        if (moduleName == "steamclient") {
            g_steamclientPatternSource = std::move(source);
            g_steamclientPatternCacheHit = cacheHit;
            g_steamclientPatternNetwork = std::move(networkResult);
            g_steamclientPatternError = std::move(lastError);
        } else if (moduleName == "steamui") {
            g_steamuiPatternSource = std::move(source);
            g_steamuiPatternCacheHit = cacheHit;
            g_steamuiPatternNetwork = std::move(networkResult);
            g_steamuiPatternError = std::move(lastError);
        } else {
            LOG_WARN("HookStatus: unknown module '{}' in RecordPatternStatus",
                     moduleName);
            return;
        }
        MaybeRepublishLocked();
    }

    void RecordSteamUiLateRetry(std::string result) {
        std::lock_guard<std::mutex> lk(g_mu);
        ++g_steamUiLateRetryCount;
        g_steamUiLateHookResult = std::move(result);
        MaybeRepublishLocked();
    }

    void RecordSteamStubDetection(std::uint32_t appId, std::string source,
                                  std::string method, std::string image,
                                  std::uint64_t candidates,
                                  bool routeAccepted, std::string routeReason) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastSteamStubAppId = appId;
        g_lastSteamStubSource = std::move(source);
        g_lastSteamStubMethod = std::move(method);
        g_lastSteamStubImage = std::move(image);
        g_lastSteamStubCandidates = candidates;
        g_lastSteamStubRouteAccepted = routeAccepted;
        g_lastSteamStubRouteReason = std::move(routeReason);
        MaybeRepublishLocked();
    }

    void RecordOnlineFixPayload(std::uint32_t appId, std::uint32_t pid,
                                std::string image, std::string state,
                                std::string detail) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastOnlineFixPayloadAppId = appId;
        g_lastOnlineFixPayloadPid = pid;
        g_lastOnlineFixPayloadImage = std::move(image);
        g_lastOnlineFixPayloadState = std::move(state);
        g_lastOnlineFixPayloadDetail = std::move(detail);
        MaybeRepublishLocked();
    }

    void RecordStatsState(std::uint32_t appId, std::string protocol,
                          std::uint64_t poolIndex, std::uint64_t poolCount,
                          std::string matchSource, std::int32_t originalResult,
                          std::string finalResult) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_lastStatsAppId = appId;
        g_lastStatsProtocol = std::move(protocol);
        g_lastStatsPoolIndex = poolIndex;
        g_lastStatsPoolCount = poolCount;
        g_lastStatsMatchSource = std::move(matchSource);
        g_lastStatsOriginalResult = originalResult;
        g_lastStatsFinalResult = std::move(finalResult);
        MaybeRepublishLocked();
    }

    void SetStartupPhase(std::string phase) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_startupPhase = std::move(phase);
        MaybeRepublishLocked();
    }

    void SetStartupRefreshState(std::string state) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_startupRefreshState = std::move(state);
        MaybeRepublishLocked();
    }

    void SetStartupSafety(std::string phase, bool safe, std::string deferredReason) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_steamLoginPhase = std::move(phase);
        g_startupSafe = safe;
        g_packageMutationDeferredReason = std::move(deferredReason);
        MaybeRepublishLocked();
    }

    void SetMappedLoaders(std::string mappedLoaders) {
        std::lock_guard<std::mutex> lk(g_mu);
        MergeCsvTokens(g_mappedLoaders, mappedLoaders);
        MaybeRepublishLocked();
    }

    void SetDiversionState(bool validated, std::string reason) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_diversionValidated = validated;
        g_diversionReason = std::move(reason);
        MaybeRepublishLocked();
    }

    void SetDiversionDetails(bool fileReady, bool loadReady,
                             std::string strategy, std::string lastError) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_diversionFileReady = fileReady;
        g_diversionLoadReady = loadReady;
        g_diversionStrategy = std::move(strategy);
        g_diversionLastError = std::move(lastError);
        MaybeRepublishLocked();
    }

    void SetSteamUiAttachState(std::string state, int attempts, bool activeFallbackUsed) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_steamUiAttachState = std::move(state);
        g_steamUiAttachAttempts = attempts;
        g_activeFallbackUsed = activeFallbackUsed;
        MaybeRepublishLocked();
    }

    void SetTomlAvailability(std::string_view moduleName, bool found) {
        std::lock_guard<std::mutex> lk(g_mu);
        if (moduleName == "steamclient") {
            g_steamclientToml = found;
        } else if (moduleName == "steamui") {
            g_steamuiToml = found;
        } else {
            LOG_WARN("HookStatus: unknown module '{}' in SetTomlAvailability",
                     std::string(moduleName));
            return;
        }
        MaybeRepublishLocked();
    }

    void SetShas(std::string steamclientSha, std::string steamuiSha) {
        std::lock_guard<std::mutex> lk(g_mu);
        g_steamclientSha = std::move(steamclientSha);
        g_steamuiSha     = std::move(steamuiSha);
        MaybeRepublishLocked();
    }

    void RecordInstalled() {
        std::lock_guard<std::mutex> lk(g_mu);
        ++g_installed;
    }

    void RecordMissed(std::string hookName) {
        if (hookName.empty()) return;
        std::lock_guard<std::mutex> lk(g_mu);
        g_missed.push_back(std::move(hookName));
    }

    void WriteToDisk() {
        std::string body;
        {
            std::lock_guard<std::mutex> lk(g_mu);
            body = SerializeLocked();
            g_initDone = true;
        }
        try {
            (void)WriteBodyAtomic(body);
        } catch (const std::exception& e) {
            LOG_WARN("HookStatus: write threw '{}'", e.what());
        } catch (...) {
            LOG_WARN("HookStatus: write threw unknown");
        }
    }

}  // namespace HookStatus
