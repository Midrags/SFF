SteaMidra v6.5.8

What's new:

### New features

* Added **Steam Error 86** to the Home page FAQ alongside the existing Error 53 and 54 troubleshooting guides.
* Added an **Auto Update Games** button to the Home page **Quick Start** section, providing quick access to the per-game Steam Auto Update manager.
* Windows downloads can now prompt you to automatically enable Steam updates for newly downloaded games while preserving your existing Auto Update selections.
* Added a **Fix Hash Issue** button to **Quick Tools** on Linux. It automatically resets the Steam bootstrap with Headcrab, reapplies SLSsteam, and fixes common **"Unknown steamclient.so hash"** errors.
* Applying **Goldberg Emulator** now lets you choose between the **Windows (gbe_fork)** and **Linux (gbe_fork_linux)** versions.

### Improvements

* Completed the cleanup of deprecated features. Removed Workshop Browser remnants, HyperVisor dialogs, obsolete Quick Tools entries, unused settings, JavaScript handlers, CSS rules, and other leftover components from previously removed functionality.
* SLSsteam configuration generation is now more complete. Missing required fields are automatically added during setup, preventing common **"Missing key"** configuration errors.
* Updated the default SLSsteam configuration to improve compatibility with Steam Deck and Steam client updates by avoiding unnecessary hash-abort failures.
* Headcrab setup now automatically detects whether Steam is installed natively or through Flatpak and installs SLSsteam to the correct locations.
* Startup is noticeably faster. The game name cache now loads directly from disk during startup instead of waiting for a large online database download.
* Linux downloads now display a Steam library selection dialog before downloading, including a **Custom folder (outside Steam)** option for manual installations without ACF generation or SLSsteam registration.

### Fixes

* Fixed Hubcap API keys being requested again during downloads after already being validated in the Store tab.
* Improved Linux ACF generation to more closely match Steam's format, including additional metadata blocks and compatibility improvements.
* Fixed the Easy Anti-Cheat guide dialog being cropped in smaller windows. The dialog now scrolls correctly when needed.
* Fixed duplicate **[DEBU]** prefixes appearing in the live log panel.
* Resolved a deadlock that could freeze SteaMidra while refreshing the cached game name database.
* Removed automatic Steam client contribution and provider cache refresh timers during startup, reducing unnecessary network activity and improving launch performance.

Full detailed changelog is in CHANGELOG.md
