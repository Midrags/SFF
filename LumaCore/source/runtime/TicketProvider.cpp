// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "TicketProvider.h"
#include "CredentialStore.h"
#include "Ticket.h"
#include "config/LuaLoader.h"
#include "Logger.h"

namespace AppTicket {

    constexpr AppId_t kForgeSourceAppId = 7;

    static void FillTicketMetadata(OwnershipTicket& out,
                                   const Ticket::AppTicketInspection& inspection) {
        out.steamIdOffset = Ticket::kAppTicketSteamIdOffset;
        out.signatureSize = Ticket::kAppTicketSignatureSize;
        if (inspection.status == Ticket::AppTicketStatus::OkForged) {
            out.totalSize = static_cast<uint32>(out.data.size() - sizeof(AppId_t));
            out.appIdOffset = inspection.forgedAppIdOffset;
            out.signatureOffset = out.appIdOffset + sizeof(AppId_t);
            return;
        }

        out.totalSize = static_cast<uint32>(out.data.size());
        out.appIdOffset = Ticket::kAppTicketAppIdOffset;
        out.signatureOffset = inspection.signatureOffset;
    }

    std::vector<uint8_t> ReadTicketFromStore(AppId_t appId) {
        if (!LuaLoader::HasDepot(appId)) {
            LOG_DEBUG("AppTicket::ReadTicketFromStore: AppId={} not tracked", appId);
            return {};
        }
        std::vector<uint8_t> out;
        auto st = CredentialStore::ReadTicket(appId, out);
        if (st != CredentialStore::Status::Ok) {
            LOG_TRACE("AppTicket::ReadTicketFromStore: AppId={} status={}", appId, CredentialStore::ToString(st));
            return {};
        }
        LOG_INFO("AppTicket::ReadTicketFromStore: AppId={} bytes={}", appId, out.size());
        return out;
    }

    std::vector<uint8_t> ReadETicketFromStore(AppId_t appId) {
        if (!LuaLoader::HasDepot(appId)) {
            LOG_DEBUG("AppTicket::ReadETicketFromStore: AppId={} not tracked", appId);
            return {};
        }
        std::vector<uint8_t> out;
        auto st = CredentialStore::ReadETicket(appId, out);
        if (st != CredentialStore::Status::Ok) {
            LOG_TRACE("AppTicket::ReadETicketFromStore: AppId={} status={}", appId, CredentialStore::ToString(st));
            return {};
        }
        LOG_INFO("AppTicket::ReadETicketFromStore: AppId={} bytes={}", appId, out.size());
        return out;
    }

    static std::vector<uint8_t> ForgeFromSource(AppId_t sourceAppId, AppId_t targetAppId) {
        return Ticket::ForgeAppTicket(sourceAppId, targetAppId);
    }

    std::vector<uint8_t> ForgeFromApp7(AppId_t appId) {
        return ForgeFromSource(kForgeSourceAppId, appId);
    }

    std::vector<uint8_t> ForgeFromBestSource(AppId_t appId, AppId_t& sourceAppId) {
        return Ticket::ForgeAppTicketFromBestSource(appId, sourceAppId);
    }

    bool GetTicket(AppId_t appId, OwnershipTicket& out, Source src) {
        out = {};
        const uint64_t activeID = Ticket::GetActiveSteamID64();

        if (src == Source::CredentialOnly || src == Source::CredentialThenForge) {
            out.data = ReadTicketFromStore(appId);
            Ticket::AppTicketInspection inspection = Ticket::InspectAppTicket(out.data, appId, activeID);
            if (Ticket::IsAppTicketStatusOk(inspection.status)) {
                FillTicketMetadata(out, inspection);
                return true;
            }
            if (!out.data.empty()) {
                LOG_WARN("AppTicket::GetTicket: AppId={} rejecting cached ticket status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                         appId, Ticket::AppTicketStatusName(inspection.status),
                         out.data.size(), inspection.steamId,
                         inspection.standardAppId, inspection.forgedAppId);
            }
        }

        if (src == Source::CredentialOnly) return false;

        AppId_t sourceAppId = 0;
        out.data = ForgeFromBestSource(appId, sourceAppId);
        if (out.data.empty()) return false;

        Ticket::AppTicketInspection forgedInspection = Ticket::InspectAppTicket(out.data, appId, activeID);
        if (!Ticket::IsAppTicketStatusOk(forgedInspection.status)) {
            LOG_WARN("AppTicket::GetTicket: AppId={} rejecting forged ticket status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                     appId, Ticket::AppTicketStatusName(forgedInspection.status),
                     out.data.size(), forgedInspection.steamId,
                     forgedInspection.standardAppId, forgedInspection.forgedAppId);
            out = {};
            return false;
        }
        FillTicketMetadata(out, forgedInspection);
        return true;
    }

    uint64_t GetSpoofSteamID(AppId_t appId) {
        if (!LuaLoader::HasDepot(appId)) {
            LOG_DEBUG("AppTicket::GetSpoofSteamID: AppId={} not tracked", appId);
            return 0;
        }

        uint64_t steamId = 0;
        auto st = CredentialStore::ReadSteamId(appId, steamId);
        if (st == CredentialStore::Status::Ok && steamId != 0) {
            LOG_DEBUG("AppTicket::GetSpoofSteamID: AppId={} -> 0x{:X}", appId, steamId);
            return steamId;
        }

        // fall back to parsing the SteamID from the cached ticket
        std::vector<uint8_t> ticket = ReadTicketFromStore(appId);
        Ticket::AppTicketInspection inspection = Ticket::InspectAppTicket(ticket, appId, 0);
        if (Ticket::IsAppTicketStatusOk(inspection.status)) {
            LOG_DEBUG("AppTicket::GetSpoofSteamID: AppId={} ticket-parse -> 0x{:X}",
                      appId, inspection.steamId);
            return inspection.steamId;
        }
        if (!ticket.empty()) {
            LOG_WARN("AppTicket::GetSpoofSteamID: AppId={} rejecting cached ticket status={} bytes={} standardAppId={} forgedAppId={}",
                     appId, Ticket::AppTicketStatusName(inspection.status),
                     ticket.size(), inspection.standardAppId, inspection.forgedAppId);
        }
        return 0;
    }

    bool WriteTicket(AppId_t appId, const std::vector<uint8_t>& data) {
        auto st = CredentialStore::WriteTicket(appId, data);
        return st == CredentialStore::Status::Ok;
    }

    bool WriteETicket(AppId_t appId, const std::vector<uint8_t>& data) {
        auto st = CredentialStore::WriteETicket(appId, data);
        return st == CredentialStore::Status::Ok;
    }

    bool WriteSteamID(AppId_t appId, uint64_t steamId) {
        auto st = CredentialStore::WriteSteamId(appId, steamId);
        return st == CredentialStore::Status::Ok;
    }

}
