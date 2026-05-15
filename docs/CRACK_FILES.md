# CrakFiles — Fixes & Bypasses Source

SteaMidra's **Fixes & Bypasses** feature fetches a curated game fix list from the CrakFiles repository on GitHub and downloads the selected fix directly into your game folder.

---

## Repository

**GitHub:** https://github.com/KoriaPolis/CrakFiles

**Raw JSON (what SteaMidra fetches):**
```
https://raw.githubusercontent.com/KoriaPolis/CrakFiles/main/crackfiles.json
```

The file is fetched fresh every time you use Fixes & Bypasses — no local cache. If a fix was added to the repo today, it is available immediately.

---

## How SteaMidra uses it

1. You click **Fixes & Bypasses** on the Fix Game tab (GUI) or choose it from the menu (CLI).
2. SteaMidra fetches `crackfiles.json` from GitHub.
3. It tries to auto-match your game by name. Exact matches appear first; you can also fuzzy-search the full list.
4. Once you pick a fix, SteaMidra downloads the archive from the `href` link (buzzheavier.com) directly to a temp folder.
5. The archive is extracted into your game folder automatically.
6. No account needed. No manual download required.

---

## JSON structure

Each entry in `crackfiles.json` looks like this:

```json
{
  "buildid": "20514355",
  "name": "Dead Island 2",
  "source_crack": [
    "https://cs.rin.ru/forum/viewtopic.php?p=3381630#p3381630"
  ],
  "original_download": [
    "https://cs.rin.ru/forum/download/file.php?id=170996"
  ],
  "fixes": [
    {
      "href": "https://buzzheavier.com/yj7sfj59oags",
      "filename": "Dead_Island_2_crack.rar",
      "size": "",
      "badges": ["Crack"]
    }
  ]
}
```

### Field reference

| Field | Type | Description |
|---|---|---|
| `buildid` | string | Steam build ID the fix was made for. Used for auto-matching. Empty string if not tied to a specific build. |
| `name` | string | Game name as it appears in Steam. Used for fuzzy search. |
| `source_crack` | array of strings | Links to the original cs.rin.ru post or thread where the crack/fix was sourced. Provided for traceability — so anyone can verify where the file originally came from. |
| `original_download` | array of strings | Direct download links to the original file on cs.rin.ru (or wherever it was hosted before being mirrored to buzzheavier). |
| `fixes` | array of objects | One or more downloadable fix entries. See sub-fields below. |

### `fixes` sub-fields

| Field | Type | Description |
|---|---|---|
| `href` | string | Download URL (buzzheavier.com). This is what SteaMidra downloads. |
| `filename` | string | Expected filename after download. Used as a display hint. |
| `size` | string | File size as a human-readable string. May be empty. |
| `badges` | array of strings | Labels describing the fix type, e.g. `["Crack"]`, `["Online Fix"]`, `["Bypass"]`. Shown in the selection menu. |

---

## source_crack and original_download

These two fields exist purely for **traceability**. They let anyone follow the paper trail back to where a fix was originally discussed or uploaded, without having to trust the buzzheavier mirror blindly.

- `source_crack` — the cs.rin.ru forum post where the crack was shared or discussed
- `original_download` — the original file download link (often a cs.rin.ru attachment)

Some entries have these empty if the original source could not be found or documented at the time of adding the entry.

---

## Notes

- Fixes extract directly into your game folder. If something breaks, verify game files via Steam to restore originals.
- The fix list covers games not available on online-fix.me and games that need a standalone crack or bypass rather than a multiplayer fix.
- Build IDs go stale when a game updates. If the fix stops working after a game update, check back later — an updated entry may have been added.
- If you want to add a fix for a game not yet in the list, contribute to the CrakFiles repository on GitHub.
