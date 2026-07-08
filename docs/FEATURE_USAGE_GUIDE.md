# Feature Guide

Short explanations of SteaMidra’s main features and how to use them.

**Parallel downloads**

SteaMidra can download several manifest files at once so adding a game is faster. You can turn this on or off in Settings. There you can also set how many downloads run at the same time (for example 4). More is faster but uses more of your connection.

**Settings export and import**

You can save your SteaMidra settings to a file and load them again later. Open Settings and use the Settings Backup buttons near the top of the page. Handy when you reinstall or move to another PC. The modern export skips saved secrets such as API keys; SteaMidra still keeps those encrypted in its own settings file.

**Library scanner**

The Scan Library option looks through your Steam libraries and lists your installed games. The modern Library tab marks games as SteaMidra-managed when their App ID appears in saved Lua files or Steam `config/stplug-in`, and the SteaMidra Only filter shows that subset.

**Recent files**

SteaMidra remembers the last Lua files you processed. Choose "Process recent .lua file" to pick one of them and run the process again without browsing for the file.

**Analytics dashboard**

SteaMidra can keep simple usage stats on your PC (nothing is sent online). You can see how many operations you ran, which games you downloaded most, and success rates. Open it from the main menu with "View analytics dashboard".

**Notifications**

On Windows, SteaMidra can show a small notification when a task finishes or when something goes wrong. You can enable or disable this in Settings.

**Backups**

Before changing important files, SteaMidra can make backups. How many backups to keep is set in Settings. Old ones are removed automatically.

**Keyboard shortcuts**

In menus you can often press a number to choose an option. Escape or Back goes back. Ctrl+C exits SteaMidra.

**Downloading games**

SteaMidra has two separate download paths:

- **Main tab "Download Games"** — downloads the **latest version** of a game directly from Steam. Fast, no .NET required. SteaMidra processes your Lua file, writes decryption keys, registers SLSsteam IDs (Linux) or LumaCore handles it via hook (Windows), and triggers Steam to download game files natively. Progress is tracked in the Downloads tab.
- **Store tab**: lets you find and download **older or specific versions** of a game using Hubcap’s manifest library. Slower: it fetches the full depot and manifest ID list first, then downloads the game files via DepotDownloaderMod (.NET 9 required). If the history list is empty, the version picker can import saved SteamDB depot HTML pages into the selectable list.

**Store browser (GUI)**

The Store tab lets you search the Hubcap manifest library by game name or App ID. You need a Hubcap API key (set it in Settings). Typing does not start a backend search until you press Enter or click Search, and stale search results are ignored if a newer search finishes first. Click **Depot Keys** to refresh the local provider cache manually; SteaMidra also attempts a background refresh every 6 hours based on the last attempt time.

**Floating Log Viewer**

Click the **Logs** button in the menu bar (to the right of Help) to open the floating log viewer. It shows Python logging output from the entire app and keeps the newest lines based on the Live Log Line Limit setting. You can filter by level (DEBUG, INFO, WARNING, ERROR), clear the log, or copy everything to the clipboard.

**Themes (GUI)**

SteaMidra has 11+ themes including Dracula, Nord, Cyberpunk, and more. Settings also let you copy in a custom PNG, JPG, or WebP background and choose a custom accent color.

**Auto update defaults**

Auto Enable Updates For New Games is off by default. If you turn it on, newly added SteaMidra games with manifest pins are allowed to receive Steam update prompts. Per-game Auto Update still wins, and protected or cracked games may break after an update.

**System tray icon (GUI)**

SteaMidra shows a system tray icon. Right-click it to show/hide the window or exit.

**Command line**

You can run SteaMidra with extra options: for example `--batch file1.lua file2.lua` to process several files, or `--dry-run` to see what would happen without doing it. Run `python Main.py --help` to see all options.

For step-by-step use of the main menu, see the [User Guide](USER_GUIDE.md). If something goes wrong, check the error message and the debug.log file in the SteaMidra folder, or ask for help on Discord.
