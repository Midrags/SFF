# Setup Guide

What you need to use SteamForge Fetcher (SFF) and how to get started.

**Before you start**

You need Steam installed on your PC. SFF will ask for your Steam folder if it can't find it (usually the folder that contains steam.exe).

**GreenLuma (required for the main workflow)**

SFF works with GreenLuma. You need to download GreenLuma yourself and set it up.

- Download GreenLuma: https://www.up-4ever.net/h3vt78x7jdap  
- Extract the ZIP and follow the instructions that come with GreenLuma.  
- When SFF asks for the AppList folder, point it to the AppList folder inside your GreenLuma folder.

**Python and dependencies (if you run from source)**

If you run SFF with Python instead of the EXE:

1. Install Python (from python.org).  
2. Open a command prompt in the SFF folder and run:  
   `pip install -r requirements.txt`  
3. Optional (Windows notifications):  
   `pip install -r requirements-optional.txt`

**Optional: Steam patch (Windows only)**

If you want Steam to read the game data SFF prepares without using an extra injector, you can use the Steam patch. The two files (`xinput1_4.dll` and `hid.dll`) are included in the `steam_patch` folder. In SFF choose **Patch / Unpatch Steam (DLL)** from the main menu and pick **Patch Steam**. Restart Steam when done.

**Multiplayer fix (online-fix.me)**

For the multiplayer fix feature you need:

- A browser (Chrome is recommended) and an archiver (7-Zip or WinRAR).  
- An account on online-fix.me. Create one on their website; SFF will ask for your username and password the first time you use the feature.

If the project includes a batch file for online-fix requirements, run it. Otherwise run:  
`pip install selenium`

**If something doesn't work**

- "Steam path not found" — Choose the folder that contains steam.exe.  
- "DLLs not found" — The two DLLs should be in the steam_patch folder; if they're missing, make sure you have the full SFF package.  
- "Selenium not installed" — Run the pip install command above.  
- "Login failed" — Check your online-fix.me username and password on their website.

If you run into other problems, check the error message and debug.log in the SFF folder, or ask on Discord.
