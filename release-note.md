SteaMidra v6.5.9

What's new:

### New features

* Added **DepotBox** as a new download provider. DepotBox integrates directly with SteaMidra using its `/api/direct-lua` API, supports both **Starter** and **Pro** plans, and can be configured through the Settings page with your API key and subscription tier.
* DepotBox is now available as a download source in all three download dialogs alongside the existing providers.
* SteaMidra now automatically removes the **read-only** attribute from Steam library folders on Windows before downloads begin, helping prevent common **Disk Write Error** issues.
* Downloads are now registered with the built-in **Download Manager**, allowing active downloads to appear in the Downloads tab for easier tracking.

### Fixes

* Fixed a critical Windows freeze when using **Download through Steam (Fastest)**. An unnecessary manifest download step could block the application for 20–45 seconds while waiting on Steam, even when running in the background. The redundant operation has been removed, making Steam-native downloads start immediately.
* Greatly improved download responsiveness by removing excessive stdout/stderr forwarding during DepotDownloaderMod downloads. Progress updates now use dedicated progress events instead of flooding the UI with thousands of log signals every second.
* Fixed a Linux ACF writer crash caused by a missing `sys` import that could prevent ACF generation on Linux.
* Fixed CreamAPI configuration generation writing an invalid backup DLL path (`steam_api.dll_o.dll`). Backup DLL paths are now generated correctly.
* Fixed Linux installation scripts generating a `run.sh` launcher that pointed to the wrong application entry point.
* Optimized the Windows read-only folder fix. Instead of recursively scanning the entire Steam installation, SteaMidra now updates only the required Steam library root folders, significantly reducing unnecessary work before downloads begin.

Full detailed changelog is in CHANGELOG.md
