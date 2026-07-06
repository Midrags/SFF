// LumaCore — Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include <windows.h>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

// Runtime pattern fetcher. Hashes the on-disk Steam DLL backing a loaded module,
// pulls a matching <sha>.toml from the user pattern repo (with jsDelivr CDN
// secondary and a local cache under <Steam>\lumacore\pattern\), parses it, and
// exposes a name-keyed Lookup so ByteScan can resolve hook addresses against
// the live binary instead of compiled-in byte arrays.
namespace PatternFetcher {

    struct Entry {
        uint32_t    rva = 0;
        std::string sig;   // "48 8B C4 ?? 56 57 41 54 41 55"
    };

    // Public parsed-entry shape returned alongside the SHA in PatternResult.
    // The hook installer macros consult Get(module).entries via ByteScan to
    // resolve a function name to an RVA. The sig field holds the prologue
    // bytes the analyzer captured, in the same "AA BB ?? CC" format as the
    // internal Entry. ByteScan verifies the live module bytes match the sig
    // before handing the address to Detours so a stale TOML rva can't point
    // hooks at random code.
    struct TomlEntry {
        std::string   name;
        std::uint64_t rva = 0;
        std::string   sig;
    };

    // Result handed to entry.cpp orchestration after LoadFor finishes. ok is
    // true only when a TOML was either loaded from cache or fetched and
    // parsed successfully. sha is the 64 lowercase hex cache key when it
    // could be computed (empty if the on-disk module hash failed).
    struct PatternResult {
        bool                   ok = false;
        std::string            sha;
        std::vector<TomlEntry> entries;
        std::string            source;
        bool                   cacheHit = false;
        std::string            networkResult;
        std::string            error;
    };

    enum class Source {
        None,
        UserMirror,
        Github,
        Cdn,
        Gitflic,
        Cache,
    };

    // Returns "user-mirror", "github", "cdn", "cache", "none" for log messages.
    const char* SourceToStr(Source s);

    // Runs the cache-first / network-fallback load chain on the calling
    // thread. Caller wraps this in a detached worker so the Steam loader
    // thread never blocks on network IO. subdir must be "steamclient" or
    // "steamui" — picks the matching folder under the pattern repo for the
    // network fetch. The local cache is flat at <Steam>\lumacore\pattern\
    // <sha>.toml since the SHA is unique per module on disk.
    PatternResult LoadFor(HMODULE moduleHandle, const char* subdir);

    // Returns the most recently loaded result for the module handle. Hook
    // installers ask this from ByteSearch when resolving a function name.
    // For a module that LoadFor never ran against, returns a sentinel result
    // with ok=false and empty entries.
    const PatternResult& Get(HMODULE moduleHandle);

    // Cache-only sync load. Hashes the module, reads
    // <Steam>\lumacore\pattern\<sha>.toml if present, installs the entries,
    // and returns. No network IO. Used by InitThread to prime the runtime
    // map before hooks install so the LM_INSTALL macros can hit the runtime
    // path on the very first hook installer instead of racing the network
    // refresh worker. Bootstrap launches with no cache return ok=false and
    // the macros short-circuit to RecordMissed without crashing.
    PatternResult LoadCachedSync(HMODULE moduleHandle, const char* subdir);

    // Detached worker for the steamui leg that polls for steamui.dll to appear
    // before calling LoadFor. Used when the loader has not mapped steamui yet
    // at InitThread dispatch time.
    PatternResult LoadForSteamUiDeferred();

    // Returns the entry for funcName in subdir, or nullopt when the TOML never
    // loaded or the function is absent. Thread-safe under a shared lock.
    std::optional<Entry> Lookup(const char* subdir, const char* funcName);

    // High-level resolver used by hook installers. Takes a module handle and a
    // bare function name, picks the right TOML subdir (steamclient/steamui)
    // based on the module, runs Lookup with a small alias fallback for legacy
    // namespaced keys, byte-verifies the prologue at module_base + rva, and
    // hands back the candidate pointer on success. Returns nullptr on any
    // miss (no TOML entry, RVA out of range, byte mismatch, MODULEINFO
    // unavailable). Logs misses via LOG_WARN; callers don't need to.
    void* Resolve(HMODULE module, const char* funcName);

    // Drops all in-memory entry maps. Called from LumaCore::Detach.
    void Reset();
}
