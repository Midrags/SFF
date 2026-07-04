// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/IPCBus.h"
#include "hooks/client/CmdUser.h"
#include "hooks/client/CmdUtils.h"
#include "runtime/Ticket.h"
#include "runtime/Logger.h"
#include "hooks/capture/SteamCapture.h"
#include "hooks/capture/RuntimeCapture.h"
#include "hooks/client/SteamStubAuto.h"
#include "hooks/client/SteamStubTicket.h"
#include "PipeWatch.h"
#include "AuthWindow.h"
#include "AsyncTicketMap.h"
#include "Steam/Callback.h"
#include "Steam/Structs.h"
#include "core/entry.h"

#include <shlwapi.h>
#pragma comment(lib, "shlwapi.lib")

// ── Helpers ───────────────────────────────────────────────────────────

namespace {

    // ── GetAPICallResult request layout ─────────────────
    struct ApiCallRequest {
        uint64_t hCall;
        uint32_t cbCallback;
        int      iCallback;

        bool Valid(int32 bufPut) const {
            return bufPut >= static_cast<int32>(sizeof(ApiCallRequest));
        }
    };

    // File-local twin of the PackagePatch.cpp helper. Two copies live
    // file-local in the call sites (per project §13 small-surface rule)
    // rather than sharing a header. Hidden-480 routes need this rewrite.
    static bool RewriteGameIdInCallback(int iCallback, void* pCallbackData,
                                        int cbCallbackData)
    {
        AppId_t real = SteamCapture::ActiveRouteRealAppId();
        if (real == 0 || real == kOnlineFixAppId) return false;
        if (cbCallbackData < static_cast<int>(sizeof(uint64_t))) return false;
        if (pCallbackData == nullptr) return false;

        auto* pGameId = static_cast<uint64_t*>(pCallbackData);
        AppId_t current = static_cast<AppId_t>(*pGameId & 0xFFFFFF);
        if (current != real) return false;

        *pGameId = (*pGameId & ~static_cast<uint64_t>(0xFFFFFF))
                 | static_cast<uint64_t>(kOnlineFixAppId);
        LOG_USRCMD_DEBUG("\"event\" \"RewiteGameId\" \"cb\" {} \"gameId\" {}->{}",
                         iCallback, real, kOnlineFixAppId);
        return true;
    }

    // ── Write boilerplate callback response ─────────────
    template<typename CallbackT, typename F>
    bool WriteCallback(CUtlBuffer* pWrite, F&& fill)
    {
        constexpr int32 total = 1 + 1 + sizeof(CallbackT) + 1;
        if (pWrite->m_Put < total) return false;

        uint8_t* base = pWrite->m_Memory.m_pMemory;
        base[0] = IPC_REPLY_TAG;
        base[1] = 1;
        base[2 + sizeof(CallbackT)] = 0;

        auto* cb = reinterpret_cast<CallbackT*>(base + 2);
        fill(*cb);
        return true;
    }

} // anonymous namespace

// ═══════════════════════════════════════════════════════════════════════
//  SteamID resolution
// ═══════════════════════════════════════════════════════════════════════

namespace CmdUser::SteamID {

    // Walks Steam's userdata directory looking for a folder named after
    // an account ID that contains a sub-folder for appId.  This covers
    // the case where no AppTicket is cached in the registry but the user
    // has previously played the game (Denuvo games in particular).
    // Returns 0 if nothing is found.
    static uint64 ResolveViaUserdata(AppId_t appId)
    {
        constexpr size_t kPathMax = 260;
        DWORD dataLen = MAX_PATH;
        char steamPath[kPathMax] = {};
        if (RegGetValueA(HKEY_CURRENT_USER,
                         "Software\\Valve\\Steam",
                         "SteamPath",
                         RRF_RT_REG_SZ, nullptr,
                         steamPath, &dataLen) != ERROR_SUCCESS)
            return 0;

        char userdataPath[kPathMax];
        snprintf(userdataPath, kPathMax, "%s\\userdata", steamPath);

        char searchPattern[kPathMax];
        snprintf(searchPattern, kPathMax, "%s\\*", userdataPath);

        WIN32_FIND_DATAA fd;
        HANDLE hFind = FindFirstFileA(searchPattern, &fd);
        if (hFind == INVALID_HANDLE_VALUE) return 0;

        uint64 outcome = 0;
        do {
            if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
            if (fd.cFileName[0] == '.') continue;

            char* end = nullptr;
            unsigned long accountId = strtoul(fd.cFileName, &end, 10);
            if (!end || *end != '\0' || accountId == 0) continue;

            char gamePath[kPathMax];
            snprintf(gamePath, kPathMax, "%s\\%s\\%u", userdataPath, fd.cFileName, static_cast<uint32>(appId));
            DWORD attrs = GetFileAttributesA(gamePath);
            if (attrs == INVALID_FILE_ATTRIBUTES || !(attrs & FILE_ATTRIBUTE_DIRECTORY)) continue;

            outcome = 0x0110000100000000ULL | static_cast<uint64>(accountId);
            break;
        } while (FindNextFileA(hFind, &fd));

        FindClose(hFind);
        return outcome;
    }

