#pragma once

namespace DepotKeys {
    // LoadDepotDecryptionKey hook: serves user-provided decryption keys for
    // depots configured via Lua.
    void Install();
    void Uninstall();
}
