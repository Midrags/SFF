#pragma once

#include "utils/ByteScan.h"
#include "StringFind.h"

// Byte-pattern signatures for every function LumaCore hooks in steamclient64.dll and steamui.dll.
//
// Steam updates its binaries regularly, so compiled function prologues shift between versions.
// Each array can hold multiple Signature entries — one per known Steam build number.
// At startup, entry.cpp reads the current build ID from steam.exe!GetBootstrapperVersion.
// ByteSearch then tries the entry whose label matches that ID first, and only falls back
// to the remaining entries if the preferred one fails to match.
// If nothing in the array matches the loaded binary, the hook is silently skipped
// and the function runs unmodified.
//
// Use ?? for bytes that vary across builds, such as small immediates, padding, or short offsets.
// "auto" entries are wildcarded fallbacks for builds not covered by specific build IDs.


// steamclient64.dll

// BuildSpawnEnvBlock: string XRef primary (update-proof), byte pattern fallback.
// Hooked to fix -onlinefix overlay: patches pOverlayCGameID from 480 to the real appid.
inline const StringXRefSig BuildSpawnEnvBlockStrSigs[] = {
    {"auto", "SteamOverlayGameId", 1},
    {"auto", "config/GameOverlay_CompatMode", 1},  // fallback if SteamOverlayGameId moves
};

inline const Signature BuildSpawnEnvBlockSigs[] = {
    {"1779155395", "4C 89 4C 24 ?? 4C 89 44 24 ?? 48 89 54 24 ?? 48 89 4C 24 ?? 55 53 56 57 41 54 41 55 41 56 41 57 48 8D AC 24 ?? ?? ?? ?? 48 81 EC ?? ?? ?? ?? 48 8B 05"},  // beta
    {"1778281814", "48 89 5C 24 ?? 4C 89 44 24 ?? 48 89 54 24 ?? 48 89 4C 24 ?? 55 56 57 41 54 41 55 41 56 41 57 48 8D AC 24 ?? ?? ?? ?? 48 81 EC ?? ?? ?? ?? 48 8B 05"},  // stable
};

// OptedInMask: string XRef primary, byte pattern fallback.
// Hooked to fix -onlinefix controller support: redirects appid 480 to the real appid.
inline const StringXRefSig OptedInMaskStrSigs[] = {
    {"auto", "GSteamEngine().IsEngineThreadRunning()", 1},
};

inline const Signature OptedInMaskSigs[] = {
    {"1779155395", "89 54 24 ?? 55 53 56 57 41 54 41 55 48 8D AC 24"},  // beta
    {"1778281814", "89 54 24 ?? 55 53 56 41 55 41 56 41 57"},           // stable
};

inline const Signature BBuildAndAsyncSendFrameSigs[] = {
    {"1778803745", "48 8B C4 55 48 8D 68 A1 48 81 EC C0 00 00 00 48 89 70 18"},  // beta
    {"1778281814", "48 8B C4 55 48 8D 68 A1 48 81 EC C0 00 00 00"},              // stable
};

inline const Signature BuildDepotDependencySigs[] = {
    {"1778803745", "48 8B C4 4C 89 48 20 89 50 10 48 89 48 08 55 ?? 48 8D"},  // beta
    {"1778281814", "48 8B C4 4C 89 48 20 89 50 10 48 89 48 08 55 ?? 48 8D"},  // stable
};

inline const Signature CUtlBufferEnsureCapacitySigs[] = {
    {"1778803745", "48 89 5C 24 08 57 48 83 EC 30 48 8B D9 8D"},          // beta
    {"1778281814", "48 89 5C 24 ?? 57 48 83 EC ?? 0F B6 41 ?? 8D 7A"},    // stable
    {"auto",       "48 89 5C 24 08 57 48 83 EC ?? 0F B6 41 1F 8D"},       // future builds
};

