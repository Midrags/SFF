// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/PipeWatch.h"

#include "AuthWindow.h"
#include "OnlineFixInject.h"
#include "ProcessExtension.h"
#include "hooks/client/SteamStubAuto.h"
#include "hooks/capture/SteamCapture.h"
#include "runtime/Logger.h"
#include "runtime/RemoteTools.h"
#include "config/Settings.h"
#include "config/LuaLoader.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstddef>
#include <cstring>
#include <cwchar>
#include <filesystem>
#include <format>
#include <iterator>
#include <mutex>
#include <optional>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <windows.h>
#include <tlhelp32.h>

namespace {

    struct ProcessKeyHash {
        std::size_t operator()(const PipeWatch::ProcessKey& key) const noexcept {
            return (static_cast<std::size_t>(key.pid) << 1) ^
                   static_cast<std::size_t>(key.creation ^ (key.creation >> 32));
        }
    };

    struct PipeKey {
        uint32 pid = 0;
        HSteamPipe pipe = 0;

        bool operator==(const PipeKey&) const = default;
    };

    struct PipeKeyHash {
        std::size_t operator()(const PipeKey& key) const noexcept {
            return (static_cast<std::size_t>(key.pid) << 1) ^
                   static_cast<std::size_t>(key.pipe);
        }
    };

    std::mutex g_lock;
    std::unordered_map<PipeWatch::ProcessKey, PipeWatch::ProcessSnapshot, ProcessKeyHash> g_processes;
    std::unordered_map<PipeKey, PipeWatch::ProcessKey, PipeKeyHash> g_pipes;

    constexpr size_t kMaxEnvironmentBytes = 1024 * 1024;

    namespace NtMini {

        enum ProcessInfoClass : ULONG {
            BasicInformation = 0,
            Wow64Information = 26,
        };

        enum MemoryInfoClass : ULONG {
            MemoryBasicInformation = 0,
        };

        struct ProcessBasicInformation {
            NTSTATUS exitStatus;
            PVOID pebBaseAddress;
            ULONG_PTR affinityMask;
            LONG basePriority;
            ULONG_PTR uniqueProcessId;
            ULONG_PTR inheritedFromUniqueProcessId;
        };

        struct Peb64 {
            BYTE reserved0[0x20];
            PVOID processParameters;
        };

        struct ProcessParameters64 {
            BYTE reserved0[0x80];
            PVOID environment;
        };

        struct Peb32 {
            BYTE reserved0[0x10];
            uint32 processParameters;
        };

        struct ProcessParameters32 {
            BYTE reserved0[0x48];
            uint32 environment;
        };

        using QueryProcess = NTSTATUS(NTAPI*)(HANDLE, ProcessInfoClass, PVOID, ULONG, PULONG);
        using QueryMemory = NTSTATUS(NTAPI*)(HANDLE, PVOID, MemoryInfoClass, PVOID, SIZE_T, PSIZE_T);

        static_assert(offsetof(Peb64, processParameters) == 0x20);
        static_assert(offsetof(ProcessParameters64, environment) == 0x80);
        static_assert(offsetof(Peb32, processParameters) == 0x10);
        static_assert(offsetof(ProcessParameters32, environment) == 0x48);

    } // namespace NtMini

    constexpr std::array<const char*, 6> kSteamNames = {
        "steam.exe",
        "steamwebhelper.exe",
        "steamservice.exe",
        "steamerrorreporter.exe",
        "gameoverlayui.exe",
        "gameoverlayui64.exe",
    };

    struct ModuleScan {
        uint32 count = 0;
        bool steamClient = false;
        bool steamApi = false;
        bool eosSdk = false;
        std::string steamClientPath;
        std::string steamApiPath;
        std::string eosSdkPath;
    };

    struct SteamEnvIds {
        AppId_t steamAppId = k_uAppIdInvalid;
        AppId_t steamGameId = k_uAppIdInvalid;
        AppId_t steamOverlayGameId = k_uAppIdInvalid;
        AppId_t selected = k_uAppIdInvalid;
        std::string source;
    };

    PipeKey MakePipeKey(const CSteamPipeClient* pipe) {
        if (!pipe) return {};
        return PipeKey{pipe->m_clientPID, static_cast<HSteamPipe>(pipe->m_hSteamPipe)};
    }

    std::string Lower(std::string text) {
        std::ranges::transform(text, text.begin(), [](unsigned char ch) {
            return static_cast<char>(std::tolower(ch));
        });
        return text;
    }

    bool IsSteamProcessName(const std::string& name) {
        const std::string lowered = Lower(name);
        return std::ranges::find(kSteamNames, lowered) != kSteamNames.end();
    }

