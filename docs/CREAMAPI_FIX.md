# CreamAPI Multiplayer Fix

SteaMidra can install CreamAPI v5.3.0.0 (bundled locally) to spoof your game as
**Spacewar (AppID 480)** for online multiplayer. No account, no browser, and no external
downloads are required — the DLLs ship with SteaMidra.

---

## Prerequisites

1. **Steam must be running** and logged in while you play.
2. **Spacewar (AppID 480) must be installed.** Open Steam and paste this URL in your
   browser address bar:
   ```
   steam://install/480
   ```
   Spacewar appears under **Tools** in your Steam library after installation.
   SteaMidra automatically checks whether Spacewar is installed and shows this reminder
   the first time it is needed — it will never ask again once you have installed it.

---

## How to use

1. Open SteaMidra and select a game from the list.
2. Choose **Apply CreamAPI Multiplayer Fix**.
3. **Linux only:** choose between *Proton/Wine (Windows .dll)* or *Native Linux (.so)*.
4. If anti-cheat (EasyAntiCheat or BattlEye) is detected, SteaMidra will offer
   **Proxy mode** — choose it for a safer install that leaves the original DLLs untouched.
5. Confirm the prompt.

---

## After applying

- **Launch the game `.exe` directly** — do NOT launch it from the Steam library.
- The Steam overlay in the top-right corner should say **"Playing Spacewar"** — this
  means AppID spoofing is working.
- **Invite friends via the Steam overlay.** Every player in the session must apply this
  fix independently to the same game.

### Proton/Wine users (Linux)

Add the following to the game's **Steam launch options**:
```
WINEDLLOVERRIDES="steam_api64=n,b" %command%
```

---

## To restore

Choose **Restore CreamAPI Multiplayer Fix** from the game menu.  
SteaMidra will remove all CreamAPI files and restore original DLLs from the backups
it created during installation.

---

## Classic vs Proxy mode

| Mode | What it does | When to use |
|---|---|---|
| **Classic** (default) | Replaces `steam_api64.dll` with CreamAPI; original backed up as `steam_api64_o.dll` | Most games — quick and reliable |
| **Proxy** | Installs CreamAPI as `winmm.dll`; original `steam_api*.dll` never touched | Games with DLL integrity checks or anti-cheat that blocks DLL replacement |

---

## Linux mode details

| Platform hint | DLL used | When to choose |
|---|---|---|
| **Proton/Wine** | `steam_api64.dll` (Windows) | Game runs under Proton/Wine on Linux |
| **Native Linux** | `libsteam_api.so` | Game has a native Linux build |

SteaMidra reads the ELF header of the existing `.so` to automatically pick the correct
x64 or x86 variant.

---

## Notes

- `cream_api.ini` (appid = 480) is placed next to the DLL.
- `steam_appid.txt` (containing `480`) is placed in the main executable's directory.
- All players in the session must apply this fix. There is no central server involved.
- If something breaks, use **Restore CreamAPI Multiplayer Fix** to undo all changes.
