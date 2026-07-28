// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/IPCBus.h"
#include "hooks/client/CmdUser.h"
#include "hooks/client/CmdUtils.h"
#include "hooks/Macros.h"
#include "hooks/client/PipeWatch.h"
#include "core/entry.h"
#include "runtime/LcFnvHash.h"
#include "runtime/IpcSpecLoader.h"
#include "hooks/capture/SteamCapture.h"
#include <map>

// ── pipe retriever, needed by LM_BIND macro (fn##_t expansion) ──
using GetPipeClient_t = CSteamPipeClient*(*)(void* pEngine, HSteamPipe hSteamPipe);
GetPipeClient_t oGetPipeClient = nullptr;

namespace IPCBus::Registry {

    static CSteamPipeClient* PipeForHandle(void* pServer, HSteamPipe handle) {
        return oGetPipeClient ? oGetPipeClient(pServer, handle) : nullptr;
    }

    static constexpr uint64_t BuildKey(EIPCInterface iface, uint32_t funcHash) {
        return (static_cast<uint64_t>(iface) << 32) | funcHash;
    }

    static std::map<uint64_t, IpcHandlerEntry> s_table;

    void Add(const IpcHandlerEntry* entries, size_t count) {
        for (size_t i = 0; i < count; ++i) {
            auto entry = entries[i];
            if (IpcSpecLoader::IsLoaded()) {
                auto specHash = IpcSpecLoader::ResolveHash(entry.name);
                if (specHash)
                    entry.funcHash = *specHash;
            }
            s_table.emplace(BuildKey(entry.interfaceID, entry.funcHash), entry);
        }
    }

    const IpcHandlerEntry* Lookup(EIPCInterface iface, uint32_t funcHash) {
        auto it = s_table.find(BuildKey(iface, funcHash));
        return (it != s_table.end()) ? &it->second : nullptr;
    }

    void Clear() {
        s_table.clear();
    }

    // internal pipes (engine-side, appid=0) get passthrough treatment
    static bool IsInternal(const CSteamPipeClient* pipe) {
        return !pipe || ((pipe->m_hSteamPipe & 0xFFFF) <= 2);
    }

    struct CallFrame {
        CSteamPipeClient*       pipe    = nullptr;
        const IpcHandlerEntry*  handler = nullptr;
        bool                    statsCall = false;
        bool                    Good() const { return pipe && handler; }
    };

    static CallFrame SetupFrame(void* pServer, HSteamPipe hPipe, CUtlBuffer* pRead) {
        CallFrame f;
        f.pipe = PipeForHandle(pServer, hPipe);
        if (!f.pipe) return f;

        if (pRead->TellPut() >= IPC_HEADER_SIZE) {
            const auto* raw = pRead->Base();
            const auto ec = static_cast<EIPCCommand>(raw[OFFSET_CMD]);

            LOG_IPCRTR_INFO("\"cmd\" \"{}\" \"pipe\" \"0x{:08X}\" \"size\" {}",
                EIPCCommandName(ec), f.pipe->m_hSteamPipe, pRead->TellPut());

            if (ec == EIPCCommand::Handshake) {
                LOG_IPCRTR_INFO("\"evt\" \"handshake\" \"pipe\" \"{}\"", f.pipe->DebugString());
                if (!IsInternal(f.pipe))
                    PipeWatch::OnHandshake(f.pipe, pRead);
            } else if (ec == EIPCCommand::InterfaceCall) {
                if (IsInternal(f.pipe)) {
                    LOG_IPCRTR_INFO("\"cmd\" \"InterfaceCall\" \"pipe\" \"0x{:08X}\" \"action\" \"passthrough\"",
                        f.pipe->m_hSteamPipe);
                    return CallFrame{f.pipe, nullptr, false};
                }
                PipeWatch::TouchPipe(f.pipe);
                const auto iface = static_cast<EIPCInterface>(raw[OFFSET_INTERFACE_ID]);
                const uint32_t fHash = *reinterpret_cast<const uint32_t*>(raw + OFFSET_FUNC_HASH);
                f.statsCall = (iface == EIPCInterface::IClientUserStats);
                f.handler = Lookup(iface, fHash);
                if (f.handler) {
                    LOG_IPCRTR_INFO("\"cmd\" \"InterfaceCall\" \"name\" \"{}\" \"pipe\" \"{}\" \"realAppId\" {} \"AppId\" {}",
                        f.handler->name, f.pipe->DebugString(),
                        SteamCapture::ResolveAppId(), SteamCapture::GetAppIDForCurrentPipe());
                } else {
                    LOG_IPCRTR_INFO("\"cmd\" \"InterfaceCall\" \"iface\" \"{}\" \"hash\" \"0x{:08X}\" \"pipe\" \"{}\" \"realAppId\" {} \"AppId\" {}",
                        EIPCInterfaceName(iface), fHash, f.pipe->DebugString(),
                        SteamCapture::ResolveAppId(), SteamCapture::GetAppIDForCurrentPipe());
                }
            } else {
                LOG_IPCRTR_INFO("\"cmd\" \"{}\" \"pipe\" \"{}\"", EIPCCommandName(ec), f.pipe->DebugString());
            }
        }
        return f;
    }

} // namespace IPCBus::Registry

