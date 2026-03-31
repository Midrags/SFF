// if you're wondering, sold = steam old

#include "steam_old_lib/steam_old_lib.hpp"

#include "common_helpers/common_helpers.hpp"
#include "dll/common_includes.h"

#include "detours/detours.h"

#include <string>
#include <stdexcept>
#include <exception>
#include <string_view>
#include <cstdint>

#define WIN32_LEAN_AND_MEAN
#include <Windows.h>

#include <Softpub.h> // WinVerifyTrust

#ifndef EMU_RELEASE_BUILD
#include "dbg_log/dbg_log.hpp"
#endif


#ifndef EMU_RELEASE_BUILD
dbg_log dbg_logger(
    []{
        static wchar_t dll_path[8192]{};
        auto chars = GetModuleFileNameW((HINSTANCE)&__ImageBase, dll_path, sizeof(dll_path) / sizeof(dll_path[0]));
        auto wpath = std::wstring_view(dll_path, chars);
        return common_helpers::to_str(wpath.substr(0, wpath.find_last_of(L"\\/"))) + PATH_SEPARATOR
            + "STEAM_OLD_LOG_" + std::to_string(common_helpers::rand_number(UINT32_MAX)) + ".log";
    }()
);
#endif


static bool dll_loaded = false;
static HMODULE my_hModule = nullptr;

static HMODULE wintrust_dll = nullptr;
static std::wstring wintrust_lib_path = L"";

static bool WinVerifyTrust_hooked = false;
static bool LoadLibraryA_hooked = false;
static bool LoadLibraryExA_hooked = false;
static bool LoadLibraryW_hooked = false;
static bool LoadLibraryExW_hooked = false;

static HMODULE hmod_steamclient = nullptr;
static void *ptr_CreateInterface = nullptr;


static inline bool is_steam_lib_A(const char *str) {
    return str && str[0] && (
        common_helpers::ends_with_i(str, "Steam.dll") ||
        common_helpers::ends_with_i(str, "Steam")
    );
}

static inline bool is_steam_lib_W(const wchar_t *str) {
    return str && str[0] && (
        common_helpers::ends_with_i(str, L"Steam.dll") ||
        common_helpers::ends_with_i(str, L"Steam")
    );
}


static decltype(WinVerifyTrust) *actual_WinVerifyTrust = nullptr;
__declspec(noinline)
static LONG WINAPI WinVerifyTrust_hook(HWND hwnd, GUID *pgActionID, LPVOID pWVTData) {
    if (WinVerifyTrust_hooked) {
        PRINT_DEBUG_ENTRY();
        Sleep(2000); // mimic original behavior
        SetLastError(ERROR_SUCCESS);
        return 0; // success
    }

    if (actual_WinVerifyTrust) {
        return actual_WinVerifyTrust(hwnd, pgActionID, pWVTData);
    }
    
    PRINT_DEBUG("[X] hook isn't enabled but original pointer is null, returning success anyway!");
    Sleep(2000); // mimic original behavior
    SetLastError(ERROR_SUCCESS);
    return 0; // success
}

static decltype(LoadLibraryA) *actual_LoadLibraryA = LoadLibraryA;
__declspec(noinline)
static HMODULE WINAPI LoadLibraryA_hook(LPCSTR lpLibFileName)
{
    if (LoadLibraryA_hooked && is_steam_lib_A(lpLibFileName)) {
        PRINT_DEBUG_ENTRY();
        SetLastError(ERROR_SUCCESS);
        return my_hModule;
    }

    return actual_LoadLibraryA(lpLibFileName);
}

static decltype(LoadLibraryExA) *actual_LoadLibraryExA = LoadLibraryExA;
__declspec(noinline)
static HMODULE WINAPI LoadLibraryExA_hook(LPCSTR lpLibFileName, HANDLE hFile, DWORD dwFlags)
{
    if (LoadLibraryExA_hooked && is_steam_lib_A(lpLibFileName)) {
        PRINT_DEBUG_ENTRY();
        SetLastError(ERROR_SUCCESS);
        return my_hModule;
    }

    return actual_LoadLibraryExA(lpLibFileName, hFile, dwFlags);
}

