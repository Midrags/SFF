# Troubleshooting

Common problems and what to try.

---

## Modern UI shows a blank black screen

The app opens but the Modern UI is completely black with only a "Switch to Classic UI" button visible. This is a `QtWebEngineProcess.exe` initialization failure — the embedded Chromium renderer could not start. Work through the steps below in order.

**Note:** The Modern UI uses **PyQt6-WebEngine** (bundled Chromium). It does **not** use Microsoft Edge WebView2 — installing WebView2 will not fix this.

---

### Step 1 — Set environment variables (fixes most cases)

1. Press `Win + R`, type `sysdm.cpl`, hit Enter.
2. Go to the **Advanced** tab → click **Environment Variables**.
3. Under **User variables**, click **New** and add both of these:

| Name | Value |
|---|---|
| `QTWEBENGINE_DISABLE_SANDBOX` | `1` |
| `QTWEBENGINE_CHROMIUM_FLAGS` | `--no-sandbox --disable-gpu --disable-web-security` |

4. Click OK, then **fully close SteaMidra from Task Manager** and reopen it.

---

### Step 2 — Install Visual C++ Redistributable (run as Administrator)

Download the **all-in-one pack** from TechPowerUp — it installs every Visual C++ version (2005–2022) in one go:

> https://www.techpowerup.com/download/visual-c-redistributable-runtime-package-all-in-one/

**Right-click the installer → Run as administrator.** Running it without admin rights is a known failure cause where it appears to succeed but doesn't actually install correctly.

Also install **Visual C++ 2013 x64** specifically if the above doesn't help — it ships as a separate package:

> https://www.microsoft.com/en-us/download/details.aspx?id=40784

---

### Step 3 — Add SteaMidra to Windows Defender exclusions

Windows Defender (and other AV) frequently quarantines or kills `QtWebEngineProcess.exe` inside `_internal/`, which prevents Chromium from ever starting.

