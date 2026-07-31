SteaMidra v6.5.7

What's new:

### Removed

* Removed **HyperVisor (HV/HVAuto) bypass support**. The third-party service hosting the required downloads became untrusted, so the feature has been discontinued. Utility functions previously shared with crack fixes have been integrated directly into SteaMidra.
* Removed **Workshop Items**, **Import Subscribed Mods**, **Workshop bypass downloads**, and **automatic Workshop import**.
* Removed **Achievement Data (UserGameStats)** and achievement schema downloads.
* Removed the **Mod Updates** checker. LumaCore now handles game update management.
* Removed the **Tools** tab, including the **GBE Token Generator** and **VDF Key Extractor**, as these relied on deprecated Steam Web API endpoints.
* Removed **Buzzheavier** support from Crack Fix downloads. Crack fixes now download exclusively through **Pixeldrain** using the built-in proxy bypass.

### Performance improvements

* Significantly improved startup time by removing full A–Z drive scanning during initialization. SteaMidra now scans only the Steam library folders configured in Steam's VDF files.
* Reduced unnecessary disk activity by debouncing cache writes. Cached data is now written at most once every five seconds during normal operation, while invalidation and cleanup operations still save immediately.
* Steam API diagnostic output now uses debug-level logging instead of `print()` calls, reducing console noise while keeping detailed diagnostics available when needed.

Full detailed changelog is in CHANGELOG.md