namespace {

    using namespace IPCBus::Registry;

    // RAII guard: enters stats scope on construction, leaves on destruction.
    // only activates when statsCall is true — no-ops otherwise.
    struct StatsGuard {
        bool m_active;
        HSteamPipe m_pipe;
        StatsGuard(bool doActivate, HSteamPipe pipe) : m_active(doActivate), m_pipe(pipe) {
            if (m_active) {
                SteamCapture::SetUserStatsContext(true);
                SteamCapture::EnterStatsScope(m_pipe);
            }
        }
        ~StatsGuard() {
            if (m_active) {
                SteamCapture::LeaveStatsScope();
                SteamCapture::SetUserStatsContext(false);
            }
        }
    };

    LM_HOOK(IPCProcessMessage, bool,
              void* pServer, HSteamPipe hPipe,
              CUtlBuffer* pRead, CUtlBuffer* pWrite)
    {
        if (pRead->TellPut() >= IPC_HEADER_SIZE) {
            const auto* raw = pRead->Base();
            if (raw[OFFSET_CMD] == static_cast<uint8_t>(EIPCCommand::InterfaceCall)) {
                const auto iface = static_cast<EIPCInterface>(raw[OFFSET_INTERFACE_ID]);
                if (iface == EIPCInterface::IClientNetworkingSocketsSerialized)
                    SteamCapture::NotifyNetworkingSocketsUsed();
            }
        }

        auto f = SetupFrame(pServer, hPipe, pRead);
        StatsGuard guard(f.statsCall, hPipe);

        const bool ok = oIPCProcessMessage(pServer, hPipe, pRead, pWrite);
        if (!ok || !f.handler) return ok;

        AppId_t appId = SteamCapture::ResolveAppId();
        if (!LuaLoader::HasDepot(appId)) {
            LOG_IPCRTR_INFO("\"cmd\" \"{}\" \"appId\" {} \"action\" \"skip-nodepot\" \"pipe\" \"{}\"",
                f.handler->name, appId, f.pipe ? f.pipe->DebugString() : "null");
            return ok;
        }

        f.handler->handler(f.pipe, pRead, pWrite);
        return ok;
    }

} // namespace

namespace IPCBus {

    void RegisterHandlers(const IpcHandlerEntry* entries, size_t count) {
        Registry::Add(entries, count);
    }

    void Install() {
        LM_BIND(GetPipeClient);
        CmdUser::Register();

        LM_TX_BEGIN();
        LM_INSTALL(IPCProcessMessage);
        LM_TX_COMMIT();

        LOG_IPCRTR_INFO("\"event\" \"install\" \"hook\" \"0x{:X}\"",
                       reinterpret_cast<uintptr_t>(oIPCProcessMessage));
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(IPCProcessMessage);
        LM_TX_COMMIT();
        oGetPipeClient = nullptr;
        Registry::Clear();
        PipeWatch::Reset();
    }

}
