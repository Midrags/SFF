# Changelog

## v4.8.0 (latest)

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
- **Fixed standalone EXE — tools not found (Steamless / SteamAutoCrack):** `root_folder()` now correctly returns `sys._MEIPASS` when frozen so all bundled tools (`third_party/`) are found inside the EXE instead of looking beside it where they don't exist.
- **Fixed standalone EXE — user-writable paths:** `credentials.json`, `all_games.txt`, and `dlc_unlocker_cache` now use `outside_internal=True` so they are created beside the EXE (writable) instead of in the read-only MEIPASS temp folder.
- **Fixed "Error: lost sys.stdin" on Steam restart:** All `input()` calls in the Steam restart flow are now guarded with `if sys.stdin:` so the windowed EXE never crashes when stdin is unavailable.

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
