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
#include <cstdio>

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

    LM_HOOK(IClientRemoteStorage_FileExists, bool,
              void* pThis, AppId_t appId, uint32_t fileRoot, const char* pchFile)
    {
        AppId_t real = SteamCapture::ActiveRouteRealAppId();
        if (real && appId == kOnlineFixAppId)
            appId = real;

        return oIClientRemoteStorage_FileExists(
            pThis, appId, fileRoot, pchFile);
    }

    LM_HOOK(IClientRemoteStorage_Dispatch, bool, void* pThis, void* pArg)
    {
        uint32_t* pAppId = reinterpret_cast<uint32_t*>(reinterpret_cast<uint8_t*>(pThis) + 0x38);
        uint32_t saved = *pAppId;
        AppId_t real = SteamCapture::ActiveRouteRealAppId();
        if (real && saved == kOnlineFixAppId)
            *pAppId = real;
        bool result = oIClientRemoteStorage_Dispatch(pThis, pArg);
        *pAppId = saved;
        return result;
    }

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
                if (iface == EIPCInterface::IClientRemoteStorage) {
                    uint32_t fHash = *reinterpret_cast<const uint32_t*>(raw + OFFSET_FUNC_HASH);
                    AppId_t real = SteamCapture::ActiveRouteRealAppId();
                    if (real && (fHash == 0x376E83D6 || fHash == 0xC69A678D || fHash == 0xA0F6FDBD)) {
                        DWORD steamId32 = 0;
                        HKEY hKey;
                        if (RegOpenKeyExA(HKEY_CURRENT_USER,
                                "Software\\Valve\\Steam\\ActiveProcess", 0,
                                KEY_READ | KEY_WOW64_64KEY, &hKey) == ERROR_SUCCESS) {
                            DWORD cb = sizeof(steamId32);
                            RegQueryValueExA(hKey, "ActiveUser", nullptr, nullptr,
                                             reinterpret_cast<LPBYTE>(&steamId32), &cb);
                            RegCloseKey(hKey);
                        }
                        if (steamId32) {
                            const uint8_t* reqData = raw + IPC_HEADER_SIZE;
                            const uint32_t reqLen = pRead->TellPut() - IPC_HEADER_SIZE;
                            char filenameBuf[256]{};
                            {
                                const char* p = reinterpret_cast<const char*>(reqData);
                                const char* end = p + reqLen;
                                const char* best = nullptr;
                                int bestLen = 0;
                                while (p < end) {
                                    if (*p >= 0x20 && *p < 0x7F) {
                                        const char* start = p;
                                        while (p < end && *p >= 0x20 && *p < 0x7F) ++p;
                                        int len = static_cast<int>(p - start);
                                        if (len > bestLen) { bestLen = len; best = start; }
                                    } else { ++p; }
                                }
                                if (best && bestLen > 0 && bestLen < 256)
                                    memcpy(filenameBuf, best, bestLen);
                            }
                            if (filenameBuf[0]) {
                                char savePath[512];
                                snprintf(savePath, sizeof(savePath),
                                         "%s/userdata/%u/%u/remote/%s",
                                         SteamInstallPath, steamId32, real, filenameBuf);

                                auto ensureCap = [&](uint32_t need) -> bool {
                                    if (pWrite->m_Memory.m_nAllocationCount >= need) return true;
                                    if (!pWrite->m_PutOverflowFunc) return false;
                                    return (pWrite->*pWrite->m_PutOverflowFunc)(need);
                                };

                                if (fHash == 0x376E83D6) {  // FileExists
                                    if (GetFileAttributesA(savePath) != INVALID_FILE_ATTRIBUTES) {
                                        if (ensureCap(14)) {
                                            uint8_t frame[14] = {};
                                            uint32_t len = 14; memcpy(frame, &len, 4);
                                            uint32_t result = 0; memcpy(frame + 4, &result, 4);
                                            frame[8] = 1;
                                            memcpy(pWrite->Base(), frame, 14);
                                            pWrite->m_Put = 14;
                                            LOG_IPCRTR_INFO("\"evt\" \"SaveInject\" \"fn\" \"FileExists\" \"path\" \"{}\" \"result\" \"found\"", savePath);
                                            return true;
                                        }
                                        LOG_IPCRTR_INFO("\"evt\" \"SaveInject\" \"fn\" \"FileExists\" \"path\" \"{}\" \"result\" \"cap-grow-failed\"", savePath);
                                    } else {
                                        LOG_IPCRTR_INFO("\"evt\" \"SaveInject\" \"fn\" \"FileExists\" \"path\" \"{}\" \"result\" \"not-found\"", savePath);
                                    }
                                } else if (fHash == 0xC69A678D) {  // GetFileSize
                                    HANDLE hFile = CreateFileA(savePath, GENERIC_READ,
                                        FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                        FILE_ATTRIBUTE_NORMAL, nullptr);
                                    if (hFile != INVALID_HANDLE_VALUE) {
                                        DWORD fileSize = GetFileSize(hFile, nullptr);
                                        CloseHandle(hFile);
                                        if (fileSize != INVALID_FILE_SIZE && ensureCap(14)) {
                                            uint8_t frame[14] = {};
                                            uint32_t len = 14; memcpy(frame, &len, 4);
                                            uint32_t result = 0; memcpy(frame + 4, &result, 4);
                                            memcpy(frame + 8, &fileSize, 4);
                                            memcpy(pWrite->Base(), frame, 14);
                                            pWrite->m_Put = 14;
                                            LOG_IPCRTR_INFO("\"evt\" \"SaveInject\" \"fn\" \"GetFileSize\" \"path\" \"{}\" \"size\" {}", savePath, fileSize);
                                            return true;
                                        }
                                    }
                                } else if (fHash == 0xA0F6FDBD) {  // FileRead
                                    HANDLE hFile = CreateFileA(savePath, GENERIC_READ,
                                        FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                        FILE_ATTRIBUTE_NORMAL, nullptr);
                                    if (hFile != INVALID_HANDLE_VALUE) {
                                        DWORD fileSize = GetFileSize(hFile, nullptr);
                                        if (fileSize != INVALID_FILE_SIZE && fileSize < 1 * 1024 * 1024
                                            && ensureCap(14u + fileSize)) {
                                            uint8_t frame[14] = {};
                                            uint32_t totalLen = 14 + fileSize; memcpy(frame, &totalLen, 4);
                                            uint32_t result = 0; memcpy(frame + 4, &result, 4);
                                            memcpy(frame + 8, &fileSize, 4);
                                            memcpy(pWrite->Base(), frame, 14);
                                            DWORD read = 0;
                                            ReadFile(hFile, pWrite->Base() + 14, fileSize, &read, nullptr);
                                            pWrite->m_Put = 14 + read;
                                            CloseHandle(hFile);
                                            LOG_IPCRTR_INFO("\"evt\" \"SaveInject\" \"fn\" \"FileRead\" \"path\" \"{}\" \"size\" {} \"read\" {}", savePath, fileSize, read);
                                            return true;
                                        }
                                        CloseHandle(hFile);
                                    }
                                }
                            }
                        }
                    }
                }
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
        {
            static constexpr StringXRefSig kFileExistsSigs[] = {
                {"IClientRemoteStorage::FileExists", ""},
            };
            LM_INSTALL_STR(IClientRemoteStorage_FileExists, kFileExistsSigs, 1);
        }
        {
            static constexpr StringXRefSig kDispatchSigs[] = {
                {"IClientRemoteStorage::Dispatch", ""},
            };
            LM_INSTALL_STR(IClientRemoteStorage_Dispatch, kDispatchSigs, 1);
        }
        LM_TX_COMMIT();

        LOG_IPCRTR_INFO("\"event\" \"install\" \"hook\" \"0x{:X}\"",
                       reinterpret_cast<uintptr_t>(oIPCProcessMessage));
    }

    void Uninstall() {
        LM_TX_BEGIN();
        LM_REMOVE(IPCProcessMessage);
        LM_REMOVE(IClientRemoteStorage_FileExists);
        LM_REMOVE(IClientRemoteStorage_Dispatch);
        LM_TX_COMMIT();
        oGetPipeClient = nullptr;
        Registry::Clear();
        PipeWatch::Reset();
    }

}