    // ▌ IPC-USER ▌ Handler: IClientUser::GetSteamID
    //  Request:  no args
    //  Response: [uint8 prefix=0x0B][uint64 SteamID]   (9 bytes)
    void OnGetSteamID(CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t appId = PipeWatch::ResolveAppId(pipe);
        LOG_USRCMD_INFO("\"handler\" \"GetSteamID\" \"appId\" {} \"enter\" 1", appId);
        uint64 spoofed = 0;
        if (AuthWindow::IsSelectedPipe(pipe)) {
            spoofed = Ticket::GetActiveSteamID64();
            if (spoofed) {
                Ticket::WriteSteamID(appId, spoofed);
                LOG_USRCMD_INFO("\"handler\" \"GetSteamID\" \"appId\" {} \"source\" \"auth\" \"steamid\" \"0x{:X}\"",
                               appId, spoofed);
            }
        }
        if (!spoofed)
            spoofed = Ticket::GetSpoofSteamID(appId);
        if (!spoofed) {
            spoofed = ResolveViaUserdata(appId);
            if (spoofed)
                LOG_USRCMD_INFO("\"handler\" \"GetSteamID\" \"appId\" {} \"source\" \"userdata\" \"steamid\" \"0x{:X}\"", appId, spoofed);
        }
        if (!spoofed) {
            LOG_USRCMD_WARN("\"handler\" \"GetSteamID\" \"appId\" {} \"no-spoof\" 1", appId);
            return;
        }
        uint8_t* base = pWrite->Base();
        base[0] = IPC_REPLY_TAG;
        memcpy(base + 1, &spoofed, sizeof(spoofed));
        LOG_USRCMD_INFO("\"handler\" \"GetSteamID\" \"appId\" {} \"steamid\" \"0x{:X}({})\"", appId, spoofed, spoofed);
    }

} // namespace CmdUser::SteamID

// ═══════════════════════════════════════════════════════════════════════
//  Ticket handlers
// ═══════════════════════════════════════════════════════════════════════

namespace CmdUser::Tickets {

    static const char* OwnershipTicketSourceName(
        bool steamStubTicket,
        const Ticket::AppTicketInspection& inspection,
        AppId_t ticketAppId)
    {
        if (steamStubTicket) {
            if (SteamStubTicket::IsApp7ForgeForTarget(inspection, ticketAppId))
                return "app7-forged";
            if (inspection.status == Ticket::AppTicketStatus::OkForged
                && inspection.forgedAppId == ticketAppId
                && inspection.standardAppId != 0)
                return "local-signed-source";
            return "steamstub";
        }

        if (inspection.status == Ticket::AppTicketStatus::OkStandard)
            return "registry-standard";
        if (inspection.status == Ticket::AppTicketStatus::OkForged)
            return "registry-forged";
        return "registry-or-forge";
    }

    static AppId_t OwnershipTicketSourceAppId(
        const Ticket::AppTicketInspection& inspection,
        AppId_t ticketAppId)
    {
        if (inspection.status == Ticket::AppTicketStatus::OkForged
            && inspection.standardAppId != 0)
            return inspection.standardAppId;
        if (inspection.status == Ticket::AppTicketStatus::OkStandard)
            return ticketAppId;
        return 0;
    }

