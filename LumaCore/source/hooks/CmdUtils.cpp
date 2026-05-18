#include "IPCBus.h"
#include "CmdUtils.h"
#include "CmdUser.h"
#include "SteamCapture.h"
#include "Steam/Callback.h"
#include "utils/Logger.h"

namespace {

    // ── IClientUtils::GetAPICallResult request args ──────────────
    struct GetAPICallResultRequest {
        uint64  hSteamAPICall;     // +0
        uint32  cubCallback;       // +8
        uint32  iCallbackExpected; // +12
    };

    // ── Helper: write the GetAPICallResult response boilerplate ───
    template<typename CallbackT, typename F>
    bool WriteCallbackResponse(CUtlBuffer* pWrite, F&& fill)
    {
        constexpr int32 total = 1 + 1 + sizeof(CallbackT) + 1;
        if (pWrite->m_Put < total) return false;

        uint8* base = pWrite->m_Memory.m_pMemory;
        base[0] = IPC_REPLY_TAG;
        base[1] = 1;
        base[2 + sizeof(CallbackT)] = 0;

        auto* cb = reinterpret_cast<CallbackT*>(base + 2);
        fill(*cb);
        return true;
    }

    // ── Handler: IClientUtils::GetAppID ──────────────────────────
    //  SpawnProcess rewrites pGameID to 480 for OnlineFix games,
    //  so steamclient returns 480.  Restore the real app_id.
    void Cmd_IClientUtils_GetAppID(
        CSteamPipeClient* pipe, CUtlBuffer*, CUtlBuffer* pWrite)
    {
        AppId_t realAppId = SteamCapture::ResolveAppId();
        if (!realAppId || pWrite->m_Put < 5) return;

        AppId_t current = *reinterpret_cast<const AppId_t*>(pWrite->Base() + 1);
        if (current == realAppId) return;

        *reinterpret_cast<AppId_t*>(pWrite->Base() + 1) = realAppId;
        LOG_IPC_INFO("GetAppID: spoof response {} -> {}", current, realAppId);
    }

    // ════════════════════════════════════════════════════════════════
    //  GetAPICallResult per-callback handlers
    // ════════════════════════════════════════════════════════════════

    bool HandleCallback_EncryptedAppTicketResponse(
        CUtlBuffer* pWrite, uint64 hAsyncCall, uint32 cubCallback)
    {
        AppId_t appId = CmdUser::LookupEticketAsyncCall(hAsyncCall);
        if (!appId) return false;

        LOG_IPC_DEBUG("GetAPICallResult: EncryptedAppTicketResponse hAsyncCall=0x{:016X} "
                  "AppId={} - injecting k_EResultOK", hAsyncCall, appId);

        if (!WriteCallbackResponse<EncryptedAppTicketResponse_t>(pWrite, [](auto& cb) {
            cb.m_eResult = k_EResultOK;
        })) return false;

        CmdUser::EraseEticketAsyncCall(hAsyncCall);
        return true;
    }

    struct GacrDispatchEntry {
        uint32  callbackId;
        bool  (*handler)(CUtlBuffer* pWrite, uint64 hAsyncCall, uint32 cubCallback);
    };

    constexpr GacrDispatchEntry g_GacrDispatch[] = {
        { EncryptedAppTicketResponse_t::k_iCallback, HandleCallback_EncryptedAppTicketResponse },
    };

    // ── Handler: IClientUtils::GetAPICallResult ──────────────────
    void Cmd_IClientUtils_GetAPICallResult(
        CSteamPipeClient*, CUtlBuffer* pRead, CUtlBuffer* pWrite)
    {
        if (pRead->m_Put < IPC_ARGS_OFFSET + sizeof(GetAPICallResultRequest)) return;

        const auto* req = reinterpret_cast<const GetAPICallResultRequest*>(
            pRead->Base() + IPC_ARGS_OFFSET);

        AppId_t appId = SteamCapture::GetAppIDForCurrentPipe();
        LOG_IPC_DEBUG("GetAPICallResult: hAsyncCall=0x{:016X} AppId={} iCallback={} cubCallback={}",
                  req->hSteamAPICall, appId, req->iCallbackExpected, req->cubCallback);
        for (auto& entry : g_GacrDispatch) {
            if (entry.callbackId == req->iCallbackExpected) {
                entry.handler(pWrite, req->hSteamAPICall, req->cubCallback);
                return;
            }
        }
    }

    const IPCBus::IpcHandlerEntry g_Entries[] = {
        REGISTER_IPC_CMD(IClientUtils, GetAppID),
        REGISTER_IPC_CMD(IClientUtils, GetAPICallResult),
    };

} // namespace

namespace CmdUtils {
    void Register() {
        IPCBus::RegisterHandlers(g_Entries, std::size(g_Entries));
    }
}
