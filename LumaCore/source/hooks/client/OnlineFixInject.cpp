// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "hooks/client/OnlineFixInject.h"
#include "hooks/Macros.h"
#include "config/Settings.h"
#include "runtime/HookStatus.h"
#include "runtime/RemoteTools.h"

#include <algorithm>
#include <cwctype>
#include <filesystem>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>

namespace {

    std::mutex g_queueLock;
    std::unordered_map<std::wstring, AppId_t> g_queue;

    struct PendingRoute {
        AppId_t appId = 0;
        std::wstring launchExe;
        uint64_t queuedAt = 0;
        std::unordered_set<uint32_t> fallbackPids;
    };

    PendingRoute g_pendingRoute;

    std::wstring LowerBasename(LPCWSTR path) {
        if (!path || !*path) return {};
        std::wstring name = std::filesystem::path(path).filename().wstring();
        std::transform(name.begin(), name.end(), name.begin(),
            [](wchar_t c){ return static_cast<wchar_t>(towlower(c)); });
        return name;
    }

    std::wstring ExeFromCmd(LPCWSTR cmd) {
        if (!cmd) return {};
        while (*cmd == L' ' || *cmd == L'\t') ++cmd;
        std::wstring out;
        if (*cmd == L'"') {
            for (++cmd; *cmd && *cmd != L'"'; ++cmd) out.push_back(*cmd);
        } else {
            for (; *cmd && *cmd != L' ' && *cmd != L'\t'; ++cmd) out.push_back(*cmd);
        }
        return out;
    }

    std::string ImageForLog(std::string_view imageName) {
        if (!imageName.empty()) return std::string(imageName);
        return "-";
    }

    std::string NarrowPath(std::wstring_view text) {
        if (text.empty()) return {};
        int needed = WideCharToMultiByte(CP_UTF8, 0, text.data(),
                                         static_cast<int>(text.size()),
                                         nullptr, 0, nullptr, nullptr);
        if (needed <= 0) return {};
        std::string out(static_cast<size_t>(needed), '\0');
        WideCharToMultiByte(CP_UTF8, 0, text.data(),
                            static_cast<int>(text.size()),
                            out.data(), needed, nullptr, nullptr);
        return out;
    }

    std::wstring WideFromUtf8(std::string_view text) {
        if (text.empty()) return {};
        int needed = MultiByteToWideChar(CP_UTF8, 0, text.data(),
                                         static_cast<int>(text.size()),
                                         nullptr, 0);
        if (needed <= 0) return {};
        std::wstring out(static_cast<size_t>(needed), L'\0');
        MultiByteToWideChar(CP_UTF8, 0, text.data(),
                            static_cast<int>(text.size()),
                            out.data(), needed);
        return out;
    }

    AppId_t ClaimPending(LPCWSTR app, LPCWSTR cmd) {
        std::wstring key = LowerBasename(app);
        if (key.empty()) key = LowerBasename(ExeFromCmd(cmd).c_str());
        if (key.empty()) {
            LOG_ONLINEFIX_DEBUG("claim miss exe=(empty)");
            return 0;
        }

        std::lock_guard lk(g_queueLock);
        auto it = g_queue.find(key);
        if (it == g_queue.end()) {
            LOG_ONLINEFIX_DEBUG("claim miss exe={}", NarrowPath(key));
            return 0;
        }
        AppId_t id = it->second;
        g_queue.erase(it);
        LOG_ONLINEFIX_INFO("claim hit appid={} exe={}", id, NarrowPath(key));
        HookStatus::RecordOnlineFixPayload(id, 0, NarrowPath(key), "claimed", "createprocess");
        return id;
    }