inline const Signature CUtlMemoryGrowSigs[] = {
    {"1778803745", "48 89 5C 24 10 57 48 83 EC 30 8B FA 48 8B D9 8B 51 08"},  // beta
    {"1778281814", "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 30"},            // stable
    {"auto",       "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC ?? 8B 71 10 48 8B D9 8B 49 08 8B FA 8D 04 16 3B C1"},  // future builds
};

// CheckAppOwnership: string XRef primary, byte pattern fallback.
inline const StringXRefSig CheckAppOwnershipStrSigs[] = {
    {"auto", "CClientJobCancelLicenseForApp", 1},
};

inline const Signature CheckAppOwnershipSigs[] = {
    {"1778803745", "48 8B C4 89 50 10 48 89 48 08 55 53"},   // beta
    {"1778281814", "48 8B C4 89 50 10 55 53 48 8D 68 D8"},   // stable
    {"auto",       "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC ?? 48 8D B9 90 E1 FF FF 8B F2 B9 E8 ?? ?? ?? ?? 4E"},  // future builds
};

// GetAppDataFromAppInfo: string XRef primary, byte pattern fallback.
inline const StringXRefSig GetAppDataFromAppInfoStrSigs[] = {
    {"auto", "name_localized/%s", 1},
};

inline const Signature GetAppDataFromAppInfoSigs[] = {
    {"1778803745", "40 53 55 56 57 41 56 41 57 48 81 EC 78 01 00 00 41 C6 01 00"},                          // beta
    {"1778281814", "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 41 56 41 57 48 81 EC 70 01 00 00"},     // stable
    {"auto",       "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 41 56 41 57 48 81 EC 70"},              // future builds
};

inline const Signature GetAppIDForCurrentPipeSigs[] = {
    {"1778803745", "8B 81 30 0D 00 00 83 F8"},                                                              // beta
    {"1778281814", "48 83 EC 08 8B 81 30 0D 00 00 4C 8B D9 44 8B 91 D8 00 00 00 83 F8 FF"},                // stable
    {"auto",       "48 83 EC ?? 8B 81 30 0D"},                                                              // future builds
};

inline const Signature GetPackageInfoSigs[] = {
    {"1778803745", "48 89 5C 24 18 89 54 24 10 55 56 57 48 83 EC 20 44 8B 49 20"},  // beta
    {"1778281814", "48 89 6C 24 ?? 41 56 48 83 EC ?? 8B 41 ?? 49 8B E8"},           // stable
    {"auto",       "48 89 6C 24 20 41 56 48 83 EC ?? 8B 41 20"},                    // future builds
};

// GetPipeClient: string XRef primary (two strings for robustness), byte pattern fallback.
inline const StringXRefSig GetPipeClientStrSigs[] = {
    {"auto", "error: IPCServer can't be cross user session but not cross process.", 1},
    {"auto", "error: InitIPC called on an initialized IPCServer with conflicting cross-process/session flag.", 1},
};

inline const Signature GetPipeClientSigs[] = {
    {"1778803745", "85 D2 74 ?? 44 0F B7 CA"},  // beta
    {"1778281814", "85 D2 74 ?? 44 0F B7 CA"},  // stable
    {"auto",       "40 53 56 57 41 56 48 83 EC ?? 48 8B F2"},  // future builds
};

// IPCProcessMessage: string XRef primary, byte pattern fallback.
inline const StringXRefSig IPCProcessMessageStrSigs[] = {
    {"auto", "Unknown IPC command code /+/ %u.  %s", 1},
};

inline const Signature IPCProcessMessageSigs[] = {
    {"1778803745", "48 89 5C 24 18 48 89 6C 24 20 57 41 54 41 55 41 56 41 57 48"},                          // beta
    {"1778281814", "48 89 5C 24 ?? 48 89 6C 24 ?? 56 41 54 41 55 41 56 41 57 48 83 EC ?? 49 8B D9"},        // stable
    {"auto",       "48 89 5C 24 18 48 89 6C 24 20 56 41 54 41 55"},                                         // future builds
};