    // ▌ IPC-USER ▌ Handler: IClientUser::GetAppOwnershipTicketExtendedData
    void OnGetOwnershipTicketExtended(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
    {
        const uint8_t* reqData = pRead->Base();
        const int32  reqSize = pRead->m_Put;
        LOG_USRCMD_INFO("\"handler\" \"GetAppOwnershipTicketExtendedData\" \"size\" {}", reqSize);
        if (reqSize < IPC_ARGS_OFFSET + 8) {
            LOG_USRCMD_WARN("\"handler\" \"GetAppOwnershipTicketExtendedData\" \"too-small\" {} \"need\" {}", reqSize, IPC_ARGS_OFFSET + 8);
            return;
        }
        const uint8_t* args = reqData + IPC_ARGS_OFFSET;
        const uint32 reqAppID   = *reinterpret_cast<const uint32*>(args);
        const int32  reqBufSize = *reinterpret_cast<const int32*>(args + 4);
        if (reqBufSize <= 0) {
            LOG_USRCMD_WARN("\"handler\" \"GetAppOwnershipTicketExtendedData\" \"appId\" {} \"bufSize\" {} \"invalid-buffer\" 1",
                            reqAppID, reqBufSize);
            return;
        }

        AppId_t ticketAppID = reqAppID;
        bool steamStubTicket = SteamStubTicket::ResolveRequest(pipe, reqAppID, ticketAppID);

        LOG_USRCMD_INFO("\"handler\" \"GetAppOwnershipTicketExtendedData\" \"appId\" {} \"ticketAppId\" {} \"bufSize\" {} \"source\" \"{}\"",
                  reqAppID, ticketAppID, reqBufSize,
                  steamStubTicket ? "steamstub-forge-only" : "registry-or-forge");

        Ticket::AppOwnershipTicket ownership{};
        bool gotTicket = steamStubTicket
            ? SteamStubTicket::GetForRoute(ticketAppID, ownership)
            : Ticket::GetAppOwnershipTicket(ticketAppID, ownership);
        if (!gotTicket || ownership.data.empty() || ownership.data.size() < 4) {
            LOG_USRCMD_WARN("\"handler\" \"GetAppOwnershipTicketExtendedData\" \"appId\" {} \"ticketAppId\" {} \"ticket-empty\" 1",
                            reqAppID, ticketAppID);
            return;
        }

        const std::vector<uint8_t>& ticket = ownership.data;
        const uint32 ticketSize = static_cast<uint32>(ticket.size());
        const uint32 returnValue = ownership.totalSize ? ownership.totalSize : ticketSize;
        const uint32 totalSize = 1 + 4 + static_cast<uint32>(reqBufSize) + 16;
        SteamCapture::EnsureBufferSize(pWrite, static_cast<int32>(totalSize));

        uint8_t* base = pWrite->Base();

        base[0] = IPC_REPLY_TAG;
        memcpy(base + 1, &returnValue, 4);
        const uint32 copySize = (ticketSize < static_cast<uint32>(reqBufSize))
                              ? ticketSize : static_cast<uint32>(reqBufSize);
        memcpy(base + 5, ticket.data(), copySize);
        if (copySize < static_cast<uint32>(reqBufSize))
            memset(base + 5 + copySize, 0, reqBufSize - copySize);

        const uint32 piAppId      = ownership.appIdOffset;
        const uint32 piSteamId    = ownership.steamIdOffset;
        const uint32 piSignature  = ownership.signatureOffset;
        const uint32 pcbSignature = ownership.signatureSize;
        const uint32 outOff = 5 + reqBufSize;
        memcpy(base + outOff,      &piAppId,      4);
        memcpy(base + outOff + 4,  &piSteamId,    4);
        memcpy(base + outOff + 8,  &piSignature,  4);
        memcpy(base + outOff + 12, &pcbSignature, 4);

        const Ticket::AppTicketInspection inspection =
            Ticket::InspectAppTicket(ticket, ticketAppID, Ticket::GetActiveSteamID64());
        const char* ticketSource =
            OwnershipTicketSourceName(steamStubTicket, inspection, ticketAppID);
        const AppId_t sourceAppId =
            OwnershipTicketSourceAppId(inspection, ticketAppID);
        AppId_t appId = PipeWatch::ResolveAppId(pipe);
        LOG_USRCMD_INFO("\"handler\" \"GetAppOwnershipTicketExtendedData\" \"appId\" {} \"requestAppId\" {} \"ticketAppId\" {} \"ticketSource\" \"{}\" \"sourceAppId\" {} \"physicalBytes\" {} \"returnValue\" {} \"cbMaxTicket\" {} \"piAppId\" {} \"piSteamId\" {} \"piSignature\" {} \"pcbSignature\" {} \"resolvedAppId\" {}",
                  appId, reqAppID, ticketAppID, ticketSource, sourceAppId,
                  ticketSize, returnValue, reqBufSize, piAppId, piSteamId,
                  piSignature, pcbSignature, appId);
    }

    // ▌ IPC-USER ▌ Handler: IClientUser::RequestEncryptedAppTicket
    void OnRequestEncrypted(CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t appId = PipeWatch::ResolveAppId(pipe);
        LOG_USRCMD_INFO("\"handler\" \"RequestEncryptedAppTicket\" \"appId\" {} \"write\" {}", appId, pWrite->m_Put);
        if (pWrite->m_Put < 9) {
            LOG_USRCMD_WARN("\"handler\" \"RequestEncryptedAppTicket\" \"appId\" {} \"write-too-small\" {}", appId, pWrite->m_Put);
            return;
        }

        auto ticket = Ticket::GetEncryptedTicketFromRegistry(appId);
        if (ticket.empty()) {
            LOG_USRCMD_WARN("\"handler\" \"RequestEncryptedAppTicket\" \"appId\" {} \"no-ticket\" 1", appId);
            return;
        }

        uint8_t* base = pWrite->Base();
        uint64_t hAsyncCall;
        memcpy(&hAsyncCall, base + 1, sizeof(hAsyncCall));

        AsyncTicketMap::Remember(hAsyncCall, appId);
        LOG_USRCMD_INFO("\"handler\" \"RequestEncryptedAppTicket\" \"appId\" {} \"hCall\" \"0x{:016X}\"", appId, hAsyncCall);
    }

    // ▌ IPC-USER ▌ Handler: IClientUser::GetEncryptedAppTicket
    void OnGetEncrypted(CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t appId = PipeWatch::ResolveAppId(pipe);
        LOG_USRCMD_INFO("\"handler\" \"GetEncryptedAppTicket\" \"appId\" {} \"enter\" 1", appId);
        auto ticket = Ticket::GetEncryptedTicketFromRegistry(appId);
        if (ticket.empty()) {
            LOG_USRCMD_WARN("\"handler\" \"GetEncryptedAppTicket\" \"appId\" {} \"no-ticket\" 1", appId);
            return;
        }

        const uint32 ticketSize = static_cast<uint32>(ticket.size());
        const int32 totalSize = 1 + 1 + 4 + ticketSize;
        SteamCapture::EnsureBufferSize(pWrite, totalSize);

        uint8_t* base = pWrite->Base();
        base[0] = IPC_REPLY_TAG;
        base[1] = 1;
        memcpy(base + 2, &ticketSize, sizeof(ticketSize));
        memcpy(base + 6, ticket.data(), ticketSize);

        LOG_USRCMD_INFO("\"handler\" \"GetEncryptedAppTicket\" \"appId\" {} \"size\" {}", appId, ticketSize);
    }

} // namespace CmdUser::Tickets

// ═══════════════════════════════════════════════════════════════════════
//  Utils handlers (IClientUtils)
// ═══════════════════════════════════════════════════════════════════════

namespace CmdUser::Utils {

