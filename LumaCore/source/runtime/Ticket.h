// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include "core/entry.h"

namespace Ticket {
    enum class AppTicketStatus {
        Empty,
        TooSmall,
        SteamIdMismatch,
        AppIdMismatch,
        OkStandard,
        OkForged,
    };

    struct AppTicketInspection {
        AppTicketStatus status = AppTicketStatus::Empty;
        uint64_t steamId = 0;
        AppId_t standardAppId = 0;
        AppId_t forgedAppId = 0;
        uint32 signatureOffset = 0;
        uint32 standardAppIdOffset = 16;
        uint32 forgedAppIdOffset = 0;
    };

    enum class TicketPreflightAction {
        Skipped,
        Kept,
        Replaced,
        Deleted,
        ForgeFailed,
        WroteMinimal,
        MinimalFailed,
    };

    enum class TicketPreflightSource {
        None,
        Standard,
        App7Forged,
        LocalSignedSource,
        TargetForgedFallback,
        Missing,
    };

    struct TicketPreflightResult {
        TicketPreflightAction action = TicketPreflightAction::Skipped;
        AppTicketStatus ticketStatus = AppTicketStatus::Empty;
        TicketPreflightSource ticketSource = TicketPreflightSource::None;
        AppId_t sourceAppId = 0;
        bool changed = false;
        bool knownSteamStub = false;
    };

    const char* AppTicketStatusName(AppTicketStatus status);
    const char* TicketPreflightActionName(TicketPreflightAction action);
    const char* TicketPreflightSourceName(TicketPreflightSource source);
    bool IsAppTicketStatusOk(AppTicketStatus status);
    AppTicketInspection InspectAppTicket(const std::vector<uint8_t>& data,
                                         AppId_t appId,
                                         uint64_t expectedSteamId);

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

    // Persist the SteamID REG_SZ beside the app tickets for tools/wrappers
    // that validate the cached ticket identity against the active user.
    bool WriteSteamID(AppId_t appId, uint64_t steamId);

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

    // SpawnProcess preflight. Validates cached AppTicket identity and fixes
    // stale registry blobs before the game wrapper reads them.
    TicketPreflightResult EnsureRegistryTicketsForApp(AppId_t appId);

    // Ticket layout offsets (for manual inspection/manipulation by IPC handlers).
    constexpr uint32 kAppTicketSteamIdOffset = 8;
    constexpr uint32 kAppTicketAppIdOffset   = 16;
    constexpr uint32 kAppTicketSignatureSize = 128;

    struct AppOwnershipTicket {
        std::vector<uint8_t> data;
        uint32 totalSize      = 0;
        uint32 appIdOffset    = kAppTicketAppIdOffset;
        uint32 steamIdOffset  = kAppTicketSteamIdOffset;
        uint32 signatureOffset = 0;
        uint32 signatureSize  = kAppTicketSignatureSize;
    };

    // Full ownership ticket fetch: registry first, then forge from app 7
    // cached ticket (via DecryptionKeyHook), then minimal unsigned fallback.
    // Returns false only when every path fails.
    bool GetAppOwnershipTicket(AppId_t appId, AppOwnershipTicket& ticket);

    // Exploit the off-by-four ticket parsing in steamdrmp:
    // take a signed source ticket, insert the target AppId right before the
    // signature, producing a valid-looking ticket for the target. Returns
    // empty vector when no source ticket is available.
    std::vector<uint8_t> ForgeAppTicket(AppId_t sourceAppId, AppId_t targetAppId);
    std::vector<uint8_t> ForgeAppTicketFromBestSource(AppId_t targetAppId, AppId_t& sourceAppId);
}