    std::string BaseName(const std::string& path) {
        const auto slash = path.find_last_of("\\/");
        if (slash == std::string::npos) return path;
        return path.substr(slash + 1);
    }

    std::string WideToUtf8(std::wstring_view text) {
        if (text.empty())
            return {};
        int needed = WideCharToMultiByte(CP_UTF8, 0, text.data(),
                                         static_cast<int>(text.size()),
                                         nullptr, 0, nullptr, nullptr);
        if (needed <= 0)
            return {};
        std::string out(static_cast<std::size_t>(needed), '\0');
        WideCharToMultiByte(CP_UTF8, 0, text.data(),
                            static_cast<int>(text.size()),
                            out.data(), needed, nullptr, nullptr);
        return out;
    }

    ModuleScan InspectModules(uint32 pid) {
        ModuleScan scan{};
        if (pid == 0) return scan;

        auto modules = RemoteTools::EnumerateModules(pid);
        scan.count = static_cast<uint32>(modules.size());
        for (const auto& module : modules) {
            const std::string lowered = Lower(WideToUtf8(module.name));
            if ((lowered == "steamclient.dll" || lowered == "steamclient64.dll") && !scan.steamClient) {
                scan.steamClient = true;
                scan.steamClientPath = WideToUtf8(module.path);
            } else if ((lowered == "steam_api.dll" || lowered == "steam_api64.dll") && !scan.steamApi) {
                scan.steamApi = true;
                scan.steamApiPath = WideToUtf8(module.path);
            } else if (lowered == "eossdk-win64-shipping.dll" && !scan.eosSdk) {
                scan.eosSdk = true;
                scan.eosSdkPath = WideToUtf8(module.path);
            }
        }
        return scan;
    }

    uint64 QueryCreation(uint32 pid) {
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (!process) return 0;

        FILETIME created{}, exited{}, kernel{}, user{};
        uint64 result = 0;
        if (GetProcessTimes(process, &created, &exited, &kernel, &user)) {
            result = (static_cast<uint64>(created.dwHighDateTime) << 32) |
                     static_cast<uint64>(created.dwLowDateTime);
        }
        CloseHandle(process);
        return result;
    }

    std::string QueryImagePath(uint32 pid) {
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (!process) return {};

        char path[32768] = {};
        DWORD size = static_cast<DWORD>(std::size(path));
        std::string result;
        if (QueryFullProcessImageNameA(process, 0, path, &size) && size > 0) {
            result.assign(path, size);
        }
        CloseHandle(process);
        return result;
    }

    template <typename Fn>
    Fn NtdllProc(const char* name) {
        HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
        if (!ntdll) return nullptr;
        return reinterpret_cast<Fn>(GetProcAddress(ntdll, name));
    }

    template <typename T>
    std::optional<T> ReadRemoteValue(HANDLE process, const void* address) {
        T value{};
        SIZE_T bytesRead = 0;
        if (!ReadProcessMemory(process, address, &value, sizeof(value), &bytesRead) ||
            bytesRead != sizeof(value)) {
            return std::nullopt;
        }
        return value;
    }

    const void* AddOffset(const void* base, size_t offset) {
        return reinterpret_cast<const void*>(reinterpret_cast<uintptr_t>(base) + offset);
    }

    std::optional<PVOID> NativeEnvironmentAddress(HANDLE process) {
        auto query = NtdllProc<NtMini::QueryProcess>("NtQueryInformationProcess");
        if (!query) return std::nullopt;

        NtMini::ProcessBasicInformation info{};
        const NTSTATUS status = query(process, NtMini::BasicInformation, &info, sizeof(info), nullptr);
        if (status < 0 || !info.pebBaseAddress) return std::nullopt;

        auto params = ReadRemoteValue<PVOID>(
            process,
            AddOffset(info.pebBaseAddress, offsetof(NtMini::Peb64, processParameters)));
        if (!params || !*params) return std::nullopt;

        auto environment = ReadRemoteValue<PVOID>(
            process,
            AddOffset(*params, offsetof(NtMini::ProcessParameters64, environment)));
        if (!environment || !*environment) return std::nullopt;

        return *environment;
    }

