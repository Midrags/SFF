SteaMidra v6.4.2

What's new:

* Home page hints have been redesigned into a proper FAQ with clearer explanations and troubleshooting steps.
* Remove DRM has been renamed to **Remove SteamStub DRM** to make its purpose clearer. It still uses the same Steamless-based, achievement-safe unpacking process.
* The UI switcher has been redesigned. Modern UI now has a proper button at the bottom of the Home page, Classic UI has a matching "Switch to Modern UI" button, and the old floating three-dot overlay has been removed.
* Frameless Windows title bar buttons are now much larger and easier to use, especially on high-DPI displays.
* Custom background images now clear correctly, and theme switching no longer restores old backgrounds unexpectedly.
* Store and Library cards now use GPU-accelerated rendering for smoother scrolling and hover animations.
* Hardware acceleration for 2D canvas and WebGL is now enabled in the modern UI, improving overall responsiveness on supported systems.
* Managed Library detection is more reliable and now finds Lua files from both current and legacy `saved_lua` locations.
* DepotDownloaderMod downloads now automatically retry once after temporary Steam CDN or network failures instead of failing immediately.
* Store search performance improved by caching normalized game names and optimizing internal text processing.
* Various internal performance improvements reduce unnecessary regex compilation and delay loading of cached file watcher data until needed.
* Added a comprehensive 136-test unit and integration test suite covering SteaMidra's core modules, download systems, parsers, provider logic, cloud saves, updater, and more.
* Library scanning is now much more robust. Missing, disconnected, BitLocker-locked, or inaccessible drives are skipped safely instead of causing crashes throughout the application.
* Drive detection has been rewritten to properly identify supported filesystems, detect locked volumes, and log exactly why drives are skipped during scans.
* Oureveryday-generated Lua files now include the correct base app decryption key and depot manifest size when available from the provider database.

### Linux improvements

* Running SteaMidra as an AppImage no longer fails when refreshing the provider cache. Cached data is now stored in a writable user directory instead of the read-only AppImage filesystem.
* DepotDownloaderMod automatically locates bundled OpenSSL libraries on Linux, improving compatibility with distributions such as Arch and CachyOS.
* The **Through Steam (Fastest)** download option is now hidden on Linux since LumaCore is Windows-only.
* SLSsteam's `config.yaml` now preserves comments and formatting when app IDs are added instead of rewriting the entire file.
* Repeated fallback debug logging has been rate-limited to prevent log spam when game list downloads fail.

Full detailed changelog is in CHANGELOG.md