    // ▌ IPC-UTILS ▌ Handler: IClientUtils::GetAppID
    //  The game needs the real appid here. SteamStub auto hides from Steam in
    //  the launch tracking path, not in this game-facing reply.
    void OnGetAppID(CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        SteamCapture::OnlineFixRouteMode mode = SteamCapture::OnlineFixMode();
        const uint32 pipeId = pipe ? pipe->m_hSteamPipe : 0;
        const uint32 pid = pipe ? pipe->m_clientPID : 0;

        if (!pWrite || pWrite->m_Put < 5) {
            LOG_IPCRTR_WARN("IClientUtils::GetAppID legacy routeMode={} pipe=0x{:08X} pid={} writeSize={} action=skip-too-small",
                            SteamStubAuto::IsActive() ? "steamstub-auto" : SteamCapture::OnlineFixRouteModeName(mode),
                            pipeId, pid, pWrite ? pWrite->m_Put : 0);
            return;
        }

        AppId_t realAppId = SteamStubAuto::IsActive()
            ? SteamStubAuto::RealAppId()
            : SteamCapture::ResolveAppId();
        AppId_t current = *reinterpret_cast<const AppId_t*>(pWrite->Base() + 1);
        AppId_t finalAppId = current;
        bool changed = false;

        if (realAppId
            && current != realAppId) {
            finalAppId = realAppId;
            *reinterpret_cast<AppId_t*>(pWrite->Base() + 1) = finalAppId;
            changed = true;
        }

        LOG_IPCRTR_INFO("IClientUtils::GetAppID legacy routeMode={} pipe=0x{:08X} pid={} current={} real={} final={} changed={}",
                        SteamStubAuto::IsActive() ? "steamstub-auto" : SteamCapture::OnlineFixRouteModeName(mode),
                        pipeId, pid, current, realAppId, finalAppId, changed);
        if (changed)
            LOG_USRCMD_INFO("\"handler\" \"GetAppID\" \"was\" {} \"now\" {}", current, finalAppId);
    }

