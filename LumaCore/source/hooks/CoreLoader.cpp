#include "CoreLoader.h"
#include "DepotKeys.h"
#include "IPCBus.h"
#include "KeyValues.h"
#include "ManifestBind.h"
#include "SteamCapture.h"
#include "PacketRouter.h"
#include "PackagePatch.h"
#include "LicenseHooks.h"


namespace LumaCore {

    void Attach() {
        DepotKeys::Install();
        IPCBus::Install();
        // KVHooks::Install();
        ManifestBind::Install();
        SteamCapture::Install();
        PacketRouter::Install();
        PackagePatch::Install();
        LicenseHooks::Install();
    }

    void Detach() {
        DepotKeys::Uninstall();
        IPCBus::Uninstall();
        // KVHooks::Uninstall();
        ManifestBind::Uninstall();
        SteamCapture::Uninstall();
        PacketRouter::Uninstall();
        PackagePatch::Uninstall();
        LicenseHooks::Uninstall();
    }
}