    std::optional<PVOID> Wow64EnvironmentAddress(HANDLE process) {
        auto query = NtdllProc<NtMini::QueryProcess>("NtQueryInformationProcess");
        if (!query) return std::nullopt;

        ULONG_PTR peb32 = 0;
        const NTSTATUS status = query(process, NtMini::Wow64Information, &peb32, sizeof(peb32), nullptr);
        if (status < 0 || peb32 == 0) return std::nullopt;

        auto params = ReadRemoteValue<uint32>(
            process,
            AddOffset(reinterpret_cast<const void*>(peb32), offsetof(NtMini::Peb32, processParameters)));
        if (!params || *params == 0) return std::nullopt;

        auto environment = ReadRemoteValue<uint32>(
            process,
            AddOffset(reinterpret_cast<const void*>(static_cast<uintptr_t>(*params)),
                      offsetof(NtMini::ProcessParameters32, environment)));
        if (!environment || *environment == 0) return std::nullopt;

        return reinterpret_cast<PVOID>(static_cast<uintptr_t>(*environment));
    }

    std::optional<size_t> ReadableBytes(HANDLE process, PVOID address) {
        auto query = NtdllProc<NtMini::QueryMemory>("NtQueryVirtualMemory");
        if (!query) return std::nullopt;

        MEMORY_BASIC_INFORMATION info{};
        const NTSTATUS status = query(
            process, address, NtMini::MemoryBasicInformation, &info, sizeof(info), nullptr);
        if (status < 0 || info.RegionSize == 0) return std::nullopt;

        const auto base = reinterpret_cast<uintptr_t>(info.BaseAddress);
        const auto env = reinterpret_cast<uintptr_t>(address);
        if (env < base) return std::nullopt;

        const size_t offset = static_cast<size_t>(env - base);
        if (offset >= info.RegionSize) return std::nullopt;
        return (std::min)(info.RegionSize - offset, kMaxEnvironmentBytes);
    }

    std::optional<std::vector<wchar_t>> ReadEnvironmentBlock(HANDLE process) {
        auto env = Wow64EnvironmentAddress(process);
        if (!env) env = NativeEnvironmentAddress(process);
        if (!env) return std::nullopt;

        auto bytes = ReadableBytes(process, *env);
        if (!bytes || *bytes < sizeof(wchar_t) * 2) return std::nullopt;

        std::vector<wchar_t> data(*bytes / sizeof(wchar_t));
        SIZE_T bytesRead = 0;
        if (!ReadProcessMemory(process, *env, data.data(), data.size() * sizeof(wchar_t), &bytesRead))
            return std::nullopt;

        data.resize(bytesRead / sizeof(wchar_t));
        auto end = std::adjacent_find(data.begin(), data.end(), [](wchar_t lhs, wchar_t rhs) {
            return lhs == L'\0' && rhs == L'\0';
        });
        if (end == data.end()) return std::nullopt;

        data.erase(std::next(end, 2), data.end());
        return data;
    }

    std::optional<std::string> FindEnvironmentValue(const std::vector<wchar_t>& block,
                                                    std::wstring_view name) {
        size_t offset = 0;
        while (offset < block.size() && block[offset] != L'\0') {
            const wchar_t* entry = block.data() + offset;
            const size_t length = wcslen(entry);
            if (length > name.size() &&
                entry[name.size()] == L'=' &&
                _wcsnicmp(entry, name.data(), name.size()) == 0) {
                std::string value;
                value.reserve(length - name.size() - 1);
                for (const wchar_t* cur = entry + name.size() + 1; *cur; ++cur) {
                    if (*cur > 0x7f) return std::nullopt;
                    value.push_back(static_cast<char>(*cur));
                }
                return value;
            }
            offset += length + 1;
        }
        return std::nullopt;
    }

    std::optional<uint64> ParseUnsigned(std::string_view text) {
        if (text.empty()) return std::nullopt;
        uint64 value = 0;
        for (unsigned char ch : text) {
            if (!std::isdigit(ch)) return std::nullopt;
            value = (value * 10) + static_cast<uint64>(ch - '0');
        }
        return value;
    }

    AppId_t AppIdFromGameId(uint64 gameId) {
        return static_cast<AppId_t>(gameId & 0xFFFFFFu);
    }

    std::optional<AppId_t> AppIdFromEnvValue(const std::vector<wchar_t>& env,
                                             std::wstring_view name,
                                             bool encodedGameId) {
        auto value = FindEnvironmentValue(env, name);
        if (!value) return std::nullopt;

        auto parsed = ParseUnsigned(*value);
        if (!parsed) return std::nullopt;

        AppId_t appId = encodedGameId ? AppIdFromGameId(*parsed) : static_cast<AppId_t>(*parsed);
        if (appId == 0 || appId == k_uAppIdInvalid) return std::nullopt;
        return appId;
    }

    std::optional<SteamEnvIds> ReadSteamEnvAppIds(uint32 pid) {
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, FALSE, pid);
        if (!process) return std::nullopt;

        auto env = ReadEnvironmentBlock(process);
        CloseHandle(process);
        if (!env) return std::nullopt;

