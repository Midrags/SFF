# SteaMidra Trusted by r/FMHY [FMHY](https://fmhy.net/gaming-tools#steam-epic) and r/Piracy [Piracy](https://www.reddit.com/r/Piracy/wiki/megathread/games/#:~:text=SteaMidra)

*Made by Midrag and his brother!*
=======
# If you use the normal mode patch of GL then you do not have to downgrade steam!!!

Steam has updated and if you accidentally update your Steam client to a version after **10/03/2026** then normal GreenLuma (none patched version) won't work! Use this command to revert your Steam version or just use the patch:

"C:\Program Files (x86)\Steam\steam.exe" -forcesteamupdate -forcepackagedownload -overridepackageurl http://web.archive.org/web/20260122074724if_/media.steampowered.com/client -exitsteam

## Educational use only. Use at your own risk.

> ⚠️ **Antivirus Warning:** Before doing anything, add the entire **SteaMidra folder** (especially `sff\dlc_unlockers\resources`) to Windows Defender exclusions — the DLC unlocker tools inside trigger false positives.
>
> To add exclusions: **Windows Security → Virus & threat protection → Manage settings → Exclusions → Add or remove exclusions → Add a folder**.

SteaMidra helps you set up games to work with Steam using Lua scripts, manifests, and GreenLuma. It writes the right files into your Steam folder so games and DLC can run. It does not replace or crack Steam itself.

Need help? Chat with us on our Discord server: https://discord.gg/V8aZqnbB84

