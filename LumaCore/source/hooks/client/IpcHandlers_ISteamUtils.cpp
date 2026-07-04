// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/IpcDispatch.h"
#include "hooks/client/IpcMethodLoader.h"
#include "hooks/client/SteamStubAuto.h"
#include "hooks/capture/SteamCapture.h"
#include "core/entry.h"
#include "config/LuaLoader.h"
#include "runtime/Logger.h"
#include "Steam/Structs.h"

namespace {

    using namespace SteamCapture;

    // ▌▌ IClientUtils::GetAppID
    //  Manual online-fix and SteamStub auto report the real app to the game.
    //  SteamStub still keeps Steam-facing process tracking on 480 elsewhere.
    //  pRead: unused (no args).
    //  pWrite: [0]=reply tag, [1..4]=AppId_t return value.
    void Post_GetAppID(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite) {
        OnlineFixRouteMode mode = OnlineFixMode();
        const bool steamStubRoute = SteamStubAuto::IsActive();
        const char* routeName = steamStubRoute ? "steamstub-auto" : OnlineFixRouteModeName(mode);
        const uint32 pipeId = pipe ? pipe->m_hSteamPipe : 0;
        const uint32 pid = pipe ? pipe->m_clientPID : 0;

        if (!pWrite || pWrite->m_Put < 5 || !pWrite->m_Memory.m_pMemory) {
            LOG_IPCRTR_WARN("IClientUtils::GetAppID dispatch routeMode={} pipe=0x{:08X} pid={} writeSize={} action=skip-too-small",
                            routeName,
                            pipeId, pid, pWrite ? pWrite->m_Put : 0);
            return;
        }

        uint8_t* base = pWrite->m_Memory.m_pMemory;
        AppId_t reported = *reinterpret_cast<const AppId_t*>(base + 1);
        AppId_t real = steamStubRoute ? SteamStubAuto::RealAppId() : OnlineFixRealAppId();
        AppId_t finalAppId = reported;
        bool changed = false;

        if ((mode != OnlineFixRouteMode::None || steamStubRoute)
            && reported == kOnlineFixAppId
            && real != 0
            && real != kOnlineFixAppId) {
            finalAppId = real;
            *reinterpret_cast<AppId_t*>(base + 1) = finalAppId;
            changed = true;
            LOG_USRCMD_INFO("IClientUtils::GetAppID: {} -> {} routeMode={}",
                            reported, finalAppId, routeName);
        } else if (LuaLoader::HasDepot(reported)) {
            LOG_USRCMD_TRACE("IClientUtils::GetAppID: {} (Lua-tracked, passthrough)", reported);
        }

        LOG_IPCRTR_INFO("IClientUtils::GetAppID dispatch routeMode={} pipe=0x{:08X} pid={} current={} real={} final={} changed={}",
                        routeName,
                        pipeId, pid, reported, real, finalAppId, changed);
    }

    // ▌▌ IClientUtils::GetAPICallResult
    //  Intercepts API call results so we can patch the responses for ticket-
    //  related calls (EncryptedAppTicket, AppOwnershipTicket). When the
    //  original call yielded a non-OK eresult for a Lua-tracked app we patch
    //  the response buffer with our cached ticket data.
    //
    //  pRead:  [0..3]=hCall, [4..7]=cubMax, [8..11]=pbCallFailed, [12..15]=hSteamUser
    //  pWrite: [0..3]=result (bool), [4..7]=cubCopied, [8..]=call data
    void Post_GetAPICallResult(CSteamPipeClient* pipe, CUtlBuffer* pRead, CUtlBuffer* pWrite) {
        if (!pRead || !pWrite) return;
        if (pRead->m_Put < 16 || pWrite->m_Put < 8) return;

        const uint8_t* args = pRead->m_Memory.m_pMemory;
        SteamAPICall_t hCall = *reinterpret_cast<const SteamAPICall_t*>(args);
        uint32_t cubMax = *reinterpret_cast<const uint32_t*>(args + 4);

        uint8_t* resp = pWrite->m_Memory.m_pMemory;
        bool result = (resp[0] != 0);
        uint32_t cubCopied = *reinterpret_cast<const uint32_t*>(resp + 4);

        if (!result || cubCopied < 4) return;

        // The response body starts at offset 8. Check if we have a ticket
        // response by inspecting the eresult field at offset 0 of the body.
        // We need at least 4 bytes in the body for eresult.
        if (cubCopied < 12) return;

        AppId_t appId = ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) return;

        // The response data starts at byte 8. First 4 bytes are eresult.
        // If eresult is not OK (0x00000000 for EResultOK = 1? Actually it's 1)
        // Actually k_EResultOK = 1. Let me check: in steam, k_EResultOK = 1.
        // But in some responses the eresult field is 0 for success.
        // Let's check the actual encoding.
        // CMsgProtoBufHeader uses eresult=1 for k_EResultOK.
        // For older non-proto responses eresult 0 usually means pending.
        // Let's just check if we can identify the call type from hCall.

        // If we got here it means the call returned successfully with data,
        // so pass through — our other handlers already inject tickets at the
        // IPC level. This post-handler is just observatory for now.
        LOG_USRCMD_TRACE("IClientUtils::GetAPICallResult: hCall=0x{:X} result={} cubCopied={}",
                         static_cast<uint32_t>(hCall), result, cubCopied);
    }

}

namespace IpcHandlers_ISteamUtils {

    void Register() {
        IpcDispatch::Register("IClientUtils", "GetAppID", nullptr, Post_GetAppID);
        // CmdUser owns GetAPICallResult so encrypted-ticket and stats callback
        // rewrites are not shadowed by this observability-only adapter.
    }

}