    AppId_t ClaimFallbackRoute(uint32_t pid, std::string_view imageName, AppId_t expectedAppId) {
        std::wstring wide = WideFromUtf8(imageName);
        std::wstring key = LowerBasename(wide.c_str());
        std::lock_guard lk(g_queueLock);
        if (!g_pendingRoute.appId) {
            LOG_ONLINEFIX_DEBUG("fallback skip appid={} pid={} exe={} reason=no-pending",
                                expectedAppId, pid, NarrowPath(key));
            return 0;
        }
        if (expectedAppId && g_pendingRoute.appId != expectedAppId) {
            LOG_ONLINEFIX_WARN("fallback skip queued={} expected={} pid={} exe={} reason=appid-mismatch",
                               g_pendingRoute.appId, expectedAppId, pid, NarrowPath(key));
            return 0;
        }
        if (pid && g_pendingRoute.fallbackPids.contains(pid)) {
            LOG_ONLINEFIX_DEBUG("fallback skip appid={} pid={} exe={} reason=already-tried",
                                g_pendingRoute.appId, pid, NarrowPath(key));
            return 0;
        }
        if (pid)
            g_pendingRoute.fallbackPids.insert(pid);
        LOG_ONLINEFIX_INFO("fallback route hit appid={} pid={} launch={} child={}",
                           g_pendingRoute.appId, pid, NarrowPath(g_pendingRoute.launchExe),
                           NarrowPath(key));
        HookStatus::RecordOnlineFixPayload(g_pendingRoute.appId, pid, NarrowPath(key),
                                           "fallback-claimed", "pipewatch-eos");
        return g_pendingRoute.appId;
    }

    using CreateProcessW_t = BOOL(WINAPI*)(LPCWSTR, LPWSTR, LPSECURITY_ATTRIBUTES,
        LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID, LPCWSTR,
        LPSTARTUPINFOW, LPPROCESS_INFORMATION);
    using CreateProcessAsUserW_t = BOOL(WINAPI*)(HANDLE, LPCWSTR, LPWSTR,
        LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID,
        LPCWSTR, LPSTARTUPINFOW, LPPROCESS_INFORMATION);

    CreateProcessW_t       oCreateProcessW       = nullptr;
    CreateProcessAsUserW_t oCreateProcessAsUserW = nullptr;

    // Inline injection matching RemoteInject::LoadDll - VirtualAllocEx +
    // CreateRemoteThread(LoadLibraryW). Uses the process HANDLE from
    // CreateProcess directly (no extra OpenProcess).
    static bool InjectPayload(HANDLE hProcess, LPCWSTR dllPath) {
        HMODULE k32 = GetModuleHandleW(L"kernel32.dll");
        if (!k32) return false;
        auto loadLib = reinterpret_cast<LPTHREAD_START_ROUTINE>(
            GetProcAddress(k32, "LoadLibraryW"));
        if (!loadLib) return false;

        const SIZE_T bytes = (wcslen(dllPath) + 1) * sizeof(wchar_t);
        void* mem = VirtualAllocEx(hProcess, nullptr, bytes,
            MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        if (!mem) return false;

        bool ok = false;
        if (WriteProcessMemory(hProcess, mem, dllPath, bytes, nullptr)) {
            HANDLE t = CreateRemoteThread(hProcess, nullptr, 0, loadLib, mem, 0, nullptr);
            if (t) {
                ok = (WaitForSingleObject(t, 5000) == WAIT_OBJECT_0);
                CloseHandle(t);
            }
        }
        VirtualFreeEx(hProcess, mem, 0, MEM_RELEASE);
        return ok;
    }

    BOOL LaunchSuspended(HANDLE token, LPCWSTR app, LPWSTR cmd, LPSECURITY_ATTRIBUTES pa,
               LPSECURITY_ATTRIBUTES ta, BOOL inherit, DWORD flags, LPVOID env,
               LPCWSTR cwd, LPSTARTUPINFOW si, LPPROCESS_INFORMATION pi)
    {
        auto fwd = [&](DWORD f) {
            return token
                ? oCreateProcessAsUserW(token, app, cmd, pa, ta, inherit, f, env, cwd, si, pi)
                : oCreateProcessW(app, cmd, pa, ta, inherit, f, env, cwd, si, pi);
        };

        AppId_t appId = ClaimPending(app, cmd);
        if (!appId) return fwd(flags);
        if (PayloadPath[0] == 0) {
            LOG_ONLINEFIX_WARN("appid={} payload path empty, forwarding without injection", appId);
            return fwd(flags);
        }

        BOOL ok = fwd(flags | CREATE_SUSPENDED);
        if (!ok) {
            LOG_ONLINEFIX_WARN("appid={} spawn failed err={}", appId, GetLastError());
            return ok;
        }

        wchar_t wPayload[MAX_PATH] = {};
        MultiByteToWideChar(CP_ACP, 0, PayloadPath, -1, wPayload, MAX_PATH);
        bool injected = InjectPayload(pi->hProcess, wPayload);
        LOG_ONLINEFIX_INFO("appid={} pid={} payload {}", appId, pi->dwProcessId,
                           injected ? "loaded" : "FAILED");
        HookStatus::RecordOnlineFixPayload(appId, pi->dwProcessId,
                                           app ? NarrowPath(LowerBasename(app)) : std::string{},
                                           injected ? "claimed-loaded" : "claimed-failed",
                                           "createprocess");

        if (!(flags & CREATE_SUSPENDED)) ResumeThread(pi->hThread);
        return ok;
    }

    BOOL WINAPI hkCreateProcessW(LPCWSTR app, LPWSTR cmd, LPSECURITY_ATTRIBUTES pa,
        LPSECURITY_ATTRIBUTES ta, BOOL inherit, DWORD flags, LPVOID env,
        LPCWSTR cwd, LPSTARTUPINFOW si, LPPROCESS_INFORMATION pi)
    {
        return LaunchSuspended(nullptr, app, cmd, pa, ta, inherit, flags, env, cwd, si, pi);
    }

    BOOL WINAPI hkCreateProcessAsUserW(HANDLE token, LPCWSTR app, LPWSTR cmd,
        LPSECURITY_ATTRIBUTES pa, LPSECURITY_ATTRIBUTES ta, BOOL inherit, DWORD flags,
        LPVOID env, LPCWSTR cwd, LPSTARTUPINFOW si, LPPROCESS_INFORMATION pi)
    {
        return LaunchSuspended(token, app, cmd, pa, ta, inherit, flags, env, cwd, si, pi);
    }

}

namespace {

