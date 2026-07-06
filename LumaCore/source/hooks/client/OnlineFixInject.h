// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include "core/entry.h"

#include <cstdint>
#include <string>

namespace OnlineFixInject {
    void Install();
    void Uninstall();

    void QueueInjection(const char* exePath, AppId_t realAppId);
    void RecordNoEos(uint32_t pid, const std::string& imageName, AppId_t realAppId);
    bool TryFallbackInject(uint32_t pid, const std::string& imageName, AppId_t realAppId);
}
