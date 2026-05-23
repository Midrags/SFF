#pragma once
#include "entry.h"
#include <vector>

namespace PackagePatch {
    // LoadPackage + CheckAppOwnership — patches the package store so that
    // user-supplied depots appear owned and accessible.
    void Install();
    void Uninstall();

    // Inject app IDs directly into the saved package 0 pointer.
    // Returns false if package 0 hasn't been captured yet.
    bool InjectIntoPackage0(const std::vector<AppId_t>& appIds);

    // Returns the saved PackageInfo* for package 0 (nullptr if not yet captured).
    PackageInfo* GetPackage0();
}
