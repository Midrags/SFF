# ⚠️ Important Update!

# If you use the normal mode patch of GL then you do not have to downgrade steam!!!

Steam has updated and if you accidentally update your Steam client to a version after **10/03/2026** then GreenLuma won't work! Use this command to revert your Steam version:

```
"C:\Program Files (x86)\Steam\steam.exe" -forcesteamupdate -forcepackagedownload -overridepackageurl http://web.archive.org/web/20260122074724if_/media.steampowered.com/client -exitsteam
```

Just so people know online-fix has updated their site and it is very annoying when they do that, since multiplayer fix is not working no more as it did before. Use Bypass/fix option instead it should have all the needed files etc for multiplayer and fixes for games.

---

# SteaMidra (Education purposes only)

"Made" by Midrag and his brother!

Quick thing before we start remember to exclude the SteaMidra folder from Windows Security or at least the folder in this path for Creaminstaller Resources to work! `sff\dlc_unlockers\resources`

SteaMidra helps you set up games to work with Steam using Lua scripts, manifests, and GreenLuma. It writes the right files into your Steam folder so games and DLC can run. It does not replace or crack Steam itself.

**Need help?** Check the [documentation](docs/README.md) or reach out to me Merium0 on the Discord and we'll sort it out. Discord server: https://discord.gg/yp3UA6QdBC

