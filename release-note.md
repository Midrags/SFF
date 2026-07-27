SteaMidra v6.5.0

What's new:

### UI improvements

* Refreshed the window chrome with a cleaner, more modern layout. The traditional title bar has been removed, and the minimize, maximize, and close buttons now float neatly in the top-right corner.
* Window dragging is now done from the top of the sidebar, and the Web UI layout has been adjusted so the floating controls never overlap page content or logs.

### Fixes

* DLCs now appear correctly in Steam Properties on Linux. SteaMidra now registers DLC app IDs in SLSsteam's configuration, including both `AdditionalApps` and `DlcData`, and DLC Check updates automatically register newly added DLCs.
* Startup is much more responsive. Building the Steam app list now happens in the background instead of blocking the UI during launch.
* Fixed download location selection being ignored. When you choose a download directory, SteaMidra now respects it instead of silently using an existing ACF location.
* **Download Older Version** is working again. Older-version downloads now correctly honor the selected provider (Hubcap or Ryuu), install using the chosen manifest IDs, and no longer fail because of an invalid backend parameter.
* ACF files now always use the latest manifest IDs and Build ID from Steam appinfo, helping Steam correctly recognize installations and display **Play** instead of **Update**, even when you've intentionally installed an older version.

### Linux improvements

* Depot keys are now written to `config.vdf` on Linux, bringing the workflow in line with Windows. Steam is stopped before configuration updates on both platforms to avoid locked configuration files.
* DLC depot entries written to ACF files now include the correct `dlcappid` metadata from Steam appinfo, improving Steam's handling of installed DLC.

Full detailed changelog is in CHANGELOG.md
