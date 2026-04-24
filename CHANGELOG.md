# Changelog

All notable changes to SteaMidra are documented here.

---

## 5.0.0

### ACCELA Linux Integration
- **Robust YAML config manager** — atomic writes with backups for SLSsteam `config.yaml`. Targeted section edits, indentation fixes, and safe concurrent access.
- **App token extraction** — `addtoken()` calls in Lua files are now parsed automatically and passed to depot downloads for authenticated access.
- **FakeAppIds prompt** — after a successful Linux download, SteaMidra prompts to add the game's AppID to the SLSsteam FakeAppIds list.
- **SLSsteam API pipe** — sends config reload signals to a running SLSsteam instance via `/tmp/SLSsteam.API`, so changes take effect without restarting Steam.
- **SLSsteam bug fixes** — corrected Flatpak LD_AUDIT path, added `.so` file copy fallback, fixed hash URL for update checks.
- **GreenLuma auto offline fix** — on Windows startup, automatically resets Steam's `WantsOfflineMode` if GreenLuma is detected, preventing the "offline mode" loop.
- **Depot Downloader cleanup** — temporary manifest files are now cleaned up after all downloads complete.
- **Linux desktop shortcuts** — create `.desktop` shortcuts for installed games with icon fetching from Steam CDN (SteamGridDB as optional fallback).
- **Game update tracker** — saves depot manifest IDs after download and checks for updates against the Steam API on demand.

### online-fix.me Multiplayer Fix
- **OFME files excluded** — online-fix.me blocks direct download of full game (OFME) packages; SteaMidra now navigates straight to the Fix Repair subfolder and downloads only the fix archive.

### Version bump
- 4.9.1 → 5.0.0

---

## 4.9.1

### online-fix.me Multiplayer Fix — complete rewrite
- **SeleniumBase UC mode** — Cloudflare bypass + ad blocking built-in. No more manual Chrome setup.
- **3-layer ad popup prevention** — extracts the uploads URL directly from the game page before clicking (Layer 1); falls back to smart 15s polling that closes only confirmed ad tabs and preserves the uploads tab (Layer 2); final page-source re-scan fallback (Layer 3).
- **Smart file server navigation** — automatically enters subfolders (`Fix Repair/`, `Generic/`, `Steam/`, `Patch/`) before scanning for archives.
- **OFME exclusion** — files containing "OFME" in the name (full game packages, typically 800 MB+) are completely excluded from download candidates.
- **401 error handling** — proactive browser refresh after initial navigation + up to 3 in-loop refresh retries when the file server returns 401, resolving transient nginx authentication failures automatically.
- **Re-apply fix replaces files** — applying the fix a second time now replaces existing fix files directly. The original `.bak` of the game's own DLL is preserved; no redundant second-level backups are created.

### Removed
- **CreamAPI Multiplayer Fix** — "Apply CreamAPI Multiplayer Fix" and "Restore CreamAPI Multiplayer Fix" menu items removed. The bundled CreamAPI DLLs remain in `third_party/online_fix/` for potential future use.

---

## 4.9.0

### CreamAPI Multiplayer Fix (new feature)
- **Apply CreamAPI Multiplayer Fix** — new menu item. Installs bundled CreamAPI v5.3.0.0 (nonlog build) to spoof your game as Spacewar (AppID 480) for online multiplayer. No credentials, no browser, no external downloads required.
- **Restore CreamAPI Multiplayer Fix** — new menu item to undo the fix and restore original DLLs.
- **Classic mode** (default): replaces `steam_api.dll` / `steam_api64.dll` in-place; `cream_api.ini` placed next to the DLL.
- **Proxy mode** (anti-cheat fallback): CreamAPI installed as `winmm.dll`; original Steam API DLLs untouched.
- **Anti-cheat detection**: automatically scans for EasyAntiCheat and BattlEye folders/files; suggests Proxy mode if found.
- **Linux platform selection**: on Linux, user chooses Proton/Wine (Windows .dll) or Native Linux (.so). ELF bitness is read from the header to select x64 vs x86 `.so` automatically.
- **Spacewar auto-check**: reads all Steam library ACF files to detect if Spacewar (AppID 480) is already installed. If not, shows a one-time `steam://install/480` prompt and stores a marker file so the user is never prompted again after the first time.
- **Existing online-fix.me button unchanged** — both methods coexist in the menu.
- **Version bump**: 4.8.4 → 4.9.0
G
---

## 4.8.4

