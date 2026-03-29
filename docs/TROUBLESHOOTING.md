# Troubleshooting

Common problems and what to try.

**Steam path not found**

SteaMidra needs to know where Steam is installed. If it cannot find it, it will ask you to choose the folder. Pick the folder that contains steam.exe (often something like Program Files (x86)\\Steam).

**Chrome or ChromeDriver errors (multiplayer fix)**

If the multiplayer fix needs a browser and you get a Chrome or ChromeDriver error, make sure Chrome is installed and updated. Some SFF versions use a different method and do not need Chrome; check the Setup Guide. If you use Chrome, try closing all Chrome windows and running SFF again, or run SFF as administrator.

**Login failed (online-fix.me)**

Check your username and password on the online-fix.me website. If you can log in there, update your credentials in SFF under Settings. Some games may no longer be available on the site.

**Download timeout or extraction failed**

Check your internet connection. Try turning off antivirus temporarily and run SFF again. Make sure you have 7-Zip or WinRAR installed if SFF needs to extract archives. If a download keeps failing, you can try downloading the fix manually from online-fix.me and extracting it into the game folder yourself.

**Permission denied or access denied**

Steam or the game folder may be in a protected location. Try running SFF as administrator (right-click the program and choose "Run as administrator"). Do not run SFF from a folder that requires admin rights to write to.

**Settings export or import error**

If exporting or importing settings fails, try exporting without including sensitive data. Make sure the folder you export to is writable. If you get a message about "JSON serializable", try updating SFF to the latest version.

**Parallel downloads or notifications not working**

Check Settings. There are options to enable or disable parallel downloads and desktop notifications. If notifications do not appear on Windows, the project may list an extra package to install (for example win10toast).

**Cache or backups taking too much space**

You can delete the file api_cache.json; SFF will create a new one when needed. Backup retention is set in Settings; you can lower how many backups are kept.

**Need more help?**

Read the error message first—it often explains what went wrong. You can also check the debug.log file in the SteaMidra folder for details. For how features work, see the [User Guide](USER_GUIDE.md) and [Feature Guide](FEATURE_USAGE_GUIDE.md).
