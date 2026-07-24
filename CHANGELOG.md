# Changelog

## 6.4.3

### Fixes

- SteaMidra no longer refuses to open after an update because of a corrupted settings file. A partial write during a crashed exit used to leave settings.bin in a state that msgpack couldn't read, and the error happened before Qt had a chance to show anything. Now corrupted settings reset to defaults with a log line instead of silently crashing.
- DDMod downloads on Windows stopped randomly failing with "An operation was attempted on something that is not a socket" across all depots at once. This was a Windows socket handle leak from the subprocess pipe setup. Each depot now retries with a longer wait when this specific error code is hit, and the handle table resets between attempts.
- The Lure Fix button in the Library tab now sets the ACF read-only after patching it. Without this, Steam would overwrite StateFlags back to the update-pending value on the next launch and the game would flip back to "Update" instead of "Play".
- Linux users on CachyOS and other distros no longer get "Permission denied" when the SLSsteam installer tries to patch steam.sh. SteaMidra now ensures the file is writable before touching it.
- Settings could silently lose changes when two things tried to save at the same time. set_setting and clear_setting now use a threading lock so the file write is serialized, and msgpack errors that used to crash the whole app now just reset to defaults.

### Ryuu

- Ryuu got a second API key slot in Settings. The original key is now labeled Reseller Key and uses the auth_code URL parameter for secure_download, resellerlua, and resellerrequestupdate. The new Premium API Key slot uses the X-Auth-Key header on the newer /api/download, /requestupdate, /request, and /requestbranch endpoints. Both keys are tried, premium first for downloads, reseller as fallback.
- The Ryuu download modal now has a branch dropdown that populates from Steam appinfo when the modal opens. Public is default, every branch Steam reports shows up with its description. A Refresh button next to it re-fetches from Steam CM and invalidates the cache first so you always get the latest branch list.
- A Request Branch button sits next to the branch selector. Select something other than public, click it, and SteaMidra asks Ryuu to add that branch to the database using the premium API key. The call runs in the background so the UI doesn't freeze while Ryuu processes it.
- File type selection: ZIP (lua + manifests, default), lua only, or manifests only. Passed through as the file_type parameter on both the old and new Ryuu download endpoints.

### Performance

- When SteaMidra minimizes to the system tray, the web view is hidden so Chromium releases its GPU textures and render surface. Background memory drops from around 300 MB to about 80 MB. Restores when you bring the window back.

### UI

- Custom background images finally clear properly without needing a restart. The clear handler was racing with a deferred settings fetch that re-applied the old image. Same fix applies to theme switching.
- The Settings page version label actually shows the version now. It was calling the wrong bridge method and getting stuck on "loading..." forever.
- The GDrive connection status in Cloud Saves now updates in real time. Same wrong bridge call pattern, same silent failure.
- The Library page drive-select dropdown no longer flickers and dies because a duplicate CustomSelect was being created on page load.
- Google Fonts are gone from the CSS. The external import was blocking the entire UI for 30+ seconds on offline machines while QtWebEngine waited for the network timeout.

### Performance

- QThread objects in the web bridge are now stored in a list alongside their workers. Python's GC used to nuke the C++ thread object while the event loop was still running, which caused intermittent crashes under load.
- Four lazy-singletons (cache, analytics, notifications, recent files) now use double-checked locking. Two threads hitting them at once could create duplicate instances with desynced state before.
- The game update state cache no longer grows forever. When it passes 1500 entries the oldest ones get evicted so checking hundreds of games doesn't leak memory over days.

### Build

- All three PyInstaller spec files no longer reference the removed static/ directory, which was causing CI builds to fail at "Appending datas" before the actual packaging step.
- The fallback depot keys database is now bundled from the correct path (sff/lua/ not sff/) so the provider database actually lands in the frozen build.
- Missing rich._unicode_data, rich.box, and rich.text hidden imports are now declared in both the GUI and Linux specs. The DLC check was importing these at runtime and crashing when they weren't bundled.
- The Linux build script no longer assumes every distro uses /usr/lib/x86_64-linux-gnu. It tries that path first, then /usr/lib64, then /usr/lib, so Fedora and Arch CI containers don't break.
- The Windows installer script now checks whether the Python version-patcher actually ran before continuing to NSIS compilation.
- The AppImage build script always re-chmods appimagetool before running it, even if the file already exists from a cached download.
- The install script no longer tries to delete a static/ directory that was removed, and curl now uses the fail-on-error flag so a 404ed dotnet-install.sh doesn't get executed as a bash script.

### Linux

- Goldberg emulator DLLs and .so files were refreshed from the latest gbe_fork build. Windows DLLs (regular and experimental), Linux .so files, steam_settings examples, lobby_connect, steamclient_loader, and the new Steam.dll for old-game compatibility are all updated.

## 6.4.2

### Home page

- The Remove DRM button got renamed to Remove SteamStub DRM so people stop asking what "DRM" means. Same tool underneath, same achievement-safe Steamless unpack.
- Home page hints got reformatted as an FAQ with actual answers instead of vague warnings. The SteamStub entry now tells you to look for the shipping.exe inside Binaries\Win64 instead of the root exe when Steamless says "Failed to unpack file". Content Still Encrypted now suggests re-adding the game from the store instead of just running Update All Games.
- The UI switcher moved from a glitchy floating 3-dots button into a proper button at the bottom of the modern Home page. Classic UI gets a matching Switch to Modern UI button on the tab bar corner. Both work the same, the 3-dots overlay is gone.

### UI

- Title bar buttons on frameless Windows got a lot wider. Close, maximize, and minimize are now 130px across instead of the old cramped size. They were nearly invisible before on high-DPI screens.
- The old floating UI toggle bar that sat on top of the title buttons and glitched through QWebEngine is completely removed. No more disappearing buttons behind the overlay.
- Custom background images properly clear when you hit the Clear button now. The handler was racing with a deferred settings fetch that re-applied the old image before the clear could finish. Same fix applies to theme switching — the custom background fetch only fires when a custom background is actually set.
- Game cards in the Store and Library got GPU layer hints so hover animations and scroll don't trigger full page re-flows. Cards promote to their own composite layer instead of invalidating the whole body.
- The QWebEngineView now has hardware-accelerated 2D canvas and WebGL explicitly enabled. Scrollbars and error pages are disabled to reduce compositor overhead. Combined with the card layer hints, UI feels smoother on mid-range hardware.
- The installed games library now scans both the root-folder and current-working-directory saved_lua paths when looking for SteaMidra-managed entries. Lua files saved by older installs sitting in Path.cwd()/saved_lua/ won't be invisible to the Managed filter anymore.
- DDMod downloads now retry each depot once on transient failures. Socket errors, network hiccups, and Steam CDN refusals that used to kill the whole download with "Depot exited with code -6" now get a second attempt after a short wait.

### Performance

- Every "import re" that was buried inside hot functions got moved to module level. The ANSI escape stripper, DDMod progress regex, filename sanitizer, and the yaml config parser no longer recompile their patterns on every call.
- The store search normalizer that strips trademark marks and Unicode accents now caches results. Searching the same game name twice hits the cache instead of running Unicode NFKD decomposition again.
- File watcher dates cache doesn't load from disk at import time anymore. It waits until depot history actually needs date info.

### Testing

- A 136-test unit/integration suite landed covering every core module: utils, structs, updater, cache, download manager, cloud saves, Lua generators, VDF parsing, ACF parsing, zip, yaml config, preserver, provider, Steam client, and all the hoisted regex patterns.

### Fixes

- Access denied crashes when Steam's libraryfolders.vdf lists a drive that doesn't exist (BitLocker-locked, disconnected network drive, or a stale Q: that was never there) are now handled everywhere. The library scan, installed games dropdown, save watcher, launch options reader, manifest update passes, and library scanner all skip inaccessible drives instead of crashing the whole operation. Each library gets its own OSError guard so one bad entry stops killing the loop for the rest.
- Drive scanning no longer blindly hits every letter from A to Z. A new disk_utils module classifies each drive before touching it, checks filesystem type (NTFS/FAT32/exFAT/ReFS only), detects BitLocker-locked volumes, and logs every skip with a reason so debug logs show exactly which drive failed and why instead of a generic PermissionError traceback.
- Oureveryday-generated lua files now include the base app's decryption key and the depot manifest size. Before this, addappid(3527290) had no key even when the provider database had one, and setManifestid had no size field. Both now match the correct format.

### Linux

- Running from an AppImage no longer crashes with "Read-only file system" when the provider cache refreshes. fallback_depotkeys.json is now written to a writable user data directory instead of inside the squashfs mount.
- DDMod downloads on Linux now find the bundled OpenSSL libraries automatically. Dotnet apps (DDMod) need libcrypto.so.3/libssl.so.3 for HTTPS depot fetches, and distros like CachyOS/Arch don't always ship them at the system level. The DDMod subprocess now gets LD_LIBRARY_PATH pointing at the runtime's shared libraries.
- The DDMod choose modal on the Home tab hides the "Through Steam (Fastest)" button on Linux. LumaCore is Windows-only and the button led users to a path that silently didn't work like it does on Windows. Linux users only see "Via DepotDownloaderMod".
- SLSsteam's config.yaml no longer gets reformatted when SteaMidra adds app IDs during a download. The old code did a full YAML parse/dump cycle that stripped all comments and reordered sections, which SLSsteam couldn't parse cleanly. Now it uses the same regex-based append that the rest of the yaml_config module uses, preserving every comment and setting.
- The "Fallback data: games=0 entries" debug log line that sprayed hundreds of times when the game list fetch failed is now rate-limited to once per minute.

## 6.4.1

### Settings

- Modern Settings now has backup buttons near the top. Export writes a JSON without saved secrets, and Import reloads the visible settings after it applies the file.

### Store / download

- The older-version picker can import one or more saved SteamDB depot pages into the selectable history list. Helps when the live history list is blocked or empty and you already have the depot pages saved.

### Fix Game / Steamless

- Bundled Steamless was refreshed to 3.1.0.5 with the matching plugin DLLs. Remove DRM uses the newer unpacker now, and the Steamless GUI build is included too for manual checks.

### UI

- Modern UI now fills the window instead of sitting under an empty host strip. The Classic UI switch is tucked behind a small corner button so it stays out of the way until you need it.

### Docs

- Docs now match the current online-fix flow and Settings backup UI. online-fix stays browser-open only, with downloads and login handled on the website.

## 6.4.0

### Store / download

- Steam native downloads now write real depot manifest blocks into the ACF instead of a bare app state. Steam should see the selected depots, build ID, size, and Linux Proton config instead of trying to repair a broken install.
- Steam appinfo timeouts are less nasty now. SteaMidra retries with longer waits, logs the Steam server state, and falls back to cached or local manifests instead of marking the app as broken for the rest of the run.
- Oureveryday downloads no longer print GitHub mirror coverage before the request-code mirrors get their shot. GitHub only shows up when SteaMidra reaches that fallback.
- Stale same-depot manifests get cleaned from Steam's live depotcache after SteaMidra knows the current manifest IDs, so old saved files stop winning over the update you picked.
- DepotDownloaderMod failures no longer end with a fake success message. If every depot fails or the download writes 0 bytes, the tracker and notification now say the file download is incomplete.
- The Store tab now has a Depot Keys refresh button, and SteaMidra refreshes the local provider cache every 6 hours based on the last attempt. Manual refreshes still run immediately.

### Library / UI

- Library scans now tag games that have SteaMidra Lua files, add a SteaMidra-only filter, cache cover URLs, and render cards in batches so large libraries feel lighter.
- Settings now supports a custom UI background image and accent color. Images are copied into SteaMidra data and can be cleared without touching the original file.
- A new opt-in setting can enable Steam update prompts for newly added SteaMidra games. The setting warns that cracked and protected games can break after Steam updates them.

## 6.3.9

### Store / search

- Store search now waits for Enter or the Search button, so typing does not spam backend searches anymore. Ranking is tighter too, with app IDs, exact names, prefixes, word-start hits, and aliases beating loose fuzzy matches.

### Logs

- Home Live Log and the native Logs window now obey a line limit setting, default 100. Long runs like Update All Games stop dragging the UI into a huge scrollback.

### LumaCore library reliability

- Lua hot reload is steadier now. New numeric lua files refresh the Steam library without needing three Steam restarts, and removed lua files stop leaving stale cards behind.
- Purchase and Install states should settle faster after startup. LumaCore attaches the package hooks earlier, checks the real app IDs it injected instead of trusting a big enough count, and retries from safe late UI frames when Steam loads package data slowly.
- Offline startup got less fragile. If Steam has enough local package data, LumaCore can seed the lua apps without waiting for a full login refresh.

### LumaCore diagnostics

- `status.json` now says why a broken install is broken instead of giving you a dead folder with almost no logs. Missing package data, empty lua loading, waiting-for-login cases, hook misses, ownership checks, cloud decisions, and the latest SteamStub detection all get surfaced there.
- Release and Debug builds now stamp `status.json` with build config, build time, package capture state, and the latest online-fix payload state, so old DLLs and missed child-process injection show up without needing verbose logs.

### LumaCore cloud / saves

- Managed games that the active account does not own keep Steam Cloud blocked without touching save folders or asking Steam to close cloud state. That protects local saves without causing the cloud error popups seen in the broken test build.
- Family-shared games are separated from fake-managed games now. If Steam marks a lua app as borrowed or family shared, LumaCore leaves its Steam Cloud answer alone instead of treating it like an unowned unlock.
- Managed games now prefer their existing app ticket or userdata SteamID before using the current login account. Satisfactory-style saves should stay in the same account folder instead of vanishing because the game looked under a new ID.

### LumaCore SteamStub

- SteamStub auto routing can detect Stray-style protected child binaries before launch and route through 480 without needing a hardcoded appid.
- SteamStub detection is stricter now. Generic protection diagnostics no longer launch normal managed games as 480, so false Spacewar launches should stop.
- The dedicated SteamStub route stays separate from manual `-onlinefix`. Manual online-fix keeps its multiplayer path, while SteamStub auto keeps Steam tracking on 480 and hides the real game from the running-app packet.

### LumaCore online-fix

- Manual `-onlinefix` keeps the existing multiplayer route, but EOS games with launcher-child splits now get the payload loaded into the child process too. Mecha Chameleon no longer gets stuck on the missing auth-token login screen after Steam starts the real game exe.

## 6.3.8

### Bug fixes

- Update All Games no longer prompts for a request code when automated sources fail. The manual CDN prompt is gone, the full automated cascade runs and reports failure silently, matching the parallel download path.
- Update All Games now respects the Auto Update toggle. Games you unchecked in the Auto Update modal are skipped entirely, so their manifests stay at whatever version you pinned.
- Removed the youxiou.com link from the fallback sources list.
- Check for Updates in Settings now tells you when SteaMidra is already current instead of leaving the button spinning forever.
- DLC Check can now add appid-only DLCs from the Oureveryday button. New DLCs without separate depot tags get written into the parent lua instead of throwing the old "no depots tagged" error.

### Home page

- The LumaCore notice checks the Steam folder before showing up. Missing installs and available updates get a clear callout, and current installs keep the Home tab clean.

### Oureveryday / manifest download

- The main request-code mirror now gets the tool user-agent it expects, and SteamRun JSON replies are parsed too. Oureveryday downloads and Update All Games stop skipping a working mirror because Cloudflare disliked the default HTTP client.

### LumaCore library / login

- Steam library refresh now publishes only numeric lua filename roots. Depot, DLC, and shared body IDs still unlock packages and manifests, but Steam no longer tries to render them as full library apps and hangs on login.
- License refresh is back on the launch-safe path. Ownership checks answer ownership only, AppLicensesChanged asks Steam for a full reload, and the package-0 refresh loop is gone.

### LumaCore achievements

- Numeric lua filenames now auto-enable stats and achievements for that app. `setStat(appid)` is only needed for manual cases, and the old two-argument form still works when you need a specific SteamID.
- Achievement fetching now tries LumaCore's SteamID pool and keeps the first useful schema or stat response. If every remote reply fails for a Lua-root app, Steam keeps the local schema instead of blanking the achievement page.

### LumaCore manifest fetch

- LumaCore's in-Steam manifest resolver now uses the primary provider's required compatibility user-agent for request codes. Steam downloads stop falling through to "no internet connection" when the provider has a valid code.

### Linux

- CachyOS setup no longer lets AppImage library paths break 7z with the readline symbol error. SLSsteam extraction tries the bundled Python extractor first, then retries system 7-Zip with a clean env.
- Restart Steam also checks the Steam folder for manually copied SLSsteam libraries after the managed install paths, so manual recovery attempts are not ignored.

### LumaCore launch fixes

- Known Steam Stub games now use a dedicated 480 tracking route instead of borrowing the manual online-fix path. Steam sees 480, the game-facing overlay, ticket, and stats identity resolve to the real app, and manual `-onlinefix` keeps its full online-fix behavior.
- SteamStub ownership tickets now prefer the app-7 source from Steam's user-local config store and keep the IPC reply layout Steam expects. Teardown no longer bounces between error 54 and 86 during launch.
- LumaCore validates AppTicket SteamID and appid before serving it, so stale cross-app tickets get rejected instead of poisoning the next launch. Target-valid fallbacks stay in place until a better app-7 ticket is available.

### LumaCore save protection

- LumaCore now turns native Steam Cloud off for managed games that the active account does not own. Owned games keep Steam Cloud, and managed story games stop letting Steam pick the wrong account folder or wipe local progress after a break.

### Store / search

- Store results only render the visible grid or list view, and cover images get cleared when you leave the tab. Visiting multiple pages in one session should stop ballooning RAM from hidden cover art.

## 6.3.7

### Bug fixes

- Remove DRM button from the web UI no longer crashes. It was running on a background thread and trying to spawn QThreads from there, which Qt6 rejects. Now routed to the main thread.
- Auto Update checkboxes no longer cross-contaminate between games. Shared redist depots (DX, VC++, .NET runtimes) were leaking into the global override file and unchecking one game would silently uncheck others sharing those depots. Redist depots are now filtered out of the exclusion set.
- Provider metadata enrichment now resolves parent app IDs for orphan depots from the bundled provider database. Depots from config.vdf and lua files without a plain addappid line get proper names, kinds, and parent info instead of staying as generic "Depot 12345" entries.
- Modern GUI blank/grey screen on some NVIDIA/AMD setups fixed. Removed `--enable-zero-copy` and `--enable-gpu-rasterization` from the default Chromium flags. Added renderer crash recovery that auto-reloads the page once, and a dark error page when the page fails to load entirely.

