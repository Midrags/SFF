# Troubleshooting

Common problems and what to try.

---

## Steam says "No Internet Connection" when downloading

SteaMidra handles this automatically, but if you still see the error:

1. **Workshop ACF fix** — The most common cause is orphaned workshop items in `appworkshop_{id}.acf` triggering a failed Workshop update. SteaMidra patches this file to clear `NeedsDownload` when no workshop content is installed.
2. **Manifest seeding** — When you process a .lua file or use "Update all manifests", manifests are written directly to Steam's `depotcache` folder before Steam starts. Steam finds them locally.
3. **ACF error state** — SteaMidra clears stale `UpdateResult` and validation flags in the game ACF so Steam doesn't get stuck in a retry loop.

---

## Steam path not found

SteaMidra needs to know where Steam is installed. If it cannot find it automatically, it will ask you to choose the folder. Pick the folder that contains `steam.exe` (usually `C:\Program Files (x86)\Steam`).

---

## Dependency conflicts / urllib3 error

Run both install commands — `requirements.txt` first, then `pip install steam==1.4.4 --no-deps`. If conflicts persist with other projects on your system, use a virtual environment. See [Python Setup](PYTHON_SETUP.md).

---

## ModuleNotFoundError

Dependencies are not installed. Run `pip install -r requirements.txt`. See [Python Setup](PYTHON_SETUP.md) for full steps.

---

## Remove SteamStub (Steamless) → WinError 2

In the GUI, clicking "Remove SteamStub" opens a file picker. Navigate to your game folder and select the `.exe` yourself — no Steam API lookup needed.

---

## SteamAutoCrack not found / "Failed to extract" error

SteamAutoCrack is bundled inside `SteaMidra_GUI.exe` and is found automatically. You do **not** need to download or extract it manually.

If you still see this error:
- Make sure you are using the latest version of SteaMidra.
- Install SteaMidra in a short path like `C:\SFF\` — very long install paths can cause Windows path-length errors (260-character limit).

If you previously tried to fix this by extracting the SteamAutoCrack release ZIP into the `third_party\SteamAutoCrack\` folder, **delete those extracted files**. The full archive contains hundreds of deeply-nested .NET build files that cause the "Failed to extract … fopen: No such file or directory" error. Only the CLI bundled inside the EXE is needed.

---

## Chrome or ChromeDriver errors (multiplayer fix)

If the multiplayer fix needs a browser and you get a Chrome or ChromeDriver error, make sure Chrome is installed and up to date. Try closing all Chrome windows and running SteaMidra again, or run it as administrator.

> ⚠️ The multiplayer fix feature is currently not working due to an online-fix.me site update. Use **Fixes/Bypasses (Ryuu)** as an alternative.

---

## Login failed (online-fix.me)

Check your username and password on the online-fix.me website. If you can log in there, update your credentials in SteaMidra under Settings. Some games may no longer be available on the site.

> ⚠️ The multiplayer fix feature is currently not working due to an online-fix.me site update. Use **Fixes/Bypasses (Ryuu)** as an alternative.

---

## Download timeout or extraction failed

Check your internet connection. Try disabling antivirus temporarily and run SteaMidra again. Make sure you have 7-Zip or WinRAR installed if SteaMidra needs to extract archives. If a download keeps failing, you can try downloading the fix manually from online-fix.me and extracting it into the game folder yourself.

---

## Permission denied or access denied

Steam or the game folder may be in a protected location. Try running SteaMidra as administrator (right-click → "Run as administrator"). Do not run SteaMidra from a folder that requires admin rights to write to.

---

## Settings export or import error

If exporting or importing settings fails, try exporting without including sensitive data. Make sure the folder you export to is writable. If you get a message about "JSON serializable", try updating SteaMidra to the latest version.

---

## Parallel downloads or notifications not working

Check Settings. There are options to enable or disable parallel downloads and desktop notifications. If notifications do not appear on Windows, install the optional package:

```batch
pip install -r requirements-optional.txt
```

---

## Cache or backups taking too much space

You can delete `api_cache.json` — SteaMidra will create a new one when needed. Backup retention is set in Settings; you can lower how many backups are kept.

---

## Need more help?

Read the error message first — it often explains what went wrong. Check `debug.log` in the SteaMidra folder for more detail.

- [User Guide](USER_GUIDE.md) — what each feature does
- [Feature Guide](FEATURE_USAGE_GUIDE.md) — parallel downloads, backups, library scanner, and more
- [Discord](https://discord.gg/V8aZqnbB84) — ask for help
