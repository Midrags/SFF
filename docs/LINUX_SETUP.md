# Linux Setup Guide

SteaMidra runs natively on Linux but the architecture differs from Windows. This page covers everything specific to the Linux build.

## TL;DR

- **LumaCore is Windows-only.** It is a Steam-client DLL hijack via `dwmapi.dll`. There is no Linux equivalent shipping today.
- On Linux SteaMidra uses **SLSsteam** for license/family-share injection and **SLScheevo** for achievements. Both run as a `LD_PRELOAD`-style injection into the Steam process.
- Manifests, depot keys, ACF writing, depot decryption, and the rest of the SteaMidra pipeline work the same as Windows.
- The Auto LC Setup button is hidden on Linux. Use **Quick Tools → Set up Linux tools (SLSsteam + .NET 9)** instead.

## What works on Linux

| Feature | Status | Notes |
|---|---|---|
| Add game (Lua + manifests + depot keys + ACF) | Works | Same code path as Windows. |
| Download via DepotDownloaderMod | Works | Needs `.NET 9` on PATH. SteaMidra installs it via the Linux setup tool if missing. |
| Download via Steam-native fetcher | Limited | Steam needs SLSsteam injected at startup so it accepts the app id. Uninjected Steam shows "Purchase". |
| Achievements | Works (SLScheevo) | Different from LumaCore but produces the same end result. |
| Family bypass | Works (SLSsteam) | The injection is what bypasses the in-family check. Re-inject after every Steam update. |
| Workshop downloads | Works | `steamcmd` Linux binary is bundled in `third_party/`. |
| Cloud save scan / restore | Works | rclone Linux binary picked automatically. |
| Manifest preserver | Works | Inotify-based watch on Linux, ReadDirectoryChangesW on Windows. |
| LC Online Fix toggle | Hidden | Windows-only; the button does not render on Linux. |
| Auto LC Setup | Hidden | Windows-only; replaced by the Linux setup tool. |
| HyperVisor (HVAuto) | Hidden | Windows-only; Linux has no equivalent code path. |
| Context Menu (Explorer) | Hidden | Windows-only. |

## Supported distros

Tested on:
- **CachyOS** (latest, kernel 6.13+)
- **Arch Linux** (rolling)
- **Debian 12 / 13**, **Ubuntu 24.04**, **Fedora 41**
- **Steam Deck** in Desktop Mode (SteamOS 3.6+)

Other distros usually work if Steam itself runs there. The path detector probes `~/.steam/root`, `~/.steam/steam`, `~/.local/share/Steam`, the Flatpak sandbox at `~/.var/app/com.valvesoftware.Steam/data/Steam`, and the Snap install in that order.

## Step-by-step

### 1. Get SteaMidra

Two options:
- **AppImage** (`SteaMidra-x.x.x-linux.AppImage`): chmod +x, double-click. Easiest path.
- **ZIP** (`SteaMidra-x.x.x-linux.zip`): extract, run `./SteaMidra_GUI`.

Both bundle Python and the GUI runtime. No system Python needed.

### 2. Install SLSsteam + SLScheevo

Open SteaMidra, go to **Quick Tools**, click **Set up Linux tools (SLSsteam + .NET 9)**.

What this does:
1. Detects the Steam install path.
2. Downloads the latest SLSsteam release from GitHub.
3. Drops `SLSteam.so` and `library-inject.so` into the Steam folder.
4. Verifies `.NET 9` is installed; offers to fetch the Microsoft installer if missing.
5. Optionally writes a desktop shortcut that launches Steam with the injection.

If you already have `.NET 9` somewhere unusual (e.g. `~/.dotnet/dotnet`), SteaMidra picks it up via the user `dotnet` config or the standard `~/.dotnet` path.

### 3. Restart Steam from SteaMidra

This is the step Linux users miss most often. SLSsteam injects via `LD_PRELOAD` at startup, so a Steam process started outside SteaMidra is **not injected** and ownership/family-bypass will not work.

Use the **Restart Steam** button on the Home tab (or **Quick Tools → Kill Steam → Start Steam**). The status line confirms the injection:

