SteaMidra v6.3.9

What's new:

* Store search now waits for Enter or the Search button before searching, so typing no longer spams backend requests.
* Store result ranking is improved. App IDs, exact names, prefixes, word-start matches, and aliases now rank above loose fuzzy matches.
* Home Live Log and the native Logs window now respect a line limit setting, defaulting to 100 lines. Long runs like Update All Games should no longer slow the UI with massive scrollback.
* Lua hot reload is more reliable. New numeric Lua files refresh the Steam library without needing multiple Steam restarts, and removed Lua files stop leaving stale library cards behind.
* Purchase and install states now settle faster after startup. LumaCore attaches package hooks earlier, verifies the real injected app IDs, and retries from safe late UI frames when Steam loads package data slowly.
* Offline startup is less fragile. If Steam has enough local package data, LumaCore can seed Lua apps without waiting for a full login refresh.
* LumaCore diagnostics are much clearer. `status.json` now explains broken installs with details like missing package data, empty Lua loading, waiting-for-login states, hook misses, ownership checks, cloud decisions, and the latest SteamStub detection.
* Release and Debug builds now stamp `status.json` with build config, build time, package capture state, and latest online-fix payload state, making old DLLs and missed child-process injection easier to spot.
* Managed games that the active account does not own now keep Steam Cloud blocked without touching save folders or forcing Steam to close cloud state, protecting local saves without causing cloud error popups.
* Family-shared games are now separated from fake-managed games. If Steam marks a Lua app as borrowed or family shared, LumaCore leaves its Steam Cloud answer alone.
* Managed games now prefer their existing app ticket or userdata SteamID before using the current login account. Games like Satisfactory should keep using the same save account folder instead of appearing to lose saves under a new ID.
* SteamStub auto routing can now detect Stray-style protected child binaries before launch and route through 480 without needing a hardcoded app ID.
* SteamStub detection is stricter. Generic protection diagnostics no longer force normal managed games into 480, reducing false Spacewar launches.
* SteamStub auto routing stays separate from manual `-onlinefix`. Manual online-fix keeps its multiplayer path, while SteamStub auto keeps Steam tracking on 480 and hides the real game from the running-app packet.
* Manual `-onlinefix` still uses the existing multiplayer route, but EOS games with launcher-child splits now also load the payload into the child process. Mecha Chameleon should no longer get stuck on the missing auth-token login screen after Steam starts the real game exe.

Full detailed changelog is in CHANGELOG.md
