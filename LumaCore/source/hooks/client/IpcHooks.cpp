// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

// Hub that registers the small IPC dispatch overlay atop IPCBus. Fixed-layout
// IClientUser replies stay in CmdUser so they cannot be shadowed by generic
// pre/post adapters registered earlier in startup.

#include "hooks/client/IpcDispatch.h"
#include "runtime/Logger.h"

// Forward declarations for interface handler registration functions.
// Each one lives in its own translation unit under hooks/client/.
namespace IpcHandlers_ISteamUtils { void Register(); }

namespace IpcHooks {

    void Install() {
        // Load IPC method metadata TOML first
        // (called earlier from Bootstrap but idempotent)

        // Register dynamic utility handlers only. CmdUser owns IClientUser
        // ticket/SteamID replies because those write fixed IPC layouts.
        IpcHandlers_ISteamUtils::Register();

        // Push all registered handlers into IPCBus's dispatch table
        IpcDispatch::Install();

        LOG_IPC_INFO("IpcHooks: utility dispatch handlers installed; CmdUser owns IClientUser replies");
    }

    void Uninstall() {
        IpcDispatch::Uninstall();
    }

}
