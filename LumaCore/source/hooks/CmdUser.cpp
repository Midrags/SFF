#include "IPCBus.h"
#include "CmdUser.h"
#include "utils/Ticket.h"
#include "utils/Logger.h"
#include "SteamCapture.h"

#include <shlwapi.h>
#pragma comment(lib, "shlwapi.lib")

namespace {
    // ── eticket: hAsyncCall → appId mapping ────────────────────────
    std::unordered_map<uint64, AppId_t> g_PendingEtickets;

    // ── Dynamic SteamID fallback ───────────────────────────────────
    // Walks Steam's userdata directory looking for a folder named after
    // an account ID that contains a sub-folder for appId.  This covers
    // the case where no AppTicket is cached in the registry but the user
    // has previously played the game (Denuvo games in particular).
    // Returns 0 if nothing is found.
    uint64 GetDynamicOwnerSteamID(AppId_t appId)
    {
        DWORD dataLen = MAX_PATH;
        char steamPath[MAX_PATH] = {};
        if (RegGetValueA(HKEY_CURRENT_USER,
                         "Software\\Valve\\Steam",
                         "SteamPath",
                         RRF_RT_REG_SZ, nullptr,
                         steamPath, &dataLen) != ERROR_SUCCESS)
            return 0;

        char userdataPath[MAX_PATH];
        snprintf(userdataPath, MAX_PATH, "%s\\userdata", steamPath);

        char searchPattern[MAX_PATH];
        snprintf(searchPattern, MAX_PATH, "%s\\*", userdataPath);

        WIN32_FIND_DATAA fd;
        HANDLE hFind = FindFirstFileA(searchPattern, &fd);
        if (hFind == INVALID_HANDLE_VALUE) return 0;

        uint64 result = 0;
        do {
            if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
            if (fd.cFileName[0] == '.') continue;

            char* end = nullptr;
            unsigned long accountId = strtoul(fd.cFileName, &end, 10);
            if (!end || *end != '\0' || accountId == 0) continue;

            char gamePath[MAX_PATH];
            snprintf(gamePath, MAX_PATH, "%s\\%s\\%u", userdataPath, fd.cFileName, static_cast<uint32>(appId));
            DWORD attrs = GetFileAttributesA(gamePath);
            if (attrs == INVALID_FILE_ATTRIBUTES || !(attrs & FILE_ATTRIBUTE_DIRECTORY)) continue;

            result = 0x0110000100000000ULL | static_cast<uint64>(accountId);
            break;
        } while (FindNextFileA(hFind, &fd));

        FindClose(hFind);
        return result;
    }

    // ── Handler: IClientUser::GetSteamID ──────────────────────────
    //  Request:  no args
    //  Response: [uint8 prefix=0x0B][uint64 SteamID]   (9 bytes)
    void Cmd_IClientUser_GetSteamID(CSteamPipeClient* pipe,
                                      CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t appId = SteamCapture::ResolveAppId();
        LOG_IPC_INFO("IClientUser::GetSteamID: ENTER AppId={}", appId);
        uint64 spoofed = Ticket::GetSpoofSteamID(appId);
        if (!spoofed) {
            spoofed = GetDynamicOwnerSteamID(appId);
            if (spoofed)
                LOG_IPC_INFO("IClientUser::GetSteamID: AppId={} using dynamic userdata SteamID 0x{:X}", appId, spoofed);
        }
        if (!spoofed) {
            LOG_IPC_WARN("IClientUser::GetSteamID: AppId={} no valid steamid - cannot spoof (RETURN no reply)", appId);
            return;
        }
        uint8* base = pWrite->Base();
        base[0] = IPC_REPLY_TAG;
        memcpy(base + 1, &spoofed, sizeof(spoofed));
        LOG_IPC_INFO("IClientUser::GetSteamID: AppId={} -> Spoofed: 0x{:X}({})", appId, spoofed, spoofed);
    }

