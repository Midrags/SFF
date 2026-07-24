SteaMidra v6.4.3

What's new:

* SteaMidra is now much more resilient to corrupted settings. If a crashed exit leaves the settings file unreadable, the app automatically resets to defaults instead of failing to launch.
* DDMod downloads on Windows are more reliable. Random "An operation was attempted on something that is not a socket" failures now trigger automatic retries, reducing failed depot downloads caused by Windows socket handle issues.
* The Library tab's Lure Fix now marks the patched ACF as read-only, preventing Steam from immediately reverting games back to the "Update" state.
* Linux users on CachyOS and similar distributions no longer encounter permission errors when the SLSsteam installer patches `steam.sh`.

### UI improvements

* Custom background images now clear correctly without requiring a restart, and theme switching no longer restores old backgrounds.
* The Settings page now displays the correct SteaMidra version instead of remaining on "Loading...".
* Google Drive connection status in Cloud Saves now updates in real time.
* Fixed the Library drive-selection dropdown flickering or disappearing on load.
* Removed Google Fonts from the UI, eliminating long startup delays on offline systems.

### Performance improvements

* Improved web bridge thread stability by preventing QThread objects from being garbage-collected while still running, reducing intermittent crashes.
* Several internal services now use thread-safe lazy initialization, preventing duplicate instances under heavy load.
* The game update state cache now automatically evicts old entries instead of growing indefinitely during long sessions.

### Build improvements

* Fixed PyInstaller build failures caused by references to the removed `static/` directory.
* The fallback provider depot keys database is now bundled correctly in frozen builds.
* Added missing Rich library hidden imports, preventing DLC Check crashes in packaged builds.
* Linux build scripts now automatically detect common library locations across Debian, Fedora, Arch, and similar distributions.
* Windows installer now verifies that version patching completed before continuing.
* AppImage builds now always restore executable permissions for `appimagetool`.
* Installation scripts now properly fail on download errors and no longer reference removed files.

### Linux

* Updated bundled Goldberg Emulator components to the latest **gbe_fork** release, including refreshed Windows DLLs, Linux shared libraries, Steam settings examples, lobby_connect, steamclient_loader, and the new `Steam.dll` for improved compatibility with older games.

Full detailed changelog is in CHANGELOG.md
