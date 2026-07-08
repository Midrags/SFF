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

Use the **Apply multiplayer fix (online-fix.me)** option to search online-fix.me for your game and open the result in your browser.

What you need:

- A browser.
- Any login, download, or extraction step required by online-fix.me is done manually on their website.

SteaMidra does not store online-fix.me credentials and does not download files from online-fix.me anymore.

You can also use **Fixes & Bypasses** as an additional source. It has no online-fix.me account requirement and downloads from its own curated fix list.

---

## Problems?

See [Troubleshooting](TROUBLESHOOTING.md) or ask on [Discord](https://discord.gg/V8aZqnbB84).