1. Open **Windows Security** → **Virus & threat protection** → **Manage settings**.
2. Scroll to **Exclusions** → **Add or remove exclusions**.
3. Add the entire SteaMidra folder (e.g. `C:\SteaMidra\`) as a **Folder** exclusion.

Restart SteaMidra after adding the exclusion.

---

### Step 4 — Run SteaMidra as Administrator

Right-click `SteaMidra_GUI.exe` → **Run as administrator**. Some sandbox/permission configurations prevent Chromium sub-processes from launching without elevated rights.

---

### Step 5 — Diagnose with Task Manager

Open **Task Manager** while SteaMidra is running and look for a process called `QtWebEngineProcess.exe`:

- **Not present at all** → Something is killing it before it can start (AV or sandbox). Go back to Steps 3–4.
- **Present but screen is still black** → The renderer started but failed to load resources. Reinstall from the latest release ZIP, making sure the `_internal/` folder is fully extracted.

---

### Step 6 — Diagnose with Event Viewer

Press `Win + R` → type `eventvwr` → **Windows Logs** → **Application**. Look for crash or error entries mentioning `QtWebEngineProcess` or `SteaMidra_GUI`. The error description will identify whether it is a missing DLL, access-denied, or GPU driver issue.

---

### Step 7 — Use Classic UI as a fallback

Click the **"Switch to Classic UI"** button in the top-right corner of the blank window. The Classic UI has no WebEngine dependency and all features are fully available. Use it while you work through the steps above.

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

SteamAutoCrack is bundled inside the `_internal/` folder (shipped alongside `SteaMidra_GUI.exe`) and is found automatically. You do **not** need to download or extract it manually.

If you still see this error:
- Make sure you are using the latest version of SteaMidra.
- Install SteaMidra in a short path like `C:\SFF\` — very long install paths can cause Windows path-length errors (260-character limit).

If you previously tried to fix this by extracting the SteamAutoCrack release ZIP into the `third_party\SteamAutoCrack\` folder, **delete those extracted files**. The full archive contains hundreds of deeply-nested .NET build files that cause the "Failed to extract … fopen: No such file or directory" error. Only the CLI bundled in `_internal/` is needed.

---

## Antivirus flags SteaMidra files

Starting with version 5.3.0, SteaMidra uses the one-dir distribution format. All files are pre-extracted into the `_internal/` folder next to `SteaMidra_GUI.exe` at install time. Nothing is extracted to `%TEMP%` at runtime, which greatly reduces false positives.

If your antivirus still flags files, add your SteaMidra folder (e.g. `C:\SteaMidra\`) to your AV exclusions. The `_internal/` folder contains Python runtime files and bundled tools — none of them are malware.

---

## Chrome or ChromeDriver errors (multiplayer fix)

If the multiplayer fix needs a browser and you get a Chrome or ChromeDriver error, make sure Chrome is installed and up to date. Try closing all Chrome windows and running SteaMidra again, or run it as administrator.

---

## Login failed (online-fix.me)

Check your username and password on the online-fix.me website. If you can log in there, update your credentials in SteaMidra under Settings. Some games may no longer be available on the site.

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

## GreenLuma — Purchase Error After Setup

If Steam shows a purchase error for a game after GreenLuma setup, it means Steam was opened directly (`steam.exe`) instead of through DLLInjector. You must always launch Steam by running **DLLInjector.exe as Administrator** — not `steam.exe` directly.

**Steps:**
1. Close Steam completely (check the system tray).
2. Right-click `DLLInjector.exe` → **Run as administrator**.
3. Steam will start automatically with GreenLuma injected.

---

### Tip — SteamKillInject (automate the above)

**SteamKillInject** closes all running Steam processes and launches DLLInjector automatically in one step.

- Run **SteamKillInject as Administrator**.
- Make sure **DLLInjector.exe is also set to Run as Administrator** — right-click → Properties → Compatibility tab → check "Run this program as an administrator".

---

## Older Versions shows no history / depot list is empty

When using the **Older Versions** feature, the depot and manifest history panel stays empty or shows no entries for some games (e.g. Resident Evil Village).

**Why it happens:** SteaMidra scrapes SteamDB to retrieve historical manifests. Cloudflare protects SteamDB with bot-detection challenges. The previous implementation sent HTTP requests with a mismatched TLS fingerprint, which caused Cloudflare to issue 403 responses and flag the IP — blocking the browser layer as well. All 3 retry sessions would fail identically.

**Fixed in 6.1.3:** A new 4-layer scraping architecture handles these cases. `zendriver` (Layer 3A) uses Chrome DevTools Protocol — no WebDriver flag — and exits early if CF persists. `SeleniumBase` (Layer 3B) automatically clicks the Cloudflare Turnstile "Verify you are human" checkbox via `uc_gui_click_captcha()`. System Chrome is detected via the Windows registry before falling back to Chrome for Testing.

If you are still seeing empty history after updating:
1. Delete `~/.sff/cf_cookie_cache.json` to clear any stale cookies.
2. Make sure `Google Chrome` is installed and up to date — the registry detection will find it automatically.
3. Re-run Older Versions. A visible Chrome window will open and click the CF checkbox automatically.

---

## High RAM usage during downloads (QtWebEngineProcess.exe)

During a large game download, `QtWebEngineProcess.exe` (the embedded Chromium renderer) consumes several GB of RAM.

**Why it happens:** Every download progress line printed by the downloader was appended as a new DOM node in the log panel with no limit. Over a long download, hundreds of thousands of nodes accumulated, causing Chromium's renderer to bloat.

**Fixed in 6.1.3:** The log panel now evicts old entries, keeping only the last 1000 lines. RAM usage stays flat regardless of download size.

If you are still seeing high RAM on an older version, update to 6.1.3 or newer.

---

## Need more help?

Read the error message first — it often explains what went wrong. Check `debug.log` in the SteaMidra folder for more detail.

- [User Guide](USER_GUIDE.md) — what each feature does
- [Feature Guide](FEATURE_USAGE_GUIDE.md) — parallel downloads, backups, library scanner, and more
- [Discord](https://discord.gg/V8aZqnbB84) — ask for help