**Small video about SteaMidra:** [Youtube Tutorial](https://youtu.be/cFfItiV8-pk)


## I'm too lazy to edit the readme.md file not, but just so people know the release got exe file now so there is no need to do all these steps under, unless you want too though.


## Quick start

### Step 1: Install dependencies

**Two commands are required** (steam has a stale `urllib3<2` constraint that conflicts with Selenium; `--no-deps` bypasses it — steam works fine at runtime with urllib3 2.x):

```batch
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps

Also run the install_online_fix_requirements.bat
```

If you get dependency conflicts with other projects on your system, use a virtual environment:

```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps

Also run the install_online_fix_requirements.bat
```

### Step 2: Run SteaMidra

**With Python:**
- CLI: `python Main.py`
- GUI: `python Main_gui.py`

**With the EXE:**
- CLI: Run `build_simple.bat`, then run `SteaMidra.exe` (administrator preferred).
- GUI: Run both install commands from Step 1, then `build_simple_gui.bat`, then run `SteaMidra_GUI.exe`.

### Step 3: GreenLuma

Download GreenLuma and set it up: https://www.up-4ever.net/lyoi96gger8y

Extract the ZIP and use the AppList folder from GreenLuma when SteaMidra asks for it. Full steps are in the [Setup Guide](docs/SETUP_GUIDE.md).

**Optional:** Windows desktop notifications: `pip install -r requirements-optional.txt`

## GUI Version

SteaMidra has a full graphical interface.

**Run with Python:** `python Main_gui.py`

**Build the GUI EXE:**
1. Install dependencies (two commands — both required):
   ```batch
   pip install -r requirements.txt
   pip install steam==1.4.4 --no-deps
   ```
2. Run `build_simple_gui.bat`
3. Run `dist\SteaMidra_GUI.exe`

**What the GUI gives you:**  
- **Tabbed interface** — Main, Store, Downloads, Fix Game, Tools, and Cloud Saves tabs.  
- Pick your game from a dropdown (all Steam libraries scanned) or set a path for games outside Steam.  
- All actions as buttons: crack, DRM removal, DLC check, workshop items, multiplayer fix, **Fixes/Bypasses (Ryuu)**, DLC unlockers, and more.  
- **Store browser** — search and browse the Hubcap Manifest library with pagination.  
- **Fix Game pipeline** — automate emulator application (Goldberg, ColdClient, ColdLoader) with SteamStub unpacking.  
- **GBE Token Generator** — generate full Goldberg emulator configs with achievements, DLCs, stats, and icons.  
- **Cloud Saves** — Steam userdata save backup/restore. Scans `Steam/userdata/<steam32id>/` for all games with saves, lets you back up the `remote/` folder to any destination, and restore it back with one click (automatic safety backup before overwrite).  
- **VDF Key Extractor** — extract depot decryption keys from Steam's config.vdf.  
- Lua/manifest processing, AppList management, and library tools all accessible from buttons.  
- Full settings dialog where you can edit, delete, export, and import all settings.  
- **11+ themes** including Dracula, Nord, Cyberpunk, and more.  
- **System tray icon** for quick show/hide and exit.  
- **Multi-language support** — switch between English and Portuguese in Settings (more locales can be added).  
- Log output shown in the window so you can see what's happening.  
- Any prompts that would normally appear in the terminal show up as dialog boxes instead.

The CLI version (`Main.py` / `SteaMidra.exe`) still works exactly the same as before.

## What SteaMidra can do

- Download and use Lua files for games, download manifests, and set up GreenLuma.  
- Write Lua and manifest data into Steam's config so games work with or without an extra injector.  
- Other features: multiplayer fixes (online-fix.me), **game fixes/bypasses (Ryuu)**, DLC status check, cracking (gbe_fork), SteamStub DRM removal (Steamless), AppList management, and DLC Unlockers (CreamInstaller-style: SmokeAPI, CreamAPI, Koaloader, Uplay).  
- **Multi-language GUI** — English and Portuguese built-in; add more via `sff/locales/`.
- Parallel downloads, backups, recent files, and settings export/import.

### AppList profiles (GreenLuma limit workaround)

GreenLuma has a hard limit of 130–134 App IDs. To use more games, use AppList profiles:

1. **Manage AppList IDs** → **AppList Profiles** (CLI) or the profiles option in the GUI
2. **Create profile** – creates an empty profile. Switch to it before adding more games.
3. **Switch to profile** – loads that profile's IDs into the AppList folder (truncated to the limit).
4. **Save current AppList to profile** – saves your current IDs into a profile (new or existing).
5. **Delete / Rename** – manage profile names and remove unused profiles.

When you reach 130 IDs, SteaMidra will remind you to create a new profile. Create an empty profile, switch to it, then add more games.

## What's new

See [CHANGELOG.md](CHANGELOG.md) for what changed in the latest update.

## Documentation

[Documentation index](docs/README.md) – Start here.

[Setup Guide](docs/SETUP_GUIDE.md) – What to install (including GreenLuma).
[User Guide](docs/USER_GUIDE.md) – What each menu option does and how to add games.

[Quick Reference](docs/QUICK_REFERENCE.md) – Commands and shortcuts.

[Feature Guide](docs/FEATURE_USAGE_GUIDE.md) – Parallel downloads, backups, library scanner, and more.

[Multiplayer Fix](docs/MULTIPLAYER_FIX.md) – Using the online-fix.me multiplayer fix.

[Fixes/Bypasses (Ryuu)](docs/RYUU_FIX.md) – Using Ryuu as a free, no-account alternative fix source.

[DLC Unlockers](docs/dlc_unlockers/README.md) – Using DLC unlockers (CreamInstaller-style).

## Requirements

`requirements.txt` covers everything: CLI, GUI (PyQt6), online-fix (Selenium), and Tor fallback.

**Install with two commands:**
```batch
pip install -r requirements.txt
pip install steam==1.4.4 --no-deps
```

The second command is needed because `steam==1.4.4` has a stale `urllib3<2` constraint that conflicts with Selenium 4.x. Steam only uses `requests` at runtime and works perfectly with urllib3 2.x — `--no-deps` simply skips the outdated constraint check.

More details in [INSTALL_DEPENDENCIES.md](INSTALL_DEPENDENCIES.md).

## Troubleshooting

**Steam says "No Internet Connection" when downloading** — SteaMidra handles this automatically.

1. **Workshop ACF fix** — The most common cause is orphaned workshop items in `appworkshop_{id}.acf` triggering a failed Workshop update. SteaMidra patches this file to clear `NeedsDownload` when no workshop content is installed.
2. **Manifest seeding** — When you process a .lua file or use "Update all manifests", manifests are written directly to Steam's `depotcache` folder before Steam starts. Steam finds them locally.
3. **ACF error state** — SteaMidra clears stale `UpdateResult` and validation flags in the game ACF so Steam doesn't get stuck in a retry loop.

**Dependency conflicts / urllib3 error** — Run both install commands from Step 1 above (requirements.txt first, then `pip install steam==1.4.4 --no-deps`). If conflicts persist with other projects on your system, use a virtual environment.

**ModuleNotFoundError** — Dependencies are not installed. Run `pip install -r requirements.txt`.

**Remove SteamStub (Steamless) → WinError 2** — In the GUI, clicking "Remove SteamStub" now opens a file picker. Just navigate to your game folder and select the `.exe` yourself — no Steam API lookup needed.

**SteamAutoCrack not found** — Make sure the SteaMidra folder is intact and hasn't had any files deleted. SteamAutoCrack is bundled in `third_party/SteamAutoCrack/cli/` and should already be there.


## Credits

**Made by Midrag and his brother.**

**GreenLuma** – SteaMidra works alongside GreenLuma for AppList injection. GreenLuma is a separate tool and must be downloaded and set up independently. GreenLuma patch developed by **Lightse**.

**gbe_fork** – The "Crack a game" feature uses **gbe_fork**, a Steam emulator for running games offline. License in `third_party_licenses/gbe_fork.LICENSE`.

**gbe_fork tools** – Build and packaging tools for gbe_fork. License in `third_party_licenses/gbe_fork_tools.LICENSE`.

**Steamless** – The "Remove SteamStub DRM" feature uses **Steamless** by Atom0s for stripping Steam DRM from executables. License in `third_party_licenses/steamless.LICENSE`.

**aria2** – Used internally for fast file downloads. License in `third_party_licenses/aria2.LICENSE`.

**fzf** – Used for fuzzy search in menus (CLI). License in `third_party_licenses/fzf.LICENSE`.

**SteamAutoCrack** – The SteamAutoCrack feature uses the **SteamAutoCrack CLI** by oureveryday. Bundled in `third_party/SteamAutoCrack/cli/`. License in `third_party_licenses/SteamAutoCrack.LICENSE`.

**CreamInstaller** – The DLC Unlockers feature is inspired by and compatible with CreamInstaller. SteaMidra does not ship CreamInstaller; it provides its own implementation that follows similar behavior.

**online-fix.me** – The multiplayer fix feature downloads fixes from online-fix.me. SteaMidra is not affiliated with online-fix.me. An account on that site is required.

**GBE Token Generator** – Goldberg Emulator configuration generation based on work by **Detanup01** ([gbe_fork](https://github.com/Detanup01/gbe_fork)), **NickAntaris**, and **Oureveryday** ([generate_game_info](https://github.com/oureveryday/Goldberg-generate_game_info)).

**Hubcap Manifest** – Store browser and manifest library API provided by **Hubcap Manifest** ([hubcapmanifest.com](https://hubcapmanifest.com)). Formerly known as Morrenus / Solus.

**RedPaper** – Credit to RedPaper for the Broken Moon MIDI cover, originally arranged by U2 Akiyama and used in Touhou 7.5: Immaterial and Missing Power. Touhou 7.5 and its assets are owned by Team Shanghai Alice and Twilight Frontier. SteaMidra is not affiliated with or endorsed by either party. All trademarks belong to their respective owners.

SteaMidra is licensed under the GNU General Public License v3.0 (see LICENSE file).

Use at your own risk. For educational purposes only.
