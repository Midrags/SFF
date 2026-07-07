SteaMidra v6.4.0

What's new:

* Steam native downloads now write real depot manifest blocks into the ACF instead of only creating a bare app state. Steam should now see the selected depots, build ID, size, and Linux Proton config correctly instead of trying to repair the install.
* Steam appinfo timeouts are handled better. SteaMidra now retries with longer waits, logs the Steam server state, and falls back to cached or local manifests instead of marking the app as broken for the rest of the run.
* Oureveryday downloads now keep the fallback log cleaner. GitHub mirror coverage is only printed when SteaMidra actually reaches the GitHub fallback, after the request-code mirrors have been tried.
* Stale same-depot manifests are now cleaned from Steam’s live depotcache after SteaMidra detects the current manifest IDs, preventing old saved files from overriding the update you selected.
* DepotDownloaderMod failures no longer show fake success messages. If every depot fails or the download writes 0 bytes, the tracker and notification now correctly say the file download is incomplete.
* Store tab now includes a Depot Keys refresh button.
* Provider depot key cache now refreshes automatically every 6 hours based on the last attempt, while manual refresh still runs immediately.
* Library scans now tag games that have SteaMidra Lua files.
* Added a SteaMidra-only library filter, making it easier to see only games managed by SteaMidra.
* Library covers are now cached, and cards render in batches so large libraries feel lighter and smoother.
* Settings now supports a custom UI background image and accent color.
* Custom background images are copied into SteaMidra data and can be cleared without deleting or touching the original file.
* Added an opt-in setting for Steam update prompts on newly added SteaMidra games.
* The new update-prompt setting warns that cracked or protected games can break if Steam updates them.

Full detailed changelog is in CHANGELOG.md
