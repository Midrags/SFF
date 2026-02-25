# Multiplayer Fix

SteamForge Fetcher (SFF) can download and apply multiplayer fixes from online-fix.me for supported games.

**What you need**

An account on online-fix.me. Create one on their website. You will enter your username and password in SFF the first time you use the feature. SFF stores them securely.

Depending on the version of SFF, you may need extra Python packages. If the project includes a batch file for online-fix requirements, run it. Otherwise the Setup Guide or project README will say what to install (for example httpx, beautifulsoup4, lxml, or selenium).

**How to use it**

Run SFF, then choose "Apply multiplayer fix (online-fix.me)" or the equivalent from the menu. Pick your Steam library and the game. SFF will log in, find the fix, download it, and extract it into the game folder. The first time you may need to enter your online-fix.me credentials.

**If something goes wrong**

If login fails, check your username and password on the online-fix.me website. If the game is not found, try the full official game name. If downloads or extraction fail, check your internet connection and antivirus. If it still fails, check debug.log in the SFF folder or ask for help on Discord.

**Responsibility**

Use this feature at your own risk. SFF only automates downloading and extracting files from online-fix.me. Respect the site’s rules and the game’s terms.
