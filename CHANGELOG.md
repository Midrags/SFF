# Changelog

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
