#pragma once

#include "entry.h"

namespace Ticket {
    // Reads the app ownership ticket cached by Steam under
    //   HKCU\Software\Valve\Steam\Apps\<AppId>\AppTicket  (REG_BINARY)
    // Returns an empty vector when no ticket is available.
    std::vector<uint8_t> GetAppOwnershipTicketFromRegistry(AppId_t appId);

    // Reads the encrypted app ticket cached by Steam under
    //   HKCU\Software\Valve\Steam\Apps\<AppId>\ETicket  (REG_BINARY)
    // Returns an empty vector when no ticket is available.
    std::vector<uint8_t> GetEncryptedTicketFromRegistry(AppId_t appId);

    //Get spoof steamID From the cached AppOwnershipTicket for the given AppId.
    uint64_t GetSpoofSteamID(AppId_t appId);

    // Write AppTicket binary data to registry.
    bool WriteAppOwnershipTicket(AppId_t appId, const std::vector<uint8_t>& data);

    // Write ETicket binary data to registry.
    bool WriteEncryptedTicket(AppId_t appId, const std::vector<uint8_t>& data);

    // Read the SteamID64 of the currently logged-in Steam user.
    // Tries HKCU\Software\Valve\Steam\ActiveProcess\ActiveUser first
    // (the live DWORD AccountID Steam writes while running), then falls
    // back to picking the most recently modified userdata\<accountid>\
    // folder if Steam is closed. Returns 0 only when neither path resolves.
    uint64_t GetActiveSteamID64();

    // True when appId is in the small hardcoded set of titles known to use
    // Steam DRM (Steam Stub) — useful for "this game will probably hit
    // error 54 without a registry ticket, suggest Steamless" diagnostics.
    bool IsKnownSteamDrmApp(AppId_t appId);

    // Build a minimal, unsigned AppTicket-shaped blob for appId baked with
    // the active user's SteamID64. The wrapper's signature check on Steam
    // Stub v3 will still reject this (no Valve private key), but pre-v2.2
    // wrappers and several tools that only look at the SteamID/AppID fields
    // accept it. Empty vector when no active user is logged in.
    std::vector<uint8_t> BuildMinimalAppTicket(AppId_t appId);

    // High-level helper called from SpawnProcess: if no AppTicket is cached
    // in the registry for appId, write a fabricated one. Wipes any existing
    // blob whose embedded SteamID doesn't match the active user (covers the
    // "switched accounts" case where a stale ticket would otherwise fail
    // the wrapper's ID compare). Returns true if any write happened.
    bool EnsureRegistryTicketsForApp(AppId_t appId);
}