static decltype(LoadLibraryW) *actual_LoadLibraryW = LoadLibraryW;
__declspec(noinline)
static HMODULE WINAPI LoadLibraryW_hook(LPCWSTR lpLibFileName)
{
    if (LoadLibraryW_hooked && is_steam_lib_W(lpLibFileName)) {
        PRINT_DEBUG_ENTRY();
        SetLastError(ERROR_SUCCESS);
        return my_hModule;
    }

    return actual_LoadLibraryW(lpLibFileName);
}

static decltype(LoadLibraryExW) *actual_LoadLibraryExW = LoadLibraryExW;
__declspec(noinline)
static HMODULE WINAPI LoadLibraryExW_hook(LPCWSTR lpLibFileName, HANDLE hFile, DWORD dwFlags)
{
    if (LoadLibraryExW_hooked && is_steam_lib_W(lpLibFileName)) {
        PRINT_DEBUG_ENTRY();
        SetLastError(ERROR_SUCCESS);
        return my_hModule;
    }

    return actual_LoadLibraryExW(lpLibFileName, hFile, dwFlags);
}


static bool redirect_win32_apis()
{
    PRINT_DEBUG_ENTRY();
    try {
        wintrust_dll = LoadLibraryExW(wintrust_lib_path.c_str(), NULL, 0);
        if (!wintrust_dll) throw std::runtime_error("failed to load wintrust lib");

        actual_WinVerifyTrust = (decltype(actual_WinVerifyTrust))GetProcAddress(wintrust_dll, "WinVerifyTrust");
        if (!actual_WinVerifyTrust) throw std::runtime_error("failed to get proc address of WinVerifyTrust()");

        if (DetourTransactionBegin() != NO_ERROR) throw std::runtime_error("call failed: DetourTransactionBegin");
        if (DetourUpdateThread(GetCurrentThread()) != NO_ERROR) throw std::runtime_error("call failed: DetourUpdateThread");

        if (DetourAttach((PVOID *)&actual_WinVerifyTrust, (PVOID)WinVerifyTrust_hook) != NO_ERROR) throw std::runtime_error("attach failed: WinVerifyTrust");
        if (DetourAttach((PVOID *)&actual_LoadLibraryA, (PVOID)LoadLibraryA_hook) != NO_ERROR) throw std::runtime_error("attach failed: LoadLibraryA");
        if (DetourAttach((PVOID *)&actual_LoadLibraryExA, (PVOID)LoadLibraryExA_hook) != NO_ERROR) throw std::runtime_error("attach failed: LoadLibraryExA");
        if (DetourAttach((PVOID *)&actual_LoadLibraryW, (PVOID)LoadLibraryW_hook) != NO_ERROR) throw std::runtime_error("attach failed: LoadLibraryW");
        if (DetourAttach((PVOID *)&actual_LoadLibraryExW, (PVOID)LoadLibraryExW_hook) != NO_ERROR) throw std::runtime_error("attach failed: LoadLibraryExW");
        if (DetourTransactionCommit() != NO_ERROR) throw std::runtime_error("call failed: DetourTransactionCommit");

        WinVerifyTrust_hooked = true;
        LoadLibraryA_hooked = true;
        LoadLibraryExA_hooked = true;
        LoadLibraryW_hooked = true;
        LoadLibraryExW_hooked = true;

        PRINT_DEBUG("success!");
        return true;
    } catch (const std::exception &ex) {
        PRINT_DEBUG("[X] error: %s", ex.what());
    }

    if (wintrust_dll) {
        FreeLibrary(wintrust_dll);
        wintrust_dll = nullptr;
    }

    PRINT_DEBUG("[X] Win32 API redirection failed");
    return false;
}

