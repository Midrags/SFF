# Changelog

## 5.4.0

### GBE Fork Update
- **Updated Windows GBE fork DLLs** — `steam_api.dll`, `steam_api64.dll`, `steamclient.dll`, `steamclient64.dll`, `GameOverlayRenderer.dll`, `GameOverlayRenderer64.dll` now use the experimental builds (~19 MB) which include full overlay support.
- **Fixed DLL extraction bug** — Goldberg auto-updater now correctly extracts experimental DLLs instead of the smaller regular builds. Full archive path is matched first before filename-only fallback.
- **Added Linux `steamclient.so`** — `steamclient.so` (x64) and `steamclient32.so` (x32) are now downloaded and deployed for Linux native games that load steamclient directly.

### Achievement & Config Generation Fixes
- **Achievements now always generated** — Fix Game pipeline now automatically uses the saved/default Steam Web API key if none is explicitly provided. Achievements were silently skipped before.
- **Per-game `configs.main.ini` now written** — `steam_settings/configs.main.ini` is generated for each game with `allow_unknown_stats=1` so stats work even without a full `stats.json`.
- **Stats format fixed** — `stats.json` now uses the correct GBE fork field names (`name`, `type`, `default`, `global`) instead of raw Steam API fields.
- **Achievement `hidden` field fixed** — `achievements.json` `hidden` field is now always a string (`"0"` or `"1"`) as required by GBE fork.
- **Overlay config updated** — `configs.overlay.ini` now includes 4 new options from the latest GBE fork release: `overlay_always_show_user_info`, `overlay_always_show_fps`, `overlay_always_show_frametime`, `overlay_always_show_playtime`.

### Tools Tab
- **GBE Token Generator pre-fills API key** — Steam Web API key is now auto-filled from saved settings (or default key) on startup. Generation no longer aborts if the field is empty — uses default key as fallback. Key is saved to settings after successful generation.

### UI Improvements
- **Fix Game tab decluttered** — checkboxes grouped into logical rows: Goldberg update + Launch.bat in one row; SteamStub + Experimental in one row. Reduces vertical space.

---

## 5.3.0

### Fixes
- **Steam launch "Access Denied" fix** — SteaMidra now checks if it is already running as administrator. If it is, it launches Steam directly instead of requesting elevation again (which caused an "Access Denied" error on Windows 11).
- **Auto-updater fixed for Windows EXE builds** — now downloads the release ZIP, extracts it next to the EXE, replaces the `_internal/` folder via a batch script, and relaunches automatically. No more aria2c or manual steps.
- **Auto-updater fixed for Linux AppImage builds** — downloads the release ZIP, extracts it, then runs `steamidra_install.sh` in your terminal automatically.

### Improvements
- **Windows EXE is now distributed as a ZIP folder** (`SteaMidra-5.3.0-windows.zip`). Extract once anywhere, run `SteaMidra_GUI.exe` from the extracted folder. This replaces the single-file EXE.
- **No more temp folder extraction on startup** — files are pre-extracted into `_internal/` at install time. Startup is faster and antivirus false positives are greatly reduced.

---

## 5.2.0

### AppList popup notification (GUI)
- **GUI now shows a warning dialog** when your AppList reaches 130 or more App IDs, reminding you to create a new AppList profile before adding more games. The popup appears once per session after any action completes. The CLI has always printed a warning at the same threshold — this extends it to the GUI.

