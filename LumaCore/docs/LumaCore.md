# LumaCore — Feature Reference

This document describes every subsystem in LumaCore, its purpose, the Steam internals it touches, and the configuration interface exposed to SteaMidra via Lua scripts.

---

## Injection chain

Steam loads DLLs from its own directory on startup.  LumaCore exploits this by placing a custom `dwmapi.dll` (a thin proxy that forwards all real DWM exports) alongside `steam.exe`.  When Steam starts, Windows loads the proxy DLL before any game code runs.  The proxy's `DllMain` loads `LumaCore.dll` and returns.

`LumaCore.dll` then:

1. Copies `steamclient64.dll` to `bin\lcoverlay.dll` (with retry logic in case the file is locked).
2. Loads `lcoverlay.dll` explicitly so it has an independent module handle.
3. Reads the current Steam build ID from `steam.exe!GetBootstrapperVersion` and stores it for pattern-search prioritisation.
4. Spawns a worker thread that installs all hooks and starts the Lua directory watcher.

The copy step is necessary because hooking the live `steamclient64.dll` while it is already mapped into the process would require patching code that is in use.  Hooking the private copy avoids race conditions and keeps the original file untouched on disk.

---

## Byte-pattern search (`utils/ByteScan.cpp`)

LumaCore locates Steam internal functions by scanning the loaded DLL image for known byte sequences.  Each function has one or more `Signature` entries in `hooks/PatternDb.h`.  A signature is a hex string where `??` is a wildcard byte.

At startup the scanner reads the Steam build ID and tries the signature whose label matches that ID first.  If the fast-path entry fails (Steam was updated), it falls back to scanning all remaining entries in order.  If no entry matches, the hook is silently skipped and Steam runs that function unmodified.

For functions that contain unique embedded strings (e.g. assert messages), the scanner can locate the function via a string cross-reference instead of (or before) the byte pattern.  See `hooks/StringFind.cpp` and `hooks/PatternDb.h` comments for details.

Note: string cross-reference hooking is available but is not used for critical startup hooks (such as `GetPipeClient` and `IPCProcessMessage` in `IPCBus`).  Those use pure byte-pattern matching to guarantee stable resolution across Steam updates and avoid ambiguous function lookups at early startup.

Run `cleintcheck/steamclient_analyzer.py` after a Steam update to verify existing patterns and generate updated signatures.

---

## Hook modules

### DepotKeys (`hooks/DepotKeys.cpp`)

Hooks `LoadDepotDecryptionKey`.

When Steam mounts a depot it calls this function to fetch the AES-128 decryption key for that depot from the user's license data.  The hook intercepts the call, checks whether `LuaLoader` has a key for the requested depot ID (loaded from the `.lua` script provided by SteaMidra), and writes it into the output buffer.  If no key is known, the call falls through to the original function.

Lua interface:

```lua
addappid(1234567, 1, "0A1B2C3D...")  -- depot 1234567, decryption key
```

---

### IPCBus (`hooks/IPCBus.cpp`)

Hooks `IPCProcessMessage` and resolves `GetPipeClient` — both via pure byte-pattern matching.

Steam uses an internal IPC bus to route messages between its client service and the UI process.  The hook intercepts `IPCProcessMessage`, inspects the command code, and dispatches it to any registered LumaCore handlers.  Currently the following handlers are active:

- `GetSteamID` — returns a spoofed SteamID (see CmdUser below)
- `GetAppOwnershipTicketExtendedData` — produces a synthetic AppTicket for apps in the Lua config

All other messages pass through unmodified.

Both `GetPipeClient` and `IPCProcessMessage` are resolved via byte-pattern scanning only.  String cross-reference was previously attempted but reverted because the referenced strings can resolve to helper functions at early startup, producing a null pipe pointer and crashing Steam on the first IPC Handshake.

---

### CmdUser (`hooks/CmdUser.cpp`)

Handles the `GetSteamID` and `GetAppOwnershipTicketExtendedData` IPC commands.

