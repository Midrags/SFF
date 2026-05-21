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


// steamclient64.dll

inline const StringXRefSig BuildSpawnEnvBlockStrSigs[] = {
    {"auto", "SteamOverlayGameId", 1},
};

inline const Signature BBuildAndAsyncSendFrameSigs[] = {
    {"1778803745", "48 8B C4 55 48 8D 68 A1 48 81 EC C0 00 00 00 48 89 70 18"},  // beta
    {"1778281814", "48 8B C4 55 48 8D 68 A1 48 81 EC C0 00 00 00"},  // stable
};

inline const Signature BuildDepotDependencySigs[] = {
    {"1778803745", "48 8B C4 4C 89 48 20 89 50 10 48 89 48 08 55 ?? 48 8D"},  // beta
    {"1778281814", "48 8B C4 4C 89 48 20 89 50 10 48 89 48 08 55 ?? 48 8D"},  // stable
};

inline const Signature CUtlBufferEnsureCapacitySigs[] = {
    {"1778803745", "48 89 5C 24 08 57 48 83 EC 30 48 8B D9 8D"},  // beta
    {"1778281814", "48 89 5C 24 ?? 57 48 83 EC ?? 0F B6 41 ?? 8D 7A"},  // stable
};

inline const Signature CUtlMemoryGrowSigs[] = {
    {"1778803745", "48 89 5C 24 10 57 48 83 EC 30 8B FA 48 8B D9 8B 51 08"},  // beta
    {"1778281814", "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 30"},  // stable
};

inline const Signature CheckAppOwnershipSigs[] = {
    {"1778803745", "48 8B C4 89 50 10 48 89 48 08 55 53"},  // beta
    {"1778281814", "48 8B C4 89 50 10 55 53 48 8D 68 D8"},  // stable
};

inline const StringXRefSig GetAppDataFromAppInfoStrSigs[] = {
    {"auto", "name_localized/%s", 1},
};

inline const Signature GetAppDataFromAppInfoSigs[] = {
    {"1778803745", "40 53 55 56 57 41 56 41 57 48 81 EC 78 01 00 00 41 C6 01 00"},  // beta
    {"1778281814", "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 41 56 41 57 48 81 EC 70 01 00 00"},  // stable
};

inline const Signature GetAppIDForCurrentPipeSigs[] = {
    {"1778803745", "8B 81 30 0D 00 00 83 F8"},  // beta
    {"1778281814", "48 83 EC 08 8B 81 30 0D 00 00 4C 8B D9 44 8B 91 D8 00 00 00 83 F8 FF"},  // stable
};

inline const Signature GetPackageInfoSigs[] = {
    {"1778803745", "48 89 5C 24 18 89 54 24 10 55 56 57 48 83 EC 20 44 8B 49 20"},  // beta
    {"1778281814", "48 89 6C 24 ?? 41 56 48 83 EC ?? 8B 41 ?? 49 8B E8"},  // stable
};

inline const StringXRefSig GetPipeClientStrSigs[] = {
    {"auto", "error: IPCServer can't be cross user session but not cross process.", 1},
};

inline const Signature GetPipeClientSigs[] = {
    {"1778803745", "85 D2 74 ?? 44 0F B7 CA"},  // beta
    {"1778281814", "85 D2 74 ?? 44 0F B7 CA"},  // stable
};

inline const StringXRefSig IPCProcessMessageStrSigs[] = {
    {"auto", "Unknown IPC command code /+/ %u.  %s", 1},
};

inline const Signature IPCProcessMessageSigs[] = {
    {"1778803745", "48 89 5C 24 18 48 89 6C 24 20 57 41 54 41 55 41 56 41 57 48"},  // beta
    {"1778281814", "48 89 5C 24 ?? 48 89 6C 24 ?? 56 41 54 41 55 41 56 41 57 48 83 EC ?? 49 8B D9"},  // stable
};

inline const Signature KeyValues_FindOrCreateKeySigs[] = {
    {"1778803745", "48 2B D1 F6 C1 07 74 14"},  // beta
    {"1778281814", "48 8B C4 4C 89 48 20 57 48 81 EC 60 04 00 00 48 89 70 E8 48 8B FA"},  // stable
};

inline const Signature KeyValues_ReadAsBinarySigs[] = {
    {"1778803745", "48 8B C4 44 88 48 20 55"},  // beta
    {"1778281814", "48 8B C4 44 88 48 20 44 89 40 18 55 57 48 8D 68 A9 48 81 EC B8 00 00 00"},  // stable
};

inline const Signature LoadDepotDecryptionKeySigs[] = {
    {"1778803745", "40 53 55 56 57 48 83 EC 38 48 63 FA 49 8B E9"},  // beta
    {"1778281814", "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 48 83 EC 30 48 63 FA 49 8B E9 8B D7 49 8B D8 48 8B F1"},  // stable
};

inline const Signature LoadPackageSigs[] = {
    {"1778803745", "44 89 44 24 18 53 55 56 57 41 55"},  // beta
    {"1778281814", "48 89 5C 24 18 48 89 6C 24 20 56 57 41 54 41 55 41 57 48 81 EC 20 01"},  // stable
};

inline const Signature MarkLicenseAsChangedSigs[] = {
    {"1778803745", "48 89 5C 24 20 89 54 24 10 55 56 57 48 83 EC 20"},  // beta
    {"1778281814", "89 54 24 ?? 53 55 56 57 41 56 48 83 EC"},  // stable
};

inline const Signature PchMsgNameFromEMsgSigs[] = {
    {"1778803745", "48 89 5C 24 08 57 48 83 EC 20 8B D9 E8"},  // beta
    {"1778281814", "48 89 5C 24 08 57 48 83 EC 20 8B D9 E8"},  // stable
};

inline const Signature ProcessPendingLicenseUpdatesSigs[] = {
    {"1778803745", "41 56 41 57 48 83 EC 38 83"},  // beta
    {"1778281814", "4C 8B DC 49 89 4B 08 41 55 41 57 48 83 EC 48 4C 8B E9"},  // stable
};

inline const Signature RecvPktSigs[] = {
    {"1778803745", "48 8B C4 55 48 8D A8 98 F6 FF FF 48 81 EC 60 0A"},  // beta
    {"1778281814", "48 8B C4 55 48 8D A8 98 F6 FF FF 48 81 EC 60 0A"},  // stable
};

inline const Signature SendCallbackToPipeSigs[] = {
    {"1778803745", "48 89 5C 24 ?? 57 48 83 EC ?? 41 8B D9 41 8B F8 E8 ?? ?? ?? ?? 48 8B C8"},  // beta
    {"1778281814", "48 89 5C 24 ?? 57 48 83 EC ?? 41 8B D9 41 8B F8 E8 ?? ?? ?? ?? 48 8B C8"},  // stable
};

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

// License hooks functions (string XRef primary, byte pattern fallback)

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

inline const Signature LoadModuleWithPathSigs[] = {
    {"1778803745", "48 89 5C 24 18 55 56 41 57 48 83 EC 40"},  // beta
    {"1778281814", "48 89 5C 24 18 48 89 6C 24 20 56 41 54 41 57 48 83 EC 40"},  // stable
};
