#pragma once

namespace PackagePatch {
    // LoadPackage + CheckAppOwnership — patches the package store so that
    // user-supplied depots appear owned and accessible.
    void Install();
    void Uninstall();
}
