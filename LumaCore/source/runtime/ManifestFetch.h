// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.
//
// Wire-level fallback for ContentServerDirectory.GetManifestRequestCode#1.
//
// When Steam asks the content server directory for a manifest request
// code on a depot we faked ownership of, the server replies eresult=2
// and an empty body. The download UI surfaces that as "NO INTERNET
// CONNECTION" even though the network is fine, which is what tripped
// up the Batman: Arkham Knight (208650) launch.
//
// The fix: when LumaCore sees an outgoing 151 with target_job_name
// "ContentServerDirectory.GetManifestRequestCode#1" for a depot we
// have a manifest override on, we kick off an async HTTP GET against
// the configured manifest_fetch.url. The matching 147 response is
// held until the future resolves (timeout cap from settings), then
// the header eresult is rewritten to OK and the body is replaced with
// a serialised CContentServerDirectory_GetManifestRequestCode_Response
// carrying the request code we just fetched.
//
// All thread-safe; futures are keyed on jobid_source so multiple
// in-flight gid lookups stay independent.

#ifndef LUMACORE_MANIFEST_FETCH_H
#define LUMACORE_MANIFEST_FETCH_H

#include <cstdint>
#include <future>
#include <optional>

namespace ManifestFetch {

    // Spawns the async lookup tied to `jobId` (Steam's jobid_source on
    // the outgoing 151). `appId` and `depotId` may be 0 if the request
    // omitted them; the URL substitution treats them as empty strings
    // in that case. Idempotent: re-submitting the same jobId is a no-op.
    void Submit(uint64_t jobId, uint64_t manifestGid,
                uint32_t appId, uint32_t depotId);

    // Drains the future for `jobId` (consuming it), waiting at most the
    // configured timeout. Returns the parsed manifest_request_code on
    // success, or std::nullopt on timeout / network failure / parse
    // failure. Thread-safe; callers are the recv handlers in PacketRouter.
    std::optional<uint64_t> Resolve(uint64_t jobId);

    // Drops any pending future for `jobId` without waiting. Used when
    // the recv side decides not to patch (e.g. depot not in our scope).
    void Discard(uint64_t jobId);

    // Clears the resolved-code cache. Call when Lua files are hot-reloaded
    // so that stale manifest codes don't persist across config changes.
    void ClearCache();
}

#endif
