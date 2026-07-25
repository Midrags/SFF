SteaMidra v6.4.5

What's new:

* Older-version downloads now respect the provider you selected. Choosing Hubcap or Ryuu now correctly fetches Lua files from that provider instead of always falling back to Oureveryday.
* Depotless DLCs are now appended correctly to Oureveryday Lua files, bringing its behavior in line with Hubcap and Ryuu.
* Fixed the Headcrab installer filter breaking Bash scripts. CloudRedirect and Flatpak sections are now commented out instead of removed, preserving valid shell syntax.
* Window resize handles are now easier to grab, and the bottom corners correctly use diagonal resize cursors for smoother resizing.

### Linux improvements

* The **Add to Library / Fastest** download option is now hidden on Linux since LumaCore is Windows-only. Linux users now see only the supported DDMod direct download and Older Version download options.
* Linux downloads that generate an ACF now automatically fall back to DepotDownloaderMod instead of simply opening Steam, ensuring game files are actually downloaded to disk.

Full detailed changelog is in CHANGELOG.md
