// LumaCore — Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once
#include "core/entry.h"
#include <vector>

namespace PackagePatch {
    // LoadPackage + CheckAppOwnership — patches the package store so that
    // user-supplied depots appear owned and accessible.
    void Install();
    void Uninstall();

    // Inject app IDs directly into package 0 after checking membership.
    // Returns false if package 0 or CUtlMemoryGrow is not available yet.
    bool InjectIntoPackage0(const std::vector<AppId_t>& appIds,
                            const char* reason = "package0");
    bool InjectIntoPackage0(PackageInfo* pPkg, const std::vector<AppId_t>& appIds,
                            const char* reason = "package0");

    // Returns the saved PackageInfo* for package 0 (nullptr if not yet captured).
    PackageInfo* GetPackage0();
}