    // ── Handler: IClientUser::GetAppOwnershipTicketExtendedData ───
    void Cmd_IClientUser_GetAppOwnershipTicketExtendedData(
        CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite)
    {
        const uint8* reqData = pRead->Base();
        const int32  reqSize = pRead->m_Put;
        LOG_IPC_INFO("IClientUser::GetAppOwnershipTicketExtendedData: ENTER reqSize={}", reqSize);
        if (reqSize < IPC_ARGS_OFFSET + 8) {
            LOG_IPC_WARN("IClientUser::GetAppOwnershipTicketExtendedData: reqSize={} too small (need {}), RETURN no reply",
                         reqSize, IPC_ARGS_OFFSET + 8);
            return;
        }
        const uint8* args = reqData + IPC_ARGS_OFFSET;
        const uint32 reqAppID   = *reinterpret_cast<const uint32*>(args);
        const int32  reqBufSize = *reinterpret_cast<const int32*>(args + 4);

        LOG_IPC_INFO("IClientUser::GetAppOwnershipTicketExtendedData: req AppID={} bufSize={}",
                  reqAppID, reqBufSize);

        std::vector<uint8_t> ticket = Ticket::GetAppOwnershipTicketFromRegistry(reqAppID);
        if (ticket.empty() || ticket.size() < 4) {
            LOG_IPC_WARN("IClientUser::GetAppOwnershipTicketExtendedData: AppId={} ticket empty/short ({} bytes), RETURN no reply",
                         reqAppID, ticket.size());
            return;
        }

        const uint32 ticketSize = static_cast<uint32>(ticket.size());
        const uint32 sigOffset  = *reinterpret_cast<const uint32*>(ticket.data());

        const uint32 totalSize = 1 + 4 + reqBufSize + 16;
        if (static_cast<uint32>(pWrite->m_Put) < totalSize) {
            LOG_IPC_WARN("IClientUser::GetAppOwnershipTicketExtendedData: AppId={} pWrite size={} < required {}, RETURN no reply",
                         reqAppID, pWrite->m_Put, totalSize);
            return;
        }

        uint8* base = pWrite->Base();

        base[0] = IPC_REPLY_TAG;
        memcpy(base + 1, &ticketSize, 4);
        const uint32 copySize = (ticketSize < static_cast<uint32>(reqBufSize))
                              ? ticketSize : static_cast<uint32>(reqBufSize);
        memcpy(base + 5, ticket.data(), copySize);
        if (copySize < static_cast<uint32>(reqBufSize))
            memset(base + 5 + copySize, 0, reqBufSize - copySize);

        const uint32 piAppId      = 16;
        const uint32 piSteamId    = 8;
        const uint32 piSignature  = sigOffset;
        const uint32 pcbSignature = 128;
        const uint32 outOff = 5 + reqBufSize;
        memcpy(base + outOff,      &piAppId,      4);
        memcpy(base + outOff + 4,  &piSteamId,    4);
        memcpy(base + outOff + 8,  &piSignature,  4);
        memcpy(base + outOff + 12, &pcbSignature, 4);

        AppId_t appId = SteamCapture::ResolveAppId();
        LOG_IPC_INFO("IClientUser::GetAppOwnershipTicketExtendedData: AppId={} -> {} bytes "
                  "(sigOffset={}) WROTE REPLY", appId, ticketSize, sigOffset);
    }

    // ── Handler: IClientUser::RequestEncryptedAppTicket ──────────
    void Cmd_IClientUser_RequestEncryptedAppTicket(
        CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t appId = SteamCapture::ResolveAppId();
        LOG_IPC_INFO("RequestEncryptedAppTicket: ENTER AppId={} pWrite.m_Put={}", appId, pWrite->m_Put);
        if (pWrite->m_Put < 9) {
            LOG_IPC_WARN("RequestEncryptedAppTicket: AppId={} pWrite size {} < 9, RETURN no reply", appId, pWrite->m_Put);
            return;
        }

        auto ticket = Ticket::GetEncryptedTicketFromRegistry(appId);
        if (ticket.empty()) {
            LOG_IPC_WARN("RequestEncryptedAppTicket: AppId={} no cached eticket, RETURN no reply", appId);
            return;
        }

        uint8* base = pWrite->Base();
        uint64 hAsyncCall;
        memcpy(&hAsyncCall, base + 1, sizeof(hAsyncCall));

        g_PendingEtickets[hAsyncCall] = appId;
        LOG_IPC_INFO("RequestEncryptedAppTicket: AppId={} hAsyncCall=0x{:016X} RECORDED", appId, hAsyncCall);
    }

    // ── Handler: IClientUser::GetEncryptedAppTicket ───────────────
    void Cmd_IClientUser_GetEncryptedAppTicket(
        CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t appId = SteamCapture::ResolveAppId();
        LOG_IPC_INFO("GetEncryptedAppTicket: ENTER AppId={}", appId);
        auto ticket = Ticket::GetEncryptedTicketFromRegistry(appId);
        if (ticket.empty()) {
            LOG_IPC_WARN("GetEncryptedAppTicket: AppId={} no cached eticket, RETURN no reply", appId);
            return;
        }

        const uint32 ticketSize = static_cast<uint32>(ticket.size());
        const int32 totalSize = 1 + 1 + 4 + ticketSize;
        SteamCapture::EnsureBufferSize(pWrite, totalSize);

        uint8* base = pWrite->Base();
        base[0] = IPC_REPLY_TAG;
        base[1] = 1;
        memcpy(base + 2, &ticketSize, sizeof(ticketSize));
        memcpy(base + 6, ticket.data(), ticketSize);

        LOG_IPC_INFO("GetEncryptedAppTicket: AppId={} -> {} bytes WROTE REPLY", appId, ticketSize);
    }

    const IPCBus::IpcHandlerEntry g_Entries[] = {
        REGISTER_IPC_CMD(IClientUser, GetSteamID),
        REGISTER_IPC_CMD(IClientUser, GetAppOwnershipTicketExtendedData),
        REGISTER_IPC_CMD(IClientUser, RequestEncryptedAppTicket),
        REGISTER_IPC_CMD(IClientUser, GetEncryptedAppTicket),
    };

} // namespace

namespace CmdUser {
    void Register() {
        IPCBus::RegisterHandlers(g_Entries, std::size(g_Entries));
    }

    AppId_t LookupEticketAsyncCall(uint64 hAsyncCall) {
        auto it = g_PendingEtickets.find(hAsyncCall);
        return it != g_PendingEtickets.end() ? it->second : 0;
    }
    void EraseEticketAsyncCall(uint64 hAsyncCall) {
        g_PendingEtickets.erase(hAsyncCall);
    }
}
