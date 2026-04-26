# SteaMidra

*Made by Midrag and his brother!*
=======
# If you use the normal mode patch of GL then you do not have to downgrade steam!!!

Steam has updated and if you accidentally update your Steam client to a version after **10/03/2026** then normal GreenLuma (none patched version) won't work! Use this command to revert your Steam version or just use the patch:

"C:\Program Files (x86)\Steam\steam.exe" -forcesteamupdate -forcepackagedownload -overridepackageurl http://web.archive.org/web/20260122074724if_/media.steampowered.com/client -exitsteam

## Educational use only. Use at your own risk.

> ⚠️ **Remember:** Exclude the SteaMidra folder from Windows Security — especially `sff\dlc_unlockers\resources` — or CreamInstaller resources may not work correctly.

SteaMidra helps you set up games to work with Steam using Lua scripts, manifests, and GreenLuma. It writes the right files into your Steam folder so games and DLC can run. It does not replace or crack Steam itself.

Need help? Chat with us on our Discord server: https://discord.gg/V8aZqnbB84

**Small video about SteaMidra:** [YouTube Tutorial](https://youtu.be/cFfItiV8-pk)

---

## Features

- Download and use Lua files for games, download manifests, and set up GreenLuma.
- Write Lua and manifest data into Steam's config so games work with or without an extra injector.
- Multiplayer fixes: **CreamAPI Multiplayer Fix** (bundled, no account needed — spoofs AppID to Spacewar 480) and **online-fix.me** integration. Also **game fixes/bypasses (Ryuu)**.
- DLC status check, cracking (gbe_fork), SteamStub DRM removal (Steamless), AppList management, and DLC Unlockers (CreamInstaller-style: SmokeAPI, CreamAPI, Koaloader, Uplay).
- **Multi-language GUI** — English and Portuguese built-in; add more via `sff/locales/`.
- Parallel downloads, backups, recent files, and settings export/import.
- **Linux support** — SLSSteam ID management, platform-aware MIDI, and Linux-compatible auto-update.
- **Direct game download** — Store tab downloads game files via DepotDownloaderMod, writes the ACF with the correct build ID and latest manifest IDs so Steam shows Play immediately after install.
- **Fast SteamDB manifest history** — 3-layer CF bypass (curl_cffi → cached cookie → SeleniumBase). Warm runs ~10-35s. Full DLC depot history included.

---

## Quick start

### Step 1: SteaMidra

Download the latest version from [here](https://github.com/Midrags/SFF/releases/latest).
Create a folder anywhere, name it `SteaMidra`, and place `SteaMidra_GUI.exe` and `SteamKillInject.exe` inside it.

### Step 2: GreenLuma

Join our [Discord server](https://discord.gg/V8aZqnbB84) to get the latest GreenLuma, or use this direct link: https://www.up-4ever.net/lyoi96gger8y

Extract the ZIP — you will see three folders. You only need `NormalModePatch.rar`.
Extract `NormalModePatch.rar` and place all files from it into your `SteaMidra\Greenluma` folder or inside `steam directory`.
Create AppList folder where GreenLuma file are located.

### Step 3: Setup GreenLuma

Go into the GreenLuma folder and run `GreenLumaSettings2025.exe`.
Type `2` in the terminal and press Enter, then set the full path to `steam.exe` (default: `C:\Program Files (x86)\Steam\steam.exe`) and `GreenLuma_2025_x64.dll` (default: `SteaMidra\Greenluma\GreenLuma_2025_x64.dll`).

> Running from source (Python)? See the [Python Setup Guide](docs/PYTHON_SETUP.md).

---

### AppList profiles (GreenLuma limit workaround)

GreenLuma has a hard limit of 130–134 App IDs. To use more games, use AppList profiles:

1. **Manage AppList IDs** → **AppList Profiles** (CLI) or the profiles option in the GUI
2. **Create profile** – creates an empty profile. Switch to it before adding more games.
3. **Switch to profile** – loads that profile's IDs into the AppList folder (truncated to the limit).
4. **Save current AppList to profile** – saves your current IDs into a profile (new or existing).
5. **Delete / Rename** – manage profile names and remove unused profiles.

When you reach 130 IDs, SteaMidra will remind you to create a new profile. Create an empty profile, switch to it, then add more games.

---

## GUI features

SteaMidra has a full graphical interface.

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

---

## What's new

See [CHANGELOG.md](CHANGELOG.md) for what changed in the latest update.

---

## Documentation

[Documentation index](docs/README.md) – Start here.

[Setup Guide](docs/SETUP_GUIDE.md) – What to install (including GreenLuma).

[User Guide](docs/USER_GUIDE.md) – What each menu option does and how to add games.

[Quick Reference](docs/QUICK_REFERENCE.md) – Commands and shortcuts.

[Feature Guide](docs/FEATURE_USAGE_GUIDE.md) – Parallel downloads, backups, library scanner, and more.

[Multiplayer Fix](docs/MULTIPLAYER_FIX.md) – Using the online-fix.me multiplayer fix.

[Fixes/Bypasses (Ryuu)](docs/RYUU_FIX.md) – Using Ryuu as a free, no-account alternative fix source.

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

**aria2** – Used internally for fast file downloads. License in `third_party_licenses/aria2.LICENSE`.

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
