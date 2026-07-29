SteaMidra v6.5.5

What's new:

### Store improvements

* Store search results now display the required **Build ID** whenever crack files are available, making it easier to match fixes with your installed game version.
* Older Version downloads now let you exclude individual depots directly from the version picker. Unchecked depots are automatically removed from the generated Lua before downloading.

### Fixes

* Updated the `00_LetUpdate_override.lua` format to match LumaCore's new manifest pinning system. Games marked for auto-update now update normally, while unchecked games remain pinned. Existing override files are migrated automatically, and shared redistributable depots are always excluded.
* Fixed the Steam Updates dialog reversing checked and unchecked states when reopened.
* Auto Update functionality is now correctly limited to Windows. Linux always reports the feature as disabled.
* Newly downloaded games are no longer automatically enabled for updates unless the corresponding setting is turned on.
* Improved depot OS filtering by falling back to depot name platform tags when Steam does not provide `oslist` information.
* Fixed CreamAPI configuration generation so `orgapi` paths are written correctly.
* Added **Simplified Chinese** and **Traditional Chinese** to the language settings.
* SLSsteam configuration files now always include the required fields, preventing missing configuration notifications.
* Removed a duplicate ACF write from the DepotDownloaderMod download flow, reducing unnecessary disk operations.

Full detailed changelog is in CHANGELOG.md