### Oureveryday / manifest download

- Added three GitHub manifest mirror repos to the oureveryday cascade: mejikuhibiniu1/k25FCdfEOoEJ42S6 and Sainan/k25FCdfEOoEJ42S6 join the existing qwe213312 repo. All three are tried in sequence after the GMRC mirrors, so if one is down the others catch it.
- Cascade reordered: mirrors → GitHub repos → ManifestHub → encrypted GMRC endpoint as last resort. ManifestHub no longer blocks GitHub access when it is down.

### Cloud saves

- Custom save paths from the Ludusavi manifest database (22k+ games) are now backed up alongside Steam userdata. Games like Lies of P that save outside the Steam remote folder are included.
- All Save Locations now groups every save path for the same game into one backup and restores each recorded path together. Old Games-folder backups still show up, so older saves don't vanish after updating.

### Settings

- Removed online-fix.me username and password fields. The feature doesn't auto-download anymore so the credentials were dead weight.

## 6.3.6

### Bug fixes

- Remove DRM button from the web UI no longer crashes SteaMidra. It was running on a background thread and trying to create QThreads from there, which Qt6 rejects. Now routed to the main thread like SteamAutoCrack.
- The `add_ids` warning is gone. LumaCoreManager writes minimal lua stubs for each app ID instead of throwing NotImplementedError on every download. No more crash during local imports either.
- Home tab game dropdown refreshes when you navigate back to it. It used to only refresh on a 10-minute timer, so newly installed games wouldn't appear until you restarted or waited.
- Hubcap key decryption failures log at startup so you can tell when the encryption key changed and your stored API key became unreadable.

### Cloud saves

- Custom save paths for games that save outside Steam userdata are now backed up. Uses the Ludusavi manifest database covering 22k+ games. For example, Lies of P saves under the game folder at `LiesofP/Saved/SaveGames/` are included alongside the Steam remote data.

### Settings

- Removed online-fix.me username and password fields from Settings. The feature doesn't auto-download anymore so credentials are dead weight.

## 6.3.5

### Bug fixes

- Right-click "Add to SteaMidra" actually works now. The frozen build was ignoring the `-f` argument, so right-clicking a `.lua`/`.zip` opened the window and did nothing. Now forwards the file to a running instance via IPC and processes it immediately on fresh launch. Lucas559-noob reported it.
- Hubcap API key no longer silently vanishes between restarts. The settings decryption layer now logs a clear warning when the encryption key has changed, and the web bridge preloads the key at startup instead of waiting for the first search to fail.
- Hubcap key saving was accepting any garbage string including entire log dumps. connect_store now validates the key format before writing it to settings.
- The Depot OS dropdown in the download modals had a white-rectangle rendering glitch on dark themes. Both selects now use the app's custom dropdown system instead of native Chromium popups, and the library drive picker is wired up too.
- Hubcap game names with em dashes or other Unicode characters no longer crash the store search with an ASCII encoding error. All exception loggers in store_browser use repr formatting now.
- Bulk import cancel button now reliably hides the progress bar.

### LumaCore setup

- LC Auto Setup was sometimes picking a stale release or the `Source code (zip)` tarball instead of the actual DLL archive. GitHub API calls now bust the CDN cache and the fallback skips source archives.
- When a DLL is missing from the downloaded archive, the zip file listing is logged alongside the error so the problem is immediately visible.

### Home page

- The yellow hint banner collapsed by default, saving vertical space for regular users. Click the arrow to expand.
- DLC Unlockers card moved to the bottom, next to Quick Tools.
- Let Updates renamed to Auto Update.

### Store / search

- A Disconnect Hubcap button sits next to the NSFW toggle. Drop the Hubcap API connection and fall back to bare Steam search without reloading.

### Crack Files

- Build ID from crackfiles.json shown next to game names when picking a fix.

## 6.3.4

### Home page

- The yellow hint banner on the home page now has a collapsible arrow button. Tuck the SteamStub / EAC / Content Still Encrypted wall of text away and bring it back with one click. Defaults to expanded.
- DLC Unlockers card moved to the bottom with Quick Tools. DLC Check is the primary DLC tool now, the unlocker stays available when you need CreamAPI or SmokeAPI.
- Let Updates renamed to Auto Update on the button.

### Crack Files

- Build ID from crackfiles.json shown next to each game name when picking a fix so you can match it against your installed version.

### Bug fixes

- Bulk import cancel now hides the progress bar when you cancel. It used to linger on screen.
- The GMRC HTTPS mirror cascade had a name mismatch that broke the fallback decrypt step. Fixed.
- `download_game_fastest` was referencing an undefined variable on success. Cleaned up.
- Bridge call queuing lost arguments when the bridge had not loaded yet. Queued calls now replay with the correct method and args.
- GDrive status check in Cloud Saves always read as disconnected. Now shows the real state.
- Provider depot key cache was never cleared after a refresh, making the update useless until restart. Clears on every provider update now.
- LumaCore `add_ids` was a silent no-op. Now raises NotImplementedError so callers can log it.
- The `os.access()` permission check in DLC unlocker validation never actually checked the result. Fixed.
- Update checker was collecting depot tokens but dropping them at the return boundary. Now returned alongside games.
- Settings file and libraryfolders.vdf writes now use atomic temp-file-then-rename. Crashing during a save no longer corrupts settings or Steam's library list.
- Store tab now guards against double-clicking Search, which was spawning duplicate threads.
- Skeleton card CSS had two overlapping definitions with dual animations. Merged.
- Provider depot key lookups in the Lua generator now load the JSON once per render instead of once per depot.
- `datetime.utcnow()` calls replaced with`datetime.now(UTC)` in depot history caching.
- Right-click "Add to SteaMidra" now actually processes the file. The frozen build was ignoring the `-f` argument because `Main_gui.py` never parsed it, so right-clicking a `.lua` or `.zip` opened SteaMidra and did nothing. Now it forwards the file to a running instance via IPC, or processes it fresh on launch. The `SingleInstanceGuard` carries the file path alongside the show request so the running window acts on it.

## 6.3.3

### Linux

- Fixed a Linux crash where the GUI tried to import a class that did not exist in steam_path.py. norduk reported it, the finder class now wraps the existing steam path probe so Ubuntu, Arch, CachyOS, and Flatpak installs launch again.

### Store / search

- A Disconnect Hubcap button lands in the web Store tab next to the NSFW toggle. Click it to drop the Hubcap API connection and fall back to bare Steam search without reloading.

## 6.3.2

### Provider / Lua

- Added the provider cache/update/contribution path, grouped Lua output, and parser support for optional `setManifestid` size arguments.
- Added safer Google Drive release credential generation and stopped Drive API backups from creating duplicate `steamidra_meta.json` files inside game save folders.
- Added LumaCore backup proxy build plumbing for `xinput1_4.dll` and continued hot-reload hardening.
- Local archive imports now stay local. Picking a `.lua`, `.zip`, `.rar`, or `.7z` no longer falls through to Hubcap, Ryuu, Oureveryday, or DDMod unless the user picked an actual download path.
- Linux depot downloads now expose Auto, Windows, Linux, and All depots so Steam Deck users can pull native Linux builds instead of being forced through Windows depots.
- Multiplayer Fix overhauled. The old automatic download flow is gone, it now searches online-fix.me for the game and opens the result in your browser. First-time users see a popup explaining the change with links to the site and Discord. The old code is backed up, not deleted.
- Library Update and Update All Games ignore old Lua manifest pins when refreshing to the latest Steam CM build. If the saved Lua is missing, Library Update now patches the ACF from public Steam CM data instead of dying at "No saved .lua".
- LumaCore now records Steam IPC pipe handshakes against the real process PID, creation time, image name, and appid. This gives launcher-heavy games a steadier per-pipe identity for ticket and stats handlers without relying only on one global launch appid.

### LumaCore — Denuvo DRM support

- Denuvo-protected games now work through the family sharing bypass. LumaCore auto-detects Denuvo in running game processes via three methods (OEP pattern, protected blob scan, and legacy section string check), opens an authorization window for the first N handshakes, and serves spoofed owner SteamIDs during that window.
- The main game executable is always scanned regardless of size. Older Denuvo titles like Sniper Elite 4 and Sonic Forces used to fall under the 80 MB detection floor and silently slip through, they now get caught.
- An eticket safety net kicks in when detection misses a real Denuvo build but an EncryptedAppTicket exists for the app. Auth engages anyway instead of giving up.
- New Lua bindings: `forcedenuvo(appId)` forces Denuvo auth when detection misses, and `addprocess(exeName, appId)` maps process names to AppIds for games that don't set SteamAppId in their environment block.

### LumaCore — EOS multiplayer bridge

- LumaCorePayload.dll injected into online-fix games bridges Epic Online Services for multiplayer lobbies. Auto-creates device IDs, strips presence flags on lobby creation, and self-propagates to child processes via CreateProcess hooks. No config needed beyond the `-onlinefix` launch flag.

### LumaCore — on-demand e-ticket minting

- New `seteticketurl(url)` Lua binding. Set a URL template with `{appid}` and LumaCore issues an HTTP POST to fetch a fresh EncryptedAppTicket at launch. Denuvo games that nonce-bind their tickets get a minted ticket instead of hitting the pre-baked one.

### LumaCore — proxy cooperation

- xinput1_4.dll now ships alongside dwmapi.dll as a backup injection gate. Both proxies check if LumaCore.dll is already loaded before calling LoadLibraryA, so they cooperate through the OS loader lock instead of racing. If dwmapi fires first, xinput1_4 skips.

### LumaCore — new Lua bindings

- `lcHttpPost(url, body)` — HTTP POST to allowlist-gated hosts.
- `fetchManifestCode(gid)` and `fetchManifestCodeEx(appId, depotId, gid)` — call registered manifest code functions from Lua.
- `getCachedAppTicket(appId)` and `getDecryptionKey(depotId)` — read cached tickets and keys from the registry, returned as hex.
- `addtoken(appId, accessToken)` — register package access tokens for license validation.
- `setAppticket(appId, data)` and `setEticket(appId, data)` — inject pre-built ticket blobs directly.

### LumaCore — manifest fetch

- Manifest download bridge now tries HTTPS endpoints first before falling back to HTTP. The three-provider chain resolves faster when the primary is up and keeps working when it is not.

### LumaCore — achievement fixes for online-fix

- Achievement callbacks now correctly rewrite m_nGameID for online-fix games. UserAchievementStored, UserAchievementIconFetched, UserStatsReceived, and GlobalAchievementPercentagesReady all bind to the real game instead of appid 480. Achievements unlock on the right game.

### LumaCore — IPC dispatch survives Steam updates

- IPC method specs (funcHash, fencepost offset, argument count per method) are now loaded from per-build TOML files instead of hardcoded. When a Steam client update changes internal hashes, LumaCore picks up the new spec from the network mirror cache on next launch. No rebuild needed.

### LumaCore — config hot-reload

- Settings in lumacore.toml now reload when the file changes on disk. No need to restart Steam after flipping a toggle.

### LumaCore — process extension injection

- Config-driven DLL injection into game processes via lumacore.toml. Point `processExtensionX86` and `processExtensionX64` at DLLs and LumaCore loads them into matching game processes at launch.

### LumaCore — pipe identity tracking

- IPC pipe handshakes are now tracked against the real process PID, creation time, image name, and appid. Launcher-heavy games get a steadier per-pipe identity for ticket and stats handlers instead of relying on one global launch appid.

### LumaCore — ownership marking

- When Steam confirms a Lua-tracked app is genuinely owned on the account (CheckAppOwnership returns true with multiple package hits), LumaCore marks it as owned so it is excluded from future patching. Stops injecting ownership for apps the user actually bought.

### LumaCore — diagnostics

- Boot diagnostic mode (opt-in via lumacore.toml) shows a popup with the Steam build ID and steamclient SHA256 when something goes wrong. Useful for reporting which Steam build needs a pattern update.
- Logging expanded to 20 per-module files covering auth, eticket, onlinefix, netpacket, steamui, and the IPC router. Every subsystem has its own log now.

### Linux

- Keyring crash on KDE and SteamOS fixed. norduk and NeruMarcus both hit this, saving an API key in Settings would crash if kwallet was disabled. Secret store now falls back to local file encryption when the desktop keychain is missing and tells you to install keyrings.alt or enable kwallet.
- Chrome for Testing download works on Bazzite and Fedora Atomic now. Br [FART]'s SSL verification error is gone, the downloader retries without CA verification on distros that ship incomplete cert bundles. Chrome-based SteamDB scraping works again.
- Wrong SSD download fixed. Dantesousa had Steam on one SSD and games on another; DLC checks and redownloads were writing to the system drive instead of the library where the game actually lives. SteaMidra now checks every Steam library for the game's ACF before picking where to put the files.
- Store search DNS failures no longer spam the live log. Network hiccups on Bazzite and offline machines stay at debug level instead of filling the log panel with red ERROR lines.

### Home page

- Game search in the home tab survives Steam Web API outages. When the API is down the search falls back to GitHub mirrors (jsnli/steamappidlist and SteamTools-Team/GameList) instead of hanging on "Fetching game list" forever. No cached all_games.txt needed, it pulls fresh from GitHub.
- Multiplayer Fix no longer auto-downloads files from online-fix.me. It now searches for the game page and opens it in your default browser. You follow their official guide yourself. The first press shows a one-time popup explaining the change, with links to the site and Discord. The old automation code is backed up as a reference.

### Store / download

- The settings file no longer hits the disk on every get_setting call. Every UI tick was reading and msgpack-decoding the same file dozens of times, that was the main source of the 2fps lag Drakrayt hit. Settings now load once and stay cached in memory until a write invalidates them.

### LumaCore — setup

- LumaCorePayload.dll is now tracked alongside dwmapi.dll, xinput1_4.dll, and LumaCore.dll during install, uninstall, and the NSIS cleanup step. The new LumaCore zip includes this fourth file and SteaMidra installs and removes it properly.

### Lua / endpoints

- oureveryday downloads reuse cached .lua files when they already exist on disk instead of re-fetching the depot list and provider keys every single time. Same app, same source, no re-fetch.
- SteamAutoCrack's NO LICENSE error from miicha7's Tmodloader case is fixed. The Steam Web API key now gets written even when config.json is missing, and the user's custom key from Settings takes priority over the bundled default.

### Workshop

- Workshop browser no longer renders half-gray when opened from Quick Tools. The page waits for the first render to finish before showing, so the gray checkerboard flash that LowEntropyCreature saw is gone.

### Installer (Windows)

- Windows Defender exclusion prompt removed from the installer. No more hidden PowerShell commands that mess with your AV settings during install or uninstall.
- Installer now runs at user level by default and installs to AppData without asking for admin. Picking Program Files triggers the normal Windows elevation prompt.

### Bug fixes

- iateacake's SteamAutoCrack STEAMLESS-ONLY crash is fixed. The legacy config key "Enable Debug Log." had a space in its alias that System.CommandLine rejected as an illegal argument, the bad key gets stripped before the CLI sees it.
- The Steam Web API game list retry loop actually retries now instead of dying on the first failure. Three attempts like it was supposed to.
- REMOVE_DRM result handling in the CLI path no longer silently swallows the success or failure message. The return type mismatch between tuple and enum is fixed.
- Scanning Steam libraries on Windows skips A: and B: drives now, so machines with physical floppy drives or legacy BIOS mappings do not stall for seconds on every directory walk.

## 6.3.1

### Home page

- DLC Unlocker card moved to its own row at the bottom of Home so DLC Check is the headline DLC tool again. The unlocker is still one click away when you actually need CreamAPI / SmokeAPI.
- Auto LC Setup now has Release / Debug radio buttons. Release is the default for everyone; flip to Debug when the maintainer asks for verbose logs from `<Steam>\lumacore\*.log` to debug a launch issue. The toggle pulls the matching asset from the LumaCore release on github.
- Workshop Item card on Home actually does something now. Click it, paste a workshop URL or item ID plus the App ID, and the 4-method cascade (SteamWebAPI direct, GGNetwork mirror, SteamCMD anonymous, SteamCMD signed-in) runs in the background. The result lands under your SteaMidra data dir, not next to the EXE, so the AppImage and frozen Windows builds don't write to a read-only mount.

### Store / download

- DLC Check no longer pop-up-spams "Depot N: enter manifest ID" when the auto strategies miss a depot. Ivanchick was hitting OK / Cancel through dozens of prompts; the GUI path now skips the manual fallback silently and lets the missing depot drop out of the manifest list. CLI users still get the prompt because they can actually answer it.
- Hubcap surfaces a clean "app is not in the Hubcap database" line when the API returns the `Page Not Found` HTML page. Used to dump the raw HTML into the live log; now you get a one-line answer plus a hint to try Ryuu or oureveryday.

### Build / CI