### Linux Compatibility Overhaul
- **Linux GBE files now fully bundled** — `third_party/gbe_fork_linux/` ships `libsteam_api.so` (x64), `libsteam_api32.so` (x32), and `generate_interfaces_x64/x32`. No internet needed on first run.
- **Fixed archive path resolution** — x64 vs x32 `libsteam_api.so` are now correctly distinguished by their full archive path, not filename (both have the same name in the release archive).
- **Linux generate_emu_config bundled** — `third_party/gbe_fork_tools_linux/` ships the Linux ELF binary. Works without Wine or any external tool.
- **GSE tool updater: Linux support** — `gse_tool_updater.py` now finds and runs the bundled Linux binary, with optional update checking against `Detanup01/gbe_fork_tools` on GitHub.
- **GSE tool updater: Windows bundled fallback** — if GitHub is unreachable, the Windows `generate_emu_config.exe` bundled in `third_party/gbe_fork_tools/` is now used as an offline fallback.
- **Fix Game tab: Linux native checkbox** — new "Linux native game" checkbox (visible on Linux only, checked by default). Uncheck for Proton/Wine mode.
- **Bundled Goldberg used on first launch** — previously, if "Check for updates" was unchecked and the cache was empty, the pipeline would abort. Now it automatically copies from `third_party/` on first run.
- **XDG_DATA_HOME support** — GSE Saves root on Linux respects `$XDG_DATA_HOME` per the official gbe_fork README.
- **Steamless via Wine** — `steamstub_unpacker.py` now runs `Steamless.CLI.exe` via Wine on Linux if Wine is available.
- **Platform-aware launch scripts** — `launch.sh` for native Linux, `launch_wine.sh` + `LUTRIS_SETUP.txt` for Proton/Wine mode.
- **Cache path XDG-compliant** — cache directory on Linux uses `~/.local/share/SteaMidra/fix_game_cache/`.

---

## 4.8.3

### New features
- **SteamDB 3-layer scraping** — dramatically faster manifest history loading. Layer 1 uses `curl_cffi` Chrome impersonation (no browser, ~80% hit rate). Layer 2 reuses a cached `cf_clearance` cookie (25-min disk cache, no browser). Layer 3 falls back to SeleniumBase and automatically saves the cookie for the next run. Warm runs typically complete in 10–35s vs 2–4 min previously.
- **DLC depot completeness** — manifest history now includes depots from DLC apps. The Steam CM fetcher reads `extended.listofdlc` and pulls depot manifests from each DLC app, so games with DLC show their full depot history.
- **Linux: SLSSteam ID management** — "Manage SLSSteam IDs" menu option now works on Linux. Fully functional Add IDs and View/Delete IDs from the SLSSteam config.
- **MIDI player rewrite** — playlist support, dynamic `.mid` / `.sf2` file scanning from the `c/` folder, COM-thread safety fix, and `IsFinished()` polling so tracks don't restart on loop.
- **Settings applied live** — editing or deleting a setting in the GUI now takes effect immediately without restarting.

### Fixes
- **ACF writing reverted** — `write_acf` restored to `StateFlags=4` with `SizeOnDisk=0`, `BytesToDownload=0`, `BytesDownloaded=0`. Previously used `StateFlags=6` + `buildid=0` which caused Steam to show "Play" instead of "Update" for new installs.
- **`_patch_acf_error_state` cleaned** — removed problematic `buildid=0` and `InstalledDepots`/`MountedDepots` deletion that caused game state corruption. Now only clears safe flags: `UpdateResult`, `FullValidateAfterNextUpdate`, `ScheduledAutoUpdate`, byte counters, and the Locked `StateFlags` bit.
- **AppList depot completeness** — `add_ids()` now adds every unique depot/DLC ID from `LuaParsedInfo.depots`, not just the base `app_id`. Previously only the base app ID was added, causing GreenLuma to miss depot authentication and Steam to skip downloading large chunks of games (e.g., RE9 only downloading 1 GB instead of 76 GB).
- **Code formatting cleanup** — removed excessive double-spacing and blank lines across all Python files while preserving copyright headers.
- **Linux MIDI library path** — `MidiFiles.MIDI_PLAYER_DLL` now resolves to `.dll` on Windows and `.so` on Linux. Previously always pointed to `.dll`, silently skipping music on Linux even if the `.so` was compiled.
- **Linux applist menu stub removed** — `applist_menu()` previously printed "Functionality for linux will be implemented soon." and returned immediately. It now routes correctly to `SLSManager` on Linux.
- **`ManifestContext` TypeError** — `auto` field in the `ManifestContext` dataclass was missing its type annotation, causing `TypeError: __init__() got an unexpected keyword argument 'auto'` when downloading manifests with auto-fetch enabled.

### Dependencies
- Added `curl_cffi>=0.7` — required for SteamDB Layer 1 Chrome impersonation.

---

## 4.8.2

- MIDI player integration: background playback thread, channel muting, soundfont support.
- Live settings apply for GUI.
- AppList profiles: create, switch, save, delete, rename.
- Cloud Saves: backup and restore Steam userdata saves.
- VDF Key Extractor: pull depot decryption keys from Steam's config.vdf.
- GBE Token Generator: generate full Goldberg emulator configs with achievements, DLCs, and stats.
- Fix Game pipeline: automate emulator application with SteamStub unpacking.
- Store browser with pagination.
- System tray icon.
- Multi-language GUI (English + Portuguese).
- 11+ themes.
