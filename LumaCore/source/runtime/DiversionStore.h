// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#ifndef DIVERSION_STORE_H
#define DIVERSION_STORE_H

// Content-addressed diversion copies for concurrent Steam sessions. Each
// build of steamclient64.dll gets its own immutable file under bin\ instead
// of every boot overwriting the fixed bin\lcoverlay.dll, which fails with
// ERROR_SHARING_VIOLATION while another session has it loaded.

#include <windows.h>
#include <string>

namespace DiversionStore {

    // LUMACORE_MULTIINSTANCE=0/1 wins over [diversion] multiinstance.
    bool Enabled();

    // Ensures a byte-exact copy of steamclientPath exists under bin\, named
    // after its sha256, and returns its full path in outArtifactPath.
    bool Prepare(const char* steamclientPath,
                 const char* steamInstallPath,
                 char* outArtifactPath, DWORD outArtifactCch,
                 std::string* outSourceSha);

    // Deletes stale lcoverlay* files no process keeps mapped.
    void StartDeferredPrune(const char* steamInstallPath,
                            const char* currentArtifactPath);

}  // namespace DiversionStore

#endif // DIVERSION_STORE_H
