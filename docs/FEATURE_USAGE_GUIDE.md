# Feature Guide

Short explanations of SteaMidra’s main features and how to use them.

**Parallel downloads**

SteaMidra can download several manifest files at once so adding a game is faster. You can turn this on or off in Settings. There you can also set how many downloads run at the same time (for example 4). More is faster but uses more of your connection.

**Settings export and import**

You can save your SteaMidra settings to a file and load them again later. Use Settings from the main menu, then Export Settings or Import Settings. Handy when you reinstall or move to another PC. When you export, you can choose whether to include things like passwords (stored encrypted).

**Library scanner**

The Scan Library option looks through your Steam libraries and lists your installed games. It can show which games have Lua backups and which might need manifest updates. You can then use that list to decide what to process next.

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

- **Main tab “Download Games”** — downloads the **latest version** of a game directly from Steam. Fast, no .NET required. SteaMidra processes your Lua file, writes decryption keys, registers the AppList/SLSsteam IDs, and triggers Steam to download game files natively. Progress is tracked in the Downloads tab.
- **Store tab** — lets you find and download **older or specific versions** of a game using Hubcap’s manifest library. Slower: it fetches the full depot and manifest ID list first, then downloads the game files via DepotDownloaderMod (.NET 9 required). Use this when you need a version other than the current latest.

**Store browser (GUI)**

The Store tab lets you search the Hubcap manifest library by game name or App ID. You need a Hubcap API key (set it in Settings). Results are paginated. Click **Download (choose version)** to fetch the full depot and manifest history from multiple sources (Steam CM, GitHub mirror, SteamDB) and pick a specific version to download. If the version list looks incomplete, click **Force Refresh** to ignore the disk cache and re-fetch all historical manifests from scratch.

**Floating Log Viewer**

Click the **Logs** button in the menu bar (to the right of Help) to open the floating log viewer. It shows all Python logging output from the entire app — every tab, every background operation. You can filter by level (DEBUG, INFO, WARNING, ERROR), clear the log, or copy everything to the clipboard. Closing the window just hides it; click Logs again to bring it back.

**Themes (GUI)**

SteaMidra has 11+ themes including Dracula, Nord, Cyberpunk, and more. Change your theme from the Theme menu in the GUI.

**System tray icon (GUI)**

SteaMidra shows a system tray icon. Right-click it to show/hide the window or exit.

**Command line**

You can run SteaMidra with extra options: for example `--batch file1.lua file2.lua` to process several files, or `--dry-run` to see what would happen without doing it. Run `python Main.py --help` to see all options.

For step-by-step use of the main menu, see the [User Guide](USER_GUIDE.md). If something goes wrong, check the error message and the debug.log file in the SteaMidra folder, or ask for help on Discord.
