// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/IpcDispatch.h"
#include "hooks/client/IpcMethodLoader.h"
#include "runtime/TicketProvider.h"
#include "runtime/EticketFetcher.h"
#include "runtime/CredentialStore.h"
#include "hooks/client/SteamStubTicket.h"
#include "hooks/capture/SteamCapture.h"
#include "core/entry.h"
#include "config/LuaLoader.h"
#include "runtime/Logger.h"
#include <mutex>

namespace {

    // per-app fresh eticket cache, populated by on-demand mint via EticketFetcher
    std::mutex g_ticketLock;
    std::unordered_map<AppId_t, std::vector<uint8_t>> g_freshCache;

    using namespace SteamCapture;

    void Post_GetSteamID(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite) {
        AppId_t appId = ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) return;

        if (pWrite->m_Put < 8) return;

        uint64_t spoofed = AppTicket::GetSpoofSteamID(appId);
        if (spoofed == 0) {
            LOG_IPC_TRACE("IClientUser::GetSteamID: AppId={} no spoof ID", appId);
            return;
        }

        memcpy(pWrite->m_Memory.m_pMemory, &spoofed, 8);
        LOG_IPC_DEBUG("IClientUser::GetSteamID: AppId={} spoofed -> 0x{:X}", appId, spoofed);
    }

    void Post_GetAppOwnershipTicketExtendedData(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite) {
        AppId_t appId = ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) return;

        constexpr int32 kArgsOffset = 10;
        if (pRead->m_Put < kArgsOffset + 8) return;
        const uint8_t* args = pRead->m_Memory.m_pMemory + kArgsOffset;
        AppId_t requestedAppId = *reinterpret_cast<const AppId_t*>(args);
        uint32_t cbMax = *reinterpret_cast<const uint32_t*>(args + 4);
        if (cbMax == 0) return;

        AppId_t ticketAppId = appId;
        bool steamStubTicket = SteamStubTicket::ResolveRequest(pipe, requestedAppId, ticketAppId);

        AppTicket::OwnershipTicket ticket;
        bool gotTicket = steamStubTicket
            ? SteamStubTicket::GetForRoute(ticketAppId, ticket)
            : AppTicket::GetTicket(ticketAppId, ticket, AppTicket::Source::CredentialThenForge);
        if (!gotTicket) return;

        if (ticket.data.size() > cbMax) {
            LOG_IPC_WARN("IClientUser::GetAppOwnershipTicketExtendedData: AppId={} ticketAppId={} source={} ticket too large ({} > {})",
                          appId, ticketAppId,
                          steamStubTicket ? "steamstub-forge-only" : "credential-then-forge",
                          ticket.data.size(), cbMax);
            return;
        }

        uint8_t* base = pWrite->m_Memory.m_pMemory;
        int32_t pos = 0;

        memcpy(base + pos, &ticket.totalSize, 4); pos += 4;
        uint32_t ticketBytes = static_cast<uint32_t>(ticket.data.size());
        memcpy(base + pos, &ticketBytes, 4); pos += 4;
        if (!ticket.data.empty()) {
            memcpy(base + pos, ticket.data.data(), ticket.data.size());
            pos += static_cast<int32_t>(ticket.data.size());
        }
        memcpy(base + pos, &ticket.appIdOffset, 4); pos += 4;
        memcpy(base + pos, &ticket.steamIdOffset, 4); pos += 4;
        memcpy(base + pos, &ticket.signatureOffset, 4); pos += 4;
        memcpy(base + pos, &ticket.signatureSize, 4); pos += 4;

        pWrite->m_Put = pos;

        LOG_IPC_DEBUG("IClientUser::GetAppOwnershipTicketExtendedData: AppId={} requested={} ticketAppId={} source={} ticket={} bytes",
                       appId, requestedAppId, ticketAppId,
                       steamStubTicket ? "steamstub-forge-only" : "credential-then-forge",
                       ticket.data.size());
    }

    void Post_RequestEncryptedAppTicket(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite) {
        AppId_t appId = ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) return;

        // extract nonce from pRead (pData passed to RequestEncryptedAppTicket by the game)
        if (pRead->m_Put > 10) {
            const uint8_t* args = pRead->m_Memory.m_pMemory + 10;
            uint32_t nonceLen = *reinterpret_cast<const uint32_t*>(args);
            if (nonceLen > 0 && nonceLen < 1024 && pRead->m_Put >= static_cast<int32>(10 + nonceLen)) {
                std::span<const uint8_t> nonce(args + 4, nonceLen);
                auto minted = EticketFetcher::MintEticket(appId, nonce);
                if (minted) {
                    std::lock_guard<std::mutex> hold(g_ticketLock);
                    g_freshCache[appId] = std::move(*minted);
                    LOG_IPC_INFO("IClientUser::RequestEncryptedAppTicket: AppId={} fresh ticket minted ({} bytes)", appId, g_freshCache[appId].size());
                }
            }
        }

        if (pWrite->m_Put < 8) return;
        SteamAPICall_t hCall = *reinterpret_cast<const SteamAPICall_t*>(pWrite->m_Memory.m_pMemory);
        LOG_IPC_DEBUG("IClientUser::RequestEncryptedAppTicket: AppId={} hCall=0x{:X}", appId, hCall);
    }

    void Post_GetEncryptedAppTicket(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite) {
        AppId_t appId = ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) return;

        // try fresh minted ticket first, fall back to credential store
        std::vector<uint8_t> ticket;
        {
            std::lock_guard<std::mutex> hold(g_ticketLock);
            auto it = g_freshCache.find(appId);
            if (it != g_freshCache.end()) {
                ticket = it->second;
                g_freshCache.erase(it);
            }
        }
        if (ticket.empty())
            ticket = AppTicket::ReadETicketFromStore(appId);
        if (ticket.empty()) {
            LOG_IPC_DEBUG("IClientUser::GetEncryptedAppTicket: AppId={} no eticket available", appId);
            return;
        }

        uint32_t ticketSize = static_cast<uint32_t>(ticket.size());
        int32_t newSize = 8 + static_cast<int32_t>(ticketSize);
        if (newSize > pWrite->m_Put + 4096) {
            LOG_IPC_DEBUG("IClientUser::GetEncryptedAppTicket: AppId={} buffer too small need={}", appId, newSize);
            return;
        }

        uint8_t* base = pWrite->m_Memory.m_pMemory;
        int32_t pos = 0;
        int32_t retVal = 1;
        memcpy(base + pos, &retVal, 4); pos += 4;
        memcpy(base + pos, &ticketSize, 4); pos += 4;
        memcpy(base + pos, ticket.data(), ticketSize); pos += static_cast<int32_t>(ticketSize);
        pWrite->m_Put = pos;

        LOG_IPC_INFO("IClientUser::GetEncryptedAppTicket: AppId={} {} bytes inserted", appId, ticket.size());
    }

}

namespace IpcHandlers_ISteamUser {

    void Register() {
        IpcDispatch::Register("IClientUser", "GetSteamID", nullptr, Post_GetSteamID);
        IpcDispatch::Register("IClientUser", "GetAppOwnershipTicketExtendedData", nullptr, Post_GetAppOwnershipTicketExtendedData);
        IpcDispatch::Register("IClientUser", "RequestEncryptedAppTicket", nullptr, Post_RequestEncryptedAppTicket);
        IpcDispatch::Register("IClientUser", "GetEncryptedAppTicket", nullptr, Post_GetEncryptedAppTicket);
    }

}
