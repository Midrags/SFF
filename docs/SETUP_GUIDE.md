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

## Step 2: LumaCore

Open SteaMidra, go to the **Home** tab, click **Auto LC Setup**, then click **Install LumaCore**. SteaMidra copies `dwmapi.dll` + `LumaCore.dll` from `sff/lumacore/` into the Steam folder and cleans up any leftover legacy injector files automatically.

If the installer reports "No DLLs found": build from `LumaCore/build.bat` or ask on [Discord](https://discord.gg/V8aZqnbB84).

---

## Multiplayer fix (online-fix.me)

Use the **Apply multiplayer fix (online-fix.me)** option to download and apply a multiplayer fix for your game directly from online-fix.me.

What you need:

- An account on online-fix.me (create one on their website).
- Chrome installed and an archiver (7-Zip or WinRAR) for extraction.

SteaMidra will log in, find the fix for your game, download it, and extract it into the game folder automatically. Your credentials are stored securely after the first use.

You can also use **Fixes & Bypasses** as an additional source — no account needed, and it covers many games not found on online-fix.me.

---

## Problems?

See [Troubleshooting](TROUBLESHOOTING.md) or ask on [Discord](https://discord.gg/V8aZqnbB84).