inline const Signature KeyValues_FindOrCreateKeySigs[] = {
    {"1778803745", "48 2B D1 F6 C1 07 74 14"},                                                              // beta
    {"1778281814", "48 8B C4 4C 89 48 20 57 48 81 EC 60 04 00 00 48 89 70 E8 48 8B FA"},                   // stable
};

inline const Signature KeyValues_ReadAsBinarySigs[] = {
    {"1778803745", "48 8B C4 44 88 48 20 55"},                                                              // beta
    {"1778281814", "48 8B C4 44 88 48 20 44 89 40 18 55 57 48 8D 68 A9 48 81 EC B8 00 00 00"},             // stable
    {"auto",       "48 8B C4 44 88 48 20 44 89"},                                                           // future builds
};

inline const Signature LoadDepotDecryptionKeySigs[] = {
    {"1778803745", "40 53 55 56 57 48 83 EC 38 48 63 FA 49 8B E9"},  // beta
    {"1778281814", "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 48 83 EC 30 48 63 FA 49 8B E9 8B D7 49 8B D8 48 8B F1"},  // stable
    {"auto",       "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 48 83 EC ?? 48 63 FA 49 8B E9 ?? ?? ?? ?? D8 48 8B F1 E8 ?? ?? ?? ?? 84 C0 0F 84 ?? ?? ?? ?? 44 8B C7 41 83 E8 ?? ?? ?? ?? 83 E8 ?? ?? ?? ?? 83 E8 ?? ?? ?? ?? 83 F8 01"},  // future builds
};

inline const Signature LoadPackageSigs[] = {
    {"1778281814", "48 89 5C 24 18 48 89 6C 24 20 56 57 41 54 41 55 41 57 48 81 EC 20 01"},  // stable (verified correct)
    {"auto",       "48 89 5C 24 18 48 89 6C 24 20 56 57 41 54 41 55 41 57 48"},              // future builds
};

inline const Signature MarkLicenseAsChangedSigs[] = {
    {"1778803745", "48 89 5C 24 20 89 54 24 10 55 56 57 48 83 EC 20"},  // beta
    {"1778281814", "89 54 24 ?? 53 55 56 57 41 56 48 83 EC"},           // stable
    {"auto",       "89 54 24 10 53 55 56 57 41 56 48 83 EC ?? 48"},     // future builds
};

inline const Signature PchMsgNameFromEMsgSigs[] = {
    {"1778803745", "48 89 5C 24 08 57 48 83 EC 20 8B D9 E8"},  // beta
    {"1778281814", "48 89 5C 24 08 57 48 83 EC 20 8B D9 E8"},  // stable
    {"auto",       "48 89 5C 24 08 57 48 83 EC ?? 8B D9 E8"},  // future builds (wildcards stack size)
};

inline const Signature ProcessPendingLicenseUpdatesSigs[] = {
    {"1778803745", "41 56 41 57 48 83 EC 38 83"},                                    // beta
    {"1778281814", "4C 8B DC 49 89 4B 08 41 55 41 57 48 83 EC 48 4C 8B E9"},        // stable
    {"auto",       "4C 8B DC 49 89 4B 08 41 55 41 57 48 83 EC ?? 4C"},              // future builds
};

inline const Signature RecvPktSigs[] = {
    {"1778803745", "48 8B C4 55 48 8D A8 98 F6 FF FF 48 81 EC 60 0A"},  // beta
    {"1778281814", "48 8B C4 55 48 8D A8 98 F6 FF FF 48 81 EC 60 0A"},  // stable
};

inline const Signature SendCallbackToPipeSigs[] = {
    {"1778803745", "48 89 5C 24 ?? 57 48 83 EC ?? 41 8B D9 41 8B F8 E8 ?? ?? ?? ?? 48 8B C8"},  // beta
    {"1778281814", "48 89 5C 24 ?? 57 48 83 EC ?? 41 8B D9 41 8B F8 E8 ?? ?? ?? ?? 48 8B C8"},  // stable
};

// SpawnProcess: string XRef primary, byte pattern fallback.
inline const StringXRefSig SpawnProcessStrSigs[] = {
    {"auto", "extended/AllowElevation", 1},
};

