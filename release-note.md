SteaMidra v6.3.8

What's new:

* Update All Games no longer asks for a manual request code when automated sources fail. The full automated cascade now runs and fails quietly, matching the parallel download path.
* Update All Games now respects the Auto Update toggle. Games unchecked in the Auto Update modal are skipped completely, keeping their manifests pinned to the version you chose.
* Removed the youxiou.com link from the fallback sources list.
* Check for Updates in Settings now correctly tells you when SteaMidra is already up to date instead of leaving the button spinning forever.
* DLC Check can now add appid-only DLCs from the Oureveryday button. DLCs without separate depot tags are written into the parent Lua instead of throwing the old “no depots tagged” error.
* LumaCore notice on the Home page now checks the Steam folder before showing. Missing installs and available updates get a clear callout, while current installs keep the Home tab clean.
* Oureveryday and Update All Games downloads are more reliable. The main request-code mirror now gets the expected tool user-agent, and SteamRun JSON replies are parsed correctly.
* Steam library refresh now publishes only numeric Lua filename roots, preventing depot, DLC, and shared body IDs from showing as full library apps or hanging Steam login.
* License refresh is back on the launch-safe path. Ownership checks stay lightweight, AppLicensesChanged handles full reloads, and the package-0 refresh loop is gone.
* LumaCore achievements are easier to use. Numeric Lua filenames now auto-enable stats and achievements for that app, while `setStat(appid)` remains available for manual cases.
* Achievement fetching now tries LumaCore’s SteamID pool and keeps the first useful schema or stat response. If remote replies fail, Steam keeps the local schema instead of blanking the achievement page.
* LumaCore’s in-Steam manifest resolver now uses the provider’s required compatibility user-agent, preventing valid request codes from falling through to “no internet connection”.
* CachyOS setup no longer lets AppImage library paths break 7z with the readline symbol error. SLSsteam extraction now tries the bundled Python extractor first, then retries system 7-Zip with a clean environment.
* Restart Steam now also checks the Steam folder for manually copied SLSsteam libraries after the managed install paths.
* Known Steam Stub games now use a dedicated 480 tracking route. Steam sees 480, while the game-facing overlay, ticket, and stats identity resolve to the real app.
* SteamStub ownership tickets now prefer the app-7 source from Steam’s user-local config store and keep the IPC reply layout Steam expects, reducing error 54/86 launch loops.
* LumaCore now validates AppTicket SteamID and appid before serving it, rejecting stale cross-app tickets before they can affect the next launch.
* Store/search memory usage improved. Only the visible grid or list view renders, and cover images are cleared when leaving the tab to stop RAM from growing across multiple pages.

Full detailed changelog is in CHANGELOG.md
