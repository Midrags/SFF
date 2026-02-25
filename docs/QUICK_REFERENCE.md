# Quick Reference

**Run SFF**
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

Process a .lua file: The main way to add a game. You choose a Lua file (or download one), pick your Steam library, and SFF sets everything up.

Process recent .lua file: Opens your last processed files so you can run them again quickly.

Scan game library: Lets SFF find games in your Steam libraries.

Patch / Unpatch Steam (DLL): On Windows only. Installs or removes two small files in your Steam folder so Steam reads the game data SFF prepares. The two DLLs are included in the steam_patch folder.

Sync saved LUAs to Steam: Copies your saved Lua files and manifests into Steam’s config so games work even without running another injector.

Settings: Change Steam path, GreenLuma folder, and other options.

**Keyboard**

You can type a number to jump to a menu option. Escape or Back goes back. Ctrl+C exits.

**Important files**

Settings are stored in `settings.bin`. Recent files are in `recent_files.json`. If something goes wrong, check `debug.log` in the SFF folder.

**Getting help**

Read the error message first. For more detail on features, see the [User Guide](USER_GUIDE.md) and [Feature Guide](FEATURE_USAGE_GUIDE.md).
