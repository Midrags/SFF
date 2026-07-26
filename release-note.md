SteaMidra v6.4.6

What's new:

* Fixed API keys and passwords disappearing between restarts on some Linux systems. The encryption key is now always backed up to a local fallback file, preventing key regeneration from making saved credentials unreadable.
* Simplified the Linux re-add game prompt. The options are now simply **Update** and **New** instead of lengthy descriptions.
* Fixed Linux depot OS filtering. SteaMidra now correctly downloads only depots matching the selected operating system instead of including Windows- and macOS-only depots by mistake.
* Every ACF file written by SteaMidra is now marked read-only immediately after creation, preventing Steam from reverting installed games back to the **Update** state.
* Restart Steam now reports live progress directly in the Web UI on Windows, with improved error reporting on both Windows and Linux.

### Linux improvements

* Fixed the Headcrab installer filter accidentally breaking installation scripts by removing valid Flatpak directory checks. The installer now blocks only actual `flatpak install` commands, preserving valid Bash syntax.
* Steam launched from SteaMidra no longer inherits AppImage environment variables, fixing silent launch failures on distributions such as Fedora and CachyOS.
* Fixed the Steam Native older-version downloader on Linux. Windows-only operations are no longer executed, and the DepotDownloaderMod fallback now passes the correct depot key data so downloads start properly.
* SteamAutoCrack now works correctly from AppImages. Temporary configuration files are written to the SteaMidra data directory when the application is running from a read-only AppImage, preventing `Errno 30` errors and ensuring API keys are injected correctly.

Full detailed changelog is in CHANGELOG.md
