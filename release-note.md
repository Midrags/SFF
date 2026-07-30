SteaMidra v6.5.6

What's new:

### Performance improvements

* Store startup is now much faster and more responsive. The game list is only built once, preventing multiple background threads from doing the same work simultaneously.
* Duplicate Store searches are now automatically merged, so repeated searches reuse the first request instead of spawning competing backend queries.
* Fixed the `games.json` retry logic. When the network is unavailable and SteaMidra falls back to the cached game list, retries now respect the cache timeout instead of continuously retrying in the background.
* Restored the native Windows title bar. Minimize, maximize, and close buttons are now handled by Windows again, fixing window resizing, taskbar auto-hide compatibility, and native hover effects.
* Long pages now scroll correctly, with visible scrollbars making it clear when additional content is available.

### Linux improvements

* DLC downloads now retrieve the actual depot content instead of only the manifest files. Downloaded DLCs now contain the required game files and work correctly after installation.
* DLC ACF generation now matches Steam's format by removing unnecessary `MountedDepots` and platform override sections.
* Fixed downloaded games being marked as corrupt after installation. SteaMidra now preserves the downloaded depot manifest IDs instead of overwriting them with the latest Steam versions, preventing Steam from deleting and re-downloading valid game files.
* Removed duplicate ACF writes from the DepotDownloaderMod download path. ACF files are now generated once after downloads finish with the correct installation size.
* Fixed the Store download dialog crashing on Linux. Crack Build ID information is now fetched asynchronously a few seconds after startup, ensuring Store searches never wait on network requests.

### Localization

* Added a complete **Simplified Chinese** translation for both the Classic and Modern interfaces, contributed by the community.
* Dynamic interface elements—including dialogs, status banners, tooltips, and placeholders—are now translated automatically after they appear, ensuring a fully localized experience.
* Technical terms are intentionally preserved in English across all supported languages for consistency.

### Tools

* Added a **File Validation** button for Library games. It uses DepotDownloaderMod's validator to verify installed game files against depot manifests without downloading the game again.
* Added shortcuts to SteaMidra's Lua, manifest, and depotcache storage locations, making manual cleanup and troubleshooting much easier.

### Fixes

* Fixed the game list updater crashing when the Steam Web API key is rejected. SteaMidra now shows a clear message explaining that the built-in API key may have been revoked and directs users to configure their own key in Settings.

Full detailed changelog is in CHANGELOG.md
