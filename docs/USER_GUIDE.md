# SteamForge Fetcher (SFF) User Guide - How to Use

## Menu Navigation

You might find it difficult to navigate the menu options, so here's what each one does.

### Process a .lua file
The main functionality of SFF. It goes through 8 steps:

**1. Input Methods**
- Add a .lua file: Manually import a .lua file that you own
- Choose from saved .lua files: Every .lua file you add gets saved by SFF, you can find them again through here (usually to update games)
- Automatically download a .lua file: Automatically download a .lua file from either manilua or oureveryday

**2. GreenLuma Achievement Toggle via Registry**
"Would you like Greenluma (normal mode) to track achievements?"

GreenLuma is able to track achievements and store them in the registry. Afaik, they can only be viewed by using external apps like Achievement Watcher (You have to use darktakayanagi's fork for GL2025 support). If you want to only run this part, there's always the original method via GreenLumaSettings_2025.exe

**3. Adding AppList IDs**
IDs from the .lua file get added to the AppList folder

**4. DLC Check**
(Check DLC section)

**5. Config VDF Writing**
Decryption keys from each depot get added to config.vdf

**6. Lua Backup**
.lua file gets saved to the 'saved_lua' folder

**7. ACF Writing**
".acf file found. Are you updating a game..."
Creates/overwrites .acf file for the game. These files basically track the state of a game. You usually don't need to overwrite but it's there just in case.

**8. Manifest Downloading**
The manifest is downloaded, and then moved to the depotcache folder. It used to also decrypt but that's been moved to the (Manifest downloads only) mode, since it's unnecessary.

### Process a .lua file (Manifest downloads only)
Basically like the first one, but it only does the .lua file input and backup, and manifest downloads. This also has an extra prompt that asks if you'd like to move these manifest files to a different folder or not. This option does not show up by default. You'll have to enable Advanced Mode in settings.

### Check DLC status of a game
There are two types of DLC. Ones that have a depot and ones that don't. SFF calls them DOWNLOAD REQUIRED and PRE-INSTALLED respectively.

- For DOWNLOAD REQUIRED, you'll need to find a .lua that contains keys for that DLC
- For PRE-INSTALLED, all you need to do is allow SFF to add them to your AppList folder

### Crack a game (gbe_fork)
Basically disconnects a game from Steam so it can run independently. Can also track achievements, and has its own in-game overlay UI.

### Remove SteamStub DRM (Steamless)
Some games will fail to run because of this DRM, run this to fix that.

### Download UserGameStatsSchema (achievements w/o gbe_fork)
Uncracked games can use Steam's actual achievement system locally. Use this to create the files needed for that to work. You can view your achievements in the library UI and in-game, but you do need to run Steam in Offline Mode.

### Offline Mode Fix
GreenLuma has a bug where if you launch Steam while in Offline Mode, it gets stuck. Use this to fix that.

### Manage AppList IDs
You can view and delete IDs that have been added to the AppList folder here.

### Patch / Unpatch Steam (DLL)
### Check for updates
You can update SFF using this. It's a bit funky though.

### Install/Uninstall Context Menu
You can immediately access SFF through right-clicking a .lua/.zip file. This just launches SFF immediately into the Process a .lua file section, along with the file you right-clicked.

### Settings
You can change settings set by SFF here. They usually get set automatically as you use SFF.

---

## Main Features

### 1. Process .lua Files (Standard SFF feature)
Downloads game manifests and sets up GreenLuma.

**Steps**:
1. Run `python Main.py`
2. Select "Process a .lua file"
3. Choose Steam library
4. Select lua source (auto-download recommended)
5. Enter game name or App ID
6. SFF will automatically:
   - Add to AppList
   - Check for DLC
   - Add decryption keys
   - Write ACF file
   - Download manifests
   - Restart Steam

**Time**: 2-5 minutes per game

---

### 2. Apply Multiplayer Fix (NEW - Online-fix.me)
Downloads and installs multiplayer fixes from online-fix.me.

**Steps**:
1. Run `python Main.py`
2. Select "Apply multiplayer fix (online-fix.me)"
3. Choose Steam library
4. Select your game
5. Enter credentials (first time only)
6. SFF will automatically:
   - Login to online-fix.me
   - Search for your game
   - Download Fix_Repair file
   - Extract to game folder

**Time**: 2-10 minutes (depends on download size)

**What You'll See**:
```
Searching for: [Game Name]
Finding best match...
Logging in...
Finding download link...
Selected: Fix_Repair_Steam_V4_Generic.rar
From: uploads.online-fix.me
Downloading... 45.3 MB
✓ Downloaded: Fix_Repair_Steam_V4_Generic.rar

Extracting: Fix_Repair_Steam_V4_Generic.rar
To: C:\...\GameFolder
Using password: online-fix.me
Archiver: 7z
✓ Extraction complete!

✓ Multiplayer fix successfully applied!
```

---

## Tips & Tricks

### Game Names
- Use full official names (e.g., "Counter-Strike: Global Offensive" not "CS:GO")
- Check online-fix.me website if game not found
- Fuzzy matching helps but exact names work best

### Credentials
- Saved securely after first use
- Update in Settings menu if needed
- Stored in SFF settings (encrypted)

### File Selection
The code automatically picks the best file:
- V4 Generic (newest, best compatibility)
- V2 Generic (older, still good)
- Generic (basic version)

### What Gets Installed
Typical fix includes:
- `steam_api.dll` / `steam_api64.dll` - Steam emulator
- `steam_settings/` - Configuration files
- Achievement/stats support
- Multiplayer components

---

## Common Issues

### "Killing Steam..." Hangs
**Fixed!** Now completes in 1-2 seconds. If it takes longer:
- Wait 15 seconds
- Choose "Force close" if prompted
- Or close Steam manually

### "No matching game found"
- Try full official name
- Check online-fix.me for exact name
- Example: "RAFT" → "Rafting over the network"

### "Download timeout"
- Check internet connection
- Disable antivirus temporarily
- Try again later

### "Wrong password"
- Very rare (all files use "online-fix.me")
- Contact online-fix.me support

### "Permission denied"
- Run SFF as administrator
- Check game folder permissions

---

## Performance

### Normal Operation:
- Steam kill: 1-2 seconds
- Game search: 3-5 seconds
- Download: 1-10 minutes (file size dependent)
- Extraction: 10-30 seconds
- Total: 2-15 minutes per game

### What's Fast:
✅ Steam operations (1-2 seconds)
✅ Game search (3-5 seconds)
✅ Extraction (10-30 seconds)

### What Takes Time:
⏱️ Downloads (depends on internet speed and file size)

---

## Settings

### Manage Credentials:
1. Go to Settings menu
2. Select "Online-fix.me Username" or "Password"
3. Update or delete as needed

### Change Steam Path:
1. Settings → "Steam Installation Path"
2. Browse to new location

### Change AppList Folder:
1. Settings → "GreenLuma AppList Folder"
2. Browse to your GreenLuma folder

---

## Safety Notes

✅ **Credentials**: Stored securely (encrypted)
✅ **Downloads**: From official online-fix.me servers
✅ **Extraction**: Password-protected archives
✅ **No data sent**: Everything runs locally
✅ **Open source**: You can review the code

⚠️ **Always backup**: Save your game files before applying fixes
⚠️ **Antivirus**: May flag files (false positive - common with game fixes)
⚠️ **Use responsibly**: Respect game developers

---

## Quick Reference

### Main Menu Options:
- **Process a .lua file** - Standard SFF feature
- **Apply multiplayer fix** - NEW online-fix.me integration
- **Check DLC status** - See what DLC a game has
- **Crack a game** - Apply gbe_fork emulator
- **Remove DRM** - Use Steamless
- **Settings** - Configure SFF

### Keyboard Shortcuts:
- Type to search in menus
- Enter to select
- Ctrl+C to cancel

### File Locations:
- **Credentials**: Stored in SFF settings (encrypted)
- **Downloads**: Temporary folder (auto-deleted)
- **Extracted files**: Game installation folder
- **Logs**: `debug.log` in SFF folder

---

## Need Help?

1. Check error messages (they're helpful!)
2. Read `debug.log` for details
3. Verify Chrome and Selenium installed
4. Test with different game
5. Check online-fix.me website manually

---

## Summary

**SFF now has two main features**:

1. **Standard .lua processing** - Downloads manifests, sets up GreenLuma
2. **Multiplayer fix** - Downloads and installs fixes from online-fix.me

Both work automatically with minimal user input. Just select what you want and SFF handles the rest!

**Enjoy!** 🎮
