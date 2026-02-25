# SteamForge Fetcher (SFF)

Quick thing before we start remember to exclude the SFF folder from Windows Security or at least the folder in this path for Creaminstaller Resources to work! `sff\dlc_unlockers\resources`

SFF helps you set up games to work with Steam using Lua scripts, manifests, and GreenLuma. It writes the right files into your Steam folder so games and DLC can run. It does not replace or crack Steam itself.

**Need help?** Check the [documentation](docs/README.md) or the discord server: https://discord.gg/bK667akcjn

## Quick start

Before doing anything after you install it first thing to do just to make sure everything works run `pip install -r requirements.txt`

**If you have the EXE**  
Run SFF.exe and follow the prompts. You'll need GreenLuma installed; see the Setup Guide for the download link.

**If you use Python**  
1. Install dependencies: `pip install -r requirements.txt`  
2. Run: `python Main.py`  or use `simple_build.bat` to get exe instead of using python everytime.
3. Optional (Windows desktop notifications): `pip install -r requirements-optional.txt`

**GreenLuma**  
SFF works with GreenLuma. You need to download and set up GreenLuma yourself:  
(https://www.up-4ever.net/h3vt78x7jdap)

Extract the ZIP and use the AppList folder from GreenLuma when SFF asks for it. Full steps are in the [Setup Guide](docs/SETUP_GUIDE.md).

## What SFF can do

- Download and use Lua files for games, download manifests, and set up GreenLuma.  
- Write Lua and manifest data into Steam's config so games work with or without an extra injector.  
- On Windows, games work with GreenLuma's AppList and your Lua setup.  
- Other features: multiplayer fixes (online-fix.me), DLC status check, cracking (gbe_fork), SteamStub DRM removal (Steamless), AppList management, and DLC Unlockers (CreamInstaller-style: SmokeAPI, CreamAPI, Koaloader, Uplay).  
- Parallel downloads, backups, recent files, and settings export/import.

## Download

- **HTTPS:** `git clone https://github.com/Midrags/SFF.git`
- **GitHub CLI:** `gh repo clone Midrags/SFF`

Then go into the project folder and see [Quick start](#quick-start) below.

## What's new

See [CHANGELOG.md](CHANGELOG.md) for what changed in the latest update (including a fix for the startup crash some people had).

## Documentation

[Documentation index](docs/README.md) – Start here.

[Setup Guide](docs/SETUP_GUIDE.md) – What to install (including GreenLuma and the optional Steam patch).

[User Guide](docs/USER_GUIDE.md) – What each menu option does and how to add games.

[Quick Reference](docs/QUICK_REFERENCE.md) – Commands and shortcuts.

[Feature Guide](docs/FEATURE_USAGE_GUIDE.md) – Parallel downloads, backups, library scanner, and more.

[Multiplayer Fix](docs/MULTIPLAYER_FIX.md) – Using the online-fix.me multiplayer fix.

[DLC Unlockers](docs/dlc_unlockers/README.md) – Using DLC unlockers (CreamInstaller-style).

## Credits

**Original SMD:** SteamForge Fetcher (SFF) is modified from the original **SMD (Steam Manifest Downloader)** by **jericjan**. This version adds more features and is maintained by Midrags. SMD remains the original project.

Credit to RedPaper for the Broken Moon MIDI cover, originally arranged by U2 Akiyama and used in Touhou 7.5: Immaterial and Missing Power. Touhou 7.5 and its related assets are owned by Team Shanghai Alice and Twilight Frontier. SFF is not affiliated with, endorsed by, or sponsored by either party. All trademarks belong to their respective owners.

**CreamInstaller** – The DLC Unlockers feature in SFF is inspired by and compatible with CreamInstaller. SFF does not ship CreamInstaller; it provides its own implementation that follows similar behavior.

Use SFF at your own risk.
