# Changelog

## v4.6.0 (latest)

### GUI version

- **Full graphical interface added.** Run `python Main_gui.py` or build `SFF_GUI.exe` using `build_simple_gui.bat`. Everything you can do in the CLI is now available through buttons, menus, and dialogs.
- **Game selection:** Pick any installed Steam game from a dropdown (all Steam libraries are scanned), or switch to "Games outside of Steam" and set a folder path, game name, and App ID manually.
- **All actions as buttons:** Game actions (crack, DRM removal, DLC check, workshop items, multiplayer fix, DLC unlockers), Lua/manifest processing (process .lua, manifests only, recent files, update all), and library/Steam tools (AppList management, Steam patching, sync LUAs, offline fix, context menu, remove game).
- **Settings dialog:** Edit, delete, export, and import all settings from a single window. Every setting type is handled (booleans, paths, passwords, enums, etc.).
- **Themes:** Light theme (black text) and dark theme (white text). Switch from the Theme menu.
- **Log output:** All action output is shown in the log panel with ANSI color codes stripped. Clear the log anytime.
- **Prompt bridge:** Any interactive prompt that would normally require a terminal (select, confirm, text input, file/folder picker) automatically shows up as a Qt dialog instead. This means every feature works in the GUI without changes to the underlying code.
- **Build script:** `build_simple_gui.bat` and `build_sff_gui.spec` produce `SFF_GUI.exe` (windowed, no console).
- **CLI unchanged:** `Main.py` and `SFF.exe` work exactly the same as before. The GUI is a separate entry point.

---

## v4.5.5

### Multiplayer fix (online-fix.me) – Selenium login fix

- **Login now works:** The multiplayer fix no longer uses HTTP-only login, which often failed with "Login failed (form still visible)". It now uses **Selenium with Chrome** (same approach as MainMango): a headless browser opens the game page, fills in your credentials, clicks the login button, and handles cookies and JavaScript like a real browser. Login and download should work reliably.
- **What you need:** Chrome browser must be installed. Install Selenium with: `pip install -r requirements-online-fix.txt` or `pip install selenium`.
- Search, match, download button, and archive extraction flow are unchanged; only the login step is now browser-based.

---

## v4.5.4

### Check for updates – automatic install

- **Automatic update:** When a newer version is available, you can choose "Download and update automatically?". SFF downloads the release zip, extracts it, and replaces the files in your install folder. When running from **source** (Python), the app restarts with the new version. When running from the **EXE**, SFF does not relaunch the EXE; it tells you to rebuild the EXE so the new updates take effect.
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
- If Steam still fails after retries, SFF automatically falls back to the **Steam Store** (no login): it fetches the DLC list and names from the store website and still shows which DLCs are in your AppList/config and lets you add missing ones.
- So the DLC check works even when the Steam client connection is flaky.

### Other fixes

- **credentials.json** is now in `.gitignore` so it never gets committed or included in release zips.
- **UPLOAD_AND_PRIVACY.md** updated with release-zip instructions and what to exclude.

---

## v4.5.1

### Fix for crash on startup (`_listeners` error)

**What was the problem?**

Some people got a crash when starting SFF. The error said something like:  
`'SteamClient' object has no attribute '_listeners'. Did you mean: 'listeners'?`

That happened because the wrong Python package named "eventemitter" was installed. SFF needs a specific one called **gevent-eventemitter**. There is another package with a similar name that does not work with SFF and caused the crash.

**What we changed**

- We now tell the installer to use the correct **gevent-eventemitter** package so new installs should not hit this crash.
- If you already had the crash, do this once:
  1. Open a command line in the SFF folder.
  2. Run: `pip uninstall eventemitter`
  3. Run: `pip install "steam[client]"`
  4. Run: `pip install -r requirements.txt`
  5. Start SFF again.

After that, SFF should start normally.