        SteamEnvIds ids{};
        if (auto appId = AppIdFromEnvValue(*env, L"SteamAppId", false))
            ids.steamAppId = *appId;
        if (auto appId = AppIdFromEnvValue(*env, L"SteamGameId", true))
            ids.steamGameId = *appId;
        if (auto appId = AppIdFromEnvValue(*env, L"SteamOverlayGameId", true))
            ids.steamOverlayGameId = *appId;

        if (ids.steamOverlayGameId != k_uAppIdInvalid) {
            ids.selected = ids.steamOverlayGameId;
            ids.source = "SteamOverlayGameId";
        } else if (ids.steamGameId != k_uAppIdInvalid) {
            ids.selected = ids.steamGameId;
            ids.source = "SteamGameId";
        } else if (ids.steamAppId != k_uAppIdInvalid) {
            ids.selected = ids.steamAppId;
            ids.source = "SteamAppId";
        } else {
            return std::nullopt;
        }

        return ids;
    }

    uint32 ReadHandshakePid(CUtlBuffer* read) {
        if (!read || read->TellPut() < 9) return 0;
        const uint8* raw = read->Base();
        uint32 pid = 0;
        memcpy(&pid, raw + 5, sizeof(pid));
        return pid;
    }

    AppId_t CurrentAppId() {
        AppId_t appId = SteamCapture::ResolveAppId();
        if (appId == k_uAppIdInvalid || appId == 0)
            appId = SteamCapture::GetAppIDForCurrentPipe();
        return appId;
    }

    PipeWatch::ProcessSnapshot Inspect(uint32 pid) {
        PipeWatch::ProcessSnapshot snap{};
        snap.key.pid = pid;
        snap.key.creation = QueryCreation(pid);
        snap.imagePath = QueryImagePath(pid);
        snap.imageName = BaseName(snap.imagePath);
        if (snap.imageName.empty() && pid == GetCurrentProcessId()) {
            snap.imageName = "steam.exe";
        }
        snap.steamProcess = IsSteamProcessName(snap.imageName);
        if (auto envIds = ReadSteamEnvAppIds(pid)) {
            snap.envAppId = envIds->selected;
            snap.envSteamAppId = envIds->steamAppId;
            snap.envSteamGameId = envIds->steamGameId;
            snap.envSteamOverlayGameId = envIds->steamOverlayGameId;
            snap.appId = envIds->selected;
            snap.appIdSource = envIds->source;
            if (AppId_t routeAppId = SteamStubAuto::ResolveForImage(snap.imageName, snap.appId)) {
                snap.appId = routeAppId;
                snap.appIdSource = "steamstub-auto";
            }
        } else {
            snap.appId = CurrentAppId();
            snap.appIdSource = "pipe";
        }
        snap.likelyGame = !snap.steamProcess && snap.appId != k_uAppIdInvalid && snap.appId != 0;
        if (snap.likelyGame) {
            snap.luaManaged = LuaLoader::HasDepot(snap.appId);
            snap.ownedByAccount = snap.luaManaged && LuaLoader::IsOwned(snap.appId);
            const ModuleScan modules = InspectModules(pid);
            snap.moduleCount = modules.count;
            snap.steamClientModule = modules.steamClient;
            snap.steamApiModule = modules.steamApi;
            snap.eosSdkModule = modules.eosSdk;
            snap.steamClientPath = modules.steamClientPath;
            snap.steamApiPath = modules.steamApiPath;
            snap.eosSdkPath = modules.eosSdkPath;
            if (snap.eosSdkModule) {
                LOG_IPCCH_WARN("PipeWatch: pid={} appid={} loaded EOSSDK module path={}",
                               pid, snap.appId,
                               snap.eosSdkPath.empty() ? "-" : snap.eosSdkPath);
            }
        }
        return snap;
    }

    void CachePipe(CSteamPipeClient* pipe, const PipeWatch::ProcessSnapshot& snap) {
        if (!pipe || !snap.key.IsValid()) return;

        std::scoped_lock lock(g_lock);
        g_processes[snap.key] = snap;
        g_pipes[MakePipeKey(pipe)] = snap.key;
    }

    void MaybeInjectManualOnlineFixPayload(const PipeWatch::ProcessSnapshot& snap) {
        if (!snap.likelyGame || !snap.luaManaged || snap.steamProcess)
            return;
        if (SteamCapture::OnlineFixMode() != SteamCapture::OnlineFixRouteMode::ManualFlag)
            return;

        const AppId_t realAppId = SteamCapture::OnlineFixRealAppId();
        if (!realAppId || snap.appId != realAppId)
            return;

        if (!snap.eosSdkModule) {
            OnlineFixInject::RecordNoEos(snap.key.pid, snap.imageName, realAppId);
            return;
        }

        (void)OnlineFixInject::TryFallbackInject(snap.key.pid, snap.imageName, realAppId);
    }

} // namespace