inline const Signature SpawnProcessSigs[] = {
    {"1778803745", "48 89 5C 24 18 4C 89 4C 24 20 48 89 54 24 10 55 56 57 41 54 41 55 41 56 41 57 48 8D"},  // beta
    {"1778281814", "48 89 5C 24 18 4C 89 4C 24 20 48 89 54 24 10 55 56 57 41 54 41 55 41 56 41 57 48 8D"},  // stable
};

inline const Signature CheckDepotLicenseSigs[] = {
    {"auto", "48 89 5C 24 08 48 89 74 24 10 48 89 7C 24 18 55 41 54 41 55 41 56 41 57 48 8B EC 48 83 EC ?? 45 8B"},
};

inline const Signature BUpdateLicensesSigs[] = {
    {"auto", "40 53 48 83 EC ?? 48 8B 05 ?? ?? ?? ?? 48 8B D9 C7"},
};

// License hook functions — string XRef primary, byte pattern fallback

inline const StringXRefSig RequiresLegacyCDKeyStrSigs[] = {
    {"auto", "RequiresLegacyCDKey", 1},
};

inline const Signature RequiresLegacyCDKeySigs[] = {
    {"auto", "48 89 5C 24 18 55 56 57 48 83 EC ?? 49 8B E8 ?? ?? ?? ?? F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4C 24 30 45 33 C9 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? B2 01"},
};

inline const StringXRefSig GetSubscribedAppsStrSigs[] = {
    {"auto", "GetSubscribedApps", 1},
};

inline const Signature GetSubscribedAppsSigs[] = {
    {"auto", "48 89 5C 24 10 55 56 57 41 56 41 57 48 8B EC 48 83 EC ?? 41 0F"},
};

inline const StringXRefSig BUpdateAppOwnershipTicketStrSigs[] = {
    {"auto", "BUpdateAppOwnershipTicket", 1},
};

inline const Signature BUpdateAppOwnershipTicketSigs[] = {
    {"auto", "48 89 5C 24 20 55 56 57 48 8B EC 48 83 EC ?? 41 0F B6 F8 8B DA 48 8B F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4D D0 45 33 C9 E8 ?? ?? ?? ?? B2 01"},
};

inline const StringXRefSig BIsDlcEnabledStrSigs[] = {
    {"auto", "BIsDlcEnabled", 1},
};

inline const Signature BIsDlcEnabledSigs[] = {
    {"auto", "40 55 53 56 57 41 56 48 8B EC 48 83 EC ?? 4D 8B F1 41 8B F8 8B DA 48 8B F1 45 33 C9 48 8D 4D D0 BA 40 00 00 00 41 B8 20 00 00 00 E8 ?? ?? ?? ?? B2 01"},
};

inline const StringXRefSig IsAppDlcInstalledStrSigs[] = {
    {"auto", "IsAppDlcInstalled", 1},
};

inline const Signature IsAppDlcInstalledSigs[] = {
    {"auto", "48 89 5C 24 20 55 56 57 48 8B EC 48 83 EC ?? 41 8B F8 8B DA 48 8B F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4D D0 45 33 C9 E8 ?? ?? ?? ?? B2 01 48 8D 4D D0 E8 ?? ?? ?? ?? B2 11"},
};

inline const StringXRefSig IsCloudEnabledForAppStrSigs[] = {
    {"auto", "IsCloudEnabledForApp", 1},
};

inline const Signature IsCloudEnabledForAppSigs[] = {
    {"auto", "40 53 56 57 48 83 EC ?? 8B DA 48 8B F9 BA 40 00 00 00 48 8D 4C 24 30 45 33 C9 41 B8 20 00 00 00 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? B2 0D"},
};

inline const Signature IsUserSubscribedAppInTicketSigs[] = {
    {"auto", "40 53 56 57 48 83 EC ?? 41 8B F8 48 8B DA 48 8B F1 BA 40 00 00 00 41 B8 20 00 00 00 48 8D 4C 24 30 45 33 C9 E8 ?? ?? ?? ?? B2 01 48 8D 4C 24 30 E8 ?? ?? ?? ?? B2 01"},
};

