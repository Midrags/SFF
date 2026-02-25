# Before You Upload or Share

This folder is a **consumer-ready** copy of SMD with no personal data in the code.

## Never commit or upload these

- **settings.bin** – Stores your settings and (if you use them) encrypted passwords.
- **settings_export.json** – Export of settings; can contain paths and usernames.
- **credentials.json** – Online-fix.me login (if present); use **credentials.json.example** as a template only.
- **debug.log**, **crash.log** – Logs that may contain paths.
- **recent_files.json**, **api_cache.json**, **analytics.json** – Local caches.
- **GreenLuma/**, **dlc_unlocker_cache/**, **backups/**, **saved_lua/** – Your own data.
- **build/**, **dist/** – Build outputs.
- **.git/** – Version control (not needed in the zip).
- **Editor/IDE config folders** – Do not include in release zips.

## Making a release zip for GitHub

When zipping this folder to upload to a release, **do not include** the files and folders listed above. Easiest: use `git archive` so only tracked files are in the zip (no .git, no local files):

```bash
git archive --format=zip --output=SMD_2-v4.5.1.zip v4.5.1
```

Then upload **SMD_2-v4.5.1.zip** to the release. If you zip by hand, exclude everything in the "Never commit or upload" list and the **.git** folder.

Editor and IDE config folders are in **.gitignore**, so they are never committed and never appear in a `git archive` zip.

The **.gitignore** in this folder is already set so that these are ignored if you use Git.

## If you use Git

1. Copy this **MainTool_Consumers** folder (or its contents) to your repo.
2. Ensure **.gitignore** is present so the files above are never committed.
3. Run `git status` and confirm that `settings.bin`, `settings_export.json`, and the other listed files do **not** appear.

## Running SMD

- Install dependencies: `pip install -r requirements.txt`
- Optional (Windows notifications): `pip install win10toast`
- Run: `python Main.py`

Settings are saved in **settings.bin** in the same folder as Main.py. Each user gets their own file when they run the tool.
