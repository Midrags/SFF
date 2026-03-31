## What is this ?
This is an old Windows-only library equivalent to `steam_api.dll` that's still used by some old games.  

## Purpose ?
Bypass initial/basic checks in old games.  

## Note
Note that it doesn't emulate all the required functionality at the moment, some functions are still missing.  

## How to use ?

### Option 1:
- Copy & paste this dll beside the game's `.exe` file
- Copy `steam_api.dll` and `steamclient.dll` from the experimental build beside the game's `.exe` file
- Generate the `steam_interfaces.txt` file
- Run the game

### Option 2:
- Copy & paste this dll inside the folder `steam_settings/load_dlls/`
- Copy `steam_api.dll` and `steamclient.dll` from the experimental build beside the game's `.exe` file
- Generate the `steam_interfaces.txt` file
- Run the game

### Option 3:
- Copy the dll to a separate folder, ex: `extra_dlls`
- In `ColdClientLoader.ini` set the options:
  * `ForceInjectSteamClient=1`
  * `DllsToInjectFolder=extra_dlls`
- Run `ColdClientLoader`
