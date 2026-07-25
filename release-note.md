SteaMidra v6.4.4

What's new:

* Fixed Linux Steam native downloads incorrectly showing **Update** instead of **Play**. The generated ACF files now include all of the metadata Steam expects, matching real Steam installs more closely.
* Fixed the root cause of rare `settings.bin` corruption. Settings writes are now fully thread-safe, preventing simultaneous writes from corrupting the configuration file.
* Steam Deck and SteamOS now handle game list downloads much more reliably. HTTPS requests automatically try multiple certificate sources before falling back to an unverified connection, eliminating common SSL certificate errors.
* Fixed Linux AppImage installations failing during the .NET 9 bootstrap process with `rl_print_keybinding` symbol lookup errors. The installer now launches with a clean environment to avoid AppImage library conflicts.

### UI improvements

* Title bar buttons have been enlarged again for better usability on high-resolution and high-DPI displays. Close, maximize, and minimize buttons are now significantly larger and easier to click.

Full detailed changelog is in CHANGELOG.md
