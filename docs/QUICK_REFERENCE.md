# Quick Reference

**Run SteaMidra**
```bash
python Main.py
```

**Other useful commands**
```bash
python Main.py --version
python Main.py --help
python Main.py --batch file1.lua file2.lua
python Main.py --quiet
python Main.py --dry-run
```
Dry run shows what would happen without doing it. Quiet mode reduces output.

**Main menu**

Process a .lua file: The main way to add a game. You choose a Lua file (or download one), pick your Steam library, and SteaMidra sets everything up.

Process recent .lua file: Opens your last processed files so you can run them again quickly.

Scan game library: Lets SteaMidra find games in your Steam libraries.

Store search: Type a game name or App ID, then press Enter or click Search. The Depot Keys button refreshes the local provider cache. In the version picker, Import HTML can read saved SteamDB depot pages into the selectable history list.

Library filter: Use SteaMidra Only to show installed games with saved Lua or `config/stplug-in` Lua entries.

Settings: Use Settings Backup near the top to export/import JSON settings, or change Steam path and other options.

**Keyboard**

You can type a number to jump to a menu option. Escape or Back goes back. Ctrl+C exits.

**Important files**

Settings are stored in `settings.bin`. Recent files are in `recent_files.json`. If something goes wrong, check `debug.log` in the SteaMidra folder.

**Getting help**

Read the error message first. For more detail on features, see the [User Guide](USER_GUIDE.md) and [Feature Guide](FEATURE_USAGE_GUIDE.md).
