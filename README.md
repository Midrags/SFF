# SteaMidra (Education purposes only)

Made by Midrag and my brother!

Quick thing before we start remember to exclude the SteaMidra folder from Windows Security or at least the folder in this path for Creaminstaller Resources to work! `sff\dlc_unlockers\resources`

SteaMidra helps you set up games to work with Steam using Lua scripts, manifests, and GreenLuma. It writes the right files into your Steam folder so games and DLC can run. It does not replace or crack Steam itself.

**Need help?** Check the [documentation](docs/README.md) or reach out to me Merium0 on the discord and we'll sort it out.

## Quick start

### Step 1: Install dependencies

```batch
pip install -r requirements.txt
```

If that fails with a grpcio-tools build error (common on Windows), use:

```batch
pip install -r requirements-consumer.txt
```

If you get dependency conflicts with other projects on your system, use a virtual environment:

```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements-consumer.txt
pip install -r requirements-gui.txt
```

### Step 2: Run SteaMidra

**With Python:**
- CLI: `python Main.py`
- GUI: `python Main_gui.py`

**With the EXE:**
- CLI: Run `build_simple.bat`, then run `SteaMidra.exe` (administrator preferred).
- GUI: Run `pip install -r requirements-gui.txt`, then `build_simple_gui.bat`, then run `SteaMidra_GUI.exe`.

### Step 3: GreenLuma

Download GreenLuma and set it up: https://www.up-4ever.net/h3vt78x7jdap

Extract the ZIP and use the AppList folder from GreenLuma when SteaMidra asks for it. Full steps are in the [Setup Guide](docs/SETUP_GUIDE.md).

**Optional:** Windows desktop notifications: `pip install -r requirements-optional.txt`

## GUI Version

SteaMidra has a full graphical interface.

**Run with Python:** `python Main_gui.py`

**Build the GUI EXE:**
1. Install dependencies: `pip install -r requirements-consumer.txt` (or `requirements.txt`)
2. Install GUI deps: `pip install -r requirements-gui.txt`
3. Run `build_simple_gui.bat`
4. Run `dist\SteaMidra_GUI.exe`

**What the GUI gives you:**  
- Pick your game from a dropdown (all Steam libraries scanned) or set a path for games outside Steam.  
- All actions as buttons: crack, DRM removal, DLC check, workshop items, multiplayer fix, DLC unlockers, and more.  
- Lua/manifest processing, AppList management, Steam patching, and library tools all accessible from buttons.  
- Full settings dialog where you can edit, delete, export, and import all settings.  
- Light and dark themes.  
- Log output shown in the window so you can see what's happening.  
- Any prompts that would normally appear in the terminal show up as dialog boxes instead.

The CLI version (`Main.py` / `SteaMidra.exe`) still works exactly the same as before.

## What SteaMidra can do

- Download and use Lua files for games, download manifests, and set up GreenLuma.  
- Write Lua and manifest data into Steam's config so games work with or without an extra injector.  
- Other features: multiplayer fixes (online-fix.me), DLC status check, cracking (gbe_fork), SteamStub DRM removal (Steamless), AppList management, and DLC Unlockers (CreamInstaller-style: SmokeAPI, CreamAPI, Koaloader, Uplay).  
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

[DLC Unlockers](docs/dlc_unlockers/README.md) – Using DLC unlockers (CreamInstaller-style).

## Requirements files

- **requirements.txt** – Full project
- **requirements-consumer.txt** – Runtime only, no grpcio-tools (use if grpcio-tools fails)
- **requirements-gui.txt** – GUI build only (PyQt6, PyQt6-WebEngine, PyInstaller)

More details in [INSTALL_DEPENDENCIES.md](INSTALL_DEPENDENCIES.md).

## Troubleshooting

**grpcio-tools build error** – Use `pip install -r requirements-consumer.txt` instead.

**Dependency conflicts** – Use a virtual environment (see Step 1 above).

**ModuleNotFoundError** – Dependencies are not installed. Run `pip install -r requirements-consumer.txt`.

## Credits

**Original SMD:** SteaMidra is modified from the original **SMD (Steam Manifest Downloader)** by **jericjan**. This version adds more features and is maintained by Midrag. SMD remains the original project.

Credit to RedPaper for the Broken Moon MIDI cover, originally arranged by U2 Akiyama and used in Touhou 7.5: Immaterial and Missing Power. Touhou 7.5 and its related assets are owned by Team Shanghai Alice and Twilight Frontier. SteaMidra is not affiliated with, endorsed by, or sponsored by either party. All trademarks belong to their respective owners.

**CreamInstaller** – The DLC Unlockers feature in SteaMidra is inspired by and compatible with CreamInstaller. SteaMidra does not ship CreamInstaller; it provides its own implementation that follows similar behavior.

Made by Midrag. Use SteaMidra at your own risk.