    void ResetPayloadLogs() {
        namespace fs = std::filesystem;
        fs::path dir = fs::path(Settings::logDir) / "payload";
        std::error_code ec;
        fs::remove_all(dir, ec);
        fs::create_directories(dir, ec);
    }

}

namespace OnlineFixInject {

    void Install() {
        if (PayloadPath[0] == 0) {
            LOG_ONLINEFIX_WARN("payload path not set; injection disabled");
            return;
        }
        if (!Settings::onlineFixInjectEnabled) {
            LOG_ONLINEFIX_INFO("online-fix injection disabled by config");
            return;
        }
        if (GetFileAttributesA(PayloadPath) == INVALID_FILE_ATTRIBUTES) {
            LOG_ONLINEFIX_WARN("payload DLL not found at \"{}\"; injection disabled", PayloadPath);
            return;
        }
        ResetPayloadLogs();
        HMODULE k32 = GetModuleHandleW(L"kernel32.dll");
        if (!k32) return;
        oCreateProcessW       = reinterpret_cast<CreateProcessW_t>      (GetProcAddress(k32, "CreateProcessW"));
        oCreateProcessAsUserW = reinterpret_cast<CreateProcessAsUserW_t>(GetProcAddress(k32, "CreateProcessAsUserW"));

        LM_TX_BEGIN();
        if (oCreateProcessW)
            DetourAttach(reinterpret_cast<PVOID*>(&oCreateProcessW),
                         reinterpret_cast<PVOID>(hkCreateProcessW));
        if (oCreateProcessAsUserW)
            DetourAttach(reinterpret_cast<PVOID*>(&oCreateProcessAsUserW),
                         reinterpret_cast<PVOID>(hkCreateProcessAsUserW));
        LM_TX_COMMIT();
        LOG_ONLINEFIX_INFO("spawn hooks installed dll=\"{}\"", PayloadPath);
    }

    void Uninstall() {
        LM_TX_BEGIN();
        if (oCreateProcessW) {
            DetourDetach(reinterpret_cast<PVOID*>(&oCreateProcessW),
                         reinterpret_cast<PVOID>(hkCreateProcessW));
            oCreateProcessW = nullptr;
        }
        if (oCreateProcessAsUserW) {
            DetourDetach(reinterpret_cast<PVOID*>(&oCreateProcessAsUserW),
                         reinterpret_cast<PVOID>(hkCreateProcessAsUserW));
            oCreateProcessAsUserW = nullptr;
        }
        LM_TX_COMMIT();

        std::lock_guard lk(g_queueLock);
        g_queue.clear();
        g_pendingRoute = {};
    }

