# SteaMidra User Guide

## Modern UI (new in 5.5.0, updated in 6.0.0)

SteaMidra 5.5.0 introduced a new browser-based interface built with QWebEngine. It launches by default alongside the classic interface. Navigate using the sidebar on the left.

### Tabs

**Home** — pick a game from the dropdown (scanned from all Steam libraries). Click ↻ to rescan manually. The list refreshes automatically after any download and every 10 minutes.

**Store** — search or browse the Hubcap manifest library. Switch between grid and list view, sort results, and page through them. Click a game to open the version picker with full depot/manifest history, then download directly.

**Library** — shows all games installed across your Steam libraries.

**Downloads** — live progress for active downloads and a history of completed ones.

**Fix Game** — select an installed game (or browse manually), pick an emulator mode (Goldberg, ColdClient, ColdLoader), and apply the full fix pipeline. Optionally remove SteamStub DRM and generate launch scripts.

**Tools**
- *GBE Token Generator* — enter an App ID and your Steam Web API key, pick an output folder, and generate a complete Goldberg config package (achievements, stats, DLCs, depots, icons).
- *VDF Key Extractor* — extract depot decryption keys from Steam's `config.vdf`.
- *Workshop Browser* — open the embedded Steam Workshop browser to find and download workshop items.

**Cloud Saves** — enter your Steam path and Steam32 ID, then scan. Select a game from the results to back up its `remote/` folder to a destination of your choice, or restore from a previous backup (a safety backup is created automatically before any overwrite).

Providers:

- **Local folder** — pick any folder on your machine or network drive.
- **Google Drive** — select Google Drive in the provider grid and click Connect. Sign in once in the browser that opens. Backups go to a `SteaMidra Backups/` folder in your Drive.
- **rclone** — supports 70+ cloud backends including Dropbox, OneDrive, MEGA, pCloud, Backblaze B2, Amazon S3, SFTP, and more. Setup flow:
  1. Select rclone in the provider grid. SteaMidra auto-fills the bundled `rclone.exe` path.
  2. Click a provider chip (Dropbox, OneDrive, MEGA, etc.) to pre-fill the remote destination format.
  3. Click **Setup in Terminal** — a terminal window opens running `rclone config`. Follow the prompts to name and authenticate your remote (takes about 2 minutes).
  4. Click **Load Remotes** to pull your configured remotes into autocomplete.
  5. Select your remote from the dropdown or type it in, then click **Test** to confirm it works.
  6. Click **Save Provider Config**, then back up normally.

**All Save Locations** (at the bottom of the tab): click Scan All to find saves across all known emu save paths — CODEX, EMPRESS, RUNE, OnlineFix, Goldberg, GSE, and Steam userdata. Check the rows you want, pick a destination, and click Backup. To restore, scan an existing backup root and pick a location and game from the dropdowns.

**Settings** — change theme (11+ options), Steam path, API keys, AppList profiles, and all other preferences. Settings apply immediately. Language changes take effect without restarting the app.

---

## Menu options

### Process a .lua file
The main way to add a game. Goes through these steps:

**1. Input**
- Add a .lua file — manually pick a .lua file you have
- Choose from saved .lua files — every file you process gets saved, find it here (useful for updates)
- Automatically download a .lua file — download one from oureveryday or Hubcap Manifest

