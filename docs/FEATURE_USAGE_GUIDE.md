# Feature Guide

Short explanations of SFF’s main features and how to use them.

**Parallel downloads**

SFF can download several manifest files at once so adding a game is faster. You can turn this on or off in Settings. There you can also set how many downloads run at the same time (for example 4). More is faster but uses more of your connection.

**Settings export and import**

You can save your SFF settings to a file and load them again later. Use Settings from the main menu, then Export Settings or Import Settings. Handy when you reinstall or move to another PC. When you export, you can choose whether to include things like passwords (stored encrypted).

**Library scanner**

The Scan Library option looks through your Steam libraries and lists your installed games. It can show which games have Lua backups and which might need manifest updates. You can then use that list to decide what to process next.

**Recent files**

SFF remembers the last Lua files you processed. Choose "Process recent .lua file" to pick one of them and run the process again without browsing for the file.

**Analytics dashboard**

SFF can keep simple usage stats on your PC (nothing is sent online). You can see how many operations you ran, which games you downloaded most, and success rates. Open it from the main menu with "View analytics dashboard".

**Notifications**

On Windows, SFF can show a small notification when a task finishes or when something goes wrong. You can enable or disable this in Settings.

**Backups**

Before changing important files, SFF can make backups. How many backups to keep is set in Settings. Old ones are removed automatically.

**Keyboard shortcuts**

In menus you can often press a number to choose an option. Escape or Back goes back. Ctrl+C exits SFF.

**Command line**

You can run SFF with extra options: for example `--batch file1.lua file2.lua` to process several files, or `--dry-run` to see what would happen without doing it. Run `python Main.py --help` to see all options.

For step-by-step use of the main menu, see the [User Guide](USER_GUIDE.md). If something goes wrong, check the error message and the debug.log file in the SFF folder, or ask for help on Discord.