    void QueueInjection(const char* exePath, AppId_t realAppId) {
        if (!realAppId || !exePath || !*exePath) return;

        wchar_t wexe[MAX_PATH] = {};
        MultiByteToWideChar(CP_UTF8, 0, exePath, -1, wexe, MAX_PATH);
        std::wstring key = LowerBasename(wexe);
        if (key.empty()) {
            LOG_ONLINEFIX_WARN("queue skipped appid={} exe=\"{}\"", realAppId, exePath);
            return;
        }

        std::lock_guard lk(g_queueLock);
        g_queue[key] = realAppId;
        g_pendingRoute = {};
        g_pendingRoute.appId = realAppId;
        g_pendingRoute.launchExe = key;
        g_pendingRoute.queuedAt = GetTickCount64();
        LOG_ONLINEFIX_INFO("queued appid={} exe={}", realAppId, NarrowPath(key));
        HookStatus::RecordOnlineFixPayload(realAppId, 0, NarrowPath(key), "queued", "manual-route");
    }

    void RecordNoEos(uint32_t pid, const std::string& imageName, AppId_t realAppId) {
        if (!pid || !realAppId) return;
        std::wstring wide = WideFromUtf8(imageName);
        std::wstring key = LowerBasename(wide.c_str());

        std::lock_guard lk(g_queueLock);
        if (g_pendingRoute.appId != realAppId)
            return;
        HookStatus::RecordOnlineFixPayload(realAppId, pid, NarrowPath(key), "no-eos", "pipewatch");
    }

    bool TryFallbackInject(uint32_t pid, const std::string& imageName, AppId_t realAppId) {
        if (!pid || !realAppId) return false;
        AppId_t queuedAppId = ClaimFallbackRoute(pid, imageName, realAppId);
        if (!queuedAppId) return false;

        if (PayloadPath[0] == 0) {
            LOG_ONLINEFIX_WARN("fallback appid={} pid={} payload path empty", queuedAppId, pid);
            HookStatus::RecordOnlineFixPayload(queuedAppId, pid, ImageForLog(imageName),
                                               "fallback-failed", "payload-empty");
            return false;
        }
        if (!Settings::onlineFixInjectEnabled) {
            LOG_ONLINEFIX_INFO("fallback appid={} pid={} injection disabled by config", queuedAppId, pid);
            HookStatus::RecordOnlineFixPayload(queuedAppId, pid, ImageForLog(imageName),
                                               "fallback-disabled", "config");
            return false;
        }
        if (GetFileAttributesA(PayloadPath) == INVALID_FILE_ATTRIBUTES) {
            LOG_ONLINEFIX_WARN("fallback appid={} pid={} payload DLL missing path=\"{}\"",
                               queuedAppId, pid, PayloadPath);
            HookStatus::RecordOnlineFixPayload(queuedAppId, pid, ImageForLog(imageName),
                                               "fallback-failed", "payload-missing");
            return false;
        }

        RemoteTools::LoadResult loaded =
            RemoteTools::LoadLibraryInto(pid, std::filesystem::path(PayloadPath));
        if (loaded.ok) {
            LOG_ONLINEFIX_INFO("fallback appid={} pid={} payload {}",
                               queuedAppId, pid,
                               loaded.alreadyLoaded ? "already-loaded" : "loaded");
            HookStatus::RecordOnlineFixPayload(queuedAppId, pid, ImageForLog(imageName),
                                               loaded.alreadyLoaded ? "fallback-already-loaded" : "fallback-loaded",
                                               "pipewatch-eos");
            return true;
        }

        LOG_ONLINEFIX_WARN("fallback appid={} pid={} payload FAILED err={}",
                           queuedAppId, pid, loaded.error);
        HookStatus::RecordOnlineFixPayload(queuedAppId, pid, ImageForLog(imageName),
                                           "fallback-failed", loaded.error);
        return false;
    }

}
