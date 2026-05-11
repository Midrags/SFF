# Fixes & Bypasses

SteaMidra can search and apply game fixes and bypasses from a curated list hosted on GitHub.

## When to use it

Use this if:

- The game isn't available on online-fix.me, or you don't have an account there.
- You want a second source to check when the multiplayer fix doesn't work.
- The game has a bypass (not just a multiplayer fix) that the fix list covers.

## How to use it

1. Select your game from the game list (or set a path for a game outside Steam).
2. Click **Fixes & Bypasses** in the GUI, or choose it from the menu in the CLI.
3. SteaMidra fetches the fix list and shows matches for your game first.
4. Use the fuzzy search to pick the fix you want.
5. The fix downloads and extracts directly into your game folder.

## Notes

- The fix list updates over time. If your game isn't there today, check back later.
- The fix extracts directly into the game folder. If something goes wrong, verify your game files via Steam.
- If the extracted files include a README or instructions, read them — some fixes need extra steps after extraction.
