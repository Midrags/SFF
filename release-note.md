SteaMidra v6.4.7

What's new:

* Added a brand-new **native Python Steam CDN downloader for Linux**. Downloads now come directly from Steam's CDN using parallel chunk downloads, manifest parsing, AES decryption, and automatic decompression—no .NET runtime required. DepotDownloaderMod remains available as a fallback if needed.
* Native Linux downloads now support **incremental updates**. Existing game files are verified first, so only changed chunks are downloaded after a manifest update instead of re-downloading the entire game.
* Added a **download concurrency** setting to Download Settings. Choose anywhere from **8 to 64** concurrent chunk downloads, and the same setting is also applied to DepotDownloaderMod.
* Improved CDN server selection with smarter server weighting, retry rotation, exponential backoff, and HTTP connection reuse for more reliable and consistent download performance.
* Fixed Linux depot OS filtering. Downloads now correctly exclude Windows-only and macOS-only depots, matching DepotDownloaderMod's operating system filtering.
* Every ACF file written by SteaMidra is now marked read-only immediately, preventing Steam from reverting installed games back to the **Update** state.
* Restart Steam now displays live progress directly in the Web UI on Windows, with improved error reporting on both Windows and Linux.
* Self-updating is now much more reliable on slow connections. Added proper download and installer timeouts throughout the entire update pipeline.
* Fixed Linux downloads after the download bridge signature changed. The Web UI and backend now use matching arguments again.
* Store status cache now has automatic eviction, preventing memory usage from growing indefinitely while browsing games.

### Linux improvements

* Steam launched through SteaMidra no longer inherits AppImage environment variables, fixing silent launch failures on Fedora, CachyOS, and similar distributions.
* Fixed the Steam Native older-version downloader attempting Windows-only operations on Linux. The native path is now correctly limited to Windows, while the DepotDownloaderMod fallback starts downloads with the proper depot key data.
* SteamAutoCrack now works correctly from AppImages by writing temporary configuration files to the SteaMidra data directory and injecting API keys without triggering `Errno 30` errors.

### Windows improvements

* Restored proper window resizing by enabling the required native Windows resize frame for the frameless window.
* DDMod downloads that encounter the Windows socket handle leak (`10038`) now automatically retry without `CREATE_NO_WINDOW`, greatly improving download reliability.

Full detailed changelog is in CHANGELOG.md
