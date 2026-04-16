# Changelog

## v4.8.2 (latest)

### New Features

- **"＋ Add depot manually" in version picker:** Each version group in the Download Version dialog now has a "＋ Add depot manually…" button. Click it to enter a Depot ID and Manifest ID by hand — the row is inserted pre-checked and picked up by Download Selected automatically. Useful for DLC depots that SteamDB couldn't scrape.
- **ColdClient (Advanced / GSE Fork) mode:** New emulator mode in the Fix Game tab that runs `generate_emu_config.exe` silently (no black console window, no credential prompt appearing in front of the GUI). Supports anonymous login or optional Steam account credentials saved in settings for reuse.

### Fixes & Improvements

- **Hubcap Manifest rebrand:** All `manifest.morrenus.xyz` URLs updated to `hubcapmanifest.com` following the Morrenus Games → Hubcap Manifest rebrand. UI label "Morrenus API Key" updated to "Hubcap API Key". Existing saved API keys are fully preserved (backward-compatible storage key).
- **Fixed black console + password prompt on Crack game:** `generate_emu_config.exe` is no longer spawned from the main Crack game path. Replaced with pure-Python `GoldbergConfigGenerator` — no console window, no credential prompt, and no real Steam username leaked into configs.
- **Fixed ColdClient files leaking into game dir on Crack:** `shutil.copytree` replaced with `shutil.copy2` — only the target `steam_api.dll` is copied to the game folder instead of the entire gbe_fork directory.
- **Configs always generated on Crack game:** Removed the "generate configs?" yes/no prompt. `configs.app.ini` and `configs.user.ini` are now always written after the DLL swap without asking.
- **Save folder path logged:** After Crack game or Fix Game, the exact save data path (`%APPDATA%\GSE Saves\{app_id}\`) is printed to the log so users can locate their save files.
- **ColdClient renamed to ColdClient (Simple):** "ColdClient Loader" renamed to "ColdClient (Simple)" in the Fix Game mode dropdown for clarity alongside the new Advanced mode.
- **Removed `GameOverlayRenderer.dll` from regular GBE apply:** The overlay DLL is not needed for a basic DLL swap — it is built into `steam_api.dll` when the overlay is enabled.
- **ColdClient deploys only matching-arch steamclient DLL:** 64-bit games receive `steamclient64.dll` only; 32-bit games receive `steamclient.dll` only. Both were previously always copied regardless of game architecture.
- **`configs.app.ini` format fixed — GoldbergGUI parity:** DLC entries now appear before `unlock_all`; `unlock_all` defaults to `1` (was `0`); real DLC names are fetched from the Steam Store API in one batch call (falls back to `"DLC {id}"` per entry on error).
- **Full `configs.overlay.ini` template:** Generated file now matches GoldbergGUI's full template exactly — `enable_experimental_overlay=1`, all appearance/timing/FPS-stats settings included instead of the previous 20-line stub.
- **Global GBE settings folder:** Identity configs (`configs.user.ini`, `configs.main.ini`) and the account avatar are now written once to `%APPDATA%\GSE Saves\settings\` rather than per-game `steam_settings\`. Per-game folders are cleaner and the avatar priority bug (per-game avatar overriding the global one silently) is fixed. `SFF.png` is used as the default avatar on first setup.
- **Steam Store API fallback for DLC list:** `_fetch_dlcs` now falls back to the Steam Store `appdetails` endpoint when SteamCMD returns no DLC, ensuring configs are still populated.
- **Fixed SteamDB fill-forward pollution:** DLC depots that were Cloudflare-blocked during SteamDB scraping (CM-only entries) no longer appear in SteamDB historical version groups with incorrect source and date. Fill-forward now strictly excludes Steam CM entries.

### Hotfix (post-release)

- **Fixed `LuaEndpoint` AttributeError crash:** All users running v4.8.2 crashed on Lua download due to a stale `MORRENUS` reference in the CLI engine. Fixed to `HUBCAP`.
- **Fixed GSE credentials never saving/loading:** Two incorrect import paths (`sff.settings` → `sff.storage.settings`) silently prevented GSE credentials from being saved after a ColdClient Advanced run or pre-filled in the UI on next launch.
- **DLC now fetched in Simple mode:** The `configs.app.ini` DLC list was incorrectly skipped when Simple mode was selected. DLC is now always fetched; only achievements, language data, and depot info are skipped.
- **Overlay disabled in Simple/Regular mode:** `configs.overlay.ini` now writes `enable_experimental_overlay=0` for Simple and Regular Goldberg modes to avoid crashes with frametime tools. Only ColdClient Advanced mode enables the overlay.
- **User identity no longer reverts:** The Fix Game tab now reads `%APPDATA%\GSE Saves\settings\configs.user.ini` on startup and pre-fills the Username and Steam64 ID fields from the global GBE identity.
- **Hubcap API key redirect:** Clicking Connect with no API key now shows a dialog with a direct "Get API Key" button that opens `https://hubcapmanifest.com/` in the browser.
- **Code cleanup:** Renamed `sff/fun.py` → `sff/extras.py`. Removed personal `# owner:` dev tags and casual inline comments across all files.

---

## v4.8.1

### New features

- **Steam userdata Save Backup:** Cloud Saves tab completely rebuilt. SteaMidra now reads your Steam32 ID (saved in Settings or entered inline), scans `Steam/userdata/<steam32id>/` for all games with save data, resolves game names from `appmanifest_*.acf` files, and lets you back up the `remote/` folder to any destination folder. Backup structure: `<dest>/<Game Name> [AppID]/remote/`. An Import (Restore) button copies a backup back to Steam with an automatic safety backup before overwriting.
- **GameOverlayRenderer.dll deployment:** `GameOverlayRenderer.dll` (x32) and `GameOverlayRenderer64.dll` (x64) are now deployed automatically to the game folder during both regular Goldberg apply and ColdClient Loader apply — arch-matched to the game exe. These DLLs are required when the experimental overlay is enabled in `configs.overlay.ini`.
- **Desktop Shortcut for ColdClient Loader:** After applying ColdClient Loader mode, SteaMidra automatically creates a `.lnk` shortcut on the Windows Desktop pointing to the correct arch loader exe (`steamclient_loader_x64.exe` / `x32.exe`). The shortcut uses the game's own exe as its icon source. No extra Python packages required — uses PowerShell `WScript.Shell`.
- **`configs.user.ini` generation:** Goldberg config generation now creates the mandatory `configs.user.ini` file with the correct `[user::general]` section containing `account_name`, `account_steamid`, and `language`. Previously this file was missing, causing gbe_fork to fall back to anonymous defaults.
- **Overlay disabled by default:** `enable_experimental_overlay` in `configs.overlay.ini` now defaults to `0`. The overlay can cause crashes in some games and should only be enabled manually when needed.

### Fixes & Improvements

- **Fixed FileNotFoundError crash on first apply:** `goldberg_applier.apply()` now creates the `steam_settings/` directory before scanning interfaces. Previously it crashed with `FileNotFoundError: steam_interfaces.txt` when the directory didn't already exist.
- **Fixed `configs.main.ini` wrong section:** Account name and Steam ID were incorrectly written to `[main::general]`. They now only appear in `configs.user.ini` under `[user::general]` as gbe_fork expects.
- **Removed Capcom Save Fix UI:** The Capcom Save Fix required SteamTools to be installed — without it the fix does nothing. Removed from the Tools tab and Cloud Saves tab to avoid confusion.
- **Removed STFixer mode from Cloud Saves tab:** Cloud Saves tab is now a single focused Steam userdata backup/restore interface.
- **Launch.bat defaults to unchecked:** The "Create Launch.bat" option in Fix Game tab now defaults to unchecked since the desktop shortcut replaces its purpose for ColdClient mode. The option remains available for users who prefer a batch file.
- **`GameOverlayRenderer.dll` added to restore() cleanup:** Restoring a game now removes the deployed overlay DLLs alongside other Goldberg files.

---

## v4.8.0

### New features

- **Tabbed GUI:** SteaMidra now uses a tabbed interface with dedicated tabs for Main, Store, Downloads, Fix Game, Tools, and Cloud Saves.
- **Store / Library Browser:** New Store tab to search and browse the Morrenus manifest library. Enter your API key, search by name or App ID, and paginate through results.
- **Cloud Saves — STFixer Mode:** Cloud Saves tab now has two modes. STFixer Mode patches broken save behavior in Capcom games (based on STFixer v0.7.1 by Selectively11). Backup/Restore Mode lets you manually snapshot and restore game save files.
- **Cloud Saves — Backup/Restore:** Create, list, restore, and delete save backups per game with a full table UI.
- **GBE Token Generator (redesigned):** Tools tab now has a full GBE Token Generator with Steam Web API Key input, App ID, output directory with browse, real-time log output, and credits. Generates complete Goldberg emulator steam_settings packages.
- **Fix Game Tab:** Dedicated tab for the Fix Game automation pipeline with emulator mode selection (Regular Goldberg, ColdClient Loader, ColdLoader DLL), SteamStub auto-unpack, and config generation options.
- **Downloads Tab:** Dedicated tab for managing active and queued downloads.
- **VDF Depot Key Extractor:** Extract decryption keys from Steam's config.vdf with a table display.
- **System Tray Icon:** SteaMidra now shows a system tray icon for quick show/hide and exit.
- **URI Handler:** Register `midra://` protocol links for deep-linking into SteaMidra.
- **9 New Themes:** Added Dracula, Nord, Cyberpunk, and more theme options in the Theme menu.

### Fixes & Improvements

- **Fixed "NO INTERNET CONNECTION" error:** Root cause identified — Steam's Workshop update was failing (not the game download itself). SteaMidra now patches the workshop ACF (`appworkshop_{id}.acf`) to clear `NeedsDownload` when no workshop content is installed, preventing orphaned workshop items from triggering Access Denied errors that cascade into "NO INTERNET CONNECTION".
- **Always refresh depotcache manifests:** Removed stale `if-not-exists` guards so manifests from Morrenus ZIPs and network downloads always overwrite depotcache. This prevents Steam from using outdated manifests.
- **ACF error state patch:** When updating an existing game (choosing "I'm updating"), SteaMidra now clears `UpdateResult`, `FullValidateAfterNextUpdate`, and byte counters in the game ACF to prevent Steam retry loops.
- **Download Tracking integration:** The "Download Games" flow now pushes entries to the Downloads tab so you can see download progress in the GUI.
- **Fixed UnicodeEncodeError:** Logging in uri_handler.py no longer crashes on Windows cp1252 consoles.
- **Fixed Store search:** Store tab now correctly calls the API (search_library, offset-based pagination).
- **Fixed EmuMode references:** Fix Game tab now uses correct enum values (COLDCLIENT_LOADER, COLDLOADER_DLL).
- **Fixed TrayIcon class name:** Main_gui.py now imports the correct TrayIcon class.
- **Fixed UriHandler calls:** Uses static methods (register/is_registered) correctly.
- **Fixed GBE Token Generator:** Now properly accepts and passes Steam Web API key to the generator backend.
- **Renamed button:** "Process .lua file" renamed to "Download Games" for clarity.

---

## v4.7.2

### Fixes & Improvements

- **Oureveryday Dynamic LUA Assembly:** Fixed a critical bug where the `oureveryday` option threw a "Failed to download Lua for App ID..." error due to the permanent deletion of the upstream SteamAutoCracks GitHub repository. Since pre-built `.lua` files for this feature are no longer hosted on the internet, SteaMidra now features a custom **Dynamic LUA Assembler**. It natively queries the official Steam Connection Manager to isolate your game's depots, downloads the active 288k+ JSON key database from GitLab, and flawlessly builds the required `.lua` file on the fly before seamlessly transitioning into the standard manifest downloads.
- **Local Fallback Database:** Added a robust final "last resort" fallback system for offline deployments so SteaMidra can parse local JSON decryption key dumps if the internet or GitLab goes down completely.

---

## v4.7.1

### New features

- **Multiplayer Fix Overhaul (online-fix.me):** The multiplayer fix download flow has been completely rewritten for maximum reliability. It now handles aggressive ad popups by monitoring window handles, supports navigating into "Fix Repair" subfolders on the primary server, and includes a robust fallback to the "Hosters" page (with automatic parsing of Pixeldrain/direct links from JSON metadata). This fixes the persistent "Archive link not found" and "Window timeout" errors.
- **Fixes/Bypasses (Ryuu):** A new second fix button is now available alongside the existing multiplayer fix. It connects to [generator.ryuu.lol](https://generator.ryuu.lol/fixes), fetches the full list of available fixes, and lets you search and pick the one for your game using fuzzy search. Once selected, the fix is downloaded and extracted directly into your game folder using Python's built-in zip support — no WinRAR or 7-Zip required. This gives a second source of game fixes that is often more up to date and has broader coverage than online-fix.me.
- **Multi-language interface (i18n):** SteaMidra now supports multiple display languages for the GUI. English and Portuguese are included out of the box. You can add more by dropping a new locale JSON file into `sff/locales/`. The active language is set in Settings and takes effect immediately on the next GUI launch.
- **Morrenus Error Handling:** Improved error reporting for Morrenus manifest downloads, specifically handling 404/Limit reached responses more gracefully by displaying the actual server error message.

---

## v4.7


### Fixes & Improvements

- **ACF installdir fix:** Fixed a bug where `write_acf` could write an empty `installdir` to the ACF file if the Steam Store API request failed and no name was entered. An empty installdir causes Steam to report "not enough free disk space" even when plenty of space is available, because Steam cannot figure out where to commit the staged download. SteaMidra now falls back to the App ID as the folder name and prints a warning so you know to rename it if needed.
- **oureveryday fallback fix:** Fixed the oureveryday option incorrectly falling back to Morrenus when manifests couldn't be fetched directly. The oureveryday path now uses this exact order: (1) encrypted site (`st-gmrc.kur0.deno.dev`) → Steam CDN, (2) Tor onion link → Steam CDN (if Tor Expert Bundle is running on port 9050/9150), (3) ManifestHub API (always up-to-date, needs API key in Settings), (4) ManifestHub GitHub direct (free, no key, may be a few weeks old), (5) interactive CDN prompt as absolute last resort. Morrenus is now only used when you explicitly chose the Morrenus option.

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
