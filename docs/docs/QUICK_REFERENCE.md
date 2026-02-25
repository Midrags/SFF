# Quick Reference

**Run SFF**
```bash
python Main.py          # CLI version
python Main_gui.py      # GUI version
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

Sync saved LUAs to Steam: Copies your saved Lua files and manifests into Steam’s config so games work even without running another injector.

Settings: Change Steam path, GreenLuma folder, and other options.

**GUI version**

Run `python Main_gui.py` or `SFF_GUI.exe` for the graphical interface. All features are available as buttons. Game selection is a dropdown. Settings have their own dialog. Build the GUI exe with `build_simple_gui.bat`.

**Keyboard (CLI)**

You can type a number to jump to a menu option. Escape or Back goes back. Ctrl+C exits.

**Important files**

Settings are stored in `settings.bin`. Recent files are in `recent_files.json`. If something goes wrong, check `debug.log` in the SFF folder.

**Getting help**

Read the error message first. For more detail on features, see the [User Guide](USER_GUIDE.md) and [Feature Guide](FEATURE_USAGE_GUIDE.md).
