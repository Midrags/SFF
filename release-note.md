SteaMidra v6.4.8

What's new:

* Added a built-in **native Python Steam CDN downloader for Linux**. Game files are downloaded directly from Steam's CDN with no .NET dependency, using parallel chunk downloads, AES decryption, LZMA/Zstd decompression, SHA1 verification, and HTTP keep-alive. DepotDownloaderMod remains available as a fallback.
* Native Linux downloads now support **incremental updates**. Existing chunks are verified before downloading, so only changed data is fetched when updating to a newer manifest.
* Added a **download concurrency** setting (8–64 threads). The same setting controls both the native downloader and DepotDownloaderMod, making it easy to tune performance for your connection.
* Fixed Linux DDMod downloads failing with bridge argument mismatch errors. The download bridge now supports both the old and new call signatures.
* Adding games to the Steam library no longer crashes when Steam has `config.vdf` locked. Locked files are now handled gracefully during backup and update operations.
* Fixed DepotDownloaderMod OpenSSL detection on Arch, CachyOS, and similar distributions by searching common system library locations when the .NET runtime does not provide its own OpenSSL libraries.

### Linux improvements

* Steam launched through SteaMidra no longer inherits AppImage environment variables, improving compatibility on Fedora, CachyOS, and other AppImage-based systems.
* Self-updates work reliably again. The installer now launches in a clean environment, survives SteaMidra closing, and automatically falls back to a headless update when no terminal is available.
* Depot OS filtering now defaults to **Linux**, correctly skipping Windows and macOS depots during downloads.

### Windows improvements

* Restored native window resize support for the frameless window by applying the required Windows resize frame.
* LumaCore installer now waits longer for Steam to fully exit before replacing DLLs. If files remain locked, SteaMidra now shows a clear **"Close Steam and try again"** message instead of failing unexpectedly.

### Home page

* Library browsing and searching are faster. Installed games are cached for one hour with background refresh, and the game catalog is parsed once into memory instead of being reloaded on every search.

### Performance improvements

* Reduced UI overhead by lowering log flush frequency, batching update checks more efficiently, and automatically limiting the store status cache size. Together these changes make the interface feel smoother during heavy workloads.

Full detailed changelog is in CHANGELOG.md
