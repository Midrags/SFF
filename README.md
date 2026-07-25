# SteaMidra Listed on r/FMHY [FMHY](https://fmhy.net/gaming-tools#steam-epic) and r/Piracy [Piracy](https://www.reddit.com/r/Piracy/wiki/megathread/games/#:~:text=SteaMidra)

*Made by Midrag and his brother!*
## Educational use only. Use at your own risk.

> ⚠️ **Antivirus Warning:** some AVs flag the binary as a generic packed-exe false positive. it's not malware. if your AV keeps quarantining it, add the SteaMidra folder to your AV exclusion list. the source is open at github.com/Midrags/SFF if you want to verify.
>
> To add exclusions: **Windows Security → Virus & threat protection → Manage settings → Exclusions → Add or remove exclusions → Add a folder**.

SteaMidra helps you set up games to work with Steam using Lua scripts, manifests, and LumaCore. It writes the right files into your Steam folder so games and DLC can run. It does not replace or crack Steam itself.

Need help? Chat with us on our Discord server: https://discord.gg/V8aZqnbB84

**SteaMidra setup tutorial:** [Full walkthrough by @yensnc](https://www.reddit.com/user/YensNC/comments/1ttw2mm/tutorial_guide_on_installing_steamidra/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1)

**API key tutorial:** [Step-by-step screenshots by @novoagain](https://imgur.com/a/ubLeqer)

**Old SteaMidra setup tutorial (outdated):** ["Outdated" tutorial for new users](https://youtu.be/9aAaQ8dSnTY)

**Python setup tutorial:** [Python Tutorial](https://youtu.be/cFfItiV8-pk)

---

## Features

- Download and use Lua files for games, download manifests, and set up LumaCore.
- Write Lua and manifest data into Steam's config.
- **LC Online Fix** — toggle `-onlinefix` on a chosen App ID in `localconfig.vdf`. Closes Steam first, picks the active SteamID3 from `loginusers.vdf`, navigates the VDF tree case-insensitively. LumaCore handles the appid-480 redirect at launch so the overlay, Steam Input, and screenshots still tag the real game.
- **Multiplayer Fix** — searches **online-fix.me** for the selected game and opens the result in your browser. SteaMidra no longer stores online-fix credentials or downloads files from the site.
- **Fixes & Bypasses** — searches a curated list from the CrakFiles repo on GitHub and applies the chosen fix to the game folder. No API key, no account. Achievement-safe — only adds bypass DLLs, leaves the Steam API intact.
- **HyperVisor Cracks (HV Auto)** — download HyperVisor bypasses for Denuvo-protected games. Includes VBS.cmd to prepare your system. See the [HyperVisor Guide](docs/HV_GUIDE.md) before use.
- DLC status check, cracking (gbe_fork), SteamStub DRM removal (Steamless), and DLC Unlockers (CreamInstaller-style: SmokeAPI, CreamAPI, Uplay).
- **Multi-language GUI** — English and Portuguese built-in; add more via `sff/locales/`.
- Parallel downloads, backups, recent files, and settings export/import.
- **Linux support** — SLSSteam ID management, platform-aware MIDI, and Linux-compatible auto-update.
- **Store tab** — ⭐ **THIS IS THE MAIN WAY TO DOWNLOAD GAMES.** Browse Hubcap's manifest library to find games, refresh depot keys, and download either the latest version through Steam or **older/specific versions** through DepotDownloaderMod (.NET 9 required, slower). Search runs when you press Enter or the Search button so the tab stays smooth.
- **Main tab "Download Game"** — Downloads the **latest version** of a game directly from Steam (fast, no .NET required for Windows OS). Processes the Lua file, writes decryption keys, copies the Lua to `config/stplug-in/` and the manifests to `depotcache/` so LumaCore picks the game up immediately, then triggers Steam to download the game files natively. Use this for 99% of games.

---

## Quick start

### Step 1: SteaMidra

Download the latest installer from [here](https://github.com/Midrags/SFF/releases/latest) and run it. The installer auto-creates the install folder, sets up file associations, and registers the uninstaller.

If the installer fails or your AV blocks it, grab the ZIP instead — `SteaMidra-x.x.x-windows.zip`. Extract anywhere, run `SteaMidra_GUI.exe` from inside the extracted folder.

**Do not run SteaMidra yet.** Complete Steps 2 and 3 first so all folders exist before first launch.

### Step 2: LumaCore

Open SteaMidra, go to the **Home** tab, click **Auto LC Setup**, then click **Install LumaCore**. SteaMidra downloads the latest LumaCore release from GitHub and installs `dwmapi.dll` + `LumaCore.dll` into the Steam folder, removing old GreenLuma files automatically.

If the install fails, ask on [Discord](https://discord.gg/V8aZqnbB84).

### Step 3: Launch Steam

Run `SteaMidra_GUI.exe` and add a game on the Home tab. LumaCore makes it appear in the Steam library immediately. See the [User Guide](docs/USER_GUIDE.md) for how to add games.

> Running from source (Python)? See the [Python Setup Guide](docs/PYTHON_SETUP.md).

---

## Linux quick start

LumaCore is a Steam-client DLL hijack and is **Windows-only**. On Linux, SteaMidra uses **SLSsteam** (license/family-share injection) plus **SLScheevo** (achievement-only Steam client) instead. Manifests, depot keys, and ACFs work the same as on Windows.

### Step 1: Download the Linux build

Grab `SteaMidra-x.x.x-linux.zip` (or the AppImage) from the [releases page](https://github.com/Midrags/SFF/releases/latest) and extract it. CachyOS, Arch, Debian, Ubuntu, Fedora, and Steam Deck Desktop Mode are all supported.

### Step 2: Set up SLSsteam + SLScheevo

Launch SteaMidra, open **Quick Tools**, run **Set up Linux tools (SLSsteam + .NET 9)**. SteaMidra installs SLSsteam into `~/.steam/steam/` (or whichever Steam install it found), drops `SLSteam.so` and `library-inject.so`, and verifies your `.NET 9` runtime is on PATH (DepotDownloaderMod needs it).

If the GUI reports `SLSteam libraries not found: SLSteam.so, library-inject.so`, the install step has not run yet — open Quick Tools and run it.

### Step 3: Add a game

Add a game on the Home tab the same way as Windows. SteaMidra writes the lua to `config/stplug-in/`, drops the manifests, registers depot keys, and writes the ACF. **Restart Steam from inside SteaMidra** so SLSsteam injects into the new Steam process — without injection, ownership and family bypass do not work.

For the full walkthrough (supported distros, troubleshooting, what files go where, Steam-Deck-specific notes), see [docs/LINUX_SETUP.md](docs/LINUX_SETUP.md).

---

## GUI features

SteaMidra has a full graphical interface with a **Modern UI** and the classic Qt interface.

**Modern UI** — the new default interface, built with QWebEngine. Accessible from a clean sidebar with 8 tabs: Home (game picker with auto-refresh), Store (search/browse Hubcap, grid/list, pagination), Library (installed games), Downloads (live progress + history), Fix Game (full emulator pipeline), Tools (GBE Token Generator, VDF Extractor, Workshop), Cloud Saves (scan/backup/restore, Google Drive, rclone with 17 provider shortcuts, All Save Locations), and Settings. Supports 11+ themes, tooltips, and toast notifications.

**What the GUI gives you:**
- **Tabbed interface** — Main, Store, Downloads, Fix Game, Tools, and Cloud Saves tabs.
- Pick your game from a dropdown (all Steam libraries scanned) or set a path for games outside Steam.
- All actions as buttons: crack, DRM removal, DLC check, workshop items, multiplayer fix, **Fixes & Bypasses**, DLC unlockers, and more.
- **Store browser** — search and browse the Hubcap Manifest library with pagination. Download opens a version picker with full depot/manifest history, and the Depot Keys button refreshes the local provider cache. **Force Refresh** bypasses cache to rebuild historical manifests.
- **Fix Game pipeline** — automate emulator application (Goldberg, ColdClient, ColdLoader) with SteamStub unpacking.
- **GBE Token Generator** — generate full Goldberg emulator configs with achievements, DLCs, stats, and icons.
- **Cloud Saves** — Steam userdata plus Ludusavi save-path backup/restore. Multiple save folders for the same App ID are grouped into one backup with per-source restore details and a safety backup before overwrites. Supports local folder, **Google Drive** (sign in once), and **rclone** (Dropbox, OneDrive, MEGA, S3, Backblaze B2, SFTP, and 70+ other backends).
- **VDF Key Extractor** — extract depot decryption keys from Steam's config.vdf.
- Lua/manifest processing and library tools all accessible from buttons.
- Full settings dialog where you can edit, delete, export, and import all settings.
- **11+ themes** including Dracula, Nord, Cyberpunk, and more.
- **System tray icon** for quick show/hide and exit.
- **Multi-language support** — switch between English and Portuguese in Settings (more locales can be added).
- **Log viewer** — "Logs" button in the menu bar (right of Help) opens a floating window showing all log output from every tab (Fix Game, Store, Tools, and more). Filterable by level (DEBUG/INFO/WARNING/ERROR), with Clear and Copy All buttons.
- Any prompts that would normally appear in the terminal show up as dialog boxes instead.

---

Full changelog: [CHANGELOG.md](CHANGELOG.md)

---

## Documentation

[Documentation index](docs/README.md) – Start here.

[Setup Guide](docs/SETUP_GUIDE.md) – What to install (including LumaCore).

[User Guide](docs/USER_GUIDE.md) – What each menu option does and how to add games.

[Quick Reference](docs/QUICK_REFERENCE.md) – Commands and shortcuts.

[Feature Guide](docs/FEATURE_USAGE_GUIDE.md) – Parallel downloads, backups, library scanner, and more.

[Multiplayer Fix](docs/MULTIPLAYER_FIX.md) – Searching online-fix.me and opening the result in your browser.

[Fixes & Bypasses](docs/CRACK_FIX.md) – Searching and applying community-maintained fixes from the CrakFiles repo. No API key, no account.

[CrakFiles — Fixes & Bypasses source](docs/CRACK_FILES.md) – What the CrakFiles repository is, how SteaMidra fetches and uses `crackfiles.json`, and a breakdown of every field in the fix list.

[HyperVisor Guide](docs/HV_GUIDE.md) – How HV cracks work, security implications, and step-by-step setup for Denuvo HyperVisor bypasses.

[DLC Unlockers](docs/dlc_unlockers/README.md) – Using DLC unlockers (CreamInstaller-style).

[Troubleshooting](docs/TROUBLESHOOTING.md) – Common problems and solutions.

[Python Setup](docs/PYTHON_SETUP.md) – Running or building from source.

---

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common problems and solutions.

---

## Credits and third-party notices

**Made by Midrag and his brother.**

SteaMidra uses, integrates with, downloads, is compatible with, or was originally influenced by several third-party projects and community tools. Third-party tools, binaries, unlockers, emulators, assets, APIs, services, and earlier project bases remain owned by their original authors and keep their original licenses/terms. They are not relicensed as SteaMidra code.

SteaMidra’s GPL license applies to SteaMidra’s own source code only. It does not claim ownership over third-party components.

**SMD / Steam Manifest Downloader** – SteaMidra originally started from an early SMD base/fork. Credit to **Kur0 / the SMD project and contributors** for the original project structure, early workflow, and inspiration. Since then, SteaMidra has been heavily reworked and expanded with its own workflows, LumaCore integration, GUI/web UI, Store/search features, online fix handling, DLC unlocker handling, fixes/bypasses, backups, library scanner, Linux-related work, updater changes, and many other modules. Any remaining SMD-derived parts remain credited to their original authors/contributors and are not claimed as original SteaMidra code.

**LumaCore** – Windows DLL hook library bundled with SteaMidra. Injects into Steam at startup via a `dwmapi.dll` proxy, reads Lua files from `Steam/config/stplug-in/`, and patches Steam's in-memory license tables so games appear owned without AppList files or Steam restarts. [LumaCore](LumaCore/CREDITS.md)

**CreamAPI** – DLC unlocker by **deadmau5**. Used/handled only as a third-party unlocker component. CreamAPI remains owned by its original author and is not licensed as SteaMidra code.

**SmokeAPI / ScreamAPI** – DLC ownership emulation/unlocker projects by **Acidicoala**. Used/handled only as third-party unlocker components where applicable. These remain owned by their original author and are not licensed as SteaMidra code.

**Uplay R1/R2 Unlocker** – Uplay unlocker projects by **Acidicoala**. Used/handled only as third-party unlocker components where applicable. These remain owned by their original author and are not licensed as SteaMidra code.

**CreamInstaller** – The DLC Unlockers feature is inspired by and compatible with CreamInstaller-style behavior. SteaMidra does not ship CreamInstaller itself; it provides its own implementation for managing compatible unlocker setups. Credit to CreamInstaller and its maintainers for the original tool/flow inspiration.

**gbe_fork** – The "Crack a game" feature uses **gbe_fork**, a Steam emulator for running games offline. License in `third_party_licenses/gbe_fork.LICENSE`.

**gbe_fork tools** – Build and packaging tools for gbe_fork. License in `third_party_licenses/gbe_fork_tools.LICENSE`.

**Steamless** – The "Remove SteamStub DRM" feature uses **Steamless** by Atom0s for stripping Steam DRM from executables. License in `third_party_licenses/steamless.LICENSE`.

**fzf** – Used for fuzzy search in menus. License in `third_party_licenses/fzf.LICENSE`.

**SteamAutoCrack** – The SteamAutoCrack feature uses the **SteamAutoCrack CLI** by oureveryday. Bundled in `third_party/SteamAutoCrack/cli/`. License in `third_party_licenses/SteamAutoCrack.LICENSE`.

**DDMod / DepotDownloaderMod** – The Direct Download via DDMod feature uses **DepotDownloaderMod** by **oureveryday**. License in `third_party_licenses/DDMod.license`.

**headcrab / h3adcr-b** – The Linux SLSsteam auto-setup uses **headcrab** by **Deadboy666** (<https://github.com/Deadboy666/h3adcr-b>) as the primary installer. headcrab downloads and installs the latest SLSsteam release, patches Steam, and sets up the config. It is downloaded and run at setup time (not bundled). headcrab does not ship with a license; it remains owned by its original author.

**ManifestHub** – The ManifestHub source uses the manifest archive/API maintained by **oureveryday**.

**rclone** – Cloud Saves uses **rclone** for transfers to remote storage providers. License in `third_party_licenses/rclone.LICENSE`.

**online-fix.me** – The Multiplayer Fix feature searches online-fix.me for the selected game and opens the result in your browser. No credentials needed. SteaMidra is not affiliated with online-fix.me; files remain owned by their respective maintainers.

**Ludusavi** — The cloud save custom-path feature uses the **Ludusavi manifest** game-save-location database maintained by **mtkennerly** (<https://github.com/mtkennerly/ludusavi-manifest>). Bundled as `sff/data/manifest.yaml`.

**GBE Token Generator** – Goldberg Emulator configuration generation based on work by **Detanup01** (`gbe_fork`), **NickAntaris**, and **Oureveryday** (`generate_game_info`).

**Hubcap Manifest** – Store browser and manifest library API provided by **Hubcap Manifest**.

**RedPaper** – Credit to RedPaper for the Broken Moon MIDI cover, originally arranged by U2 Akiyama and used in Touhou 7.5: Immaterial and Missing Power. Touhou 7.5 and its assets are owned by Team Shanghai Alice and Twilight Frontier. SteaMidra is not affiliated with or endorsed by either party. All trademarks belong to their respective owners.

**Tutorials** – Setup walkthrough by **@yensnc**. API key tutorial by **@novoagain**.

README editing help by **itsphox**.

See `third_party_licenses/` and `THIRD_PARTY_NOTICES.md` for third-party license and provenance details.

## License scope

SteaMidra is licensed under the GNU General Public License v3.0 for SteaMidra’s own source code.

This license does not relicense third-party tools, binaries, unlockers, emulators, assets, APIs, services, or external projects used by, bundled with, downloaded by, or integrated with SteaMidra. Those components remain under their original authorship, licenses, and terms.

If any third-party credit, license notice, or ownership note is missing or unclear, please open an issue with the exact file/component and it will be reviewed.

## Disclaimer

This project is provided for research and educational purposes only. You are responsible for complying with local laws, platform terms of service, and software licenses.
