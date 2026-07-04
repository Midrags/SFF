// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/SteamStubTicket.h"
#include "hooks/client/PipeWatch.h"
#include "hooks/client/SteamStubAuto.h"
#include "runtime/Logger.h"

namespace {
    constexpr AppId_t kForgeSourceAppId = 7;

    void FillTicketMetadata(Ticket::AppOwnershipTicket& out,
                            const Ticket::AppTicketInspection& inspection) {
        out.totalSize = static_cast<uint32>(out.data.size());
        out.appIdOffset = Ticket::kAppTicketAppIdOffset;
        out.steamIdOffset = Ticket::kAppTicketSteamIdOffset;
        out.signatureOffset = inspection.signatureOffset;
        out.signatureSize = Ticket::kAppTicketSignatureSize;
        if (inspection.status == Ticket::AppTicketStatus::OkForged) {
            out.totalSize = static_cast<uint32>(out.data.size() - sizeof(AppId_t));
            out.appIdOffset = inspection.forgedAppIdOffset;
            out.signatureOffset = out.appIdOffset + sizeof(AppId_t);
        }
    }

    void FillTicketMetadata(AppTicket::OwnershipTicket& out,
                            const Ticket::AppTicketInspection& inspection) {
        out.totalSize = static_cast<uint32>(out.data.size());
        out.appIdOffset = Ticket::kAppTicketAppIdOffset;
        out.steamIdOffset = Ticket::kAppTicketSteamIdOffset;
        out.signatureOffset = inspection.signatureOffset;
        out.signatureSize = Ticket::kAppTicketSignatureSize;
        if (inspection.status == Ticket::AppTicketStatus::OkForged) {
            out.totalSize = static_cast<uint32>(out.data.size() - sizeof(AppId_t));
            out.appIdOffset = inspection.forgedAppIdOffset;
            out.signatureOffset = out.appIdOffset + sizeof(AppId_t);
        }
    }

    void LogTicket(AppId_t appId, const char* source, const std::vector<uint8_t>& data) {
        const uint64_t activeId = Ticket::GetActiveSteamID64();
        const Ticket::AppTicketInspection inspection =
            Ticket::InspectAppTicket(data, appId, activeId);
        uint32 returnValue = static_cast<uint32>(data.size());
        uint32 piAppId = Ticket::kAppTicketAppIdOffset;
        uint32 piSteamId = Ticket::kAppTicketSteamIdOffset;
        uint32 piSignature = inspection.signatureOffset;
        uint32 pcbSignature = Ticket::kAppTicketSignatureSize;
        if (inspection.status == Ticket::AppTicketStatus::OkForged) {
            returnValue = static_cast<uint32>(data.size() - sizeof(AppId_t));
            piAppId = inspection.forgedAppIdOffset;
            piSignature = piAppId + sizeof(AppId_t);
        }
        LOG_IPC_INFO("SteamStubTicket: ticketSource={} target={} status={} physicalBytes={} returnValue={} steamId=0x{:X} standardAppId={} forgedAppId={} piAppId={} piSteamId={} piSignature={} pcbSignature={} rawSigOffset={}",
                     source,
                     appId,
                     Ticket::AppTicketStatusName(inspection.status),
                     data.size(),
                     returnValue,
                     inspection.steamId,
                     inspection.standardAppId,
                     inspection.forgedAppId,
                     piAppId,
                     piSteamId,
                     piSignature,
                     pcbSignature,
                     inspection.signatureOffset);
    }

    const char* TicketSourceName(const Ticket::AppTicketInspection& inspection,
                                 AppId_t appId) {
        if (SteamStubTicket::IsApp7ForgeForTarget(inspection, appId))
            return "app7-forged";
        if (inspection.status == Ticket::AppTicketStatus::OkForged
            && inspection.forgedAppId == appId
            && inspection.standardAppId != 0)
            return "local-signed-source";
        return "target-forged-fallback";
    }

    void CopyTicket(const AppTicket::OwnershipTicket& from, Ticket::AppOwnershipTicket& to) {
        to.data = from.data;
        to.totalSize = from.totalSize;
        to.appIdOffset = from.appIdOffset;
        to.steamIdOffset = from.steamIdOffset;
        to.signatureOffset = from.signatureOffset;
        to.signatureSize = from.signatureSize;
    }

    void CopyTicket(const Ticket::AppOwnershipTicket& from, AppTicket::OwnershipTicket& to) {
        to.data = from.data;
        to.totalSize = from.totalSize;
        to.appIdOffset = from.appIdOffset;
        to.steamIdOffset = from.steamIdOffset;
        to.signatureOffset = from.signatureOffset;
        to.signatureSize = from.signatureSize;
    }

