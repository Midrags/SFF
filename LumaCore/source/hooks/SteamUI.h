#pragma once

#include <cstdint>
#include <cstddef>
#include "entry.h"

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
}
