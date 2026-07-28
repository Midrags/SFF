SteaMidra v6.5.1

What's new:

### UI improvements

* Window dragging now works properly. An invisible 56px strip at the top of the window lets you drag the app or double-click to maximize, without adding a visible title bar or wasting screen space.
* The Web UI now starts below the window controls, preventing the minimize, maximize, and close buttons from overlapping logs or page content.
* SteaMidra now automatically writes a `crash.log` file to the data directory whenever the application encounters an unexpected crash, making it much easier to diagnose and report issues.

### Fixes

* **Download Older Version** now works correctly with DepotDownloaderMod. The backend now accepts the required arguments, preventing crashes and ensuring your selected manifest IDs are correctly pinned before installation.
* DLCs now appear correctly in Steam Properties on Linux through proper SLSsteam registration using both `AdditionalApps` and `DlcData`.
* Startup is more efficient. SteaMidra no longer builds the Steam application list twice during launch, reducing unnecessary work and improving startup performance.

Full detailed changelog is in CHANGELOG.md
