# Multiplayer Fix

SteaMidra can download and apply multiplayer fixes from online-fix.me for supported games.

---

## online-fix.me method

**What you need**

An account on online-fix.me. Create one on their website. You will enter your username and password in SteaMidra the first time you use the feature. SteaMidra stores them securely.

**How to use it**

Open SteaMidra and choose **Apply multiplayer fix (online-fix.me)**. Select your game from the list. SteaMidra will:

1. Open Chrome with Cloudflare bypass and ad blocking active
2. Log in to online-fix.me automatically
3. Find your game on the site using fuzzy name matching
4. Navigate to the file server, automatically entering subfolders like `Fix Repair/` or `Generic/`
5. Download only the actual fix file (full game packages are excluded automatically)
6. Extract it directly into your game folder, preserving originals as `.bak` backups

Re-applying the fix a second time replaces the fix files directly — the original `.bak` backup of your game's DLL is preserved.

**If something goes wrong**

If login fails, check your username and password on the online-fix.me website. If the game is not found, try the full official game name. If the file server shows 401, SteaMidra retries automatically (up to 3 times). If it still fails, check debug.log in the SteaMidra folder or ask for help on Discord.

**Responsibility**

Use this feature at your own risk. SteaMidra only automates downloading and extracting files from online-fix.me. Respect the site's rules and the game's terms.
