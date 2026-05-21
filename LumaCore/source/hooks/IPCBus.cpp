#include "IPCBus.h"
#include "CmdUser.h"
#include "CmdUtils.h"
#include "Macros.h"
#include "entry.h"
#include "utils/Hash.h"
#include "SteamCapture.h"
#include <unordered_map>

namespace {

    using GetPipeClient_t = CSteamPipeClient*(*)(void* pEngine, HSteamPipe hSteamPipe);
    GetPipeClient_t oGetPipeClient = nullptr;

    static CSteamPipeClient* GetPipe(void* pServer, HSteamPipe hSteamPipe) {
        return oGetPipeClient ? oGetPipeClient(pServer, hSteamPipe) : nullptr;
    }

    // ════════════════════════════════════════════════════════════════
    //  Handler registry
    // ════════════════════════════════════════════════════════════════
    using namespace IPCBus;

    static constexpr uint64 MakeHandlerKey(EIPCInterface iface, uint32 funcHash) {
        return (static_cast<uint64>(iface) << 32) | funcHash;
    }

    std::unordered_map<uint64, IpcHandlerEntry> g_Handlers;

    static const IpcHandlerEntry* FindHandler(EIPCInterface iface, uint32 funcHash) {
        auto it = g_Handlers.find(MakeHandlerKey(iface, funcHash));
        return (it != g_Handlers.end()) ? &it->second : nullptr;
    }

    // ════════════════════════════════════════════════════════════════
    //  Main hook
    // ════════════════════════════════════════════════════════════════
    LC_HOOK_DEF(IPCProcessMessage, bool,
              void* pServer, HSteamPipe hSteamPipe,
              CUtlBuffer* pRead, CUtlBuffer* pWrite)
    {
        auto* pipe = GetPipe(pServer, hSteamPipe);

        // ── Parse header, find handler ──────────────────────────
        const IpcHandlerEntry* entry = nullptr;

        if (pRead->TellPut() >= IPC_HEADER_SIZE) {
            const uint8* data = pRead->Base();
            const auto cmd = static_cast<EIPCCommand>(data[OFFSET_CMD]);

            if (cmd == EIPCCommand::Handshake) {
                if (pipe) LOG_IPC_INFO("[Handshake]: {}", pipe->DebugString());
            } else if (cmd == EIPCCommand::InterfaceCall) {
                // exclude InterfaceCall from steam
                if (!pipe || (pipe->m_hSteamPipe & 0xFFFF) <= 2) {
                    LOG_IPC_TRACE("[InterfaceCall] from steam, pipe=0x{:08X} skip handler", pipe->m_hSteamPipe);
                    return oIPCProcessMessage(pServer, hSteamPipe, pRead, pWrite);
                }
                const auto iface = static_cast<EIPCInterface>(data[OFFSET_INTERFACE_ID]);
                const uint32 funcHash = *reinterpret_cast<const uint32*>(data + OFFSET_FUNC_HASH);
                entry = FindHandler(iface, funcHash);
                if (entry) {
                    LOG_IPC_DEBUG("[InterfaceCall] {} {} realAppId={},AppId={}",
                                  entry->name, pipe->DebugString(),
                                  SteamCapture::ResolveAppId(),
                                  SteamCapture::GetAppIDForCurrentPipe()
                                );
                } else {
                    LOG_IPC_TRACE("[InterfaceCall(unhandled)]{}::0x{:08X} {} realAppId={},AppId={}",
                                  EIPCInterfaceName(iface), funcHash,
                                  pipe->DebugString(),
                                  SteamCapture::ResolveAppId(),
                                  SteamCapture::GetAppIDForCurrentPipe()
                                );
                }
            } else {
                LOG_IPC_TRACE("[{}] {}", EIPCCommandName(cmd), pipe->DebugString());
            }
        }

        // ── Run original ────────────────────────────────────────
        const bool result = oIPCProcessMessage(pServer, hSteamPipe, pRead, pWrite);
        if (!result || !entry) return result;

        // Only run handlers for apps with configured depots.
        AppId_t appId = SteamCapture::ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) {
            LOG_IPC_TRACE("{}: appId={} has no configured depot, skip handler {}",
                entry->name, appId, pipe->DebugString());
            return result;
        }

        entry->handler(pipe, pRead, pWrite);
        return result;
    }

} // namespace


namespace IPCBus {

    void RegisterHandlers(const IpcHandlerEntry* entries, size_t count) {
        g_Handlers.reserve(g_Handlers.size() + count);
        for (size_t i = 0; i < count; ++i)
            g_Handlers.emplace(MakeHandlerKey(entries[i].interfaceID, entries[i].funcHash), entries[i]);
    }

    void Install() {
        LC_RESOLVE_D(GetPipeClient);

        // Interface modules register their handlers here.
        CmdUser::Register();
        CmdUtils::Register();

        LC_TX_OPEN();
        LC_ATTACH_D(IPCProcessMessage);
        LC_TX_COMMIT();
    }

    void Uninstall() {
        LC_TX_OPEN();
        LC_DETACH(IPCProcessMessage);
        LC_TX_COMMIT();
        oGetPipeClient = nullptr;
        g_Handlers.clear();
    }

}
