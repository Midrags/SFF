#include "CoreLoader.h"
#include "Macros.h"
#include <thread>
#include <chrono>

namespace {
    using namespace std::chrono_literals;
    constexpr int MAX_RETRY = 20;
    constexpr auto RETRY_INTERVAL = 300ms;

    LC_HOOK_DEF(LoadModuleWithPath, HMODULE, const char* path, bool flags) {
        LOG_INFO("LoadModuleWithPath called with path: {} , flags: {}", path, flags);
        // wait for hooks to be installed 
        for (int i = 0; i < MAX_RETRY && !g_HooksInstalled.load(); ++i){
            LOG_DEBUG("LoadModuleWithPath: waiting for hooks to be installed... (attempt {}/{},interval: {})", i + 1, MAX_RETRY, RETRY_INTERVAL.count());
            std::this_thread::sleep_for(RETRY_INTERVAL);
        }
        HMODULE h = oLoadModuleWithPath(path, flags);
        if (!strcmp(path, "steamclient64.dll"))
            h = diversion_hModule;
        return h;
    }
}

namespace SteamUI {
    void CoreHook() {
        LC_TX_OPEN();
        LC_ATTACH(GetModuleHandleA("steamui.dll"), LoadModuleWithPath);
        LC_TX_COMMIT();
    }

    void CoreUnhook() {
        LC_TX_OPEN();
        LC_DETACH(LoadModuleWithPath);
        LC_TX_COMMIT();
    }
}