static bool restore_win32_apis()
{
    PRINT_DEBUG_ENTRY();
    WinVerifyTrust_hooked = false;
    LoadLibraryA_hooked = false;
    LoadLibraryExA_hooked = false;
    LoadLibraryW_hooked = false;
    LoadLibraryExW_hooked = false;

    bool ret = false;

    try {
        if (DetourTransactionBegin() != NO_ERROR) throw std::runtime_error("call failed: DetourTransactionBegin");
        if (DetourUpdateThread(GetCurrentThread()) != NO_ERROR) throw std::runtime_error("call failed: DetourUpdateThread");

        if (actual_WinVerifyTrust) {
            DetourDetach((PVOID *)&actual_WinVerifyTrust, (PVOID)WinVerifyTrust_hook);
        }

        DetourDetach((PVOID *)&actual_LoadLibraryA, (PVOID)LoadLibraryA_hook);
        DetourDetach((PVOID *)&actual_LoadLibraryExA, (PVOID)LoadLibraryExA_hook);
        DetourDetach((PVOID *)&actual_LoadLibraryW, (PVOID)LoadLibraryW_hook);
        DetourDetach((PVOID *)&actual_LoadLibraryExW, (PVOID)LoadLibraryExW_hook);
        if (DetourTransactionCommit() != NO_ERROR) throw std::runtime_error("call failed: DetourTransactionCommit");

        ret = true;
    } catch (const std::exception &ex) {
        PRINT_DEBUG("[X] error: %s", ex.what());
    }

    if (wintrust_dll) {
        FreeLibrary(wintrust_dll);
        wintrust_dll = nullptr;
    }

    PRINT_DEBUG("result = %i", (int)ret);
    return ret;
}

static void* steamclient_loader(bool load)
{
    if (load) {
        if (!ptr_CreateInterface) {
            PRINT_DEBUG("loading steamclient");
            if (!hmod_steamclient) {
                hmod_steamclient = LoadLibraryExW(L"steamclient.dll", NULL, 0);
            }

            if (hmod_steamclient) {
                ptr_CreateInterface = GetProcAddress(hmod_steamclient, "CreateInterface");
            }
        }
    } else {
        if (hmod_steamclient) {
            PRINT_DEBUG("unloading steamclient");
            FreeLibrary(hmod_steamclient);
            hmod_steamclient = nullptr;
            ptr_CreateInterface = nullptr;
        }
    }
    return ptr_CreateInterface;
}

static bool patch()
{
    PRINT_DEBUG_ENTRY();
    if (wintrust_lib_path.empty()) {
        auto size = GetSystemDirectoryW(&wintrust_lib_path[0], 0);
        if (size <= 0) return false;

        wintrust_lib_path.resize(size);
        size = GetSystemDirectoryW(&wintrust_lib_path[0], (unsigned)wintrust_lib_path.size());
        if (size >= (unsigned)wintrust_lib_path.size()) {
            wintrust_lib_path.clear();
            return false;
        }

        wintrust_lib_path.pop_back(); // remove null
        wintrust_lib_path += L"\\Wintrust.dll";
    }

    return redirect_win32_apis();
}

static void deinit()
{
    PRINT_DEBUG_ENTRY();
    steamclient_loader(false);
    sold::set_steamclient_loader(nullptr);
    sold::set_tid(0);
    if (dll_loaded) {
        restore_win32_apis();
    }
}


BOOL APIENTRY DllMain(HMODULE hModule, DWORD  reason, LPVOID lpReserved)
{
    switch (reason) {
    case DLL_PROCESS_ATTACH: {
        PRINT_DEBUG("DLL_PROCESS_ATTACH");
        my_hModule = hModule;
        auto my_tid = GetCurrentThreadId();
        if (!steamclient_loader(true)) {
            PRINT_DEBUG("[X] failed to load steamclient.dll");
            // https://learn.microsoft.com/en-us/windows/win32/dlls/dllmain
            // "The system immediately calls your entry-point function with DLL_PROCESS_DETACH and unloads the DLL"
            return FALSE;
        }
        if (!patch()) {
            PRINT_DEBUG("[X] failed to patch");
            return FALSE;
        }

        sold::set_steamclient_loader(steamclient_loader);
        sold::set_tid(my_tid);
        dll_loaded = true;
    }
    break;

    case DLL_PROCESS_DETACH: {
        PRINT_DEBUG("DLL_PROCESS_DETACH");
        deinit();
    }
    break;
    }

    return TRUE;
}