- Github workflow build was producing a half-empty EXE because `pip install -r requirements.txt` was failing the resolver loop. Seleniumbase pins move on every release and conflict with our exact-version pins for attrs / charset-normalizer / idna / packaging / requests / selenium / setuptools / trio / urllib3 / wsproto / websocket-client / beautifulsoup4 — every build the runner spent five minutes walking 100+ seleniumbase versions and gave up. The result: PyInstaller ran on a venv that only had `steam` and `pyinstaller` installed, so `_internal\` shipped without PyQt6, prompt_toolkit, selenium, keyring, nacl, cryptography, google-auth, zendriver, bs4, win10toast. Arxalor's auto-update pulled that broken artifact and SteaMidra wouldn't launch. Pulled seleniumbase out of `requirements.txt` so the resolver completes cleanly. Seleniumbase is only used by the SteamDB Cloudflare-bypass fallback (lazy-imported, ImportError-guarded), so 99% of users never touch it. Anyone who wants the SteamDB UC mode runs `pip install seleniumbase --no-deps` separately. Linux already worked this way (see `build_linux_appimage.sh`), Windows now matches.
- Workflow now fails loudly when the venv is missing core deps. Each pip step has `|| exit /b 1` so a resolver failure stops the build. Added a sanity import check (`python -c "import PyQt6.QtCore, ..."`) right before PyInstaller runs so a hollow install can never silently make it into the .exe again. Plus a post-build check for `_internal\PyQt6\Qt6\bin\Qt6Core.dll` so even if PyInstaller logs `Hidden import not found` errors, the workflow fails before uploading the artifact. Combined this should be impossible to ship a broken EXE on the github release page.
- Boot guard in `Main_gui.py` for the worst case: if a user does end up with an EXE that's missing PyQt6, they now get a clear native Windows MessageBox saying "SteaMidra failed to start because PyQt6 is missing — re-download the latest release" instead of a silent crash with no error window. Linux gets the same message on stderr.

### Installer (Windows)

- The .NET 9 and VC++ Redistributable steps used to silently fail when the user had no internet or an AV firewall blocked the powershell download. Svenhoz hit a confusing error mid-install on a clean box. Now both steps detect the failure, print one human line in the install log explaining what happened, and keep going. The .NET 9 step also skips the re-download when SteaMidra already installed it under `%LOCALAPPDATA%\Microsoft\dotnet\` from a previous launch, which saves the runner 30 MB on a reinstall. SteaMidra still offers .NET 9 again at first launch if the system install is missing.
- No more terminal flashes when SteaMidra runs subprocesses on Windows. Every time you ran SteamAutoCrack, removed SteamStub, fixed a game with Goldberg, or backed up a save the frozen build briefly popped a black console window. PR from @0xBadCod3 adds the Windows `CREATE_NO_WINDOW` flag to every subprocess we spawn, so all of those now run silent. Linux is untouched, the flag is gated behind `sys.platform == "win32"`.

### LumaCore — security

- Removed the script-side HTTP binding from LumaCore. Lua files in stplug-in should not be able to phone home from inside Steam.
- LumaCore can verify RSA-PSS-SHA256 signatures before external hook metadata is accepted. The default stays permissive for now, but bad signatures are fatal because that means someone tampered with the file.

### LumaCore — hot-reload

- Drop a fresh .lua into stplug-in while Steam is running and LumaCore picks it up on the spot. Delete one and the depots, tickets, and manifest overrides that file published get retracted on the spot too. Used to need a Steam restart for both. The bulk-delete freeze that hit when 160 .lua files came and went in one shot is gone, the watcher now recovers from the kernel buffer overflow instead of silently dying.

### LumaCore — setup

- Auto LC Setup got a Browse button next to the Steam path. Yiso had two Steam folders on disk and the auto-detect picked the wrong one, the button lets you pin the right one in seconds. Saving the pick also updates the same `steam_path` setting the rest of the app reads, so Cloud Saves and the Library tab stay in sync.

### Settings

- New "Show in-Steam 'Update available' prompts on installed games" toggle in Settings. Flip it on and SteaMidra drops a tiny override .lua into stplug-in so games render the Update prompt the way DarkH2o was doing manually. Flip it off and the file gets cleaned up. LumaCore picks up the change without a Steam restart.

### Boot

- SteaMidra checks for .NET 9 the moment it launches and grabs it in the background if it's missing. Yiso's case had Hubcap and DepotDownloader silently fail because the installer skipped .NET 9 and there was no second try; now the bootstrap kicks on every run, so the next time you go to download a game the runtime is already there.

### Store / download

- Hubcap and Ryuu now cover depotless DLCs the same way Oureveryday does. Some games have DLCs that ship as their own appid with no depots and just piggyback on the main game's manifest. Those used to stay locked when you pulled a Hubcap or Ryuu .lua, now they unlock alongside the rest. Best effort: if Steam appinfo hiccups the .lua stays exactly as the provider wrote it.

### Translations

- Filled in the strings that were still showing in English on non-English locales. The settings dropdown languages (PT, DE, ES, FR, IT, PL, CS, ID) now render their library / store / log labels in the right language instead of falling back to the English source. The other locales were already complete on the value side. There's a maintainer audit script that runs alongside the test suite now so this kind of drift gets caught before release.

### Linux

- Modern UI on Linux renders properly now. The platform-only hide rules in main.css were too greedy and were eating the whole page when the body's platform class wasn't set the way the rule expected. Pirat tracked it down to two lines and the swap he tested cleared the white screen.

## 6.3.0

### Store / search

- Hubcap library and search calls no longer dump scary [ERRO] popups in the live log when Hubcap returns 400 or 500. The 500 cluster on cyrillic queries (RU users typing "рф" hit it constantly) and the random 503s during Hubcap outages are server-side, the client can't fix them. Now those responses log one debug line and the rest of the pipeline (Steam applist, fallback paths) fills in quietly. Real network failures (DNS, timeouts, connection reset) still surface as ERROR like before.

### Store / download

- SOCKS4 proxy in HTTPS_PROXY no longer crashes the Hubcap download path. httpx supports http, https, and socks5, but socks4 is unsupported and used to bubble up as `ValueError: Unknown scheme for proxy URL`. A VPN user with NekoBox/v2rayN running a socks4 listener tripped this every time. Now the env gets sanitised at process start (one WARN line listing the unsupported scheme) and individual httpx clients fall back to a direct connection if the env still has something weird in it.

### LumaCore — Manifest fetch

- Manifest fetch fallback now tries three providers in order instead of just one. A dead first provider doesn't break manifest resolution anymore. Single-URL config (`[manifest_fetch] url = "..."`) still works for users who want to pin one provider. New `[manifest_fetch] urls = [...]` array form lets you customise the chain.

### Linux

- Modern UI on Linux gets a Chromium GPU fallback flag stack baked in so NVIDIA + Mesa GBM lookup failures no longer leave the page blank. The CPU-render flags (`--disable-gpu --disable-gpu-compositing --disable-features=UseOzonePlatform --disable-software-rasterizer`) only apply when the user hasn't set their own `QTWEBENGINE_CHROMIUM_FLAGS`, so power users keep their setup. Skyflizz hit this on Mint and was switching to Classic UI to recover, baked-in fallback skips that step.
- SLSsteam install now logs the actual 7z stdout/stderr tail when extraction fails, plus retries once after a 500ms pause for AV-mid-scan stalls. The old "Extraction failed and bin/ dir not found" line told you nothing. The next bug report at least includes the real 7z output so the cause is obvious.

### README

- Setup Step 1 recommends the installer first now and falls back to the ZIP only when AVs / corp policies block the installer. Antivirus warning rewrote to say what it actually is (generic packed-exe false positive, point AV at the source on github) and dropped the koaloader-era language.

### Linux

- Modern UI on Linux is one flag stack again. 6.2.7 / 6.2.8 tried to detect Wayland vs X11 and pick different Chromium flags per session, but the detection kept misclassifying Cinnamon-Wayland and GNOME-Wayland-with-XWayland users and dropping them into the wrong branch, which is what made the page render grey or not paint for Glitch on Mint. Reverted to the same single line 6.2.3 shipped: `--no-sandbox --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy`. No more session detection, no software escape hatch env-var, just the flag stack users actually confirmed working back then.
- Stripped the `WA_OpaquePaintEvent` / `WA_NoSystemBackground` attributes off the QWebEngineView on Linux. They were added in 6.2.6 to fix the Windows drag-flash and they help on Windows, but on Linux they conflict with how Mesa-on-X11 reports the window surface and can leave the page area unpainted on first show. Now Windows-only, Linux gets the default Qt opaque-paint behaviour (which is what 6.2.3 had).
- Splash overlay no longer installs on Linux. The QLabel sitting on top of the QWebEngineView fades out cleanly on Windows but on Mesa-X11 the swap chain composition leaves it visible because the loadFinished fade-out timer never gets the surface ready signal it expects. Sc0rthyn hit a stuck splash on Mint. 6.2.3 didn't have a splash and rendered fine, so Linux gets the 6.2.3 default again, no overlay, just the page paints when the renderer is ready.

### DLC check

- DLC modal got checkboxes plus a Local files button. Every missing DLC is ticked by default, depots are disabled because they aren't standalone, and the column header has a select-all toggle. Hubcap and Ryuu still queue the parent game's full bundle (single click, all DLCs come with it). Oureveryday loops over the checked DLCs only and appends keys to the parent lua. Local files opens the manifest folder picker and runs DDMod against the parent like the Store tab does.
- DLC check now also reads `config.vdf` depot keys, the depotcache `<id>_<gid>.manifest` filename pattern, and on Windows the `HKCU\\Software\\Valve\\Steam\\Apps\\<id>\\Installed=1` registry flag. Six sources in total before a DLC counts as missing. The 30s Steam-API ceiling is 45s now and on a hard timeout the modal still renders from the on-disk app-info cache so people stuck behind a flaky CM can still see the list. c was hitting this every time.
- DLC check Download buttons split by source now. Hubcap and Ryuu route to the parent game's full bundle (same as the regular Store download), since both of them only ship the parent zip and trying to pull a standalone DLC through them kept failing. Oureveryday now does the right thing for per-DLC clicks: pulls just the DLC's depot manifest through the gmrc / ManifestHub / GitHub cascade, looks the depot key up in the bundled key DB, and APPENDS to the existing `<parent>.lua` instead of overwriting it. So DLC keys you add later don't wipe out the keys the parent download already wrote. If the parent lua doesn't exist yet, oureveryday seeds one with `addappid(<parent>)` plus the new DLC lines. Lawbymike and Kinge both hit the overwrite case.

### Manifest downloads

- Oureveryday cascade is strictly sequential, one host at a time, with its own connect+read budget per host. Order: gmrc primary, two HTTPS gmrc mirrors, ManifestHub API, GitHub raw mirror. Slow hosts can't hold up the chain anymore. Some users were getting the cascade wedged after the two new mirrors landed because all three were racing in parallel.

### In-place updater (Windows frozen build)

- Updater bat reverted to the 6.2.5 shape because the 6.2.6/7/8 /MIR rewrite kept wedging on locked `_internal\` DLLs and leaving users on the old build (Arxalor confirmed 6.2.5 was the last one that updated cleanly). Old shape: 3s wait, taskkill, wipe `_internal\`, robocopy /E /IS /IT, relaunch. Simple beats clever when the clever one doesn't ship.
- Check for Updates now forces a visible "Update Available" popup as soon as the version compare fires. Some users on 6.2.5 / 6.2.8 said they clicked the menu item, the log said a newer version was found, and nothing else happened. The follow-up download confirm prompt was getting eaten by the worker-thread routing on certain setups. The popup runs straight on the GUI thread now.

### Live log

- Stripped the `get_setting:` debug line that fired on every settings read, the `update-check tick: GLOBAL_UPDATE_CHECK off, skipping` line that fired every 5 minutes, and the per-tile `get_game_update_state` line that fired for every game in the library on every refresh. The live log was unreadable under the spam and debug.log was filling up with thousands of repeats per minute. Real errors stay.
- The `search_games: filtered Hubcap appid=...` lines are gated behind `SFF_VERBOSE_FILTER=1` now. Default is silent. Search would dump thousands of those per tab switch on big catalogs and bury everything else.

### System tray

- Tray icon resource path now resolves through PyInstaller's `_MEIPASS` and the exe directory before falling back to cwd. Some users were getting a tray entry with no actual icon because Start menu / taskbar pin shortcuts launch the exe with a different cwd than the install directory. The icon also tries `sff.ico` (lowercase) so the freeze-built name matches.

### README

- Added a YouTube setup walkthrough by @yensnc and a step-by-step API key tutorial by @novoagain to the README, both credited.

## 6.2.9

### Library tab

- Library tab no longer freezes for a beat every time you switch back to it. The drive-letter walk that finds extra Steam libraries was re-running on every Library / Fix Game / Lure Fix call, parsing every `appmanifest_*.acf` each time. Now cached for 5 seconds across the whole bridge, so coming back to Library reuses the previous scan instead of redoing it. DaemonCipher hit this on a 35-game library.

### Store / search

- Store sort options actually sort now. "Recently Updated", "Newest", "Oldest", "Name A-Z", and "Name Z-A" all changed nothing in 6.2.8 because the Steam catalog page sliced results by raw appid order before the sort key was applied. Sort goes through before pagination now. Ivanchick reported this.

### DLC check

- DLC check now reads three on-disk sources before flagging a DLC as missing: SLSSteam's local applist, the parent's `<parent>.lua` under stplug-in, and the parent's `appmanifest_<id>.acf` MountedDepots block. Steam's own UI uses the same files. Batman Arkham Knight reporting "0 of 24 unlocked" while every DLC was actually installed was the Steam web check timing out and the local fallback never running. Three sources mean a single network hiccup can't make the modal lie to you.
- DLC check Steam-side query no longer hangs forever on a flaky CM. The 'This operation would block forever' gevent error from SteamKit is now caught with a 30s ceiling and the check falls through to the store + local checks instead of getting wedged.

### Cloud Saves

- Local provider now has a "Local Backup Folder" picker on the Cloud Saves tab. Pick any folder on your PC and that's where every per-game backup goes (`<your folder>/Game Name [AppID]/remote/`). Setting persists across sessions. Leave it blank and the legacy `%APPDATA%\SteaMidra\save_backups\` default still works. Was an explicit ask to know where Local backups land and to be able to change it.

### Manifest downloads

- The encrypted gmrc primary endpoint now has two HTTPS fallback mirrors when it goes down or returns garbage. Both fallbacks travel over TLS and are kept encrypted in source the same way the primary URL is, and stay redacted in the live log. Manifest downloads keep working through the gmrc downtime windows users keep hitting.
- Returned request codes are sanity-checked before use. Captive portals and MITM attempts on the http primary used to slip through with HTML or ad redirects in the body, which then turned into "manifest id" prompts later. Anything that isn't a numeric request code (real responses are 16-22 digit decimals) is rejected and the next fallback runs instead.

### Steam-option download

- The Steam-option download (the one that grabs the lua + manifests, not DDMod) no longer freezes at 10% forever. The Steam app-info call inside the lua-build step had no timeout, so a flaky Steam CM left the worker wedged at "Downloading Lua" with the bar stuck. Hard 30s ceiling now. On timeout the user gets a clear error telling them the CM is unreachable and to retry or switch source instead of staring at a frozen bar.

## 6.2.8

### Store / download

- Steam-option downloads (the lua + manifest path, not DDMod) now actually fall back to ManifestHub when the primary GMRC endpoint is dead or 503'ing. Before, if the encrypted endpoint was down, the download just stopped after a few depots without ever asking for a ManifestHub key or trying it. Now if you have the ManifestHub API key set in Settings (or get prompted to add one), missing manifests pull from there too.
- DDMod download progress bar moves now instead of sitting stuck at 35% for the whole download. The bar maps DDMod's own percent output onto the 35-95 range so you actually see download progress in real time.
- DDMod log spam in the modern UI is way more controlled. The live log only updates the home page log when you're actually on the home page, and the scroll-to-bottom is rAF-throttled so a 200-line burst from DDMod is one repaint instead of 800.
- Hubcap's "filtered DLC" debug spam during search no longer floods the live log. Those lines still go to debug.log on disk for triage but they don't reach the modern UI's live log anymore. The "not responding" reports during searching were caused by this exact spam.

### Update All Games

- Update All Games does what the name suggests now. First pass walks every installed game's `.acf`, skips anything in your "Exclude from Manifest Updates" list, refreshes the manifest GIDs through the same gmrc / ManifestHub / GitHub mirror cascade, and patches `InstalledDepots` + `MountedDepots` in the ACF so Steam picks the new version up. Second pass scans every `.lua` under `<steam>\config\stplug-in\` and fills in any depot whose manifest never made it to depotcache — useful for games you have a lua for but never finished installing, and for catching depots that silently failed first time around. LumaCore-locked games can finally update through SteaMidra without the manual "delete depotcache + redownload" dance.
- New "Content Still Encrypted" tip on the home page next to the EAC and SteamStub banners. If Steam throws that error on a download or update, it just means the game's manifests are missing or stale. Run Update All Games and they'll come back. Saves the "why won't this update" question in support.

### LumaCore — Lua sandbox

- Plugin .lua files no longer get the full Lua standard library. The VM used to call `luaL_openlibs` which loaded io, os, package, debug, coroutine alongside the safe libs, which means a hostile lua could read arbitrary files, shell out, or pull external bytecode into the process. Whitelist load now opens base + table + string + math only, then strips dofile, loadfile, load, loadstring, require, and collectgarbage off the base lib. Every binding SteaMidra ships (addappid, setManifestid, setAppticket, etc.) keeps working because they're registered separately. Reported by 𝙈𝙊𝙇𝙀𝘾𝙐𝙇𝙀.

### Live log

- Live log no longer prints the encrypted GMRC endpoint URL or the upstream HTML body when it's redacted. The endpoint is encrypted on purpose and was leaking into the live log on every request.
- "Access denied" / "accesso negato" spam from the manifest watcher is gone. That's a normal condition when Steam holds the depotcache locked, no point flooding the live log with it.

### Home page

- New EAC fix guide button next to the Steam DRM banner. Click "Show EAC fix steps" and you get a 7-page modal walking through verify integrity, Steam launch options, renaming the EasyAntiCheat folder, the executable swap, steam_appid.txt / .bat tricks, the firewall block, and crack files as a last resort. Methods are ranked easiest first and the modal is upfront that SteaMidra's tools (Goldberg, Remove DRM, SteamAutoCrack) don't fix EAC themselves.
- Steam DRM banner now mentions "Application load error 6:0000065432" alongside error 53 / 54. Older games hit that popup instead, same SteamStub root cause and same Remove DRM fix.
- Remove from library now tells you what to do if the game still shows in Steam after deleting. The lua gets deleted properly, but if LumaCore isn't loaded the running Steam keeps the appid in memory until restart. The new message says to restart Steam or run Auto LC Setup if you haven't yet.
- Remove DRM (Steamless) doesn't crash on the second click anymore. The worker thread cleanup was leaving a stale reference in some edge cases (Steamless cmd window closing fast, second exe locked by the launcher), and the next click hit "An action is already running" forever. The cleanup now drops the stale reference and waits for the thread to drain instead of hanging the GUI thread.
- Steamless no longer pops a separate cmd window on Windows. It still captures the output and pipes it to the live log like before, just without the flickering cmd window confusing users into thinking the app froze.
- If Steamless can't replace the original .exe (file held by the game's launcher process, antivirus lock, etc.), it now restores the backup and tells you what to do instead of leaving both the original AND the .unpacked.exe sitting on disk.
- DLC Check modal now has actual download buttons. Each missing DLC has its own Download button, and the footer has bulk buttons (Hubcap / Oureveryday / Ryuu) that queue every missing DLC at once through the chosen provider. Per-row downloads default to Hubcap.

### Linux

- Modern UI renders correctly on Mint, Pop!_OS, and pretty much every Linux desktop again. The 6.2.7 / 6.2.8-early splits between Wayland and X11 kept misclassifying sessions and dropping users into the wrong flag stack, which is what made the modern UI go grey on Glitch's Mint setup. The flag stack is back to byte-identical to 6.2.3 unconditionally for every Linux session, which is the version users actually confirmed working. `STEAMIDRA_LINUX_FORCE_SOFTWARE=1` stays as the opt-in software-render escape hatch for hopeless GPU stacks.

### System tray

- Tray icon fires a one-shot balloon notification on first appearance. Windows 11 hides new tray icons in the overflow menu by default, so users couldn't tell if SteaMidra was alive. The balloon now confirms the icon is up even when overflowed; right-click the system tray and enable SteaMidra in Other system tray icons to make it permanent.

### Updater

- 6.2.6 → 6.2.7 in-place update silently no-op'd for several users (the bat ran, the exe relaunched into the same 6.2.6 build). The bug was in the 6.2.6 bat itself and it's already fixed in the 6.2.7 bat going forward, so 6.2.7 → 6.2.8 will work normally. Users still on 6.2.6 need to manually install 6.2.7 once.

## 6.2.7

### In-place updater (Windows frozen build)

- The updater no longer leaves `tmp_update\` and `update.zip` lying around next to the EXE after an update. Cleanup runs at the end of the bat now, success OR fail, so yall don't end up with what looks like another SteaMidra inside SteaMidra after a bad run. If something does get left behind because of a reboot or a Ctrl-C, the GUI sweeps it on next launch. The actual install itself never gets touched, only the staging junk.
- Updater also keeps your stuff alive now. `settings.bin`, `recent_files.json`, `analytics.json`, `workshop_tracker.json`, `all_games.txt`, plus the `saved_lua\`, `backups\`, and `webengine_profile\` folders all stay untouched during an update. Old build artifacts under `_internal\` still get purged so PyInstaller doesn't pick the wrong files.

### Store / download

- DDMod downloads no longer freeze the modern UI on Linux or stutter the live log on Windows. DDMod prints thousands of validation and progress lines per second, and the modern UI couldn't keep up. Now those high-frequency lines get summarised once every 2 seconds while errors and warnings still come through normally.
- Steam-option downloads (the one that just grabs the lua and manifests, not DDMod) no longer freeze the whole window. The print() output from the manifest downloader was hitting the GUI thread synchronously per line. Now it's buffered and drained on a 100ms timer so a burst of hundreds of lines doesn't lock things up. c was getting 10-minute freezes on this, gone now.
- Live log no longer spams "access denied" / "accesso negato" every second when Steam holds the depotcache locked. Common when SteaMidra runs as admin and Steam doesn't, or vice versa. The condition is normal so it just goes to the debug log now instead of flooding the panel.

### Home page

- Remove from library now tells you what to do if the game still shows in Steam after deleting. The lua gets deleted properly, but if LumaCore isn't loaded the running Steam keeps the appid in memory until restart. The new message says to restart Steam or run Auto LC Setup if you haven't yet.

### Linux

- Modern UI no longer renders grey on Ubuntu XFCE and other X11 + lightweight WM setups. The earlier 6.2.7 flag set was tuned only for Wayland and was fighting xfwm4 on X11. Now it picks the right flag set per session: Wayland keeps the in-process-gpu flags, X11 drops them and uses the same plain GPU path Windows uses. Skyflizz and AlukardBF were both hitting this.
- Modern UI rendered black on Wayland on a chunk of distros (NixOS, recent Fedora, Bazzite, etc). The QtWebEngine GPU process was producing frames Mesa Wayland couldn't import. Fixed with `--in-process-gpu --disable-gpu-compositing` so the dma-buf handoff is gone.
- `STEAMIDRA_LINUX_FORCE_SOFTWARE=1` actually works now. The old version still spawned a GPU process; the new one collapses everything into one process with SwiftShader software raster. Slowest path that exists but it renders on configs where every GPU path fails.

### Store / search

- Metro Exodus Enhanced Edition (1449560) shows up in the Store search now. Same fix covers Mafia Definitive Edition, Crysis Remastered, Saints Row 2 Re-elected, the GTA V Enhanced Edition family, and any other Steam re-release. Steam tags these as type 14 with a parent_appid pointing at the base game, same shape as DLC, so the DLC filter was eating them by mistake. Re-releases keep going through now, DLC still gets dropped the same way.

## 6.2.6

### In-place updater (Windows frozen build)

- 6.2.4 → 6.2.5 silently no-op'd for several users. The exe downloaded the new zip, extracted it, said "Extracting update..." and relaunched right back into 6.2.4. The bat killed the process and then tried to wipe `_internal\` immediately after, before Windows finished releasing file locks on the python and Qt DLLs, so the wipe half-failed. Robocopy then ran additive (no purge) so old 6.2.4 files stayed mixed with new 6.2.5 files, and the import order ended up resolving to the old build. The headless cmd window also swallowed every error code so a fatal failure looked like success. New bat: waits up to 30 seconds for the exe to actually exit, runs `robocopy /MIR` so stale files purge properly, excludes user data folders so settings stay alive, and writes `tmp_updater.log` next to the exe on every step. Relaunch only fires on a clean robocopy exit. Anything else aborts in place and leaves the log behind so I can triage.
- New startup probe in the GUI reads `tmp_updater.log` a couple seconds after the window paints. Any FAIL / WARN line surfaces as a popup, then the log gets deleted so it doesn't keep firing. Headless bat windows can't swallow update failures silently anymore.

### Store / search

- Reverted yesterday's Hubcap filter-decision cache. The cache landed alongside an attempt to drop per-item DEBUG noise but the rewire broke result counts and tile rendering — searches were returning ~50 entries instead of the 20-row first page, results filled with raw Hubcap rows that should have been dropped, and several rows shipped without cover art. The filter loop is back to the pre-change shape that re-walks `_STEAM_PLATFORM_CACHE` per search and emits one DEBUG line per drop. Re-runs of the same query do hit the metadata cache (`_STEAM_PLATFORM_CACHE` was untouched) so they don't pay the GetItems round trip again; the only thing the rollback gives back is the per-item debug spam, which only shows up at DEBUG log level
- Pagination on the Store tab now honours the per-page limit when Hubcap-only extras are merged in. The previous shape sliced Steam rows for the requested page, then appended every Hubcap-only row to the result regardless of which page the user was on, so page 1 rendered ~45 tiles (20 Steam plus the full Hubcap tail) and pages 2 / 3 / 4 repeated the same Hubcap tail under fresh Steam rows. The merged list is now treated as one virtual sequence: `[steam_total Steam rows] + [extras_total Hubcap rows]`, and the Hubcap tail gets sliced into the same `[offset, offset + per_page)` window the Steam slice uses. Page 1 of an empty query is back to 20 tiles, and `data.total` reports the true combined count so `Math.ceil(total / perPage)` lines up with what the user can actually scroll through
- Hubcap-only rows shipped on the current page now resolve cover art through `IStoreBrowseService/GetItems/v1` (same path Steam rows use) before the page is emitted, so delisted classics surface with proper header.jpg artwork instead of a broken-image placeholder. Rows that aren't on the current page skip the lookup so a 200-row Hubcap library doesn't pay 200 GetItems hits per search

### Window paint flicker

- Dropped the white / checker flash a few users hit when dragging the SteaMidra window, starting a download, or typing into the search box, especially on dark themes. Two stacking causes. First, the Windows Chromium flag set passed `--enable-zero-copy` to QtWebEngine. Zero-copy lets the GPU hand its texture straight to DWM without a CPU bounce, which is faster, but on the Windows 10 / 11 compositor it produces a one-frame placeholder texture whenever the renderer rebinds its surface during drag, layout invalidation, or theme reload. That placeholder is what users were seeing as a checker / white flash. Removed the flag from `Main_gui.py`. GPU rasterization (`--enable-gpu-rasterization`) and the blocklist override (`--ignore-gpu-blocklist`) stay on so the store grid still rasters on the GPU. Second, the `QWebEngineView` was constructed without `WA_OpaquePaintEvent`, so Qt's drag pipeline erased the parent under the view to the platform default background for one frame before the renderer's texture landed on top. Set `WA_OpaquePaintEvent`, `WA_NoSystemBackground`, and `setAutoFillBackground(False)` on the view in `main_window` so the parent-erase step is skipped entirely. Together the two fixes make drag, theme switch, and download-start repaints opaque from frame zero

### Linux

- 6.2.5 wouldn't launch for a chunk of Linux users: the AppImage opened, then exited within a second. Confirmed on CachyOS, Bazzite, Nobara, recent Fedora KDE / GNOME — anything running a pure Wayland session with no XWayland fallback. Cause: the 6.2.5 Linux Chromium flag set forced `--use-gl=desktop` on top of `--disable-gpu-compositing`. `--use-gl=desktop` pins libGL with GLX, and GLX needs an X server context that pure Wayland sessions don't expose, so Chromium's renderer died during GPU init and the parent process exited. The blank-window dma-buf workaround the flag was meant to support is fully covered by `--disable-gpu-compositing` alone, since software-compositing the final frame skips the dma-buf handoff regardless of which GL backend the rasterizer picks. Pulled `--use-gl=desktop` out of the Linux flag set; Chromium auto-selects EGL on Wayland and GLX on X11 from here. Added a `STEAMIDRA_LINUX_FORCE_SOFTWARE=1` env-var escape hatch that switches to `--disable-gpu` for users who hit a GPU init failure on out-of-tree Mesa or a busted vendor driver and need to limp along until the underlying stack is fixed

### Home page — game-update toggle default

- The "Check for game updates" global setting is now actually OFF by default, matching the declared `Settings.GLOBAL_UPDATE_CHECK = False`. The 6.2.5 release shipped two read paths in `main_window._run_update_check_tick` and `web_bridge._app_update_check_enabled` that coerced an unset setting to `True`, so on a fresh install or an empty `settings.bin` the periodic CM sweep + appdetails burst fired automatically every 60 minutes plus once at startup. Both call sites now coerce unset / blank to `False`. Users opt in from the Settings panel or per-tile toggle

### Home page — tile rename

- Renamed the "Update All Manifests" home-tile to "Update All Games" with the subtitle "Refresh all installed games". Same dispatch path, same modal, same backend behaviour — only the user-visible label changed. The function still walks every installed game's `.acf` against your saved Lua files, skips entries listed under "Exclude from Manifest Updates", and pulls fresh manifests through the configured provider. The settings tooltip and the bridge's "no manifest provider" toast picked up the new name too. Locale strings updated for all 19 webui translations

### LumaCore — robustness hardening

- `KeyValues::ReadAsBinary` and `KeyValues::FindOrCreateKey` hooks no longer log every fire. Earlier builds wrote 30+ MB of disk traffic in under 30 seconds once Steam loaded its app list. Install / Uninstall lines stay so attach failures still show.
- LicenseHooks keeps `OptedInMask` and `RequiresLegacyCDKey` as the only two detoured surfaces. The five extra DLC / cloud / subscription detours that were briefly added (BIsDlcEnabled, IsAppDlcInstalled, IsCloudEnabledForApp, GetSubscribedApps, BUpdateAppOwnershipTicket, BUpdateLicenses) caused random Steam crashes after a few minutes of clicking through games and flipped cloud-save on for every Lua-tracked app. Those six are gone now.

## 6.2.5

### Auto LC Setup

- "Check for updates" inside Auto LC Setup now actually fires when the modal opens. The version row used to gate the initial probe behind the modal's one-time init, so users who opened the modal a second time saw stale dashes for installed and latest. The probe runs on every modal open now, and the Check for updates button bypasses the 6-hour cache so the user gets a fresh GitHub round-trip on demand. The slot also surfaces backend errors as a toast instead of swallowing them.

### Quick Tools — Steam updates toggle

- Added a Steam Updates button under Quick Tools that writes `BootStrapperInhibitAll=Enable` (block) or `BootStrapperInhibitAll=False` (unblock) into `<Steam>\steam.cfg`. Reads the current state on click, prompts with a confirmation showing what will change, then writes the file. Existing lines in `steam.cfg` are preserved; only the `BootStrapperInhibitAll` line is replaced or appended. Restart Steam for the change to take effect.

### Store / download

- "Direct download via DDMod" now returns a specific failure reason instead of the generic `DepotDownloaderMod reported failure` line. When zero manifests resolved for any depot, the modal shows that the lookup failed and points the user at the manifest folder drop, the source picker, or Update All Manifests. When some depots downloaded but others failed, the toast explains that and tells the user to check the per-depot exit codes in the live log. Empty install dir produces a different message that calls out missing manifest pins, blocked depots, or .NET 9 spawn failures
- "Download older version" no longer leaks the SteamDB scraper window into Alt-Tab and the taskbar. The Chrome process now launches with `--start-minimized`, `--silent-launch`, `--no-first-run`, and a 1×1 off-screen window. When the scrape finishes (or times out) the process gets a hard `taskkill /F /T` so it can't linger in the background. Cloudflare still treats the session as a real browser because the rendering pipeline stays intact

### LumaCore — robustness hardening

- Lua uint64 strings now go through a strict-decimal helper before parsing. Empty input, embedded whitespace, signs, and `0x` prefixes get rejected upfront so a malformed `.lua` config errors cleanly instead of unwinding into Steam's loader.
- DirWatch caps the configured-directory list at the Win32 wait limit before entering its loop. Beyond the cap the watcher used to die silently; now it truncates with a warning. Empty lists exit immediately.
- DllMain pins the LumaCore module on attach so a stray `FreeLibrary` cannot unmap the DLL while hooks and worker threads are still running. On process termination the detach path skips MinHook teardown to avoid a loader-lock deadlock.

### Achievements — OnlineFix stats follow-ups

- Achievement and user-stats callbacks now reach OnlineFix games' callback registrations correctly. `SendCallbackToPipe` rewrites the low-24 bits of `m_nGameID` from the real appid back to 480 on `UserStatsReceived_t`, `UserStatsStored_t`, `UserAchievementStored_t`, and `UserAchievementIconFetched_t` callbacks before forwarding to the pipe. The high 40 bits stay untouched
- `IClientUtils::GetAPICallResult` handler picks up matching dispatch entries for the three async-call result ids (`UserStatsReceived`, `GlobalAchievementPercentagesReady`, `GlobalStatsReceived`) so the same rewrite applies on the result-fetch path
- A new pipe-scope gate (`g_StatsScopePipe`) tracks the `HSteamPipe` that originated a user-stats IPC dispatch. Callback rewrites only fire on the matching pipe, so cross-pipe bleed when worker threads share an `HSteamPipe` value can no longer mis-tag a callback. The existing thread-local depth counter stays as the coarse gate
- `SendCallbackToPipe` also runs an additional appid-480 dispatch after the real-appid dispatch returns for OnlineFix sessions, so games whose callback registration is bound to 480 still see the callback even though Steam routed the original to the real appid pipe. Gate is `g_OnlineFixRealAppId != 0` plus the pipe match plus the four-id callback set; everything is a no-op outside an active OnlineFix session

### Home page

- New game-update-available badges on every library tile. A green dot means the installed buildid matches Steam's CM-published buildid and the cached state is fresh; an amber dot means an update is available; no dot means the cache is missing, stale, or in error. Click the dot for a popover with the installed buildid, the Steam buildid, and a Check now button. Useful for LumaCore-locked games where the user wants to know when an update lands without auto-updating
- New global Settings entry "Check for game updates" plus a per-game override map (`UPDATE_CHECK_OVERRIDES`) and an interval setting (`UPDATE_CHECK_INTERVAL_MIN`, default 60). A periodic timer walks every installed game once per interval, gates on the global setting and the per-game override, and dispatches at most one Steam CM check per game per interval. Cross-game dispatches are paced one per 2 seconds
- Splash overlay during web UI startup. The QtWebEngine renderer used to paint a white block for one to four seconds while the page warmed up. A `QLabel` parented to the view now sits over the renderer with the SteaMidra logo on the active theme background colour, fades out over 150 ms once the page reports `loadFinished(True)`, and never registers as a separate top-level window or taskbar entry
- Workshop Item panel gains an "Import subscribed mods" action. Scans `<steam>\steamapps\workshop\content\<appid>\` for numeric subscriber IDs, dedupes against already-downloaded items, and queues the rest through the existing 4-method `download_workshop_item` cascade. Useful when Steam fails to download a chain of dependency mods that are still listed in the subscribed folder

### Workshop

- New ownership-bypass workshop downloader for games that block direct subscribe (Karter 2 case). Routes through `IPublishedFileService/GetDetails` plus the UGC CDN (`steamusercontent-a.akamaihd.net/ugc/<hcontent_file>/`) instead of the Steam subscribe API, so workshop items still pull when subscribe returns "No internet connection". Accepts a single item URL, a collection URL (resolved through `GetCollectionDetails` before any download starts), or a newline-separated paste list; concurrency capped at 4. The bypass path sends only the configured Web API key and never Steam session cookies, and verifies body length against `file_size` from `GetDetails` before writing the output file
- New "Bypass download" tab in the Workshop Browser dialog. Two text fields (URL or paste list, optional Web API key override) and a Download button; per-item progress and errors stream into a list view so the user sees which IDs landed and which failed without digging through the log panel. Workshop Browser dialog is now a per-process singleton: opening while an existing instance is visible focuses the existing dialog instead of constructing a new one. The `QWebEngineProfile` is also a singleton, parented to `QApplication.instance()`, so the four Tools entries no longer paint white boxes on a second open

### UI fixes

- Close-to-tray toggle now actually works. With "Close button hide to tray" set to OFF, closing the window via the X button, the right-click taskbar menu, or Alt+F4 hides the tray icon, drops the tray reference, calls `QApplication.quit()`, and accepts the close event so the process terminates within a second. The tray icon used to keep the QApplication alive after the window closed, leaving an orphan SteaMidra in the background that only Task Manager could kill. ON branch keeps the existing hide-to-tray behaviour
- Show-software-in-Store toggle now actually filters. Flipping the setting clears `store_browser._cached_grid` and forces the `_STEAM_APPLIST_CACHE` TTL to 0 so the next Store request rebuilds. `list_games` reads the setting on every call and drops every entry whose `type` equals `"software"` when the toggle is OFF, regardless of what `IStoreService/GetAppList`'s `include_software` parameter returned. The result set changes within one round trip after a flip

### DLC check

- DLC check no longer crashes with `No module named 'rich._unicode_data.unicode17-0-0'` in the frozen build. The legacy `lumacore.dlc_check` and `sls.dlc_check` paths used to build a Rich console table the Web UI never displayed, and the lazy `rich._unicode_data` import failed under PyInstaller. Both `dlc_check` paths now print a plain text table directly. `build_sff.spec` adds `rich._unicode_data`, `rich.box`, `rich.text` to `hiddenimports` plus `collect_data_files("rich", include_py_files=False)` for the SLSsteam codepath that still uses Rich, and the spec aborts with a clear error before PyInstaller's analysis pass when either of those entries is missing
- Hubcap merge alias-expands the user query before sending it to Hubcap. Typing "gta san andreas" used to send "gta san andreas" verbatim, which Hubcap matches as a plain substring against game names where the classic title is stored as "Grand Theft Auto: San Andreas" with no "GTA" anywhere. The merge step now also queries Hubcap with "grand theft auto san andreas" (and the matching expansion for re, cod, rdr, kh, er, wukong, and the rest of the alias map), then dedupes results by appid
- Hubcap merge filters out macOS-only and Linux-only entries. Searching "grand theft auto san andreas" no longer shows the Mac port (appid 12250) alongside the Windows classic (12120) and the Definitive Edition (1547000)
- Switched the Steam metadata lookup from `appdetails` (rate-limited at 200 req / 5 min, returning HTTP 429 mid-search) to `IStoreBrowseService/GetItems` (batched up to 50 appids per call, no per-IP rate limit), so the type signal actually arrives instead of falling through

### DLC check

- The DLC check button now actually shows something. The old code piped a Rich console table into stdout that the Web UI never displayed, so clicking the button looked like a no-op. New `dlc_check_get_list` slot returns structured JSON, and a new modal renders the DLC list with status (Unlocked / Missing), app id, name, and depot / appid type. Reads from the Steam Web API when available, falls back to Steam Store `appdetails` when the Web client times out

### Linux

- Fixed blank / white WebEngine window on Linux Wayland sessions. Two users on KDE Plasma Wayland reported the GUI launching with the chrome rendered but the page area completely blank. Diagnostic logs confirmed the WebEngine renderer was producing frames and the WebChannel handshake was completing — the JS app loaded translations and fetched the game list — but the dma-buf textures the compositor hands to Wayland never made it to the screen. ANGLE-on-Wayland with Intel UHD + Mesa is the bad combination; the renderer logs say `EGL: MESA extensions found but missing EGL_MESA_drm_image, will use dma-buf, some older graphics cards may not be supported` and then silently fails to display. Switched the Linux-only Chromium flags to `--no-sandbox --disable-gpu-compositing --use-gl=desktop` so page rasterization still runs on the GPU but the final compositing step moves to software, bypassing the dma-buf import path entirely. Windows keeps the existing `--ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy` flags since they're not affected
- DDMod now runs on Linux instead of getting skipped. The previous Linux flow stopped after writing manifests + ACF and told the user to open Steam and click Update, expecting SLSteam to pull the content. That worked in some setups but failed silently in others, so users got a "download finished" message with no game content on disk. DDMod is the reliable content-fetch path on both Windows and Linux when .NET 9 is present, and SteaMidra now installs .NET 9 automatically on first Linux launch, so this path Just Works
- Steamless on Linux now uses the framework-dependent `Steamless.CLI.dll` via `dotnet` instead of running the Windows `Steamless.CLI.exe` through Wine. The Library tab Steamless flow (`game_specific.py`) and the Fix Game SteamStub unpacker both pick the DLL up automatically when on Linux. Wine fallback stays in place when the DLL is missing, so distros without .NET 9 keep working
- .NET 9 now installs automatically on first Linux launch when missing. Previously the user had to run Linux Tools Setup once before any download or Steamless action would work; now SteaMidra spawns `dotnet-install.sh` on a daemon thread 6 seconds after the window paints, so the runtime lands in `~/.dotnet/` while the user is still browsing the home page. Failures log to `debug.log` and don't block the GUI

### Home page

- Achievement Data button now flags itself as Goldberg-only with a yellow warning subtitle. The button downloads `UserGameStats_*.bin` for Goldberg / GBE setups and is not needed when LumaCore is installed (LumaCore handles achievements through Steam natively). Misuse with LumaCore could overwrite the on-disk achievement cache, so the tooltip and subtitle now make the scope clear

### Bulk import — drag and drop

- Drag-and-drop into the Bulk Import drop zone works again. QtWebEngine 6.10 ships Chromium 124 which removed the non-standard `file.path` property, so dropped Lua / manifest files were arriving at the bridge with just the bare filename. The bridge then resolved that against the working directory (giving an invalid path), the first drop failed with "not there", and a second drop hit the dedupe set with the same invalid path and reported "already there". Drop now reads each file's content via `FileReader.readAsDataURL`, base64-encodes it, and ships `{name, content_b64}` to a new `enqueue_dropped_blobs` slot that materializes the bytes under `<sff_data>/.bulk_import_drop/` and runs the standard pipeline. The result list shows the original filename instead of the temp path

## 6.2.4

### LumaCore — CD key bypass

- Lua-tracked games no longer hit the legacy CD key prompt for keys Steam itself wants. Older titles like Wargame: Red Dragon used to refuse to launch because Steam asked for a key the user doesn't have. The new license layer answers `false` for `RequiresLegacyCDKey` on apps tracked by Lua, so the prompt never fires.
- DLC ownership / install / cloud checks deliberately stay out of the new hook. Steam already returns the right answer for Lua-tracked appids through the existing CheckAppOwnership patch

### LumaCore — version checker + deactivate

- Auto LC Setup modal now shows the installed LumaCore version next to the latest GitHub release. SteaMidra hits the GitHub releases API at most once every six hours and caches the answer, so the version line is instant on subsequent opens. A blue banner appears when an update is available
- New "Deactivate LumaCore" button next to "Install LumaCore". Asks for confirmation, closes Steam plus steamwebhelper / steamservice, then removes `LumaCore.dll`, `dwmapi.dll`, and `bin/lcoverlay.dll`

### Home page

- Multiplayer Fix sits at the top alongside LC Online Fix and Auto LC Setup. The LumaCore notice mentions Multiplayer Fix as the LC-Online-Fix fallback when a game doesn't work
- The duplicate LC Online Fix, Auto LC Setup, and Multiplayer Fix tiles in Quick Tools are gone. Those three live at the top now

### SteamAutoCrack

- The home page card no longer flatly says it breaks achievements. The label now reflects that SteamAutoCrack runs in either Steamless-only mode (achievement-safe) or Steamless + Goldberg mode, and the existing default-mode setting controls which one runs without re-prompting

### Store / search

- Common franchise abbreviations work in the search box. Typing `gta` finds Grand Theft Auto, `re` finds Resident Evil, `cod` Call of Duty, `rdr` Red Dead, `kh` Kingdom Hearts, `er` Elden Ring, `tf2` Team Fortress 2, `cs2` Counter-Strike 2, and so on. Full names still match the same way they did
- Hubcap entries that aren't in Steam's catalog now merge into search results when a Hubcap key is configured. Delisted titles like classic Grand Theft Auto: San Andreas show up alongside the regular Steam hits instead of being silently dropped
- Oureveryday Lua now includes appid-only DLCs (the kind that don't ship their own depot). The downloader pulls `extended.listofdlc` from the game's app info and writes one `addappid(<dlc_id>)` line per entry under the keyed lines. LumaCore picks them up on the next license refresh, so the DLC unlocks without needing the user to add it manually

### Achievements

- Achievements now unlock for `-onlinefix` titles. The fake Spacewar (480) appid was leaking into the achievement IPC path and binding unlocks to the wrong app. The override is now scoped to `IClientUserStats` calls only, so achievements bind to the real game and lobby / friends / controller paths stay untouched
- Wukong (`2358720`) and Resident Evil Requiem (`3764200`) achievement panels now render. The two spoof handlers were too strict and pass-through'd shapes that should have been spoofed, leaving the panels empty
- `keyvalue.log`, `ipc.log`, and `license.log` were 0 bytes after a session. KVHooks, IPCBus, and LicenseHooks now each emit at least one entry per session
- Restored the achievement handler to the last working baseline. The on-disk wipe of `<steam>/appcache/stats/UserGameStats_*` is gone, so legitimate local achievement state is no longer clobbered on Steam launch
- Callback intercepts on UserStatsReceived and UserAchievementStored are gone; only the existing `AppLicensesChanged.m_bReloadAll → true` flip stays

### Linux

- Home page shows a Linux-specific notice instead of the Windows LumaCore-required banner. The notice explains LumaCore is Windows-only and points at SLSsteam + SLScheevo as the Linux equivalents, with a link to the new setup doc
- New [docs/LINUX_SETUP.md](docs/LINUX_SETUP.md) walks through the Linux install path end to end: supported distros (CachyOS, Arch, Debian, Ubuntu, Fedora, Steam Deck Desktop Mode), what works and what's hidden, the SLSsteam + .NET 9 setup tool, the "restart Steam from inside SteaMidra so injection happens" gotcha, and a troubleshooting block for the most common failure modes
- README adds a Linux quick-start section pointing at the same doc

### Bulk lua downloader

- `LumaCoreForWork/allgames/download_zips.py` (the bulk .lua downloader) no longer pegs the CPU. Rewritten on asyncio with HTTP/2 connection pooling, separate semaphores for network vs decompression (decompress capped at half the cpu count), and per-appid parallel source fetching so wall time per appid is `max(source1, source2)` instead of `source1 + source2`. The output directory is scanned once at startup instead of once per worker per appid. Tunable via `DZ_NET` / `DZ_CPU` / `DZ_TIMEOUT` env vars


</content>
</file>
### LumaCore-required notice

- Added a blue notice banner above the existing Steam-error-54 banner on the home page. It tells users that adding games to their Steam library and downloading them needs LumaCore installed first, and points them at Auto LC Setup in Quick Tools below. This is for the users who don't read the guide

### Steam path detection (Linux)

- Fixed "Steam installation path couldn't be found" on CachyOS, Arch, and other distros that don't ship the legacy `~/.steam/root` symlink. The GUI now probes `~/.steam/steam`, `~/.local/share/Steam`, the Flatpak sandbox at `~/.var/app/com.valvesoftware.Steam/data/Steam`, and the Snap install — same set the CLI already covered
- Steam product info no longer crashes the GUI when the connection drops mid-fetch. Plain socket timeouts, connection resets, and EOFs are now caught alongside the gevent timeout that was already handled. After three retries SteaMidra falls back to an empty result and surfaces a clean "no info" message instead of taking the worker thread down

### Store / search

- Search now matches games whose names carry trademark, registered, or copyright marks. Typing `lego batman` finally hits `LEGO® Batman™: Legacy of the Dark Knight`, and `resident evil requiem` finds `Resident Evil Requiem` regardless of whatever decorative punctuation Steam ships in the catalog name. Accents (café, jalapeño) collapse to their plain ASCII equivalent on both sides of the comparison

## 6.2.3

### SteaMidra — Revert Fix Game changes actually works

- Web UI Revert button was calling `FixGameService.revert(path)` — a method that doesn't exist anywhere. Crashed with `AttributeError` and silently failed. Fixed: instantiate `FixGameService()` and call `restore_game(path)`, the real method
- `restore_game` now distinguishes "had nothing to revert" from "reverted N files" instead of always reporting success. Clean folder gives a clear "Nothing to revert in this folder — no Fix Game backups, no steam_settings/, no launch scripts" toast instead of a misleading "Changes reverted"
- Returns a proper summary: `Reverted: 2 SteamStub backup(s), restored 3 file(s), 1 launch script(s)`
- `SteamStubUnpacker.restore_directory` now skips SteaMidra's own backup folders during recursion (`.steamidra_exe_backups/`, `.steamlocked.bak/`, `saved_lua/`, `manifests/`) so revert can't process stale backups that were never paired with a live exe. Also returns the actual count of restored files so the caller can report it

### LumaCore

- Full debug coverage on every IPC, network, hook, registry probe (verbose log mode, defaults on)
- Steam-DRM appid table — when `CheckAppOwnership` patches a known SteamStub title, log suggests using Remove DRM (Steamless)
- Auto-fabricate minimal AppTicket from active SteamID on launch when registry is empty (helps older v1.5/early-v2 wrappers; v3 still needs Steamless)
- Wipe stale tickets when the active Steam account changes
- Hot-reload crash fix when deleting a `.lua` file from `config/stplug-in/` (card may linger as Purchase until Steam restart — accepted trade-off)
- Family-share lock-status bypass: clear `k_EMsgClientSharedLibraryLockStatus` (9405) in addition to 9406
- SteamUI hook hardening: safer `LoadModuleWithPath` attach path, removed double-attach
- Multi-account fix: clear `OwnedAppIdSet` on Lua re-parse / `addappid`
- `-onlinefix` debug logs every SpawnProcess hit with reason for skip

### SteaMidra — UI / actions

- Home tab error-54 hint banner pointing users at Remove DRM (Steamless)
- Achievement-breakage warning dialog on Crack game (gbe_fork) and SteamAutoCrack; toggle in Settings (default on)
- Inline action-card subtitles: yellow "Breaks Steam achievements" on crack/SteamAutoCrack, green "Achievements safe" on Remove DRM and Fixes & Bypasses
- Removed orphaned Offline Fix button (GreenLuma-era leftover)
- LC Online Fix closes Steam first, picks active SteamID3 from `loginusers.vdf`, navigates VDF case-insensitively
- Restart Steam from elevated SteaMidra: now bounces through `explorer.exe` (fixes WinError 740)

### SteaMidra — Steamless / DRM Remover

- Picker now opens a single `QFileDialog` at the game folder (was: redundant Explorer window + dialog at workspace root)
- Passes `--exp` so v3.0/v3.1 wrappers (Teardown, Doom Eternal, etc.) actually get unpacked
- Backs original up to `<exe>.steamlocked.bak` instead of deleting
- Pre-validates input: refuses non-`.exe` files and missing `MZ` PE header
- Maps Steamless failure signatures to user-friendly messages and surfaces them in the GUI (popup + toast), not just stdout

### SteaMidra — Fix Game / SteamStub Unpacker

- `SteamStubUnpacker` no longer recurses into `.steamidra_exe_backups/`, `.steamlocked.bak/`, `saved_lua/`, `manifests/`; skips `*.steamstub.bak` / `*.unpacked.exe` artefacts
- `GoldbergApplier.find_main_exe` honors the same skip-dir set so backups can't be picked as the main exe

### SteaMidra — Tray / window behavior

- Tray icon retries availability check every 3 s for up to 90 s (cold-boot Win11 fix)
- Tray now parented to `QApplication` so it survives window destroy/recreate; 30 s heartbeat re-shows on Explorer restart
- New setting: **Close button hides to tray (off = quit)**, default off

### SteaMidra — Other fixes

- DLC Check on the LumaCore path: fixed `get_dlc_list_from_store() takes 1 positional argument but 2 were given`
- Fixes & Bypasses correctly described (was wrongly attributed to Ryuu); achievement-safe — no Steam API replacement
- Lure Fix / Update buttons no longer crash SteaMidra (kwarg collision in `_emit_task_result`)
- Download Games via DDMod now copies the Lua to `config/stplug-in/` and writes decryption keys so LumaCore picks the game up immediately
- Stopped writing ACF on Windows (LumaCore handles ownership; Linux still writes ACF for SLSteam)
- Linux: DDMod manifest path covers both `steamapps/depotcache` and `config/depotcache`; Multiplayer Fix subprocess flags platform-branched; `_detect_archiver` resolves `7z`/`7zz`/`unrar` via `shutil.which`; AppList IDs button routes to `injection_menu()`
- SLSsteam auto-installs on first Linux run when no version file exists
- `build_installer.bat` no longer exits immediately (PowerShell quoting + `(x86)` parens fix)
- Auto LC Setup marker moved out of `<steam>/lumacore/` (was colliding with LumaCore's runtime log dir)
- Pixeldrain bypass downloader for the Fixes & Bypasses flow
- 12 new languages: Chinese Simplified/Traditional, French, Italian, Japanese, Korean, Turkish, Ukrainian, Vietnamese, Indonesian, Thai, Czech

---
## 6.2.2

### LumaCore — Hook System Overhaul

- Fixed Steam crash on startup. `OptedInMask` and `BuildSpawnEnvBlock` now land on the correct aligned entry points instead of corrupting the call stack on the current Steam build.
- Re-enabled the `-onlinefix` controller and overlay fix. `OptedInMask` redirects appid 480 (Spacewar) to the real game appid so Steam Input opt-in and SDL controller env vars are correct; `BuildSpawnEnvBlock` patches `pOverlayCGameID` so the overlay shows the right game name, screenshots tag correctly, and "View Community Hub" opens the right hub
- Fixed `AppLicensesChanged` not triggering a full library reload. `SendCallbackToPipe` now forces `m_bReloadAll = true` on every `AppLicensesChanged` callback
- Hook and capture failures now log enough detail to make missing Steam build coverage obvious in `main.log`.
- Added fallback coverage for several LumaCore capture points that used to miss on some Steam builds.
- `RuntimeCapture.cpp` cleanup: removed the disabled env-block-string-rebuild path for `BuildSpawnEnvBlock` (was the source of the earlier crashes); replaced with the working `pOverlayCGameID` patch

### SteaMidra — Linux SLSteam Auto-Update

- **Auto-install on startup** — `check_and_notify_update` now automatically installs SLSteam updates when a newer version is detected on startup, instead of just printing a notification message
- **`patch_slssteam_config`** — new function that patches `config.yaml` after install/update to enable `PlayNotOwnedGames: yes`, `SafeMode: yes`, `NotifyInit: yes`, `Notifications: yes` (mirrors h3adcr-b's `editconfig()` behavior); uses a `.headcrabd` marker so it only patches once
- **Platform guards** — all public functions in `slssteam.py` now return immediately on non-Linux platforms (`_IS_LINUX` guard); the startup call in `Main.py` was already guarded by `if sys.platform == "linux":`

---

## 6.2.1

### Bug Fixes

- Fixed system tray icon not appearing after reboot or fresh install — tray now retries automatically every 3 seconds if the system tray is not yet available (Windows shell still loading), and the tray object is properly anchored to the window to prevent garbage collection
- Fixed "Expecting value: line 1 column 1 (char 0)" crash on Update All Manifests and Open Recent .lua file — caused by empty `recent_files.json` or `api_cache.json` files; both now handle empty files gracefully
- Removed Offline Mode Fix menu entry — this was a GreenLuma-specific feature that no longer applies
- Added SLSteam update check on Linux startup — SteaMidra now silently checks for a newer SLSteam release on every launch and notifies if one is available

---

## 6.2

### LumaCore — Bug Fixes and Improvements

- Fixed critical bug where Lua-added app IDs were invisible to Steam after injection — the app ID vector size was not updated after memory growth in two separate code paths
- Fixed packet router writing modifications directly into Steam's own memory buffers — all patched data now goes into a dedicated local buffer
- Fixed unbounded `g_JobIdToAppId` map growth — entries older than 30 seconds are pruned on each insert
- Fixed data race on the online-fix real app ID — converted to `std::atomic<AppId_t>`
- Fixed race conditions in the send and receive ring buffers — separate mutexes added for each pool
- Fixed DLL unload race — the init thread handle is now stored globally and waited on during detach
- Fixed Steam install path detection at startup — uses `GetModuleHandleExA` + `GetModuleFileNameA` instead of `GetCurrentDirectoryA`, which was unreliable inside DllMain
- Fixed `-onlinefix` flag detection — uses exact word-boundary matching to prevent false matches on flags like `-onlinefixpatch`
- Fixed buffer overflow risk in the packet router — size check added before all protobuf serialization calls
- Fixed controller and game overlay compatibility when `-onlinefix` is active
- Fixed IPC handler lookup — replaced linear O(N) scan with an O(1) unordered map
- Added `RichPresence` module — games unlocked via Lua now show a "currently playing" status in Steam

### SteaMidra — Improvements

- Auto LC Setup now removes the legacy `diversion.dll` file when updating from an older LumaCore version
- Added `LumaCoreManager` class for consistent app ID management on Windows
- Added game name caching for Lua backup file listings
- Various download manager, UI, and SLSteam improvements
- Also fixed the bugs with OS unsupported and all that stuff

---

## 6.1.5

### New Feature — LumaCore replaces GreenLuma (Windows)

- LumaCore replaces GreenLuma as the DLL injector. Copy `dwmapi.dll` + `LumaCore.dll` into your Steam folder — no AppList folder, no `DLLInjector.ini`, no restart to add games.
- **Auto LC Setup** (Home tab) — copies LumaCore DLLs from `sff/lumacore/` to your Steam folder and removes existing GreenLuma files automatically.
- **LC Online Fix** (Home tab) — toggles `-onlinefix` in Steam's `localconfig.vdf` for a chosen app ID. LumaCore handles the SpaceWar (AppID 480) redirect at launch.
- LumaCore reads `Steam/config/stplug-in/*.lua` — the same folder SteaMidra writes to. No migration needed.
- Hot-add: games appear in the Steam library the moment their Lua file is created.
- GreenLuma Settings page section removed: GL version, AppList folder, AppList profiles, achievement tracking, and ID limit settings are gone.

### New Feature — Windows Installer (`SteaMidra-6.1.5-Setup.exe`)

- Added a modern NSIS MUI2 wizard installer for Windows.
- Installs to `C:\Program Files\SteaMidra` by default; user can choose any directory.
- Components page lets users select: .NET 9 Runtime, Visual C++ 2022 Redistributable (x64 + x86), Desktop Shortcut, Start Menu Shortcut.
- .NET 9 Runtime and VC++ 2022 Redistributable components detect existing installations and skip silently if already present. Downloads happen at install time from official Microsoft URLs.
- Prompts the user to add the installation directory to Windows Defender exclusions (prevents false-positive flags on the download tool).
- Registers SteaMidra in Windows Add/Remove Programs (with publisher, version, icon, and uninstall string).
- Uninstaller gracefully terminates `SteaMidra_GUI.exe`, removes all files, shortcuts, registry entries, and the Defender exclusion.
- `build_installer.bat` automates the full build: runs PyInstaller then compiles the NSIS script.

### Improvement — Settings Page: Updates Section

- "Check for Updates" is now a prominent button at the very top of the Settings page under a dedicated "Updates" section.
- Current version is displayed dynamically next to the button.
- The small link previously hidden in the "About" section has been removed.

---

## 6.1.4

### Bug Fix — Download Library / Drive Picker Missing on Home Tab Steam Downloads

- The Home tab "Steam" source download button was calling `download_game_with_source` directly, bypassing `_startDownload`. This meant the Steam library selection dialog never appeared when multiple libraries were detected, so downloads always went to the first library.
- Fixed: the button now routes through `_startDownload`, which shows the library picker before handing off to the download function.

### Bug Fix — DDMod Downloaded Non-Windows Depots (Linux / macOS Content)

- DepotDownloaderMod had no OS filter, so it would request depots whose `oslist` is set to `linux` or `macos` only — depots that contain no Windows game files. For multi-platform titles this wasted bandwidth and disk space downloading content that serves no purpose on Windows.
- Fixed: new `filter_depots_by_os` helper reads the `config.oslist` field from App Info for each depot and drops any depot whose oslist is non-empty and does not include `windows`. Applied in `ui.py` (`process_lua_full`, `process_from_store`) and `web_bridge.py` (`download_game_ddmod`).
- DDMod itself is now also launched with `-os windows` as an additional safeguard.

### Bug Fix / Performance — DDMod Efficiency Improvements

- Reduced `-max-downloads` from 255 to 32 — 255 simultaneous CDN connections caused throttling and incomplete transfers on many CDN nodes.
- Replaced the byte-by-byte stdout read loop with `readline()` — the old loop burned significant CPU for every character emitted by DDMod during a download.

### Bug Fix — Depot History Fill-Forward Included Future Depots

- The "Older Versions" fill-forward logic incorrectly included depots in build groups that predate the depot's own debut. For example, a depot that first appeared on 2024-01-15 could show up inside a version group dated 2023-06-01.
- Fixed: if all dated non-CM manifest entries for a depot are strictly newer than the group date, the depot is excluded from that group.

### Bug Fix — GUI Freeze / Memory Growth During Downloads

- Web UI log forwarding (`_forward_log_to_web`, `_forward_stdout_to_web`) now returns immediately when `_web_ui_active` is `False`, preventing signal emissions and string processing for a panel the user is not looking at.
- Stdout forwarding to the web UI is now throttled — at most one emission per 50 ms — so rapid DDMod progress lines cannot flood the Qt signal queue.
- The classic UI `QPlainTextEdit` log now has `setMaximumBlockCount(5000)`, capping unbounded line accumulation during very long downloads.

### Bug Fix — Store Tab Game Search Auto-Creates Missing Game List

- If `all_games.txt` did not exist (e.g. fresh install, file deleted), the Store tab search silently returned no results with no indication of what was wrong.
- Fixed: `search_games_file` now calls `update_games_file()` in the background and returns a user-visible message while the download runs.

---

## 6.1.3

### Bug Fix — Cloudflare Blocks All Depot Pages (Older Versions)

- Root cause: `curl_cffi` TLS fingerprint mismatches caused Cloudflare to issue 403 responses on every request, and repeated 403s flagged the client IP — causing even the browser to be blocked on the same depot URLs immediately after. This created a 3-session failure loop where no depots were ever scraped (confirmed in logs: RE Village, Skullgirls, and other titles with aggressive CF protection).
- Fixed with a new 4-layer scraping architecture:
  - **Layer 1** — `curl_cffi` Chrome impersonation (unchanged, ~80% hit rate on fresh sessions)
  - **Layer 2** — `httpx` with cached `cf_clearance` cookie (unchanged, fast no-browser path)
  - **Layer 3A** — `zendriver` (NEW): uses Chrome DevTools Protocol directly — no `navigator.webdriver` flag, no WebDriver protocol — invisible to Cloudflare fingerprinting. Bails after 2 consecutive CF challenges on depot pages (interactive Turnstile requires a GUI click that CDP cannot perform) and hands off to Layer 3B immediately.
  - **Layer 3B** — `SeleniumBase` UC mode: now clicks the Cloudflare Turnstile "Verify you are human" checkbox automatically via `uc_gui_click_captcha()` (OS-level mouse click). All sessions use a visible browser window — headless mode prevented the click from registering.
- `curl_cffi` is now disabled for the remainder of a session after 3 consecutive 403s, preventing IP contamination that was poisoning the browser layer.
- New `_is_cf_challenge(html)` helper replaces the brittle `'td.tabular-nums' not in html` check with accurate CF marker detection.
- SeleniumBase tuning: reconnect timeout 5s -> 8s, element wait 7s -> 12s, inter-page sleep 0.2-0.5s -> 1.5-3.0s, consecutive CF restart threshold 2 -> 3.
- Layer 3A outer timeout reduced to 90s; `zendriver` exits early if CF persists on the first 2 depot pages.
- `_detect_sb_browser` now checks the Windows registry (`HKLM` + `HKCU` `App Paths\chrome.exe`) for system Chrome before falling back to Chrome for Testing.

### Bug Fix — High RAM Usage During Downloads

- `QtWebEngineProcess.exe` could consume several GB of RAM during long downloads. Root cause: `_appendLog` in the web UI appended every download progress line as a full DOM node with no eviction, causing unbounded DOM growth.
- Fixed: added a 1000-entry ring-buffer eviction to `_appendLog` (matching the existing 200-entry cap on `_appendHomeLog`).
- Secondary fix: `http_utils.py` debug log now records response byte count instead of the full response body, preventing multi-MB JSON responses from being serialised into the log DOM.

### New Dependency

- `zendriver>=0.15.0` added to `requirements.txt` and `requirements-linux.txt`.

---

## 6.1.2

### Bug Fix — Buzzheavier Download Always Failed

- `_download_buzzheavier` used a two-step flow that hit `/{id}/download` with no token. Buzzheavier now requires a signed time-based token embedded in the page HTML. The old flow received HTML back instead of a file, causing 403 errors or py7zr reporting "not a 7z file".
- Fixed: rewrote to a four-step flow — fetch page, extract token via regex, trigger download with token, validate magic bytes. Falls back to Server 2 (`&alt=true`) if Server 1 returns no redirect. Covers all callers: HV cracks, crack fixes, and Auto GL Setup.

### Bug Fix — Auto GL Setup Unicode Crash on Windows

- `greenluma_setup.py` logged the extraction step with a `→` arrow (U+2192). On systems using cp1252 encoding this raised a `UnicodeEncodeError` and aborted setup.
- Fixed: replaced `→` with `->`.

### Bug Fix — Auto GL Setup "Not a 7z File" on Wrong Extension

- `extract_archive` dispatched solely on file extension. If the extension was wrong (e.g. a `.7z` file that was actually RAR or ZIP), it raised immediately with no fallback.
- Fixed: when the extension-based extractor raises, the function now tries RAR, 7z, and ZIP in sequence before giving up.

### Docs — CrakFiles Guide Added

- New `docs/CRACK_FILES.md` documents the CrakFiles repository, the JSON structure, all field definitions, and how SteaMidra fetches and uses the fix list.

---

## 6.1.1

### Feature — Auto GreenLuma One-Click Download & Setup

- The GreenLuma setup modal now downloads GreenLuma directly from the official link with one click. No need to locate or browse for an archive file.
- Progress is reported live during download, extraction, and INI patching.

### Bug Fix — DLLInjector GetHBITMAP Failed After Auto Setup

- DLLInjector.ini was not receiving `UseFullPathsFromIni = 1` or a cleared `BootImage` value after auto-setup. Without `UseFullPathsFromIni = 1`, absolute paths written to the INI were ignored; a leftover `BootImage` path caused Windows to call `GetHBITMAP` on a non-existent bitmap file.
- Fixed: INI patcher now enforces all required keys to match the reference working configuration.

### Bug Fix — "Through Steam" Download Option Triggered DDMod Anonymously

- The "Through Steam (Fastest)" button in the download choice dialog was routing through `process_lua_full` which also runs DepotDownloaderMod at the end using anonymous login. This caused 401 errors on games whose depot manifests require an authenticated session.
- Fixed: button now routes directly to `download_game_fastest` (Steam-native path only, no DDMod invocation).

---

## 6.1.0

### Bug Fix — System Tray Icon Not Visible

- **Root cause:** `TrayIcon.setup()` called `self._tray.setIcon(app_icon)` without checking `app_icon.isNull()`. A null `QIcon` is truthy in Python, so the tray icon was created with no icon and stayed invisible.
- Fixed: icon is now only set when `not app_icon.isNull()`. The tray icon appears correctly on first launch.

### Bug Fix — Remove Button Dialog Closed Janky

- Modal dismiss was instant (`display: none` with no exit animation), so the dialog snapped away instead of fading out.
- Fixed: modal now plays a `fadeOut + slideDown` animation over 150 ms before hiding. The deleted game card also fades and shrinks out before the library grid refreshes, so there is no sudden flash.

### Bug Fix — Horizontal Scrollbar Visible in Library

- The `.content` area had `overflow-y: auto` but no `overflow-x` rule, so any element that briefly overflowed caused a bottom scrollbar.
- Fixed: added `overflow-x: hidden` to `.content`.

### Bug Fix — Linux Startup Crash (SLSteam Config Missing)

- **Root cause:** `UI.__init__` called `SLSManager(steam_path, provider)` unconditionally on Linux. `SLSManager.__init__` raised `FileNotFoundError` when `~/.config/SLSsteam/config.yaml` did not exist, crashing the app before it opened.
- Fixed: `SLSManager` is now created inside a `try/except FileNotFoundError`. If the config is absent, `sls_man` is set to `None` and a warning is logged. SteaMidra starts normally without SLSteam. Run "Linux Tools Setup" to install SLSteam.

### Bug Fix — Linux Taskbar Icon Not Visible (KDE / Wayland)

- KDE Plasma requires both `app.setDesktopFileName()` and `window.setWindowIcon()` to display the icon in the taskbar. Only `app.setWindowIcon()` was called.
- Fixed: `app.setDesktopFileName("steamidra")` is now set on Linux at startup, and `window.setWindowIcon()` is called directly on the `SFFMainWindow` instance after creation.

## 6.0.5

### DDMod Download — Correct Game Folder Name

- DDMod downloads now resolve the install folder name from Steam App Info (`config.installdir`) instead of defaulting to `App_{appid}`.
- If Steam App Info is unavailable (offline / no connection), the first short game-name comment from the Lua file is used as the folder name.
- Final fallback remains `App_{appid}` so downloads never silently fail.

### DDMod Download — ACF File Created After Download

- An ACF (`appmanifest_{appid}.acf`) is written to the Steam library's `steamapps/` folder after every successful DDMod download.
- ACF contains correct `appid`, `name`, `installdir`, `buildid`, `SizeOnDisk`, and all installed depot + manifest IDs.
- Steam recognises the install without any manual file editing.

### DDMod Download — Manifest Folder Selector

- Both DDMod modals now show a Manifest Folder row when a local Lua file is selected.
- Point to any folder of pre-extracted `.manifest` files (e.g., from a ZIP) and those manifests are used directly — no re-fetching required.

### DDMod Download — ManifestHub + GitHub Auto-Fetch

- For any depot whose manifest ID is known but the manifest file is missing, SteaMidra now tries ManifestHub and GitHub automatically before passing control to DepotDownloaderMod.
- Fetched files are written to both the staging folder and `depotcache` immediately.

### DDMod Download — ZIP Lua Support

- Lua files packaged as `.zip` are now fully supported. The `.lua` is extracted from the archive and any `.manifest` files embedded in the ZIP are seeded into `depotcache` automatically.

### Bug Fix — DDMod Log Double Prefix

- Log messages forwarded from the Qt logging system to the web UI log panel no longer show a doubled log-level prefix (e.g., `INFO INFO message`).

### Bug Fix — Cloud Save Provider Not Persisting

- **Root cause fixed** — `cloud_provider`, `cloud_rclone_exe`, and `cloud_rclone_remote` were missing from the `Settings` enum. Every call to save these from the Cloud Saves tab silently did nothing. On restart the provider always reverted to local and rclone fields were empty.
- Added all three as proper `SettingItem` entries. The Cloud Saves tab now saves and restores the chosen provider and rclone configuration correctly across restarts.

### Bug Fix — rclone Auto-Backup Silently Failing

- **Bundled exe fallback** — the Settings page auto-backup intentionally stores `rclone_exe = ''` (user should not need to enter a path). `_cloud_save_backup` in `main_window.py` returned early when the exe was empty. Now falls back to `third_party/rclone/rclone.exe` (same logic already present in the manual backup path).

### Bug Fix — Google Drive Shows Not Connected on Restart

- Resolved by the provider persistence fix above. `cloud_provider = 'gdrive'` now saves and restores, so `_checkGdriveStatus()` fires automatically on page enter. `get_service()` refreshes the cached OAuth token without user interaction.

### Auto-Scan for New Games

- `_cloud_save_backup` already called `scan_all_save_locations` before every backup run. New game save folders are picked up automatically — no manual rescan required. This path was unreachable before due to the silent save bug above.

### CMD Flash Hardening

- Added `stdin=subprocess.DEVNULL` to every rclone `subprocess.run` call across `cloud_saves.py`, `main_window.py`, and `web_bridge.py`. Closes stdin cleanly and prevents any stdin-triggered console allocation on Windows.

---

## 6.0.4

### Bug Fix — rclone CMD Window

- **CMD flash fixed** — `rclone_backup_save`, `rclone_list_remotes`, and `rclone_test_remote` in `web_bridge.py` now pass `creationflags=CREATE_NO_WINDOW` on Windows. Auto cloud save no longer opens visible CMD windows repeatedly in the background.

### Fixes & Bypasses

- **New feature** — `sff/crack_fix.py` downloads community-maintained fixes and bypasses from the `KoriaPolis/CrakFiles` GitHub JSON. Searches by game name, presents matched fixes with badge labels, downloads from buzzheavier, and extracts directly into the game folder. Available as "Fixes & Bypasses" in the CLI menu and Web UI.
- Replaces the Ryuu API requirement — no API key needed.

### HyperVisor Bypasses (HVAuto)

- **New feature** — `sff/hv_fix.py` downloads HyperVisor bypass files from the `KoriaPolis/HVAuto` GitHub JSON. Searches by game name, downloads from buzzheavier, and extracts into the game folder. Available as "HyperVisor (HVAuto)" in the CLI menu and Web UI.

---

## 6.0.3

### Bug Fix — Silent Cloud Save Backups

- **CMD window flash fixed** — all `subprocess.run` calls for rclone in `cloud_saves.py`, `main_window.py`, and `web_bridge.py` now pass `creationflags=CREATE_NO_WINDOW` on Windows. The backup process no longer opens visible CMD windows that flash and close repeatedly.

### Store — VR Games Category

- **VR genre chip** — added a VR chip to the Store genre row. Clicking it searches for VR games via the existing genre-chip mechanism.

### Home & Library — Search Bars

- **Home game filter** — a text input above the game selector filters the dropdown list in real-time as you type.
- **Library search** — a search input in the Library controls bar filters visible game cards by name without reloading.

### Library — Disk Space Display

- **Drive info** — the Library page now shows free and total disk space for the Steam installation drive (e.g. `💾 450.2 GB free of 931.5 GB`).
- New `get_disk_usage(path)` bridge slot returns `{total, used, free}` bytes.

### Cloud Saves — Backup Progress Bar

- **Live progress bar** — the All Save Locations backup now shows a progress bar with per-game granularity. It displays percentage fill, current game label, done/total count, and live ✓ succeeded / ✗ failed counters. The bar auto-hides 3 seconds after completion.

### Home — Auto GreenLuma Setup (Windows only)

- **Auto GL Setup button** — new compact card in Quick Tools (Windows only). Opens a modal to choose installation method (next to SteaMidra.exe or inside Steam folder), browse for the GL archive (ZIP/RAR/7z), and set the Steam exe path.
- **`sff/greenluma_setup.py`** — new module: extracts GL archive, finds the DLL, patches `DLLInjector.ini` with correct `Exe` and `Dll` paths, creates `AppList/` folder. Supports ZIP (built-in), RAR (`rarfile` + WinRAR fallback), 7z (`py7zr` + system 7z fallback).
- **`rarfile>=4.2`** added to `requirements.txt`.

---

## 6.0.2

### Library — Lure Fix

- **Lure Fix button** — each Library game card now has a Lure Fix button. It contacts Steam CM, reads the latest manifest IDs and buildid for the public branch, and patches the game's ACF file in-place. No game files are downloaded or changed. Steam stops showing the update prompt because the ACF now claims the current manifests are installed.
- **Info callout** — the Library page shows a short description of what Lure Fix does, visible above the game grid.
- **Bridge slot** `lure_fix_acf(app_id)` — callable from any JS context. Emits `task_finished {task:"lure_fix"}`.

### Settings — Avatar

- **Global GBE avatar** — browse for a PNG/JPG image and apply it to all games at once via GSE Saves/settings/account_avatar. The avatar preview loads on page enter and updates as you browse.

### Library — Game Update Check

- **Update button** — each Library card now has an Update button. Clicking it compares the installed ACF buildid against the current public buildid on Steam CM. If a newer build exists, it downloads updated manifests and patches the ACF InstalledDepots/MountedDepots automatically, then shows a toast with the new build number. If already current, it shows "Already up to date".

### Workshop Downloader

- **Download Item button** — the embedded Workshop browser now has a Download Item button. It reads the current item URL, extracts the workshop item ID, and tries four methods in order: SteamWebAPI direct file_url, GGNetwork API, SteamCMD anonymous, SteamCMD authenticated. Progress shows in a status label below the toolbar.
- **Bridge slot** `download_workshop_item` — the Library page can also trigger workshop item downloads programmatically via the web bridge.

### Workshop Browser

- Persistent Steam session across launches (cookies + storage stored in webengine_profile/).
- Chrome User-Agent for full page rendering.
- Game-specific workshop URL when opening from a Library card.

### Bug Fixes

- Fixed `check_game_update` (Update button) — incorrect internal import paths corrected so the button works at runtime.
- Update Manifests exclusion list modal now pre-populates checkboxes from saved settings on open.
- ACF patched after manifest update to prevent the "0 B installed" regression.

---

## 6.0.1

### System Tray

- **Minimize to tray** — closing the window now hides it to the system tray instead of leaving a background process with no visible icon. The SteaMidra icon appears in the notification area (bottom right).
- **Single instance** — launching the exe while SteaMidra is already running brings the existing window to the front. No duplicate processes.
- **Exit from tray** — clicking Exit in the tray context menu now terminates the process correctly.

### Cloud Saves — Auto Backup

- **Background auto-backup** — SteaMidra checks your save files on a timer and backs up anything that changed. Configure it in Settings under the new Auto Backup section.
- **Interval** — set the check interval in minutes (0 disables it). Changes take effect immediately without restarting.
- **Permanent provider** — pick Local Folder, rclone, or Google Drive. For rclone, enter your remote destination and click Load Remotes to autocomplete from your configured remotes. For Google Drive, it reuses the account you already connected in Cloud Saves. The chosen provider persists across restarts.
- Backup runs in a background thread so the app stays responsive.

---

## 6.0.0

### Cloud Saves — Google Drive Support

- **Google Drive cloud saves** — back up and restore saves directly to Google Drive. Select Google Drive in the Cloud Saves tab provider grid, click Connect, and sign in once. All backups go to a `SteaMidra Backups/` folder in your Drive.

### Cloud Saves — All Save Locations

- **All Save Locations** — new section at the bottom of the Cloud Saves tab. Scans all known emu save paths in one click: CODEX, EMPRESS, RUNE, OnlineFix, Goldberg, GSE, and Steam userdata. Results show in a table with per-row checkboxes so you can pick exactly which folders to back up.
- **Backup all** — back up every checked folder to a local destination, rclone remote, or Google Drive in one operation.
- **Restore from backup** — scan an existing backup root, pick a location and game from the dropdowns, and restore. A safety backup of the current save is created automatically before any overwrite.

### Cloud Saves — rclone Overhaul

- **Dropbox API provider removed** — Dropbox now works through rclone. No app key or OAuth flow needed. Add a Dropbox remote once with `rclone config` and pick it in SteaMidra.
- **Ludusavi removed** — bundled executable and its 86 MB manifest removed from the package.
- **Provider shortcut strip** — 17 clickable provider chips in the rclone config panel: Dropbox, OneDrive, MEGA, pCloud, Box, Proton Drive, Backblaze B2, Amazon S3, Wasabi, Yandex Disk, Jottacloud, Koofr, Storj, iCloud Drive, SFTP, FTP, WebDAV. Each chip pre-fills the Remote Destination field with the correct format for that backend.
- **"Setup in Terminal" button** — opens `rclone config` in a new terminal window directly from the Cloud Saves tab. On Linux it tries `gnome-terminal`, `xterm`, `konsole`, and `xfce4-terminal` in order.
- **"Load Remotes" button** — reads all configured rclone remotes and populates autocomplete on the destination input.
- **"Test" button** — verifies a remote is reachable before starting a backup (15 s timeout).
- **Backup All is now parallel** — all selected games upload simultaneously instead of one at a time. Significantly faster on every provider.
- **Duplicate auto-fix** — any duplicates created by rclone are resolved automatically after every Backup All on providers that support deduplication.

### Performance

- **Image themes no longer lag** — Dawn, Dusk, Flow, Lake, Midnight City, and Snow themes now run smoothly at full speed.
- **GPU hardware acceleration enabled** — the entire interface now renders with hardware acceleration.

### Settings — Language Live Switch

- Language changes now apply instantly without restarting the app.

---

## 5.8.0

### Self-Updater — Windows Fix

- **Cmd window no longer closes instantly** — PyInstaller EXEs run inside a Windows Job Object. The updater batch was launched with `DETACHED_PROCESS` only, so Windows killed it the moment SteaMidra exited. Added `CREATE_BREAKAWAY_FROM_JOB` flag so the batch runs independently of the parent job.
- **Files no longer locked during update** — `sys.exit(0)` from a Qt worker thread raised `SystemExit` in that thread only, leaving the Qt main loop and all file handles alive. Replaced with `os._exit(0)` to kill the full process cleanly before robocopy runs.
- Both the script-mode path (`_do_auto_update`) and the frozen EXE path (`_do_windows_frozen_update`) are fixed.

### HyperVisor (HV Auto) — Buzzheavier Download Fix

- **Automatic download now works** — buzzheavier.com uses a two-step download flow: a request to `/{id}/download` with HTMX headers returns an `Hx-Redirect` header containing a signed CDN URL; SteaMidra then streams the file from that URL. Previously a plain GET returned an HTML page, causing a fallback to manual download every time.
- **Correct filename from CDN** — filename is parsed from the `Content-Disposition` header of the CDN response, falling back to `{file_id}.7z` if absent.
- **Archive password auto-filled** — password-protected HV archives (`.zip`, `.7z`, `.rar`) now automatically use `cs.rin.ru` during extraction.

---

## 5.7.0

### Linux — SLSsteam Fixes

- **Fixed "NoneType is not iterable" crash** — `AdditionalApps: null` in the SLSsteam config now handled correctly. `YAMLParser.read()` also catches all parse/IO errors and returns a safe empty value so callers never receive `None`.
- **Offline mode confirmation prompt** — toggling a Steam account to offline mode now shows a warning before writing the change, preventing accidental Steam lockout.
- **Bundled SLSsteam binaries removed** — SteaMidra no longer ships outdated `.so` files. The installer always downloads the latest SLSsteam release from GitHub (`AceSLS/SLSsteam`).
- **Arch Linux package conflict fix** — installer now removes the `slssteam` or `slssteam-git` pacman package before installing, matching the reference install flow and preventing `.so` conflicts.

---

## 5.6.0

### Ryuu Generator — New Lua Endpoint

- **Ryuu endpoint added** — third option for Lua and manifest downloads alongside OurEveryday and Hubcap. Requires a Ryuu API key; downloads a ZIP containing the Lua file and all manifests in one request.
- **Optional update request** — before downloading, you can request Ryuu to regenerate data for the game. Works in both CLI (prompt) and the web UI (checkbox in the download modal, only shown when Ryuu is selected).
- **Ryuu API Key in Settings** — stored securely; enter it once in the Settings tab or the CLI key prompt.

### Store Tab Improvements

- **Ryuu source selector** — download modal now shows three sources: Hubcap, OurEveryday, Ryuu. Selecting Ryuu reveals the optional update-request checkbox.

---

## 5.5.0

### Modern UI — New Browser-Based Interface

- **New modern interface** built with QWebEngine — replaces the classic Qt widget UI as the primary interface. All tabs are accessible from a sidebar with a clean, themed layout.
- **Home tab** — select a game from a dropdown populated from all your Steam libraries. Refresh button rescans instantly; the list also refreshes automatically after a download and every 10 minutes.
- **Store tab** — browse and search the Hubcap manifest library. Switch between grid and list view, sort by latest or other criteria, and paginate through results. Download opens the version picker for full depot/manifest history.
- **Library tab** — view all installed Steam games across your libraries.
- **Downloads tab** — live progress bars for active downloads and a full download history.
- **Fix Game tab** — full emulator setup pipeline: apply Goldberg, ColdClient, or ColdLoader; remove SteamStub DRM; launch script generation.
- **Tools tab** — GBE Token Generator (generates full Goldberg configs with achievements, stats, DLCs, depots, and icons), VDF Key Extractor, and embedded Workshop browser.
- **Cloud Saves tab** — scan all games with cloud saves, back up the `remote/` folder to any destination, and restore with one click (automatic safety backup created before any overwrite).
- **Settings tab** — theme picker (11+ themes), Steam path, API keys, AppList profile management, and all other preferences.
- Tooltips on every control, toast notifications for actions, and a floating log viewer accessible from any tab.

---

## 5.4.0

### Store Tab — Bug Fixes & Improvements
- **Crash fix** — Download button can no longer be re-enabled by table row clicks or incoming search results while a depot history fetch is already in progress. All three re-enable paths are now guarded by a `_fetching` flag, preventing a second fetch thread from starting concurrently.
- **All historical manifest IDs now fetched** — Cache freshness check now requires at least one non-Steam-CM source entry (GitHub mirror or SteamDB). Previously a cache containing only the current Steam CM manifest would be served as "fresh" indefinitely, hiding all historical manifests from the version picker.
- **Force Refresh button** — New button next to Download bypasses both the disk cache and the in-memory session cache entirely. Use it when version history looks incomplete or you want to force a fresh SteamDB scrape.
- **SteamDB batch scraper timeouts improved** — `uc_open_with_reconnect` increased 4→5 s, `wait_for_element` 3→7 s, fallback sleep 1→3 s, retry sleep 3→5 s. Greatly reduces Cloudflare challenge failures during multi-depot batch scraping.
- **asyncio loop fix** — `_fetch_steamdb_layer1` (curl_cffi fast path) now uses `asyncio.new_event_loop()` + `run_until_complete()` instead of `asyncio.run()`, fixing silent failures on Windows when called inside a QThread.
- **Chrome download progress** — Status label now shows "Downloading Chrome for Testing (~300 MB, one-time setup)…" during the one-time Chrome for Testing download instead of appearing to hang silently.

### UI — Floating Log Viewer
- **"Logs" button in menu bar** — New button to the right of Help opens a floating, non-modal log viewer showing all Python `logging` output from every part of the app (Fix Game, Store, Tools, and everything else). Supports DEBUG / INFO / WARNING / ERROR level filter, Clear, and Copy All. Closing the window hides it; it can be re-opened at any time.

### GBE Fork Update
- **Updated Windows GBE fork DLLs** — `steam_api.dll`, `steam_api64.dll`, `steamclient.dll`, `steamclient64.dll`, `GameOverlayRenderer.dll`, `GameOverlayRenderer64.dll` now use the experimental builds (~19 MB) which include full overlay support.
- **Fixed DLL extraction bug** — Goldberg auto-updater now correctly extracts experimental DLLs instead of the smaller regular builds. Full archive path is matched first before filename-only fallback.
- **Added Linux `steamclient.so`** — `steamclient.so` (x64) and `steamclient32.so` (x32) are now downloaded and deployed for Linux native games that load steamclient directly.

### Achievement & Config Generation Fixes
- **Achievements now always generated** — Fix Game pipeline now automatically uses the saved/default Steam Web API key if none is explicitly provided. Achievements were silently skipped before.
- **Per-game `configs.main.ini` now written** — `steam_settings/configs.main.ini` is generated for each game with `allow_unknown_stats=1` so stats work even without a full `stats.json`.
- **Stats format fixed** — `stats.json` now uses the correct GBE fork field names (`name`, `type`, `default`, `global`) instead of raw Steam API fields.
- **Achievement `hidden` field fixed** — `achievements.json` `hidden` field is now always a string (`"0"` or `"1"`) as required by GBE fork.
- **Overlay config updated** — `configs.overlay.ini` now includes 4 new options from the latest GBE fork release: `overlay_always_show_user_info`, `overlay_always_show_fps`, `overlay_always_show_frametime`, `overlay_always_show_playtime`.

### Tools Tab
- **GBE Token Generator pre-fills API key** — Steam Web API key is now auto-filled from saved settings (or default key) on startup. Generation no longer aborts if the field is empty — uses default key as fallback. Key is saved to settings after successful generation.

### UI Improvements
- **Fix Game tab decluttered** — checkboxes grouped into logical rows: Goldberg update + Launch.bat in one row; SteamStub + Experimental in one row. Reduces vertical space.

---

## 5.3.0

### Fixes
- **Steam launch "Access Denied" fix** — SteaMidra now checks if it is already running as administrator. If it is, it launches Steam directly instead of requesting elevation again (which caused an "Access Denied" error on Windows 11).
- **Auto-updater fixed for Windows EXE builds** — now downloads the release ZIP, extracts it next to the EXE, replaces the `_internal/` folder via a batch script, and relaunches automatically. No more aria2c or manual steps.
- **Auto-updater fixed for Linux AppImage builds** — downloads the release ZIP, extracts it, then runs `steamidra_install.sh` in your terminal automatically.

### Improvements
- **Windows EXE is now distributed as a ZIP folder** (`SteaMidra-5.3.0-windows.zip`). Extract once anywhere, run `SteaMidra_GUI.exe` from the extracted folder. This replaces the single-file EXE.
- **No more temp folder extraction on startup** — files are pre-extracted into `_internal/` at install time. Startup is faster and antivirus false positives are greatly reduced.

---

## 5.2.0

### AppList popup notification (GUI)
- **GUI now shows a warning dialog** when your AppList reaches 130 or more App IDs, reminding you to create a new AppList profile before adding more games. The popup appears once per session after any action completes. The CLI has always printed a warning at the same threshold — this extends it to the GUI.

### Linux fixes (12 bugs)
- **`all_games.txt` crash fix** — `choices.py` and `cloud_saves.py` both read/wrote `all_games.txt` using `sys._MEIPASS` or the bare `root_folder()` path, which points to the read-only squashfs inside an AppImage. Fixed to use `root_folder(outside_internal=True)` (writable user data dir `~/.local/share/SteaMidra/`) for both read and write.
- **Flatpak LD_AUDIT path fixed** — `slssteam.py` `patch_steam_sh()` constructed the Flatpak `LD_AUDIT` path with an erroneous `/data/Steam` segment (resulting in a non-existent path). Fixed: `flatpak_base` is now `~/.var/app/com.valvesoftware.Steam` with no extra segment.
- **Flatpak default `.so` paths fixed** — `steam_process.py` default path lists for `SLSsteam.so` and `library-inject.so` contained the same `/data/Steam` error. Fixed to match the correct Flatpak layout.
- **7z exit-code tolerance** — `install_from_github()` now tolerates non-zero 7z exit codes caused by symlink warnings (common with `SLSsteam-Any.7z`). If `setup.sh` is found in the extracted directory despite the non-zero code, extraction continues with a warning instead of aborting.
- **`extract_dir.mkdir()` added** — the extraction directory is now created explicitly before the 7z call, preventing `FileNotFoundError` on first install.
- **Config template from extracted archive** — new `_setup_config_from_extracted()` copies `res/config.yaml` from the freshly downloaded archive to `~/.config/SLSsteam/config.yaml` (only if the user config doesn't exist). Previously the bundled copy was used, which could be stale.
- **`updates.yaml` URL corrected** — was `main/updates.yaml`, now `refs/heads/main/res/updates.yaml` to match the actual repo structure.
- **Hash parsing fixed** — replaced broken regex approach with YAML `SafeModeHashes` parsing so `check_steamclient_hash()` correctly validates the hash against all known entries.
- **Flatpak `.so` copy** — new `_copy_so_to_flatpak()` copies installed `.so` files to the Flatpak Steam path after install, so Flatpak Steam can find them.
- **`get_installed_version()` + `check_update_available()`** — new functions to track and check the installed SLSsteam version against the latest GitHub release.
- **GitHub-only install** — removed the bundled install option from `handle_linux_setup()`. SLSsteam is now always installed from the latest GitHub release.
- **Update check menu** — when SLSsteam is already installed, a 3-way menu now appears: check for updates / reinstall from GitHub / skip. The update check shows installed vs latest version and prompts to install if an update is found.

### Documentation + README cleanup
- Removed all references to CreamAPI Multiplayer Fix from `README.md`, `USER_GUIDE.md`, `QUICK_REFERENCE.md`, and `MULTIPLAYER_FIX.md` (feature was removed in 4.9.1).
- Removed broken `CREAMAPI_FIX.md` link from `MULTIPLAYER_FIX.md`.
- Removed "Fast SteamDB manifest history" from `README.md` features list.
- Clarified download methods in `README.md` and `FEATURE_USAGE_GUIDE.md`: Main tab "Download Game" = latest version via Steam-native download (fast, no .NET); Store tab = older/specific versions via DepotDownloaderMod (.NET 9 required, slower).
- Fixed false claim in `README.md` that SteaMidra "reminds you" at 130 IDs — it now accurately says a popup dialog appears.

---

## v5.1.0

### Store tab ACF fix: Play button instead of Update

- **ACF `InstalledDepots`** now uses the **latest manifest GIDs** from the Steam API (not the Lua IDs). Steam compares these IDs against CDN on startup; writing the latest GIDs means Steam sees the game as fully up-to-date and shows **Play** instead of **Update**.
- **ACF `buildid`** is now fetched from the Steam API (`depots.branches.public.buildid`) and written correctly, matching the installed version Steam expects.
- **ACF `LastUpdated`** is now set to the current Unix timestamp on every write.
- **Depotcache cleanup**: manifest files are pre-downloaded for DepotDownloaderMod authentication, then **deleted from `depotcache`** immediately after the download completes. The Store tab no longer leaves stale `.manifest` files in your Steam depotcache folder.
- **Linux**: `buildid` is also fetched from the Steam API in the Linux download path.

---

## v5.0.0

### Store tab — direct game download (Windows + Linux)

- **Download game files directly** from the Store tab version picker via DepotDownloaderMod. Previously the Store tab only set up Lua/manifests and left the actual game download to you; now it downloads the full game automatically.
- **Full pipeline**: Lua fetch → decryption keys written → manifest pre-download → DepotDownloaderMod download → ACF written → Steam library registered.
- **Parallel manifest download** support — respects the `USE_PARALLEL_DOWNLOADS` setting.
- **Real `SizeOnDisk`** calculated from the downloaded files and written into the ACF.
- **Linux**: same pipeline available via `handle_linux_download` with `acf_writer.create_acf`.

---

## 4.9.1

### online-fix.me Multiplayer Fix — complete rewrite
- **SeleniumBase UC mode** — Cloudflare bypass + ad blocking built-in. No more manual Chrome setup.
- **3-layer ad popup prevention** — extracts the uploads URL directly from the game page before clicking (Layer 1); falls back to smart 15s polling that closes only confirmed ad tabs and preserves the uploads tab (Layer 2); final page-source re-scan fallback (Layer 3).
- **Smart file server navigation** — automatically enters subfolders (`Fix Repair/`, `Generic/`, `Steam/`, `Patch/`) before scanning for archives.
- **OFME exclusion** — files containing "OFME" in the name (full game packages, typically 800 MB+) are completely excluded from download candidates.
- **401 error handling** — proactive browser refresh after initial navigation + up to 3 in-loop refresh retries when the file server returns 401, resolving transient nginx authentication failures automatically.
- **Re-apply fix replaces files** — applying the fix a second time now replaces existing fix files directly. The original `.bak` of the game's own DLL is preserved; no redundant second-level backups are created.

### Removed
- **CreamAPI Multiplayer Fix** — "Apply CreamAPI Multiplayer Fix" and "Restore CreamAPI Multiplayer Fix" menu items removed. The bundled CreamAPI DLLs remain in `third_party/online_fix/` for potential future use.

---

## 4.9.0

### CreamAPI Multiplayer Fix (new feature)
- **Apply CreamAPI Multiplayer Fix** — new menu item. Installs bundled CreamAPI v5.3.0.0 (nonlog build) to spoof your game as Spacewar (AppID 480) for online multiplayer. No credentials, no browser, no external downloads required.
- **Restore CreamAPI Multiplayer Fix** — new menu item to undo the fix and restore original DLLs.
- **Classic mode** (default): replaces `steam_api.dll` / `steam_api64.dll` in-place; `cream_api.ini` placed next to the DLL.
- **Proxy mode** (anti-cheat fallback): CreamAPI installed as `winmm.dll`; original Steam API DLLs untouched.
- **Anti-cheat detection**: automatically scans for EasyAntiCheat and BattlEye folders/files; suggests Proxy mode if found.
- **Linux platform selection**: on Linux, user chooses Proton/Wine (Windows .dll) or Native Linux (.so). ELF bitness is read from the header to select x64 vs x86 `.so` automatically.
- **Spacewar auto-check**: reads all Steam library ACF files to detect if Spacewar (AppID 480) is already installed. If not, shows a one-time `steam://install/480` prompt and stores a marker file so the user is never prompted again after the first time.
- **Existing online-fix.me button unchanged** — both methods coexist in the menu.
- **Version bump**: 4.8.4 → 4.9.0

---

## 4.8.4

### Linux Compatibility Overhaul
- **Linux GBE files now fully bundled** — `third_party/gbe_fork_linux/` ships `libsteam_api.so` (x64), `libsteam_api32.so` (x32), and `generate_interfaces_x64/x32`. No internet needed on first run.
- **Fixed archive path resolution** — x64 vs x32 `libsteam_api.so` are now correctly distinguished by their full archive path, not filename (both have the same name in the release archive).
- **Linux generate_emu_config bundled** — `third_party/gbe_fork_tools_linux/` ships the Linux ELF binary. Works without Wine or any external tool.
- **GSE tool updater: Linux support** — `gse_tool_updater.py` now finds and runs the bundled Linux binary, with optional update checking against `Detanup01/gbe_fork_tools` on GitHub.
- **GSE tool updater: Windows bundled fallback** — if GitHub is unreachable, the Windows `generate_emu_config.exe` bundled in `third_party/gbe_fork_tools/` is now used as an offline fallback.
- **Fix Game tab: Linux native checkbox** — new "Linux native game" checkbox (visible on Linux only, checked by default). Uncheck for Proton/Wine mode.
- **Bundled Goldberg used on first launch** — previously, if "Check for updates" was unchecked and the cache was empty, the pipeline would abort. Now it automatically copies from `third_party/` on first run.
- **XDG_DATA_HOME support** — GSE Saves root on Linux respects `$XDG_DATA_HOME` per the official gbe_fork README.
- **Steamless via Wine** — `steamstub_unpacker.py` now runs `Steamless.CLI.exe` via Wine on Linux if Wine is available.
- **Platform-aware launch scripts** — `launch.sh` for native Linux, `launch_wine.sh` + `LUTRIS_SETUP.txt` for Proton/Wine mode.
- **Cache path XDG-compliant** — cache directory on Linux uses `~/.local/share/SteaMidra/fix_game_cache/`.

---

## 4.8.3

### New features
- **SteamDB 3-layer scraping** — dramatically faster manifest history loading. Layer 1 uses `curl_cffi` Chrome impersonation (no browser, ~80% hit rate). Layer 2 reuses a cached `cf_clearance` cookie (25-min disk cache, no browser). Layer 3 falls back to SeleniumBase and automatically saves the cookie for the next run. Warm runs typically complete in 10–35s vs 2–4 min previously.
- **DLC depot completeness** — manifest history now includes depots from DLC apps. The Steam CM fetcher reads `extended.listofdlc` and pulls depot manifests from each DLC app, so games with DLC show their full depot history.
- **Linux: SLSSteam ID management** — "Manage SLSSteam IDs" menu option now works on Linux. Fully functional Add IDs and View/Delete IDs from the SLSSteam config.
- **MIDI player rewrite** — playlist support, dynamic `.mid` / `.sf2` file scanning from the `c/` folder, COM-thread safety fix, and `IsFinished()` polling so tracks don't restart on loop.
- **Settings applied live** — editing or deleting a setting in the GUI now takes effect immediately without restarting.

### Fixes
- **ACF writing reverted** — `write_acf` restored to `StateFlags=4` with `SizeOnDisk=0`, `BytesToDownload=0`, `BytesDownloaded=0`. Previously used `StateFlags=6` + `buildid=0` which caused Steam to show "Play" instead of "Update" for new installs.
- **`_patch_acf_error_state` cleaned** — removed problematic `buildid=0` and `InstalledDepots`/`MountedDepots` deletion that caused game state corruption. Now only clears safe flags: `UpdateResult`, `FullValidateAfterNextUpdate`, `ScheduledAutoUpdate`, byte counters, and the Locked `StateFlags` bit.
- **AppList depot completeness** — `add_ids()` now adds every unique depot/DLC ID from `LuaParsedInfo.depots`, not just the base `app_id`. Previously only the base app ID was added, causing GreenLuma to miss depot authentication and Steam to skip downloading large chunks of games (e.g., RE9 only downloading 1 GB instead of 76 GB).
- **Code formatting cleanup** — removed excessive double-spacing and blank lines across all Python files while preserving copyright headers.
- **Linux MIDI library path** — `MidiFiles.MIDI_PLAYER_DLL` now resolves to `.dll` on Windows and `.so` on Linux. Previously always pointed to `.dll`, silently skipping music on Linux even if the `.so` was compiled.
- **Linux applist menu stub removed** — `applist_menu()` previously printed "Functionality for linux will be implemented soon." and returned immediately. It now routes correctly to `SLSManager` on Linux.
- **`ManifestContext` TypeError** — `auto` field in the `ManifestContext` dataclass was missing its type annotation, causing `TypeError: __init__() got an unexpected keyword argument 'auto'` when downloading manifests with auto-fetch enabled.

### Dependencies
- Added `curl_cffi>=0.7` — required for SteamDB Layer 1 Chrome impersonation.

---

## 4.8.2

- MIDI player integration: background playback thread, channel muting, soundfont support.
- Live settings apply for GUI.
- AppList profiles: create, switch, save, delete, rename.
- Cloud Saves: backup and restore Steam userdata saves.
- VDF Key Extractor: pull depot decryption keys from Steam's config.vdf.
- GBE Token Generator: generate full Goldberg emulator configs with achievements, DLCs, and stats.
- Fix Game pipeline: automate emulator application with SteamStub unpacking.
- Store browser with pagination.
- System tray icon.
- Multi-language GUI (English + Portuguese).
- 11+ themes.

---


## v4.6.5

### New features

- **SteamAuto:** One-click auto-crack via SteamAutoCrack for the selected game. In the GUI, select a Steam game or a folder for a game outside Steam, then click SteamAuto to run the full crack process. In the CLI, choose Steam or non-Steam, then pick the game or enter its path and App ID. Place the Steam-auto-crack repo in `third_party/SteamAutoCrack` and optionally build its CLI into `third_party/SteamAutoCrack/cli/` (or use the build script when the repo is present).

---

## v4.6.4

### New features

- **AppList profiles:** Work around GreenLuma's 130–134 ID limit by using multiple profiles. Create empty profiles, switch between them, save the current AppList to a profile, and delete or rename profiles. Each profile can hold up to 134 IDs (configurable in settings). When you reach 130 IDs, a message reminds you to create a new profile before adding more games.

---

## v4.6.3

### New features

- **Embedded Workshop browser:** Open Workshop from the GUI to browse Steam Workshop in an embedded web view. Login to Steam, browse workshop pages, copy links, and download items without leaving SteaMidra. Uses a persistent profile so your session is kept.
- **Workshop item download:** Paste a workshop URL or item/collection ID to download manifests. Supports single items and full collections.
- **Check mod updates:** Track workshop items and check for newer versions, then update outdated mods in one go.
- **Check for updates – automatic install:** When a newer version is available, download and update automatically. SteaMidra fetches the release, extracts it, and replaces files in your install folder.

---

## v4.6.2

### Removed features

- **Steam patch removed:** The Steam patch feature (xinput1_4.dll, hid.dll) has been removed from all variants.
- **Sync Lua removed:** The option to sync saved Lua files and manifests into Steam's config has been removed.
- Version bump to 4.6.2.

---

## v4.6.1

### Multiplayer fix (online-fix.me) – Selenium login fix

- **Login now works:** The multiplayer fix no longer uses HTTP-only login, which often failed with "Login failed (form still visible)". It now uses **Selenium with Chrome**: a headless browser opens the game page, fills in your credentials, clicks the login button, and handles cookies and JavaScript like a real browser. Login and download should work reliably.
- **What you need:** Chrome browser must be installed. Selenium is in the main requirements: `pip install -r requirements.txt`.
- Search, match, download button, and archive extraction flow are unchanged; only the login step is now browser-based.

---

## v4.5.4

### Check for updates – automatic install

- **Automatic update:** When a newer version is available, you can choose "Download and update automatically?". SteaMidra downloads the release zip, extracts it, and replaces the files in your install folder. When running from **source** (Python), the app restarts with the new version. When running from the **EXE**, SteaMidra does not relaunch the EXE; it tells you to rebuild the EXE so the new updates take effect.
- Updates use the same folder as your current install, so no manual copying or extracting is needed.

---

## v4.5.3

### Multiplayer fix (online-fix.me) – correct game and better matching

- **"Game: Unknown" fixed:** The game name is now read from the ACF in the **same Steam library** where the game is installed (e.g. if the game is on `D:\SteamLibrary\...`, we read that library’s manifest, not the first one). If the name is still missing, we fetch the official name from the **Steam Store API** so we never search with "Unknown".
- **Wrong game match fixed:** Search now uses a stricter minimum match (50%) and prefers results whose link text contains the game name (e.g. "R.E.P.O. по сети" for R.E.P.O.). We also search with "game name online-fix" to narrow results. This avoids picking the wrong game (e.g. "Species Unknown" when you selected R.E.P.O.).

---

## v4.5.2

### Update check (Check for updates)

- **Check for updates** now works for everyone: it always checks GitHub for the latest release and shows your version vs latest.
- If you're up to date: *"You're already on the latest version."*
- If a newer version exists: you can open the release page in your browser to download (or, for the Windows EXE with a matching update package, update from inside the app).
- The updater uses proper GitHub API headers and a fallback when the "latest" endpoint is unavailable.

### DLC check reliability

- **DLC check** no longer gets stuck when Steam is slow or times out.
- Steam API requests (app info, DLC details) now retry up to 3 times with a short delay instead of looping forever.
- If Steam still fails after retries, SteaMidra automatically falls back to the **Steam Store** (no login): it fetches the DLC list and names from the store website and still shows which DLCs are in your AppList/config and lets you add missing ones.
- So the DLC check works even when the Steam client connection is flaky.

### Other fixes

- **credentials.json** is now in `.gitignore` so it never gets committed or included in release zips.
- **UPLOAD_AND_PRIVACY.md** updated with release-zip instructions and what to exclude.

---

## v4.5.1

### Fix for crash on startup (`_listeners` error)

**What was the problem?**

Some people got a crash when starting SteaMidra. The error said something like:  
`'SteamClient' object has no attribute '_listeners'. Did you mean: 'listeners'?`

That happened because the wrong Python package named "eventemitter" was installed. SteaMidra needs a specific one called **gevent-eventemitter**. There is another package with a similar name that does not work with SteaMidra and caused the crash.

**What we changed**

- We now tell the installer to use the correct **gevent-eventemitter** package so new installs should not hit this crash.
- If you already had the crash, do this once:
  1. Open a command line in the SteaMidra folder.
  2. Run: `pip uninstall eventemitter`
  3. Run: `pip install "steam[client]"`
  4. Run: `pip install -r requirements.txt`
  5. Start SteaMidra again.

After that, SteaMidra should start normally.