**Latest SteaMidra setup tutorial:** ["Normal" tutorial for new users](https://youtu.be/9aAaQ8dSnTY)

**Python setup tutorial:** [Python Tutorial](https://youtu.be/cFfItiV8-pk)

---

## Features

- Download and use Lua files for games, download manifests, and set up GreenLuma.
- Write Lua and manifest data into Steam's config.
- Multiplayer fixes: **online-fix.me** integration and **game fixes/bypasses (Ryuu)**.
- **HyperVisor Cracks (HV Auto)** — download HyperVisor bypasses for Denuvo-protected games. Includes VBS.cmd (v1.6.2) to prepare your system. See the [HyperVisor Guide](docs/HV_GUIDE.md) before use.
- DLC status check, cracking (gbe_fork), SteamStub DRM removal (Steamless), AppList management, and DLC Unlockers (CreamInstaller-style: SmokeAPI, CreamAPI, Koaloader, Uplay).
- **Multi-language GUI** — English and Portuguese built-in; add more via `sff/locales/`.
- Parallel downloads, backups, recent files, and settings export/import.
- **Linux support** — SLSSteam ID management, platform-aware MIDI, and Linux-compatible auto-update.
- **Main tab "Download Game"** — ⭐ **THIS IS THE MAIN WAY TO DOWNLOAD GAMES.** Downloads the **latest version** of a game directly from Steam (fast, no .NET required for Windows OS). Processes the Lua file, writes decryption keys, registers AppList/SLSsteam IDs, and triggers Steam to download the game files natively. Use this for 99% of games.
- **Store tab** — browse Hubcap's manifest library to find games and download either using the Steam download function for downloading latest versions very quick or **older or specific versions** of a game via DepotDownloaderMod (.NET 9 required, slower). Use this **only** when you need a specific older version of a game, not the latest.

---

## Quick start

### Step 1: SteaMidra

Download the latest version from [here](https://github.com/Midrags/SFF/releases/latest).
You will get a ZIP file (`SteaMidra-x.x.x-windows.zip`). Extract it anywhere — you will see a folder containing `SteaMidra_GUI.exe` and an `_internal/` folder. Place this folder wherever you want (e.g. `C:\SteaMidra\`).

**Do not run SteaMidra yet.** Complete Steps 2 and 3 first so all folders exist before first launch.

### Step 2: GreenLuma

Join our [Discord server](https://discord.gg/V8aZqnbB84) to get the latest GreenLuma, or use this direct link: [GreenLuma Link](https://buzzheavier.com/cuygee4bo1ch) [FIRST CLICK OPENS MALWARE POPUP!].

> **Tip (6.0.3+):** SteaMidra can set up GreenLuma automatically. After downloading `GLPatch.rar`, open SteaMidra, go to the **Home** tab, click **Auto GL Setup** in the Quick Tools section, browse for the archive, choose Method A or B, and click **Setup GreenLuma**. It will extract the files, patch `DLLInjector.ini`, and create the `AppList` folder for you. Skip to Step 3 if you use this.

Download `GLPatch.rar` from the link above. Or extract it manually and follow Plan A or Plan B:

**Method A — Separate folder (next to SteaMidra)**
1. Create a `Greenluma` folder next to `SteaMidra_GUI.exe` (e.g. `C:\SteaMidra\Greenluma\`).
2. Copy all files from `GLPatch.rar` into `C:\SteaMidra\Greenluma\`.
3. Create an `AppList` folder inside it: `C:\SteaMidra\Greenluma\AppList\`.

**Method B — Inside Steam folder (simpler)**
1. Copy all files from `GLPatch.rar` directly into `C:\Program Files (x86)\Steam\`.
2. Create an `AppList` folder inside Steam: `C:\Program Files (x86)\Steam\AppList\`.

### Step 3: Setup GreenLuma

**If you used Auto GL Setup (recommended):** `DLLInjector.ini` is already patched. Skip to launching SteaMidra below.

**Manual setup:** Go into whichever folder you chose in Step 2 and run `GreenLumaSettings_2025.exe`.

- Type `2` and press Enter — set the full path to `steam.exe` (default: `C:\Program Files (x86)\Steam\steam.exe`) and to `GreenLuma_2025_x64.dll` (example for Method A: `C:\SteaMidra\Greenluma\GreenLuma_2025_x64.dll`; for Method B: `C:\Program Files (x86)\Steam\GreenLuma_2025_x64.dll`).
- Type `4` and press Enter — disables GreenLuma's questions/prompts on every Steam launch.

Now run `SteaMidra_GUI.exe`. On first launch it will ask you to select your AppList folder — point it to the one you created in Step 2 (e.g. `C:\SteaMidra\Greenluma\AppList` or `C:\Program Files (x86)\Steam\AppList`). You are all set. See the [User Guide](docs/USER_GUIDE.md) for how to add games.

> Running from source (Python)? See the [Python Setup Guide](docs/PYTHON_SETUP.md).

---

### AppList profiles (GreenLuma limit workaround)

GreenLuma has a hard limit of 184 App IDs (patched). To use more games, use AppList profiles:

1. **Manage AppList IDs** → **AppList Profiles** (CLI) or the profiles option in the GUI
2. **Create profile** – creates an empty profile. Switch to it before adding more games.
3. **Switch to profile** – loads that profile's IDs into the AppList folder (truncated to the limit).
4. **Save current AppList to profile** – saves your current IDs into a profile (new or existing).
5. **Delete / Rename** – manage profile names and remove unused profiles.

When your AppList reaches 130 IDs, SteaMidra shows a popup dialog reminding you to create a new profile. Create an empty profile, switch to it, then add more games.

---

## GUI features

SteaMidra has a full graphical interface with a **Modern UI (new in 5.5.0, updated in 6.0.0)** and the classic Qt interface.

**Modern UI** — the new default interface, built with QWebEngine. Accessible from a clean sidebar with 8 tabs: Home (game picker with auto-refresh), Store (search/browse Hubcap, grid/list, pagination), Library (installed games), Downloads (live progress + history), Fix Game (full emulator pipeline), Tools (GBE Token Generator, VDF Extractor, Workshop), Cloud Saves (scan/backup/restore, Google Drive, rclone with 17 provider shortcuts, All Save Locations), and Settings. Supports 11+ themes, tooltips, and toast notifications.

**Millennium Plugin** — SteaMidra ships a [Millennium](https://steambrew.app) plugin (`PlugInFiles/`) that adds SteaMidra controls directly inside the Steam client. See [PlugInFiles/README.md](PlugInFiles/README.md) for setup.

**What the GUI gives you:**
- **Tabbed interface** — Main, Store, Downloads, Fix Game, Tools, and Cloud Saves tabs.
- Pick your game from a dropdown (all Steam libraries scanned) or set a path for games outside Steam.
- All actions as buttons: crack, DRM removal, DLC check, workshop items, multiplayer fix, **Fixes/Bypasses (Ryuu)**, DLC unlockers, and more.
- **Store browser** — search and browse the Hubcap Manifest library with pagination. Download button opens a version picker with full depot/manifest history (SteamDB + GitHub mirror sources). **Force Refresh** button bypasses cache to re-scrape all historical manifests.
- **Fix Game pipeline** — automate emulator application (Goldberg, ColdClient, ColdLoader) with SteamStub unpacking.
- **GBE Token Generator** — generate full Goldberg emulator configs with achievements, DLCs, stats, and icons.
- **Cloud Saves** — Steam userdata save backup/restore. Scans `Steam/userdata/<steam32id>/` for all games with saves, back up and restore with one click (safety backup created automatically). Supports local folder, **Google Drive** (sign in once), and **rclone** (Dropbox, OneDrive, MEGA, S3, Backblaze B2, SFTP, and 70+ other backends — click a provider shortcut to pre-fill the remote format, then hit Setup in Terminal to configure it without leaving the app). **All Save Locations** scans every known emu save path (CODEX, EMPRESS, RUNE, OnlineFix, Goldberg, GSE, Steam userdata) and backs them all up in one operation.
- **VDF Key Extractor** — extract depot decryption keys from Steam's config.vdf.
- Lua/manifest processing, AppList management, and library tools all accessible from buttons.
- Full settings dialog where you can edit, delete, export, and import all settings.
- **11+ themes** including Dracula, Nord, Cyberpunk, and more.
- **System tray icon** for quick show/hide and exit.
- **Multi-language support** — switch between English and Portuguese in Settings (more locales can be added).
- **Log viewer** — "Logs" button in the menu bar (right of Help) opens a floating window showing all log output from every tab (Fix Game, Store, Tools, and more). Filterable by level (DEBUG/INFO/WARNING/ERROR), with Clear and Copy All buttons.
- Any prompts that would normally appear in the terminal show up as dialog boxes instead.

---

## What's new in 6.1.0

- System tray icon now shows correctly on launch (was invisible due to a null icon check bug).
- Remove dialog and game cards animate out smoothly instead of snapping away.
- Horizontal scrollbar no longer appears in the library page.
- Millennium plugin released — add SteaMidra to your Steam client without leaving Steam.

Full history: [CHANGELOG.md](CHANGELOG.md)

---

## Documentation

[Documentation index](docs/README.md) – Start here.

[Setup Guide](docs/SETUP_GUIDE.md) – What to install (including GreenLuma).

[User Guide](docs/USER_GUIDE.md) – What each menu option does and how to add games.

[Quick Reference](docs/QUICK_REFERENCE.md) – Commands and shortcuts.

[Feature Guide](docs/FEATURE_USAGE_GUIDE.md) – Parallel downloads, backups, library scanner, and more.

[Multiplayer Fix](docs/MULTIPLAYER_FIX.md) – Using the online-fix.me multiplayer fix.

[Fixes/Bypasses (Ryuu)](docs/RYUU_FIX.md) – Using Ryuu as a free, no-account alternative fix source.

[HyperVisor Guide](docs/HV_GUIDE.md) – How HV cracks work, security implications, and step-by-step setup for Denuvo HyperVisor bypasses.

[DLC Unlockers](docs/dlc_unlockers/README.md) – Using DLC unlockers (CreamInstaller-style).

[Troubleshooting](docs/TROUBLESHOOTING.md) – Common problems and solutions.

[Python Setup](docs/PYTHON_SETUP.md) – Running or building from source.

---

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common problems and solutions.

---

## Credits

**Made by Midrag and his brother.**

**GreenLuma** – SteaMidra works alongside GreenLuma for AppList injection. GreenLuma is a separate tool and must be downloaded and set up independently. GreenLuma patch developed by **Lightse**.

**gbe_fork** – The "Crack a game" feature uses **gbe_fork**, a Steam emulator for running games offline. License in `third_party_licenses/gbe_fork.LICENSE`.

**gbe_fork tools** – Build and packaging tools for gbe_fork. License in `third_party_licenses/gbe_fork_tools.LICENSE`.

**Steamless** – The "Remove SteamStub DRM" feature uses **Steamless** by Atom0s for stripping Steam DRM from executables. License in `third_party_licenses/steamless.LICENSE`.

**fzf** – Used for fuzzy search in menus (CLI). License in `third_party_licenses/fzf.LICENSE`.

**SteamAutoCrack** – The SteamAutoCrack feature uses the **SteamAutoCrack CLI** by oureveryday. Bundled in `third_party/SteamAutoCrack/cli/`. License in `third_party_licenses/SteamAutoCrack.LICENSE`.

**CreamInstaller** – The DLC Unlockers feature is inspired by and compatible with CreamInstaller. SteaMidra does not ship CreamInstaller; it provides its own implementation that follows similar behavior.

**online-fix.me** – The multiplayer fix feature downloads fixes from online-fix.me. SteaMidra is not affiliated with online-fix.me. An account on that site is required.

**GBE Token Generator** – Goldberg Emulator configuration generation based on work by **Detanup01** ([gbe_fork](https://github.com/Detanup01/gbe_fork)), **NickAntaris**, and **Oureveryday** ([generate_game_info](https://github.com/oureveryday/Goldberg-generate_game_info)).

**Hubcap Manifest** – Store browser and manifest library API provided by **Hubcap Manifest** ([hubcapmanifest.com](https://hubcapmanifest.com)). Formerly known as Morrenus / Solus.

**RedPaper** – Credit to RedPaper for the Broken Moon MIDI cover, originally arranged by U2 Akiyama and used in Touhou 7.5: Immaterial and Missing Power. Touhou 7.5 and its assets are owned by Team Shanghai Alice and Twilight Frontier. SteaMidra is not affiliated with or endorsed by either party. All trademarks belong to their respective owners.

README rewrite assisted by **itsphox**.

SteaMidra is licensed under the GNU General Public License v3.0 (see LICENSE file).

Use at your own risk. For educational purposes only.