// steamui.dll

// GetAppByID: resolves CSteamUIAppController::GetAppByID for RemoveAppOverview.
inline const Signature GetAppByIDSigs[] = {
    {"1779155395", "89 54 24 ?? 53 48 83 EC ?? 48 8B 05 ?? ?? ?? ?? 41 0F B6 D8"},  // beta
    {"1778281814", "89 54 24 ?? 56 48 83 EC ?? 48 8B 05"},                           // stable
    {"auto",       "89 54 24 10 56 48 83 EC ?? 48"},                                 // future builds
};

// TopManagerCall: anchor inside MarkAppChange; rel32 at +10 points to GetTopManager getter.
inline const Signature TopManagerCallSigs[] = {
    {"1779155395", "83 FE 07 0F 84 ?? ?? ?? ?? E8 ?? ?? ?? ?? 45 33 C0"},  // beta
    {"1778281814", "83 FF 07 0F 84 ?? ?? ?? ?? E8 ?? ?? ?? ?? 45 33 C0"},  // stable
    {"auto",       "83 FF 07 0F 84 ?? ?? ?? ?? E8 ?? ?? ?? ?? 45 33 C0"},  // future builds (same as stable)
};

// AddProtobufAsBinary: string XRef primary (update-proof), byte pattern fallback.
// Serializes a protobuf message into the args buffer for subscriber dispatch.
inline const StringXRefSig AddProtobufAsBinaryStrSigs[] = {
    {"auto", "CJSMethodArgs::AddProtobufAsBinary", 1},
};

inline const Signature AddProtobufAsBinarySigs[] = {
    {"1779155395", "40 53 55 56 57 48 83 EC ?? 48 8B 05 ?? ?? ?? ?? 48 8B F2"},                                                                                                                    // beta
    {"1778281814", "48 89 5C 24 ?? 48 89 6C 24 ?? 48 89 74 24 ?? 57 48 83 EC 20 48 8B 05 ?? ?? ?? ?? 48 8B F2 48 8B D9 44 8B 00"},  // stable
    {"auto",       "48 89 5C 24 10 48 89 6C 24 18 48 89 74 24 20 57 48 83 EC ?? 48 8B 05 ?? ?? ?? ?? 48 8B F2"},  // future builds
};

// LoadModuleWithPath: byte pattern only (string XRef is unsafe here).
// Hooked to redirect steamclient64.dll loads to the diversion copy.
//
// IMPORTANT — May 22 2026 Steam build 1779486452 surfaced two functions that look
// similar.  The JS-callable JSMethod handler at a separate RVA contains the literal
// "LoadModule" string (it's a dispatch-table key), but Steam NEVER invokes that
// function to load steamclient64.dll.  The real LoadModuleWithPath uses the
// MAX_UNICODE_PATH_IN_UTF8 assert string and matches the historical OST 1.4.2
// prologue.  Hooking the wrong function leaves the diversion DLL unused and games
// show as "Purchase".
//
// We do NOT use string XRef for this hook: the real function spans multiple .pdata
// unwind sub-regions, and the assert string sits in a non-leading sub-region.
// StringFind::FindFunction would return that sub-region's BeginAddress instead of
// the true function start, corrupting the prologue when Detours rewrites it.
// The byte pattern below is unique within steamui.dll and points at the entry.
inline const Signature LoadModuleWithPathSigs[] = {
    {"1778281814", "48 89 5C 24 18 48 89 6C 24 20 56 41 54 41 57 48 83 EC 40"},  // stable (still matches 1779486452)
    {"1778803745", "48 89 5C 24 18 55 56 41 57 48 83 EC 40"},                    // beta
    {"auto",       "48 89 5C 24 18 48 89 6C 24 20 56 41 54 41 57 48 83 EC ??"},  // future builds
};
