#pragma once
#include <cstdint>

namespace ManifestBind {
    void Install();
    void Uninstall();

    // Fetch the manifest request code for *manifestGid* from manifest.steam.run.
    // Returns true and writes the code to *outCode* on success.
    // Called from PacketRouter's async GetManifestRequestCode handler.
    bool FetchManifestRequestCode(uint64_t manifestGid, uint64_t* outCode,
                                   uint32_t appId, uint32_t depotId);
}