    // ════════════════════════════════════════════════════════
    //  GetAPICallResult per-callback handlers
    // ════════════════════════════════════════════════════════

    static bool OnEncryptedAppTicketResponse(
        CUtlBuffer* pWrite, uint64_t hAsyncCall, uint32_t cubCallback)
    {
        auto appId = AsyncTicketMap::Claim(hAsyncCall);
        if (!appId) return false;

        LOG_USRCMD_DEBUG("\"handler\" \"GetAPICallResult\" \"cb\" \"EncryptedAppTicketResponse\" \"hCall\" \"0x{:016X}\" \"appId\" {}",
                  hAsyncCall, *appId);

        if (!WriteCallback<EncryptedAppTicketResponse_t>(pWrite, [](auto& cb) {
            cb.m_eResult = k_EResultOK;
        })) {
            AsyncTicketMap::Remember(hAsyncCall, *appId);
            return false;
        }

        return true;
    }

    // ── Achievement-callback m_nGameID rewrite for GetAPICallResult ──
    static bool OnAchievementStatsResult(
        HSteamPipe pipe, CUtlBuffer* pWrite, int iCallback, uint32_t cubCallback)
    {
        if (SteamCapture::ActiveRouteRealAppId() == 0) return false;
        if (SteamCapture::StatsScopePipe() != pipe) return false;
        if (cubCallback < sizeof(uint64_t)) return false;
        const int32 minTotal = static_cast<int32>(2 + sizeof(uint64_t));
        if (pWrite->m_Put < minTotal) return false;

        uint8_t* base = pWrite->Base();
        if (base[0] != IPC_REPLY_TAG || base[1] != 1) return false;

        return RewriteGameIdInCallback(iCallback, base + 2,
                                       static_cast<int>(cubCallback));
    }

    static bool OnUserStatsReceived(
        CSteamPipeClient* pipe, CUtlBuffer* pWrite, uint64_t, uint32_t cubCallback) {
        return OnAchievementStatsResult(
            pipe ? pipe->m_hSteamPipe : 0, pWrite,
            UserStatsReceived_t::k_iCallback, cubCallback);
    }

    static bool OnGlobalAchievementPercentagesReady(
        CSteamPipeClient* pipe, CUtlBuffer* pWrite, uint64_t, uint32_t cubCallback) {
        return OnAchievementStatsResult(
            pipe ? pipe->m_hSteamPipe : 0, pWrite,
            GlobalAchievementPercentagesReady_t::k_iCallback, cubCallback);
    }

    static bool OnGlobalStatsReceived(
        CSteamPipeClient* pipe, CUtlBuffer* pWrite, uint64_t, uint32_t cubCallback) {
        return OnAchievementStatsResult(
            pipe ? pipe->m_hSteamPipe : 0, pWrite,
            GlobalStatsReceived_t::k_iCallback, cubCallback);
    }