**GetSteamID**: returns the SteamID configured in `lumacore.toml` under `[user] steam_id`.  For Denuvo-protected titles, which embed the owning SteamID in the AppTicket and validate it at runtime, LumaCore uses `GetDynamicOwnerSteamID`.  That function searches `Steam\userdata\` directories for an account that has local app data for the requested game and returns that account's ID.  This avoids hardcoding a single SteamID for users who run multiple accounts.

**GetAppOwnershipTicketExtendedData**: builds a synthetic AppTicket and ETicket for apps listed in the active `.lua` config.  The ticket includes the SteamID resolved above, the app's package ID read from the Lua script, and a minimal set of ownership flags.

---

### ManifestBind (`hooks/ManifestBind.cpp`)

Handles the manifest-key binding that associates a depot manifest with the active decryption key.  When Steam mounts a manifest, it calls this function to verify that the manifest's encryption was produced with the key the user holds.  The hook ensures keys supplied via Lua are accepted for this check.

---

### SteamCapture (`hooks/SteamCapture.cpp`)

Uses VEH one-shot int3 captures (not Detours hooks) to resolve internal Steam object pointers at runtime.

This module arms single-byte breakpoints at the entry of several Steam functions.  When each fires for the first time, the VEH handler records `RCX` (the `this` pointer) into a module-level variable, then restores the original byte and resumes execution normally.  The captured pointers are:

| Function | Captured into |
|---|---|
| `GetAppIDForCurrentPipe` | `g_steamEngine` |
| `GetAppDataFromAppInfo` | `g_pCAppInfoCache` |
| `MarkLicenseAsChanged` | `g_pCUser` |
| `GetPackageInfo` | `g_pCPackageInfo` |

`ProcessPendingLicenseUpdates`, `CUtlBufferEnsureCapacity`, and `CUtlMemoryGrow` are resolved without int3 (address-only).

`SteamCapture::NotifyLicenseChanged` uses the captured `g_pCUser` and resolved function pointers to push new ownership records into Steam's in-memory license tables and trigger an ownership refresh without restarting Steam.

---

### PacketRouter (`hooks/PacketRouter.cpp`)

Hooks `BBuildAndAsyncSendFrame` and `RecvPkt`.

Steam communicates with the Steam Network (CM servers) using a protobuf-over-TCP framing.  PacketRouter intercepts outgoing and incoming packet frames and replaces the content of specific message types:

- `FamilyGroupsClient.NotifyRunningApps` — replaces the running-app list so family-sharing session checks on the CM side see the correct owner rather than the borrower account.
- `Player.GetUserStats` — rewrites the SteamID in the stats request so achievements are loaded from the account configured in the Lua `setStat` call.

Packet replacement uses a fixed-size ring-buffer pool to avoid heap allocation on the hot path.

Lua interface:

```lua
setStat(1234567, "76561198028121353")  -- load stats from this SteamID for app 1234567
```

If no `setStat` is provided for an app, the fallback SteamID defined in `entry.h` (`ONLINE_FIX_APP_ID`) is used.

---

### PackagePatch (`hooks/PackagePatch.cpp`)

Hooks `LoadPackage`, `CheckAppOwnership`, and `SendCallbackToPipe`.

- **`LoadPackage`** — intercepts the call for Package 0 (the free-to-play base package) and appends all app IDs from the active Lua config to its `AppIdVec`, so Steam considers them part of the base license.
- **`CheckAppOwnership`** — patches the returned `CAppOwnershipInfo` struct for apps present in the Lua config so they show as owned, released, and playable.  If the app is genuinely owned it is marked as such and excluded from future patching.
- **`SendCallbackToPipe`** — intercepts `AppLicensesChanged` callbacks and forces `m_bReloadAll = true` so Steam fully refreshes its license state after an ownership injection.

---

### LicenseHooks (`hooks/LicenseHooks.cpp`)

Reserved for future license-related hooks.  Currently a no-op placeholder; `Install()` performs no operations.

---

### RuntimeCapture (`hooks/RuntimeCapture.cpp`)

VEH-based captures and hooks used by the `-onlinefix` game-launch path.

- Arms a one-shot int3 on `CUser_SpawnProcess`.  When Steam is about to launch a game, the VEH fires, checks whether `-onlinefix` is present in the launch command, and if so records the real app ID for the session.  The original byte is restored and execution continues.
- Hooks `BuildSpawnEnvBlock` (via string XRef, since this function is only called at launch — not at startup — making string-based resolution safe here) to patch `SteamOverlayGameId` and `SteamAppId` environment variables so overlays and stats bind to the correct app.
- Uses `GetAppDataFromAppInfo` captures from `SteamCapture` to resolve game names for rich-presence labelling.

---

### RichPresence (`hooks/RichPresence.cpp`)

Patches `CMsgClientPersonaState` protobuf messages intercepted by PacketRouter.

When an online-fix game is running, Steam's presence broadcasts the SpaceWar app ID (480) rather than the real game ID.  `RichPresence::HandleRecv` rewrites the `game_played_app_id` field to the real app ID resolved by RuntimeCapture, so friends see the correct game name in their friend list.

---

### StringFind (`hooks/StringFind.cpp`)

Implements the string cross-reference search used by the `_STR_D` hook macros.  Scans the `.rdata` section of a module for a target string, finds all code locations that reference it via RIP-relative `LEA`/`MOV` instructions, locates the enclosing function via `.pdata` RUNTIME_FUNCTION lookup, and returns the function entry point.

This is more update-proof for functions called only at game-launch time.  It is intentionally **not** used for hooks that fire during early Steam startup (e.g. `IPCBus`) — those use pure byte patterns to avoid the risk of the string residing in a helper function and resolving to the wrong address.

---

## Lua configuration format

SteaMidra writes `.lua` files to `Steam\config\stplug-in\<appid>.lua`.  LumaCore watches this directory and reloads files as they change.

### App and depot registration

```lua
-- Register ownership of app 1234567 with a depot decryption key
addappid(1234567)
addappid(1001, 1, "0A1B2C3D4E5F6071820394A5B6C7D8E9")
```

`addappid(appId)` — registers ownership of appId without a depot key.
`addappid(depotId, 1, "hexkey")` — registers ownership and provides the AES-128 decryption key for depotId.

### Manifest pinning

```lua
setManifestid(1001, "1234567890123456789")
```

Pins the manifest GID for depot 1001.  LumaCore reports this GID when Steam asks for the active manifest, preventing automatic updates from switching to a newer manifest that may not have a corresponding decryption key.

### Stats and achievements

```lua
setStat(1234567, "76561198028121353")
```

Instructs PacketRouter to load achievement and stats data from the given SteamID for app 1234567.  Required when the game checks online achievement state against a specific account.

---

## Configuration file (`lumacore.toml`)

Placed in the Steam installation directory.  SteaMidra writes this file during LumaCore setup.

```toml
[user]
steam_id = "76561198028121353"  # SteamID64 to spoof in GetSteamID responses
```

All other settings use built-in defaults.

---

## Pattern maintenance

After a Steam client update, some byte patterns in `hooks/PatternDb.h` may stop matching.  Run the pattern analyzer to check:

```
cd cleintcheck
python steamclient_analyzer.py
```

The script scans the bundled `steamclient64.dll`, reports which functions were found and which were not, and emits an updated `Patterns_new.h` with refreshed signatures.  Copy the updated entries into `hooks/PatternDb.h` and rebuild.

---

## Logging

Logging is compiled in only for Debug builds (`LUMACORE_LOGGING_ENABLED` define).  Release builds compile all `LOG_*` macros to no-ops so there is no runtime overhead.

When enabled, logs are written to `Steam\lumacore\` alongside `LumaCore.dll`.  Each module writes to its own file:

| File | Module |
|---|---|
| `main.log` | Core init, DLL loading, build ID detection |
| `ipc.log` | IPCBus — IPC message dispatch |
| `package.log` | PackagePatch / PackageInfo / DirWatch |
| `capture.log` | SteamCapture / RuntimeCapture VEH events |
| `packet.log` | PacketRouter — protobuf frame interception |

Log level is controlled by `lumacore.toml` under `[log] level = "debug"` (default: `info`).
