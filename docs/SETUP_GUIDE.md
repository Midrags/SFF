# Setup Guide

What you need to use SteaMidra and how to get started.

> Running from source (Python)? See [Python Setup](PYTHON_SETUP.md) instead.

---

## Before you start

- Steam must be installed on your PC.
- Exclude the SteaMidra folder from Windows Security — especially `sff\dlc_unlockers\resources` — or CreamInstaller resources may not work. Add a Windows Defender exclusion for the folder.

---

## Step 1: Download SteaMidra

Download the latest release from [GitHub Releases](https://github.com/Midrags/SFF/releases/latest).

Extract the ZIP anywhere — you will get a folder with `SteaMidra_GUI.exe` and an `_internal/` folder inside. Place the whole folder wherever you want (e.g. `C:\SteaMidra\`) and run `SteaMidra_GUI.exe` from inside it.

---

## Step 2: GreenLuma

Join our [Discord server](https://discord.gg/V8aZqnbB84) to get the latest GreenLuma, or use this direct link: https://www.up-4ever.net/lyoi96gger8y

1. Extract the ZIP — you will see three folders. You only need `NormalModePatch.rar`.
2. Extract `NormalModePatch.rar` and place all files into your `SteaMidra\Greenluma` folder.

---

## Step 3: Configure GreenLuma

1. Open your `SteaMidra\Greenluma` folder and run `GreenLumaSettings2025.exe`.
2. Type `2` and press Enter.
3. Set the full path to `steam.exe` (default: `C:\Program Files (x86)\Steam\steam.exe`).
4. Set the full path to `GreenLuma_2025_x64.dll` (default: `SteaMidra\Greenluma\GreenLuma_2025_x64.dll`).

---

## Multiplayer fix (online-fix.me)

Use the **Apply multiplayer fix (online-fix.me)** option to download and apply a multiplayer fix for your game directly from online-fix.me.

What you need:

- An account on online-fix.me (create one on their website).
- Chrome installed and an archiver (7-Zip or WinRAR) for extraction.

SteaMidra will log in, find the fix for your game, download it, and extract it into the game folder automatically. Your credentials are stored securely after the first use.

You can also use **Fixes/Bypasses (Ryuu)** as an additional source — no account needed, and it covers many games not found on online-fix.me.

---

## Problems?

See [Troubleshooting](TROUBLESHOOTING.md) or ask on [Discord](https://discord.gg/V8aZqnbB84).