    struct CallbackHandler {
        uint32_t callbackId;
        bool   (*handler)(CSteamPipeClient* pipe, CUtlBuffer* pWrite,
                          uint64_t hAsyncCall, uint32_t cubCallback);
    };

    static bool AdaptEncryptedTicket(
        CSteamPipeClient*, CUtlBuffer* pWrite, uint64_t hAsyncCall, uint32_t cubCallback) {
        return OnEncryptedAppTicketResponse(pWrite, hAsyncCall, cubCallback);
    }

    static constexpr CallbackHandler kCallbackHandlers[] = {
        { EncryptedAppTicketResponse_t::k_iCallback,         AdaptEncryptedTicket },
        { UserStatsReceived_t::k_iCallback,                  OnUserStatsReceived },
        { GlobalAchievementPercentagesReady_t::k_iCallback,  OnGlobalAchievementPercentagesReady },
        { GlobalStatsReceived_t::k_iCallback,                OnGlobalStatsReceived },
    };

    // ▌ IPC-UTILS ▌ Handler: IClientUtils::GetAPICallResult
    void OnGetAPICallResult(
        CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
    {
        if (pRead->m_Put < IPC_ARGS_OFFSET + sizeof(ApiCallRequest)) return;

        const auto* req = reinterpret_cast<const ApiCallRequest*>(
            pRead->Base() + IPC_ARGS_OFFSET);

        AppId_t appId = SteamCapture::GetAppIDForCurrentPipe();
        LOG_USRCMD_DEBUG("\"handler\" \"GetAPICallResult\" \"hCall\" \"0x{:016X}\" \"appId\" {} \"cb\" {} \"size\" {}",
                  req->hCall, appId, req->iCallback, req->cbCallback);
        for (auto& entry : kCallbackHandlers) {
            if (entry.callbackId == static_cast<uint32_t>(req->iCallback)) {
                entry.handler(pipe, pWrite, req->hCall, req->cbCallback);
                return;
            }
        }
    }

} // namespace CmdUser::Utils

// ═══════════════════════════════════════════════════════════════════════
//  Cmd_* wrappers (required by REGISTER_IPC_CMD macro)
// ═══════════════════════════════════════════════════════════════════════

static void Cmd_IClientUser_GetSteamID(
    CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
{ CmdUser::SteamID::OnGetSteamID(pipe, pRead, pWrite); }

static void Cmd_IClientUser_GetAppOwnershipTicketExtendedData(
    CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
{ CmdUser::Tickets::OnGetOwnershipTicketExtended(pipe, pRead, pWrite); }

static void Cmd_IClientUser_RequestEncryptedAppTicket(
    CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
{ CmdUser::Tickets::OnRequestEncrypted(pipe, pRead, pWrite); }

static void Cmd_IClientUser_GetEncryptedAppTicket(
    CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
{ CmdUser::Tickets::OnGetEncrypted(pipe, pRead, pWrite); }

static void Cmd_IClientUtils_GetAppID(
    CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
{ CmdUser::Utils::OnGetAppID(pipe, pRead, pWrite); }

static void Cmd_IClientUtils_GetAPICallResult(
    CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
{ CmdUser::Utils::OnGetAPICallResult(pipe, pRead, pWrite); }

// ═══════════════════════════════════════════════════════════════════════
//  Registration
// ═══════════════════════════════════════════════════════════════════════

namespace {

    const IPCBus::IpcHandlerEntry g_UserEntries[] = {
        REGISTER_IPC_CMD(IClientUser, GetSteamID),
        REGISTER_IPC_CMD(IClientUser, GetAppOwnershipTicketExtendedData),
        REGISTER_IPC_CMD(IClientUser, RequestEncryptedAppTicket),
        REGISTER_IPC_CMD(IClientUser, GetEncryptedAppTicket),
    };

    const IPCBus::IpcHandlerEntry g_UtilsEntries[] = {
        REGISTER_IPC_CMD(IClientUtils, GetAppID),
        REGISTER_IPC_CMD(IClientUtils, GetAPICallResult),
    };

} // namespace

namespace CmdUser {
    void Register() {
        IPCBus::RegisterHandlers(g_UserEntries, std::size(g_UserEntries));
        IPCBus::RegisterHandlers(g_UtilsEntries, std::size(g_UtilsEntries));
    }
}
