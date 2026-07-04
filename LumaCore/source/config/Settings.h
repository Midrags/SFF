// LumaCore - Steam client hook layer for SteaMidra.
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags).
// Distributed under the GNU General Public License v3 or later.
// See <https://www.gnu.org/licenses/> for the full license text.

#pragma once

#include <string>
#include <vector>
#include <windows.h>

namespace Settings {

    enum class LogLevel { Trace, Debug, Info, Warn, Error };

    void Load(const std::string& configPath);
    struct ReloadResult { bool reloaded = false; bool luaPathsChanged = false; };
    ReloadResult ReloadIfChanged();

    // [log]
    inline LogLevel logLevel = LogLevel::Debug;

    // When true, every per-module logger is forced to Trace at startup so
    // we get the most detailed possible log of every IPC, network packet,
    // and hook call. Useful for diagnosing launch failures (Steam error 54
    // and similar). Defaults on so users do not need to touch config.toml
    // before sending logs.
    inline bool verbose = true;

    // derived from configPath: <steam>/lumacore/
    inline std::string logDir;

    // [lua]
    inline std::vector<std::string> luaPaths;

    // [lua] http_allowlist
    // Extra hosts that lcHttpGet() lua binding may reach. The default set
    // (manifesthub, github raw, jsdelivr cdn) is hardcoded and always
    // honoured even when the user clears this list. Any host in this
    // list is matched case-insensitively against the URL's host portion;
    // exact match only, no wildcards. Anything not on the combined list
    // gets a 403/empty-body response without the network ever being hit,
    // which is the data-exfil mitigation. Adding "*" is treated as
    // empty (we do NOT support disabling the gate).
    inline std::vector<std::string> luaHttpAllowlistExtra;

    // [pattern_fetch] mirror
    // Optional URL template for the pattern repo, with {subdir} and {sha}
    // placeholders. Empty string means "no override; go straight to the
    // GitHub primary -> jsDelivr -> gitflic -> local cache fallback chain".
    inline std::string patternMirror;

    // [pattern_fetch] gitflic_enabled
    // gitflic.ru fallback for users in regions where github + jsdelivr are
    // blocked or rate-limited (RU primarily). Sits after the github + cdn
    // legs and before the local cache. Set to false to skip it entirely.
    inline bool patternGitflicEnabled = true;

    // [pattern_fetch] require_signed
    // When true, the pattern fetcher refuses every TOML body whose .sig
    // sidecar fails RSA-PSS-SHA256 verification against the LumaCore-
    // embedded public key. The signature lives at <body_url>.sig — same
    // path with a ".sig" suffix appended. When false, we still verify and
    // log a warning on a missing/bad signature but installed entries from
    // unsigned legs are accepted for back-compat with pattern repos that
    // haven't started shipping signatures yet. Default false until the
    // pattern repo rolls out signed TOMLs across the whole tree, then
    // flip this to true to make rejection fatal.
    inline bool patternRequireSigned = false;

    // [manifest_fetch]
    // URL templates the wire-level GetManifestRequestCode bridge hits when
    // Steam asks for a manifest gid we have a depot binding for but the
    // server returned eresult != OK. Placeholders: {gid}, {appid}, {depotid}.
    // The body is parsed as either a plain decimal uint64 OR a JSON object
    // with a "content" digit-string field, so wudrm-style and steam.run-style
    // endpoints both work as is.
    //
    // The list is tried in order, first one that gives back a parseable code
    // wins. An empty list (e.g. user set [manifest_fetch] urls = []) disables
    // the bridge and lets the original eresult fall through.
    //
    // Single-string [manifest_fetch] url = "..." is honoured for back-compat
    // by Settings::Load: when present it OVERRIDES the chain (single-URL mode).
    // [manifest_fetch] urls = [...] takes precedence over the single form.
    inline std::vector<std::string> manifestFetchUrls = {
        "https://manifest.opensteamtool.com/{gid}",
        "https://manifest.steam.run/api/manifest/{gid}",
        "http://gmrc.wudrm.com/manifest/{gid}",
    };

    // Total wall clock the recv handler waits on the HTTP future before
    // giving up and letting the original eresult fall through. Applied
    // per-provider; the chain stops as soon as one returns a code, so a
    // healthy first provider doesn't pay the budget of the slow ones.
    inline int manifestFetchTimeoutSec = 12;
    inline std::vector<std::string> manifestFetchTrustedHosts;
    inline bool statsEnableApi = true;
    inline bool processExtensionEnabled = false;
    inline std::string processExtensionX86;
    inline std::string processExtensionX64;

    // [onlinefix]
    // Master switch for the CreateProcessW/AsUserW injection hooks that load
    // LumaCorePayload.dll into -onlinefix game processes. Set to false when
    // only Lua-level decoy / ticket forging is needed (no multiplayer bridge).
    inline bool onlineFixInjectEnabled = true;

    // [boot]
    // When true, BootDiag::ReportMissing shows a MessageBoxA popup with
    // Steam build ID and steamclient SHA256 when IPC specs cannot be
    // loaded (pattern repo doesn't yet support this build). Default false
    // so users are not surprised by a popup on first launch. When a Steam
    // update breaks dispatch, users can flip this to true and share the
    // popup content in bug reports.
    inline bool diagnosticPopupEnabled = true;


}