    bool ReadFallback(AppId_t appId, Ticket::AppOwnershipTicket& out) {
        out = {};
        out.data = Ticket::GetAppOwnershipTicketFromRegistry(appId);
        const uint64_t activeId = Ticket::GetActiveSteamID64();
        const Ticket::AppTicketInspection inspection =
            Ticket::InspectAppTicket(out.data, appId, activeId);
        if (inspection.status != Ticket::AppTicketStatus::OkForged || inspection.forgedAppId != appId) {
            LOG_IPC_WARN("SteamStubTicket: ticketSource=missing target={} fallback status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                         appId,
                         Ticket::AppTicketStatusName(inspection.status),
                         out.data.size(),
                         inspection.steamId,
                         inspection.standardAppId,
                         inspection.forgedAppId);
            out = {};
            return false;
        }

        FillTicketMetadata(out, inspection);
        const char* source = TicketSourceName(inspection, appId);
        if (!SteamStubTicket::IsApp7ForgeForTarget(inspection, appId)) {
            LOG_IPC_WARN("SteamStubTicket: using fallback ticketSource={} target={} sourceAppId={} status={} physicalBytes={} returnValue={}",
                         source,
                         appId,
                         inspection.standardAppId,
                         Ticket::AppTicketStatusName(inspection.status),
                         out.data.size(),
                         out.totalSize);
        }
        LogTicket(appId, source, out.data);
        return true;
    }

    bool ReadFallback(AppId_t appId, AppTicket::OwnershipTicket& out) {
        Ticket::AppOwnershipTicket ticket;
        if (!ReadFallback(appId, ticket))
            return false;
        out.data = ticket.data;
        out.totalSize = ticket.totalSize;
        out.appIdOffset = ticket.appIdOffset;
        out.steamIdOffset = ticket.steamIdOffset;
        out.signatureOffset = ticket.signatureOffset;
        out.signatureSize = ticket.signatureSize;
        return true;
    }
}

namespace SteamStubTicket {

    bool IsApp7ForgeForTarget(const Ticket::AppTicketInspection& inspection, AppId_t targetAppId) {
        return inspection.status == Ticket::AppTicketStatus::OkForged
            && inspection.standardAppId == kForgeSourceAppId
            && inspection.forgedAppId == targetAppId;
    }

    bool ResolveRequest(CSteamPipeClient* pipe, AppId_t requestedAppId, AppId_t& ticketAppId) {
        if (!SteamStubAuto::IsActive())
            return false;

        AppId_t realAppId = SteamStubAuto::RealAppId();
        if (!realAppId || realAppId == kOnlineFixAppId)
            return false;

        AppId_t pipeAppId = PipeWatch::ResolveAppId(pipe);
        if (requestedAppId == kOnlineFixAppId || requestedAppId == realAppId || pipeAppId == realAppId) {
            ticketAppId = realAppId;
            LOG_IPC_INFO("SteamStubTicket: request map requested={} pipeAppId={} -> ticketAppId={}",
                         requestedAppId, pipeAppId, ticketAppId);
            return true;
        }

        return false;
    }

    bool GetForgeOnly(AppId_t appId, Ticket::AppOwnershipTicket& out) {
        out = {};
        out.data = Ticket::ForgeAppTicket(kForgeSourceAppId, appId);
        const Ticket::AppTicketInspection inspection =
            Ticket::InspectAppTicket(out.data, appId, Ticket::GetActiveSteamID64());
        if (!IsApp7ForgeForTarget(inspection, appId)) {
            LOG_IPC_WARN("SteamStubTicket: ticketSource=app7-forged sourceAppId={} target={} result=failed status={} bytes={} steamId=0x{:X} standardAppId={} forgedAppId={}",
                         kForgeSourceAppId,
                         appId,
                         Ticket::AppTicketStatusName(inspection.status),
                         out.data.size(),
                         inspection.steamId,
                         inspection.standardAppId,
                         inspection.forgedAppId);
            out = {};
            return false;
        }

        FillTicketMetadata(out, inspection);
        LogTicket(appId, "app7-forged", out.data);
        return true;
    }

    bool GetForgeOnly(AppId_t appId, AppTicket::OwnershipTicket& out) {
        Ticket::AppOwnershipTicket ticket;
        if (!GetForgeOnly(appId, ticket))
            return false;
        CopyTicket(ticket, out);
        return true;
    }

    bool GetForRoute(AppId_t appId, AppTicket::OwnershipTicket& out) {
        if (GetForgeOnly(appId, out))
            return true;
        return ReadFallback(appId, out);
    }

    bool GetForRoute(AppId_t appId, Ticket::AppOwnershipTicket& out) {
        if (GetForgeOnly(appId, out))
            return true;
        return ReadFallback(appId, out);
    }

}
