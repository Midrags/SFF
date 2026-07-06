// LumaCore — Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include <cstdint>
#include <cstddef>
#include "core/entry.h"

// Hooks targeting steamui.dll:
//   * LoadModuleWithPath  -> redirect steamclient64.dll loads to the diversion copy
//   * RemoveAppOverview   -> evict a card from the live library UI by
//                           emitting a synthesized CAppOverview_Change to
//                           every registered webhelper subscriber.
namespace SteamUI {
    void CoreHook();
    void CoreUnhook();

    // Drop appId from the webhelper's m_mapApps and clear the host-side
    // CSteamApp owned flag so the next full snapshot also excludes it.
    void RemoveAppOverview(AppId_t appId);

    // Batch eviction: filter out non-app IDs (sub-depots that have no
    // CSteamApp) and emit a single CAppOverview_Change for the rest. The
    // per-id variant above just calls into this with count=1.
    void RemoveAppOverviewBatch(const AppId_t* ids, size_t count);

    // Queues an appId for removal from the library UI on the next
    // CSteamUIAppControllerRunFrame tick. Thread-safe.
    void QueueLibraryRemoval(AppId_t appId);

    // Queues a safe MarkAppChange touch for newly added roots on the next
    // CSteamUIAppControllerRunFrame tick. Thread-safe.
    void QueueLibraryTouch(AppId_t appId);

    // Cancels a queued removal when the app is added again before
    // the UI drains it. Thread-safe.
    void CancelLibraryRemoval(AppId_t appId);
}
