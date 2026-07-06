// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include "core/entry.h"

#include <string_view>

namespace SteamStubAuto {
    bool ShouldActivate(AppId_t appId, bool hasDepot, bool owned,
                        bool hasManualFlag, bool detectedSteamStub);

    void Arm(AppId_t realAppId, const char* exePath, std::string_view detectedImagePath = {});
    void Clear();
    bool IsActive();
    AppId_t RealAppId();

    AppId_t ResolveForImage(std::string_view imageName, AppId_t envAppId);
}
