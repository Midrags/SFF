// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#include "core/Orchestrator.h"
#include "hooks/client/DepotKeys.h"
#include "hooks/client/DecryptionKeyHook.h"
#include "hooks/client/IPCBus.h"
#include "hooks/client/KeyValues.h"
#include "hooks/client/ManifestBind.h"
#include "patterns/PatternFetcher.h"
#include "hooks/capture/SteamCapture.h"
#include "hooks/ui/SteamUI.h"
#include "hooks/client/PacketRouter.h"
#include "hooks/client/PackagePatch.h"
#include "hooks/client/LicenseHooks.h"
#include "hooks/client/OnlineFixInject.h"
#include "runtime/Diagnostics.h"


namespace LumaCore {

    using HookOp = void(*)();
    static constexpr HookOp kInstallOrder[] = {
        DepotKeys::Install,
        DecryptionKeyHook::Install,
        IPCBus::Install,
        KVHooks::Install,
        ManifestBind::Install,
        PacketRouter::Install,
        OnlineFixInject::Install,
        LicenseHooks::Install,
    };
    static constexpr HookOp kUninstallOrder[] = {
        DepotKeys::Uninstall,
        DecryptionKeyHook::Uninstall,
        IPCBus::Uninstall,
        KVHooks::Uninstall,
        ManifestBind::Uninstall,
        SteamCapture::Uninstall,
        SteamUI::CoreUnhook,
        PacketRouter::Uninstall,
        OnlineFixInject::Uninstall,
        PackagePatch::Uninstall,
        LicenseHooks::Uninstall,
    };

    void Attach() { for (auto fn : kInstallOrder) fn(); }
    void AttachLight() {
        for (auto fn : {DepotKeys::Install, DecryptionKeyHook::Install, IPCBus::Install,
                         KVHooks::Install, ManifestBind::Install, PacketRouter::Install,
                         OnlineFixInject::Install, LicenseHooks::Install}) fn();
    }
    void AttachHeavy() { SteamCapture::Install(); }

    void Detach() {
#ifdef LUMACORE_DIAGNOSTICS_ENABLED
        Diagnostics::DumpForDetach();
#endif
        for (auto fn : kUninstallOrder) fn();
        PatternFetcher::Reset();
    }
}
