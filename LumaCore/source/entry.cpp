#include "entry.h"
#include "hooks/CoreLoader.h"
#include "utils/DirWatch.h"

// Prepares the runtime paths and loads the hooked copy of steamclient64.dll.
//
// The diversion pattern: instead of hooking the real steamclient64.dll directly,
// LumaCore copies it to bin\lcoverlay.dll and loads that copy. The SteamUI hook then
// intercepts steamui.dll's LoadModuleWithPath("steamclient64.dll") call and returns
// diversion_hModule, so Steam's UI layer ends up using the hooked copy transparently.
//
// CopyFileA is retried up to 30 times (3 seconds total) because steamclient64.dll can be
// briefly locked by the Steam service during early startup. Same retry logic for LoadLibraryA.
// Returns false if either operation fails after all retries.
bool LoadDiversion()
{
    HMODULE hSelf = nullptr;
    GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCSTR>(&LoadDiversion), &hSelf);
    if (!GetModuleFileNameA(hSelf, SteamInstallPath, MAX_PATH))
        return false;
    char* lastSlash = strrchr(SteamInstallPath, '\\');
    if (lastSlash) *lastSlash = '\0';

    sprintf_s(SteamclientPath, MAX_PATH, "%s\\steamclient64.dll",   SteamInstallPath);
    sprintf_s(DiversionPath,   MAX_PATH, "%s\\bin\\lcoverlay.dll",  SteamInstallPath);
    sprintf_s(LuaDir,          MAX_PATH, "%s\\config\\stplug-in", SteamInstallPath);
    sprintf_s(ConfigPath,      MAX_PATH, "%s\\lumacore.toml",      SteamInstallPath);
    // ensure bin\ directory exists before copying
    char binDir[MAX_PATH];
    sprintf_s(binDir, MAX_PATH, "%s\\bin", SteamInstallPath);
    CreateDirectoryA(binDir, nullptr);  // no-op if already exists
    // Retry: steamclient64.dll may be briefly locked during Steam startup
    {
        int attempts = 0;
        while (!CopyFileA(SteamclientPath, DiversionPath, FALSE)) {
            if (++attempts >= 30) {
                LOG_ERROR("CopyFileA failed after 30 attempts: {} -> {}", SteamclientPath, DiversionPath);
                return false;
            }
            LOG_WARN("CopyFileA attempt {}/30 failed (err={}), retrying...", attempts, GetLastError());
            Sleep(100);
        }
    }
    {
        int attempts = 0;
        while (!(diversion_hModule = LoadLibraryA(DiversionPath))) {
            if (++attempts >= 30) {
                LOG_ERROR("LoadLibraryA failed after 30 attempts: {}", DiversionPath);
                return false;
            }
            LOG_WARN("LoadLibraryA attempt {}/30 failed (err={}), retrying...", attempts, GetLastError());
            Sleep(100);
        }
    }
    LOG_INFO("LumaCore: loaded lcoverlay.dll from {}", DiversionPath);
    return true;
}

// Reads the current Steam build number from steam.exe and stores it as a string in g_steamBuildId.
// Steam exports GetBootstrapperVersion from steam.exe, which returns the build number as an int64.
// Converting it to a string gives us the label format used in PatternDb.h (e.g. "1778803745").
// If steam.exe is not yet loaded or doesn't export this function, g_steamBuildId stays empty
// and ByteSearch falls back to trying every pattern entry in declaration order.
static void DetectSteamBuildId() {
    using GetBootstrapperVersion_t = int64_t (*)();
    HMODULE hSteam = GetModuleHandleA("steam.exe");
    if (!hSteam) {
        LOG_WARN("SteamVersion: steam.exe module not loaded; build id unavailable");
        return;
    }
    auto fn = reinterpret_cast<GetBootstrapperVersion_t>(
        GetProcAddress(hSteam, "GetBootstrapperVersion"));
    if (!fn) {
        LOG_WARN("SteamVersion: steam.exe!GetBootstrapperVersion not exported; "
                 "ByteSearch will fall back to try-all order");
        return;
    }
    g_steamBuildId = std::to_string(fn());
    LOG_INFO("SteamVersion: build id = {}", g_steamBuildId);
}

// Worker thread that runs all real startup work outside of DllMain.
// Windows holds the loader lock during DllMain, which means calling LoadLibrary, doing
// file I/O, or installing Detours hooks from DllMain risks a deadlock. Spinning up a
// separate thread lets us do all of that safely once the loader lock is released.
static DWORD WINAPI InitThread(LPVOID param) {
    HMODULE selfModule = static_cast<HMODULE>(param);
    Logger::Init(selfModule);
    LOG_INFO("LumaCore init thread started");

    DetectSteamBuildId();

    if (!LoadDiversion()) {
        LOG_ERROR("LoadDiversion failed");
        return 1;
    }

    Settings::Load(ConfigPath);
    Logger::InitModules();

    std::vector<std::string> watchDirs = Settings::luaPaths;
    watchDirs.push_back(std::string(LuaDir));
    for (const auto& dir : watchDirs)
        LuaLoader::ParseDirectory(dir);

    DirWatch::Start(watchDirs);

    SteamUI::CoreHook();
    LumaCore::Attach();
    g_HooksInstalled.store(true);
    LOG_INFO("LumaCore init complete");
    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD dwReason, PVOID pvReserved)
{
    if (dwReason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(hModule);
        // Start InitThread to do all real work outside the loader lock.
        // DllMain must return quickly and must not call LoadLibrary, open files,
        // or install hooks — doing so under the loader lock causes deadlocks.
        g_InitThread = CreateThread(nullptr, 0, InitThread, hModule, 0, nullptr);
    }
    else if (dwReason == DLL_PROCESS_DETACH)
    {
        if (g_InitThread) {
            WaitForSingleObject(g_InitThread, 5000);
            CloseHandle(g_InitThread);
            g_InitThread = nullptr;
        }
        if (g_HooksInstalled.load()) {
            DirWatch::Stop();
            SteamUI::CoreUnhook();
            LumaCore::Detach();
        }
    }

    return TRUE;
}