**2. GreenLuma achievement tracking**
"Would you like GreenLuma (normal mode) to track achievements?"
GreenLuma can store achievements in the registry. They can be viewed with Achievement Watcher (use darktakayanagi's fork for GL2025 support).

**3. Adding AppList IDs**
IDs from the .lua file are added to the AppList folder.

**4. DLC Check**
Runs the DLC check automatically (see Check DLC section below).

**5. Config VDF writing**
Decryption keys from each depot are written into Steam's config.vdf.

**6. Lua backup**
The .lua file is saved to the `saved_lua` folder.

**7. ACF writing**
Creates or overwrites the .acf file for the game. ACF files tell Steam the state of a game installation. If SteaMidra asks "Are you updating a game you already have installed or is this a new installation?", choose "I'm updating a game" to skip rewriting it, or "New installation" to overwrite it.

**8. Manifest downloading**
Manifests are downloaded and moved to Steam's depotcache folder.

### Store tab — Download game directly

The Store tab lets you pick a specific game version (depot + manifest combination) and download the full game files automatically via DepotDownloaderMod. This is separate from the main tab GreenLuma flow.

**How it works:**

**1. Version selection**
Browse the Store tab, find the game, and pick the version you want. SteaMidra fetches the available depot/manifest combinations from the source.

**2. Lua download**
SteaMidra automatically downloads the Lua file for the selected game (from Hubcap or OurEveryday, depending on your selection).

**3. Setup**
Decryption keys are added to Steam's config.vdf. AppList / SLSSteam IDs are registered. The Lua is saved to `saved_lua`.

**4. Manifest pre-download**
Manifest files are downloaded using your selected manifest IDs. These are required by DepotDownloaderMod for authentication (`GetManifestRequestCode` verification).

**5. Game file download**
DepotDownloaderMod downloads the full game files to your selected Steam library. This requires .NET 9 runtime.

**6. Cleanup**
The temporary manifest files used for authentication are deleted from `depotcache`. Your depotcache stays clean.

**7. ACF writing**
SteaMidra writes the ACF file with:
- The **latest manifest GIDs** from the Steam API — so Steam recognises the game as fully installed
- The **correct `buildid`** from the Steam API — matching what Steam expects
- The real `SizeOnDisk` from the downloaded files

After this, Steam shows a **Play** button immediately — no update prompt.

> **Note:** The actual game files are downloaded using the manifest IDs you selected. The ACF is written with the latest CDN manifest IDs so Steam's update checker is satisfied.

### Process a .lua file (Manifest downloads only)
Like the main option but skips AppList, config.vdf, and ACF steps — only does the .lua input, backup, and manifest downloads. Has an extra prompt asking if you want to move the manifest files to a different folder. Hidden by default; enable Advanced Mode in Settings to see it.

### Process recent .lua file
Opens a list of the last .lua files you processed so you can run one again quickly without browsing for the file.

### Update manifests for all outdated games
Scans your Steam library for games that have outdated manifests and updates them in one go.

### Scan game library
Scans all your Steam libraries and lists your installed games. Shows which ones have Lua backups saved and which might need manifest updates.

### Download workshop item manifest
Paste a Steam Workshop URL or item/collection ID to download its manifest. Supports both single items and full collections.

### Check for mod updates
Tracks workshop items you have and checks if newer versions are available. You can update outdated mods from here.

### Check DLC status of a game
Shows all DLC for a game and whether each one is available to you. There are two types:
- **DOWNLOAD REQUIRED** — has a depot, you need a .lua file that contains keys for that DLC
- **PRE-INSTALLED** — no depot needed, just add the DLC ID to your AppList folder (SteaMidra can do this for you)

### DLC Unlockers (CreamInstaller)
Install DLC unlockers for Steam or Ubisoft games. For Steam games you can use SmokeAPI or CreamAPI (with optional Koaloader). For Ubisoft games, older and newer Ubisoft Connect unlockers are supported. The menu will guide you through choosing the game and which DLC to unlock.

### Crack a game (gbe_fork)
Uses gbe_fork to disconnect a game from Steam so it can run offline/independently. gbe_fork can also track achievements locally and has its own in-game overlay.

### Remove SteamStub DRM (Steamless)
Some games have SteamStub DRM that causes them to fail when launched without Steam's DRM validation. Run this to strip it using Steamless.

### Download UserGameStatsSchema
Downloads the achievements schema for a game. Uncracked games can use Steam's own achievement system when running in Offline Mode. Use this to create the files needed for that.

### Apply multiplayer fix (online-fix.me)
Logs into online-fix.me, finds the fix for your game, downloads it, and extracts it into the game folder. You need an account on online-fix.me. SteaMidra stores your credentials securely after the first use. See [Multiplayer Fix](MULTIPLAYER_FIX.md) for more detail.


### Fixes & Bypasses
Searches a curated fix list for a fix or bypass for your game. No account needed — SteaMidra fetches the list, lets you search with fuzzy matching, downloads the fix, and extracts it straight into the game folder. This is a second source of fixes that often covers games not found on online-fix.me. See [Fixes & Bypasses](CRACK_FIX.md) for more detail.

### Offline Mode Fix
GreenLuma has a bug where Steam gets stuck if launched in Offline Mode. This toggles the Offline Mode flag in Steam's loginusers.vdf for the selected user so you can get back to Online Mode.

### Manage AppList IDs
View and delete IDs that have been added to your AppList folder. Also lets you manage AppList profiles if you need to work around GreenLuma's 184 ID limit (see README for how profiles work).

### Remove a game from library (stplug-in)
Removes a game's Lua from the stplug-in folder and cleans up its AppList entry. Choose from a list of games or type an App ID. Restart Steam afterward for changes to take effect.

### View analytics dashboard
Shows local usage stats — how many operations you ran, which features you used most, and success rates. Nothing is sent online; it's all stored locally.

### Check for updates
Checks GitHub for the latest SteaMidra release and compares it to your version. If a newer version is available you can download and update automatically (source installs will relaunch; EXE users need to rebuild).

### Install/Uninstall Context Menu
Adds or removes a right-click option on .lua and .zip files in Windows Explorer that opens SteaMidra directly into the "Process a .lua file" step with that file already loaded.

### SteamAutoCrack
Runs the SteamAutoCrack CLI on a game. Choose a Steam game from your library or point to any game folder outside Steam. Requires the SteamAutoCrack repo placed in `third_party/SteamAutoCrack` with the CLI built into `third_party/SteamAutoCrack/cli/`.

### Settings
Edit, export, or import SteaMidra settings. Settings are usually set automatically as you use the tool, but you can change Steam path, GreenLuma folder, API keys, credentials, and feature toggles here. Export saves your config to a JSON file; import loads it back.

---

## GUI Tabs (v4.8.0+)

The GUI uses a tabbed interface. All CLI features are on the **Main** tab. The other tabs are:

### Store Tab
Search and browse the Hubcap manifest library. Enter your API key in Settings first. Search by game name or App ID, paginate through results, and pick a version to download.

### Downloads Tab
View and manage active and queued downloads. When you use "Download Games" on the Main tab, downloads appear here with progress tracking.

### Fix Game Tab
Automate the emulator application pipeline. Choose an emulator mode (Regular Goldberg, ColdClient Loader, or ColdLoader DLL), toggle SteamStub auto-unpack, and configure generation options. Select a game and click Fix to apply. Achievements, stats, DLC, and language configs are automatically generated using the Steam Web API key from Settings (no input required).

### Tools Tab
- **GBE Token Generator** — Generate full Goldberg emulator configs (achievements, DLCs, stats, icons) for a game. The Steam Web API key is auto-filled from Settings on startup. If you haven’t set a key, the built-in default key is used automatically.
- **VDF Depot Key Extractor** — Extract decryption keys from Steam's config.vdf and display them in a table.

### Cloud Saves Tab
Two modes:
- **STFixer Mode** — Patches broken save behavior in Capcom games (based on STFixer by Selectively11). Enable Cloud Fix and Hubcap Fallback.
- **Backup/Restore Mode** — Create, list, restore, and delete save backups per game.

---

## File locations

| File | Purpose |
|---|---|
| `settings.bin` | All SteaMidra settings (encrypted where needed) |
| `saved_lua/` | Backup of every .lua file you have processed |
| `debug.log` | Detailed log of the last run |
| `recent_files.json` | List of recently processed .lua files |
| `Steam/config/config.vdf` | Where decryption keys are written |
| `Steam/steamapps/depotcache/` | Where manifests are placed |
| `Steam/steamapps/appmanifest_*.acf` | Game state file written by the ACF step |

---

## Tips

- **Use full game names** when searching online-fix.me (e.g. "Counter-Strike: Global Offensive" not "CS:GO").
- **Fixes & Bypasses** — if a game isn't found on online-fix.me, try the **Fixes & Bypasses** option. It has a broader fix list and no account required.
- **Language** — change the GUI display language in Settings → Language.
- **Credentials** for online-fix.me are stored encrypted after the first use. Update them in Settings if they change.
- **If Steam path is wrong**, go to Settings → Steam Installation Path and set it manually to the folder containing steam.exe.
- **Antivirus** may flag files downloaded by SteaMidra (false positives are common with game-related tools). Exclude the SteaMidra folder and `sff\dlc_unlockers\resources` from Windows Security if needed.
- **Run as administrator** if you get permission errors.
- For more detail on specific features, see the [Feature Guide](FEATURE_USAGE_GUIDE.md). For problems, see [Troubleshooting](TROUBLESHOOTING.md).