### Linux fixes (12 bugs)
- **`all_games.txt` crash fix** — `choices.py` and `cloud_saves.py` both read/wrote `all_games.txt` using `sys._MEIPASS` or the bare `root_folder()` path, which points to the read-only squashfs inside an AppImage. Fixed to use `root_folder(outside_internal=True)` (writable user data dir `~/.local/share/SteaMidra/`) for both read and write.
- **Flatpak LD_AUDIT path fixed** — `slssteam.py` `patch_steam_sh()` constructed the Flatpak `LD_AUDIT` path with an erroneous `/data/Steam` segment (resulting in a non-existent path). Fixed: `flatpak_base` is now `~/.var/app/com.valvesoftware.Steam` with no extra segment.
- **Flatpak default `.so` paths fixed** — `steam_process.py` default path lists for `SLSsteam.so` and `library-inject.so` contained the same `/data/Steam` error. Fixed to match the correct Flatpak layout.
- **7z exit-code tolerance** — `install_from_github()` now tolerates non-zero 7z exit codes caused by symlink warnings (common with `SLSsteam-Any.7z`). If `setup.sh` is found in the extracted directory despite the non-zero code, extraction continues with a warning instead of aborting.
- **`extract_dir.mkdir()` added** — the extraction directory is now created explicitly before the 7z call, preventing `FileNotFoundError` on first install.
- **Config template from extracted archive** — new `_setup_config_from_extracted()` copies `res/config.yaml` from the freshly downloaded archive to `~/.config/SLSsteam/config.yaml` (only if the user config doesn't exist). Previously the bundled copy was used, which could be stale.
- **`updates.yaml` URL corrected** — was `main/updates.yaml`, now `refs/heads/main/res/updates.yaml` to match the actual repo structure.
- **Hash parsing fixed** — replaced broken regex approach with YAML `SafeModeHashes` parsing so `check_steamclient_hash()` correctly validates the hash against all known entries.
- **Flatpak `.so` copy** — new `_copy_so_to_flatpak()` copies installed `.so` files to the Flatpak Steam path after install, so Flatpak Steam can find them.
- **`get_installed_version()` + `check_update_available()`** — new functions to track and check the installed SLSsteam version against the latest GitHub release.
- **GitHub-only install** — removed the bundled install option from `handle_linux_setup()`. SLSsteam is now always installed from the latest GitHub release.
- **Update check menu** — when SLSsteam is already installed, a 3-way menu now appears: check for updates / reinstall from GitHub / skip. The update check shows installed vs latest version and prompts to install if an update is found.

### Documentation + README cleanup
- Removed all references to CreamAPI Multiplayer Fix from `README.md`, `USER_GUIDE.md`, `QUICK_REFERENCE.md`, and `MULTIPLAYER_FIX.md` (feature was removed in 4.9.1).
- Removed broken `CREAMAPI_FIX.md` link from `MULTIPLAYER_FIX.md`.
- Removed "Fast SteamDB manifest history" from `README.md` features list.
- Clarified download methods in `README.md` and `FEATURE_USAGE_GUIDE.md`: Main tab "Download Game" = latest version via Steam-native download (fast, no .NET); Store tab = older/specific versions via DepotDownloaderMod (.NET 9 required, slower).
- Fixed false claim in `README.md` that SteaMidra "reminds you" at 130 IDs — it now accurately says a popup dialog appears.

---

## v5.1.0

### Store tab ACF fix: Play button instead of Update

- **ACF `InstalledDepots`** now uses the **latest manifest GIDs** from the Steam API (not the Lua IDs). Steam compares these IDs against CDN on startup; writing the latest GIDs means Steam sees the game as fully up-to-date and shows **Play** instead of **Update**.
- **ACF `buildid`** is now fetched from the Steam API (`depots.branches.public.buildid`) and written correctly, matching the installed version Steam expects.
- **ACF `LastUpdated`** is now set to the current Unix timestamp on every write.
- **Depotcache cleanup**: manifest files are pre-downloaded for DepotDownloaderMod authentication, then **deleted from `depotcache`** immediately after the download completes. The Store tab no longer leaves stale `.manifest` files in your Steam depotcache folder.
- **Linux**: `buildid` is also fetched from the Steam API in the Linux download path.

---

## v5.0.0

### Store tab — direct game download (Windows + Linux)

- **Download game files directly** from the Store tab version picker via DepotDownloaderMod. Previously the Store tab only set up Lua/manifests and left the actual game download to you; now it downloads the full game automatically.
- **Full pipeline**: Lua fetch → decryption keys written → manifest pre-download → DepotDownloaderMod download → ACF written → Steam library registered.
- **Parallel manifest download** support — respects the `USE_PARALLEL_DOWNLOADS` setting.
- **Real `SizeOnDisk`** calculated from the downloaded files and written into the ACF.
- **Linux**: same pipeline available via `handle_linux_download` with `acf_writer.create_acf`.

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

---


## v4.6.5

### New features

- **SteamAuto:** One-click auto-crack via SteamAutoCrack for the selected game. In the GUI, select a Steam game or a folder for a game outside Steam, then click SteamAuto to run the full crack process. In the CLI, choose Steam or non-Steam, then pick the game or enter its path and App ID. Place the Steam-auto-crack repo in `third_party/SteamAutoCrack` and optionally build its CLI into `third_party/SteamAutoCrack/cli/` (or use the build script when the repo is present).

---

## v4.6.4

### New features

- **AppList profiles:** Work around GreenLuma's 130–134 ID limit by using multiple profiles. Create empty profiles, switch between them, save the current AppList to a profile, and delete or rename profiles. Each profile can hold up to 134 IDs (configurable in settings). When you reach 130 IDs, a message reminds you to create a new profile before adding more games.

---

## v4.6.3

### New features

- **Embedded Workshop browser:** Open Workshop from the GUI to browse Steam Workshop in an embedded web view. Login to Steam, browse workshop pages, copy links, and download items without leaving SteaMidra. Uses a persistent profile so your session is kept.
- **Workshop item download:** Paste a workshop URL or item/collection ID to download manifests. Supports single items and full collections.
- **Check mod updates:** Track workshop items and check for newer versions, then update outdated mods in one go.
- **Check for updates – automatic install:** When a newer version is available, download and update automatically. SteaMidra fetches the release, extracts it, and replaces files in your install folder.

---

## v4.6.2

### Removed features

- **Steam patch removed:** The Steam patch feature (xinput1_4.dll, hid.dll) has been removed from all variants.
- **Sync Lua removed:** The option to sync saved Lua files and manifests into Steam's config has been removed.
- Version bump to 4.6.2.

---

## v4.6.1

### Multiplayer fix (online-fix.me) – Selenium login fix

- **Login now works:** The multiplayer fix no longer uses HTTP-only login, which often failed with "Login failed (form still visible)". It now uses **Selenium with Chrome**: a headless browser opens the game page, fills in your credentials, clicks the login button, and handles cookies and JavaScript like a real browser. Login and download should work reliably.
- **What you need:** Chrome browser must be installed. Selenium is in the main requirements: `pip install -r requirements.txt`.
- Search, match, download button, and archive extraction flow are unchanged; only the login step is now browser-based.

---

## v4.5.4

### Check for updates – automatic install

- **Automatic update:** When a newer version is available, you can choose "Download and update automatically?". SteaMidra downloads the release zip, extracts it, and replaces the files in your install folder. When running from **source** (Python), the app restarts with the new version. When running from the **EXE**, SteaMidra does not relaunch the EXE; it tells you to rebuild the EXE so the new updates take effect.
- Updates use the same folder as your current install, so no manual copying or extracting is needed.

---

## v4.5.3

### Multiplayer fix (online-fix.me) – correct game and better matching

- **"Game: Unknown" fixed:** The game name is now read from the ACF in the **same Steam library** where the game is installed (e.g. if the game is on `D:\SteamLibrary\...`, we read that library’s manifest, not the first one). If the name is still missing, we fetch the official name from the **Steam Store API** so we never search with "Unknown".
- **Wrong game match fixed:** Search now uses a stricter minimum match (50%) and prefers results whose link text contains the game name (e.g. "R.E.P.O. по сети" for R.E.P.O.). We also search with "game name online-fix" to narrow results. This avoids picking the wrong game (e.g. "Species Unknown" when you selected R.E.P.O.).

---

## v4.5.2

### Update check (Check for updates)

- **Check for updates** now works for everyone: it always checks GitHub for the latest release and shows your version vs latest.
- If you're up to date: *"You're already on the latest version."*
- If a newer version exists: you can open the release page in your browser to download (or, for the Windows EXE with a matching update package, update from inside the app).
- The updater uses proper GitHub API headers and a fallback when the "latest" endpoint is unavailable.

### DLC check reliability

- **DLC check** no longer gets stuck when Steam is slow or times out.
- Steam API requests (app info, DLC details) now retry up to 3 times with a short delay instead of looping forever.
- If Steam still fails after retries, SteaMidra automatically falls back to the **Steam Store** (no login): it fetches the DLC list and names from the store website and still shows which DLCs are in your AppList/config and lets you add missing ones.
- So the DLC check works even when the Steam client connection is flaky.

### Other fixes

- **credentials.json** is now in `.gitignore` so it never gets committed or included in release zips.
- **UPLOAD_AND_PRIVACY.md** updated with release-zip instructions and what to exclude.

---

## v4.5.1

### Fix for crash on startup (`_listeners` error)

**What was the problem?**

Some people got a crash when starting SteaMidra. The error said something like:  
`'SteamClient' object has no attribute '_listeners'. Did you mean: 'listeners'?`

That happened because the wrong Python package named "eventemitter" was installed. SteaMidra needs a specific one called **gevent-eventemitter**. There is another package with a similar name that does not work with SteaMidra and caused the crash.

**What we changed**

- We now tell the installer to use the correct **gevent-eventemitter** package so new installs should not hit this crash.
- If you already had the crash, do this once:
  1. Open a command line in the SteaMidra folder.
  2. Run: `pip uninstall eventemitter`
  3. Run: `pip install "steam[client]"`
  4. Run: `pip install -r requirements.txt`
  5. Start SteaMidra again.

After that, SteaMidra should start normally.