```
Steam process killed (PID 678253).
SLSteam libraries found at /home/you/.steam/steam/SLSteam.so + library-inject.so.
Starting Steam with SLSteam injection.
Steam started (with SLSteam).
```

If it instead shows:
```
SLSteam libraries not found: SLSteam.so, library-inject.so
Starting Steam without SLSteam injection.
Steam started (without SLSteam).
```
…the install step has not run yet. Go back to Quick Tools.

### 4. Add a game

Same as Windows. The Home tab walks you through it. After the depots download, the game shows up in Steam (no restart needed; SLSsteam picks up new lua files dynamically).

## Troubleshooting

### "Steam installation path couldn't be found"

The path detector covers the standard locations. If yours is non-standard:
- Set the path manually in **Settings → Steam path**.
- Or symlink `~/.steam/root → /your/steam/install`.

### Games show "Purchase" instead of "Install"

Steam was started without SLSsteam injected. Use the SteaMidra **Restart Steam** button to relaunch with injection.

### `SLSteam libraries not found`

The setup tool has not run, or the SLSsteam files were wiped by a Steam update. Re-run **Quick Tools → Set up Linux tools**.

If you manually placed `SLSteam.so` and `library-inject.so` under the Steam folder, current builds check that location after the managed install path. Use **Restart Steam** again after placing the files.

### SLSsteam extraction fails on CachyOS or Arch

Current builds extract the SLSsteam archive with Python first, then fall back to `7zz`, `7z`, or `7za` using a cleaned subprocess environment. If you still see a readline or shell symbol error, install the distro package for p7zip or 7zip, then run **Set up Linux tools** again.

### `.NET 9` errors on download

DepotDownloaderMod runs on `.NET 9`. If `dotnet --list-runtimes` does not list a 9.x entry:
- Use the SteaMidra setup tool's `.NET 9` step (it fetches the Microsoft installer for your distro).
- Or install via your package manager: `sudo pacman -S dotnet-runtime` on Arch, `sudo apt install dotnet-runtime-9.0` on Debian/Ubuntu.

### `Encountered 401 for depot manifest`

DepotDownloaderMod is logging in anonymously. Some manifests (e.g. the base app id of titles like Ready or Not, app `1144200`) require an authenticated account. Workaround: use the Home tab's **Steam download** path instead — it goes through the injected Steam client which has authentication via your account.

### Family bypass not working

SLSsteam handles family bypass on Linux. If a friend in your Steam Family is playing a shared title and you see "Currently Unavailable":
1. Confirm SLSsteam is injected (status line on Restart Steam).
2. Confirm the game's lua is present in `config/stplug-in/`.
3. Restart Steam from SteaMidra (not from a desktop icon).

### Steam Deck specific

- Run from Desktop Mode, not Game Mode. The injection cannot attach in Game Mode.
- Steam Deck's read-only root means you cannot install `.NET 9` system-wide. Use the user-local `~/.dotnet/dotnet` install path; the SteaMidra setup tool defaults to this.
- Adding `STEAM_RUNTIME=0` is rarely needed but works around some Proton+SLSsteam edge cases.

## Differences from Windows

| Topic | Windows | Linux |
|---|---|---|
| Ownership injection | LumaCore (DLL hijack via `dwmapi.dll`) | SLSsteam (`LD_PRELOAD` of `SLSteam.so`) |
| Achievements | LumaCore (in-process protobuf rewrite) | SLScheevo (separate Steam client) |
| Library entries | LumaCore picks them up live | SLSsteam picks them up live; Steam restart not needed |
| ACF writes | Skipped (LumaCore handles ownership) | Required (SLSsteam reads ACFs) |
| `.NET 9` | Optional (only for DepotDownloaderMod) | Required for DepotDownloaderMod path |
| Auto-update | In-app via the updater script | In-app; AppImage variant updates via separate AppImage download |

## Reporting Linux bugs

When opening an issue please include:
- Distro + version (`lsb_release -a` or `cat /etc/os-release`)
- Steam install location (`echo $HOME/.steam/steam` resolves the symlink)
- The four lines from the Restart Steam status block
- Whether `dotnet --list-runtimes` shows a 9.x entry
- The contents of the Logs panel from inside SteaMidra (last 50 lines is plenty)
