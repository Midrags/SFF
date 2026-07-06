// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include "Steam/Types.h"

#include <cstdint>
#include <string>

namespace ProtectionProbe {
    struct ScanResult {
        bool valid = false;
        bool detected = false;
        bool routeAccepted = false;
        std::string method;
        std::string routeReason;
        std::string imagePath;
        std::uint64_t fileSize = 0;
        std::uint64_t bytesScanned = 0;
        std::uint64_t candidates = 0;
    };

    ScanResult ScanOnce(uint32 pid, uint64 creation, AppId_t appId, const std::string& imagePath);
    ScanResult ScanBeforeSpawn(AppId_t appId, const std::string& imagePath);
}