namespace PipeWatch {

    std::string ProcessSnapshot::DebugString() const {
        return std::format("pid={} created={} image={} appid={} source={} env={} rawSteamAppId={} rawSteamGameId={} rawSteamOverlayGameId={} steam={} game={} managed={} owned={} modules={} steamclient={} steamapi={} eos={} steamclient_path={} steamapi_path={} eos_path={}",
                           key.pid, key.creation,
                           imageName.empty() ? "-" : imageName,
                           appId,
                           appIdSource.empty() ? "-" : appIdSource,
                           envAppId,
                           envSteamAppId, envSteamGameId, envSteamOverlayGameId,
                           steamProcess, likelyGame, luaManaged, ownedByAccount,
                           moduleCount, steamClientModule, steamApiModule, eosSdkModule,
                           steamClientPath.empty() ? "-" : steamClientPath,
                           steamApiPath.empty() ? "-" : steamApiPath,
                           eosSdkPath.empty() ? "-" : eosSdkPath);
    }

    void Reset() {
        std::scoped_lock lock(g_lock);
        g_processes.clear();
        g_pipes.clear();
        AuthWindow::Reset();
        ProcessExtension::Reset();
    }

    void OnHandshake(CSteamPipeClient* pipe, CUtlBuffer* pRead) {
        if (!pipe) return;
        Settings::ReloadIfChanged();

        const uint32 handPid = ReadHandshakePid(pRead);
        if (handPid != 0) pipe->m_clientPID = handPid;
        const uint32 pid = pipe->m_clientPID;
        if (pid == 0) return;

        auto snap = Inspect(pid);
        CachePipe(pipe, snap);
        LOG_IPCCH_INFO("PipeWatch: handshake {} {}", pipe->DebugString(), snap.DebugString());
        MaybeInjectManualOnlineFixPayload(snap);
        if (snap.likelyGame && snap.luaManaged)
            AuthWindow::OnGamePipe(snap, pipe);
        ProcessExtension::OnGamePipe(snap);
    }

    void TouchPipe(CSteamPipeClient* pipe) {
        if (!pipe || pipe->m_clientPID == 0) return;
        Settings::ReloadIfChanged();
        if (SnapshotForPipe(pipe)) return;

        auto snap = Inspect(pipe->m_clientPID);
        CachePipe(pipe, snap);
        LOG_IPCCH_DEBUG("PipeWatch: late snapshot {} {}", pipe->DebugString(), snap.DebugString());
        MaybeInjectManualOnlineFixPayload(snap);
        if (snap.likelyGame && snap.luaManaged)
            AuthWindow::OnGamePipe(snap, pipe);
        ProcessExtension::OnGamePipe(snap);
    }

    std::optional<ProcessSnapshot> SnapshotForPipe(const CSteamPipeClient* pipe) {
        if (!pipe) return std::nullopt;

        std::scoped_lock lock(g_lock);
        const auto pipeIt = g_pipes.find(MakePipeKey(pipe));
        if (pipeIt == g_pipes.end()) return std::nullopt;

        const auto procIt = g_processes.find(pipeIt->second);
        if (procIt == g_processes.end()) return std::nullopt;
        return procIt->second;
    }

    AppId_t ResolveAppId(const CSteamPipeClient* pipe) {
        if (auto snap = SnapshotForPipe(pipe)) {
            if (snap->appId != k_uAppIdInvalid && snap->appId != 0)
                return snap->appId;
            // fall back to process-name mapping from addprocess() lua binding
            if (!snap->imageName.empty()) {
                AppId_t mapped = LuaLoader::GetAppIdForProcess(snap->imageName);
                if (mapped != k_uAppIdInvalid) return mapped;
            }
        }
        return CurrentAppId();
    }

    bool IsLikelyGamePipe(const CSteamPipeClient* pipe) {
        if (auto snap = SnapshotForPipe(pipe))
            return snap->likelyGame;
        return false;
    }

    bool IsLuaManagedPipe(const CSteamPipeClient* pipe) {
        if (auto snap = SnapshotForPipe(pipe))
            return snap->luaManaged;
        return false;
    }

    bool IsAccountOwnedPipe(const CSteamPipeClient* pipe) {
        if (auto snap = SnapshotForPipe(pipe))
            return snap->ownedByAccount;
        return false;
    }

}


