# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

"""
Cloud saves — local backup and restore for game save files.

Scans common save locations, backs up to %APPDATA%/SteaMidra/save_backups/,
and provides timestamped restore points.
"""

import os
import shutil
import logging
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict

from sff.utils import root_folder

logger = logging.getLogger(__name__)

# module-level cache for all_games.txt — parsed once per session
_ALL_GAMES_CACHE = None


def _load_all_games_cache():
    """Parse all_games.txt into {app_id: name}. Returns cached dict after first call."""
    global _ALL_GAMES_CACHE
    if _ALL_GAMES_CACHE is not None:
        return _ALL_GAMES_CACHE
    _ALL_GAMES_CACHE = {}
    try:
        base = root_folder(outside_internal=True)
        txt = base / "all_games.txt"
        if not txt.exists():
            return _ALL_GAMES_CACHE
        with txt.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # format: Game Name [ID=12345]
                if "[ID=" in line and line.endswith("]"):
                    idx = line.rfind("[ID=")
                    name = line[:idx].strip()
                    appid_str = line[idx + 4 : -1]
                    if appid_str.isdigit() and name:
                        _ALL_GAMES_CACHE[int(appid_str)] = name
    except Exception as e:
        logger.debug("all_games.txt load failed: %s", e)
    return _ALL_GAMES_CACHE

# common save file locations to scan
SAVE_LOCATIONS = [
    # %APPDATA%
    Path(os.environ.get("APPDATA", "")) / "Roaming",
    Path(os.environ.get("APPDATA", "")),
    # %LOCALAPPDATA%
    Path(os.environ.get("LOCALAPPDATA", "")),
    # Documents
    Path.home() / "Documents" / "My Games",
    Path.home() / "Documents",
    # Saved Games
    Path.home() / "Saved Games",
    # Steam userdata
    Path(r"C:\Program Files (x86)\Steam\userdata"),
]

# folder names that often contain game saves
SAVE_FOLDER_HINTS = [
    "save", "saves", "savegame", "savegames",
    "userdata", "profile", "profiles",
    "data", "config",
]


@dataclass
class SaveInfo:
    """information about a detected save location"""
    app_id: int
    game_name: str
    save_path: str
    file_count = 0
    total_size = 0
    last_modified = 0.0


@dataclass
class BackupInfo:
    """information about a save backup"""
    app_id: int
    game_name: str
    backup_path: str
    timestamp: float = 0.0
    file_count: int = 0
    total_size: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _get_backup_dir():
    """get the save backup root directory"""
    base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    backup_dir = base / "SteaMidra" / "save_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


class CloudSaves:
    """
    Local save backup and restore system.

    Backs up game saves to %APPDATA%/SteaMidra/save_backups/{appid}/
    with timestamped snapshots.

    Structure:
        save_backups/
        ├── {appid}/
        │   ├── manifest.json
        │   ├── backup_20260413_120000/
        │   │   └── (save files)
        │   └── backup_20260413_130000/
        │       └── (save files)
        └── ...
    """

    def __init__(self):
        self.backup_dir = _get_backup_dir()

    def detect_saves(self, app_id, game_name = ""):
        """
        Try to detect save files for a game.
        Searches common locations for folders matching the app ID or game name.
        """
        results = []
        search_terms = [str(app_id)]
        if game_name:
            # add cleaned game name variants
            clean_name = game_name.replace(":", "").replace("'", "").strip()
            search_terms.extend([
                clean_name,
                clean_name.replace(" ", ""),
                clean_name.replace(" ", "_"),
            ])
        for base_path in SAVE_LOCATIONS:
            if not base_path.exists():
                continue
            try:
                for item in base_path.iterdir():
                    if not item.is_dir():
                        continue
                    name_lower = item.name.lower()
                    for term in search_terms:
                        if term.lower() in name_lower:
                            info = self._scan_save_dir(item, app_id, game_name)
                            if info and info.file_count > 0:
                                results.append(info)
                            break
            except PermissionError:
                continue
        return results

    def _scan_save_dir(self, path, app_id, game_name):
        """scan a directory for save files"""
        try:
            file_count = 0
            total_size = 0
            last_modified = 0.0
            for f in path.rglob("*"):
                if f.is_file():
                    file_count += 1
                    stat = f.stat()
                    total_size += stat.st_size
                    last_modified = max(last_modified, stat.st_mtime)
            if file_count == 0:
                return None
            return SaveInfo(
                app_id=app_id,
                game_name=game_name,
                save_path=str(path),
                file_count=file_count,
                total_size=total_size,
                last_modified=last_modified,
            )
        except Exception as e:
            logger.warning("Failed to scan %s: %s", path, e)
            return None

    def backup(self, app_id, save_path, game_name = "", log_func=None):
        """
        Create a timestamped backup of save files.
        Returns BackupInfo on success, None on failure.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        src = Path(save_path)
        if not src.exists():
            log(f"Save path not found: {save_path}")
            return None
        # create timestamped backup folder
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / str(app_id) / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        try:
            # copy all files
            file_count = 0
            total_size = 0
            if src.is_file():
                shutil.copy2(src, backup_path / src.name)
                file_count = 1
                total_size = src.stat().st_size
            else:
                for f in src.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(src)
                        dest = backup_path / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, dest)
                        file_count += 1
                        total_size += f.stat().st_size
            info = BackupInfo(
                app_id=app_id,
                game_name=game_name,
                backup_path=str(backup_path),
                timestamp=time.time(),
                file_count=file_count,
                total_size=total_size,
            )
            # save manifest
            self._save_manifest(app_id, game_name, save_path, info)
            log(f"✓ Backed up {file_count} files ({self._format_size(total_size)})")
            return info
        except Exception as e:
            logger.error("Backup failed: %s", e)
            log(f"Backup failed: {e}")
            return None

    def restore(self, app_id, backup_path, save_path, log_func=None):
        """
        Restore save files from a backup.
        Returns True on success.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        src = Path(backup_path)
        dest = Path(save_path)
        if not src.exists():
            log(f"Backup not found: {backup_path}")
            return False
        try:
            # create a safety backup of current saves first
            if dest.exists():
                safety_ts = time.strftime("%Y%m%d_%H%M%S")
                safety_path = self.backup_dir / str(app_id) / f"pre_restore_{safety_ts}"
                shutil.copytree(dest, safety_path, dirs_exist_ok=True)
                log("Created safety backup before restore")
            # restore
            dest.mkdir(parents=True, exist_ok=True)
            restored = 0
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    restored += 1
            log(f"✓ Restored {restored} files")
            return True
        except Exception as e:
            logger.error("Restore failed: %s", e)
            log(f"Restore failed: {e}")
            return False

    def get_backups(self, app_id):
        """get all backups for a game, newest first"""
        app_dir = self.backup_dir / str(app_id)
        if not app_dir.exists():
            return []
        backups = []
        manifest = self._load_manifest(app_id)
        for d in sorted(app_dir.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("backup_"):
                # count files
                files = list(d.rglob("*"))
                file_count = sum(1 for f in files if f.is_file())
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                backups.append(BackupInfo(
                    app_id=app_id,
                    game_name=manifest.get("game_name", ""),
                    backup_path=str(d),
                    timestamp=d.stat().st_mtime,
                    file_count=file_count,
                    total_size=total_size,
                ))
        return backups

    def delete_backup(self, backup_path):
        """delete a specific backup"""
        try:
            shutil.rmtree(backup_path)
            logger.info("Deleted backup: %s", backup_path)
            return True
        except Exception as e:
            logger.error("Failed to delete backup: %s", e)
            return False

    def _save_manifest(self, app_id, game_name, save_path, latest):
        """save per-game manifest with metadata"""
        manifest_path = self.backup_dir / str(app_id) / "manifest.json"
        data = {
            "app_id": app_id,
            "game_name": game_name,
            "save_path": save_path,
            "latest_backup": latest.to_dict(),
        }
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_manifest(self, app_id):
        """load per-game manifest"""
        manifest_path = self.backup_dir / str(app_id) / "manifest.json"
        try:
            if manifest_path.exists():
                return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    # --- Steam userdata methods ---

    @staticmethod
    def list_steam_games(steam_path, steam32_id):
        """
        Enumerate games in Steam userdata for the given Steam32 ID.
        Returns a list of (app_id, game_name) sorted by game name.
        Name resolution — three layers, in order:
          1. appmanifest_*.acf across all Steam library folders (installed games)
          2. SteaMidra fix_game_cache CachedAppInfo (previously fixed games)
          3. Batch Steam Store API call for anything still unresolved (uninstalled games)
        """
        userdata_dir = Path(steam_path) / "userdata" / str(steam32_id)
        if not userdata_dir.exists():
            return []
        # --- collect all app IDs that have a remote/ folder ---
        app_ids = []
        try:
            for item in userdata_dir.iterdir():
                if not item.is_dir() or not item.name.isdigit():
                    continue
                appid = int(item.name)
                if appid == 0:
                    continue
                if (item / "remote").exists():
                    app_ids.append(appid)
        except PermissionError:
            return []
        if not app_ids:
            return []
        name_map = {}
        # --- Layer 1: ACF files via get_steam_libs (same as main menu) ---
        try:
            from sff.storage.vdf import get_steam_libs, vdf_load
            steam_root = Path(steam_path)
            libs = get_steam_libs(steam_root)
            if steam_root not in libs:
                libs = [steam_root] + list(libs)
            for lib in libs:
                steamapps = lib / "steamapps"
                if not steamapps.exists():
                    continue
                for acf in steamapps.glob("appmanifest_*.acf"):
                    try:
                        appid_str = acf.stem.split("_", 1)[1]
                        if not appid_str.isdigit():
                            continue
                        appid = int(appid_str)
                        if appid in name_map:
                            continue
                        data = vdf_load(acf)
                        name = data.get("AppState", {}).get("name", "")
                        if name:
                            name_map[appid] = name
                    except Exception:
                        pass
        except Exception:
            pass
        # --- Layer 2: SteaMidra fix_game_cache (previously fixed games) ---
        unresolved = [a for a in app_ids if a not in name_map]
        if unresolved:
            try:
                from sff.fix_game.cache import FixGameCache
                fgc = FixGameCache()
                for appid in unresolved:
                    info = fgc.load_app_info(appid)
                    if info and info.name:
                        name_map[appid] = info.name
            except Exception:
                pass
        # --- Layer 3: all_games.txt local lookup (instant, offline) ---
        unresolved_3 = [a for a in app_ids if a not in name_map]
        if unresolved_3:
            games_db = _load_all_games_cache()
            for appid in unresolved_3:
                n = games_db.get(appid)
                if n:
                    name_map[appid] = n
        # --- Layer 4: Parallel Steam Store API (last resort for unlisted games) ---
        still_unresolved = [a for a in app_ids if a not in name_map]
        if still_unresolved:
            try:
                import httpx
                from concurrent.futures import ThreadPoolExecutor, as_completed
                def _fetch_name(appid):
                    try:
                        r = httpx.get(
                            "https://store.steampowered.com/api/appdetails",
                            params={"appids": appid, "filters": "basic"},
                            timeout=10.0,
                        )
                        if r.status_code == 200:
                            info = r.json().get(str(appid), {})
                            if info.get("success"):
                                name = info.get("data", {}).get("name", "")
                                if name:
                                    return appid, name
                    except Exception:
                        pass
                    return appid, ""
                with ThreadPoolExecutor(max_workers=5) as pool:
                    futures = {pool.submit(_fetch_name, a): a for a in still_unresolved}
                    for future in as_completed(futures):
                        appid, name = future.result()
                        if name:
                            name_map[appid] = name
            except Exception:
                pass
        results = [
            (appid, name_map.get(appid, f"App {appid}"))
            for appid in app_ids
        ]
        # resolved names first (alphabetical), unresolved "App XXXX" at the bottom
        results.sort(key=lambda x: (x[1].startswith("App "), x[1].lower()))
        return results

    def backup_steam_save(
        self,
        steam_path: str,
        steam32_id: str,
        app_id: int,
        game_name: str,
        dest_folder: str,
        log_func=None,
    ):
        """
        Copy <Steam>/userdata/<steam32id>/<app_id>/remote/ to
        <dest_folder>/<game_name> [<app_id>]/remote/.
        Returns the created backup folder path on success, None on failure.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        src = Path(steam_path) / "userdata" / str(steam32_id) / str(app_id) / "remote"
        if not src.exists():
            log(f"No remote/ folder found at {src}")
            return None
        safe_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in game_name)
        dest = Path(dest_folder) / f"{safe_name} [{app_id}]" / "remote"
        dest.mkdir(parents=True, exist_ok=True)
        try:
            file_count = 0
            total_size = 0
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    file_count += 1
                    total_size += f.stat().st_size
            log(f"✓ Backed up {file_count} file(s) ({self._format_size(total_size)}) → {dest}")
            return str(dest.parent)
        except Exception as e:
            log(f"Backup failed: {e}")
            return None

    def restore_steam_save(
        self,
        backup_folder: str,
        steam_path: str,
        steam32_id: str,
        app_id: int,
        log_func=None,
    ):
        """
        Copy <backup_folder>/remote/ back to
        <Steam>/userdata/<steam32id>/<app_id>/remote/.
        Automatically creates a safety backup of current saves first.
        Returns True on success.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        src = Path(backup_folder) / "remote"
        if not src.exists():
            log(f"Backup remote/ folder not found at {src}")
            return False
        dest = Path(steam_path) / "userdata" / str(steam32_id) / str(app_id) / "remote"
        # safety backup of current saves
        if dest.exists():
            safety_ts = time.strftime("%Y%m%d_%H%M%S")
            safety = self.backup_dir / str(app_id) / f"pre_restore_{safety_ts}"
            try:
                shutil.copytree(dest, safety, dirs_exist_ok=True)
                log(f"Safety backup of current saves → {safety}")
            except Exception as e:
                log(f"Warning: safety backup failed ({e}), proceeding anyway")
        try:
            dest.mkdir(parents=True, exist_ok=True)
            restored = 0
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    restored += 1
            log(f"✓ Restored {restored} file(s) to {dest}")
            return True
        except Exception as e:
            log(f"Restore failed: {e}")
            return False

    @staticmethod
    def _format_size(size_bytes):
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"


# ---------------------------------------------------------------------------
# All-save-locations backup & restore
# ---------------------------------------------------------------------------

EMU_SAVE_LOCATIONS = {
    "Public RUNE":            Path("C:/Users/Public/Documents/RUNE"),
    "Public OnlineFix":       Path("C:/Users/Public/Documents/OnlineFix"),
    "Public Steam EMPRESS":   Path("C:/Users/Public/Documents/Steam/EMPRESS"),
    "Public Steam CODEX":     Path("C:/Users/Public/Documents/Steam/CODEX"),
    "Public CODEX":           Path("C:/Users/Public/Documents/CODEX"),
    "Public EMPRESS":         Path("C:/Users/Public/Documents/EMPRESS"),
    "Public Steam RUNE":      Path("C:/Users/Public/Documents/Steam/RUNE"),
    "Public Steam OnlineFix": Path("C:/Users/Public/Documents/Steam/OnlineFix"),
    "GSE Saves":              Path(os.environ.get("APPDATA", "")) / "GSE Saves",
    "Goldberg SteamEmu Saves": Path(os.environ.get("APPDATA", "")) / "Goldberg SteamEmu Saves",
    "Goldberg SocialClub Emu Saves": Path(os.environ.get("APPDATA", "")) / "Goldberg SocialClub Emu Saves",
}

_BACKUP_ROOT = Path(os.environ.get("APPDATA", "")) / "SteaMidra" / "save_backups"


def _resolve_game_name(folder_name, name_map_cache=None):
    """
    Given a subfolder name, return (app_id_or_none, game_name, label).
    Numeric → resolve from cache layers. String → use as-is.
    name_map_cache is an optional {int: str} dict from ACF / FixGameCache / all_games.
    """
    if folder_name.isdigit():
        app_id = int(folder_name)
        name = None
        if name_map_cache:
            name = name_map_cache.get(app_id)
        if not name:
            games_db = _load_all_games_cache()
            name = games_db.get(app_id)
        if not name:
            try:
                from sff.fix_game.cache import FixGameCache
                info = FixGameCache().load_app_info(app_id)
                if info and info.name:
                    name = info.name
            except Exception:
                pass
        game_name = name or f"App {app_id}"
        label = f"{app_id} - {game_name}"
        return app_id, game_name, label
    else:
        return None, folder_name, folder_name


def scan_all_save_locations(steam_path=None, steam32_id=None):
    """
    Scan all EMU_SAVE_LOCATIONS plus Steam userdata.
    Returns list of dicts:
      {location, folder_name, app_id, game_name, label, source_path, file_count}
    """
    results = []

    # Steam userdata
    if steam_path and steam32_id:
        userdata_dir = Path(steam_path) / "userdata" / str(steam32_id)
        if userdata_dir.exists():
            try:
                name_map = {}
                try:
                    from sff.storage.vdf import get_steam_libs, vdf_load
                    steam_root = Path(steam_path)
                    libs = get_steam_libs(steam_root)
                    if steam_root not in libs:
                        libs = [steam_root] + list(libs)
                    for lib in libs:
                        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
                            try:
                                appid_str = acf.stem.split("_", 1)[1]
                                if not appid_str.isdigit():
                                    continue
                                appid = int(appid_str)
                                if appid not in name_map:
                                    data = vdf_load(acf)
                                    n = data.get("AppState", {}).get("name", "")
                                    if n:
                                        name_map[appid] = n
                            except Exception:
                                pass
                except Exception:
                    pass
                for item in userdata_dir.iterdir():
                    if not item.is_dir() or not item.name.isdigit():
                        continue
                    appid = int(item.name)
                    if appid == 0:
                        continue
                    remote = item / "remote"
                    files = [f for f in item.rglob("*") if f.is_file()] if not remote.exists() else [f for f in remote.rglob("*") if f.is_file()]
                    if not files:
                        continue
                    app_id, game_name, label = _resolve_game_name(item.name, name_map)
                    results.append({
                        "location": "Steam Userdata",
                        "folder_name": item.name,
                        "app_id": app_id,
                        "game_name": game_name,
                        "label": label,
                        "source_path": str(item),
                        "file_count": len(files),
                    })
            except Exception as e:
                logger.warning("scan Steam userdata: %s", e)

    # EMU locations
    for loc_name, base_path in EMU_SAVE_LOCATIONS.items():
        if not base_path.exists():
            continue
        try:
            for item in base_path.iterdir():
                if not item.is_dir():
                    continue
                files = [f for f in item.rglob("*") if f.is_file()]
                if not files:
                    continue
                app_id, game_name, label = _resolve_game_name(item.name)
                results.append({
                    "location": loc_name,
                    "folder_name": item.name,
                    "app_id": app_id,
                    "game_name": game_name,
                    "label": label,
                    "source_path": str(item),
                    "file_count": len(files),
                })
        except Exception as e:
            logger.warning("scan %s: %s", loc_name, e)

    return results


def _make_meta(app_id, game_name, source_path, location):
    import datetime
    return {
        "app_id": app_id,
        "game_name": game_name,
        "source_path": str(source_path),
        "location": location,
        "backed_up_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def backup_save_location_local(entry, dest_root, log_func=None):
    """
    Copy one save entry to dest_root/SteaMidraAllSaves/{location}/{label}/.
    Skips files that are already up-to-date (same size and backup is not older).
    Returns dest folder path on success, None on failure.
    """
    log = log_func or (lambda m: None)
    src = Path(entry["source_path"])
    if not src.exists():
        log(f"[!] Source not found: {src}")
        return None
    label = entry["label"]
    location = entry["location"]
    dest = Path(dest_root) / "SteaMidraAllSaves" / location / label
    try:
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        skipped = 0
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    src_stat = f.stat()
                    dst_stat = target.stat()
                    if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime <= dst_stat.st_mtime:
                        skipped += 1
                        continue
                shutil.copy2(f, target)
                copied += 1
        meta_path = dest / "steamidra_meta.json"
        meta_path.write_text(
            json.dumps(_make_meta(entry.get("app_id"), entry["game_name"], src, location), indent=2),
            encoding="utf-8"
        )
        if skipped:
            log(f"  Backed up {copied} file(s), skipped {skipped} unchanged: {label}")
        else:
            log(f"  Backed up {copied} file(s): {label}")
        return str(dest)
    except Exception as e:
        log(f"  [FAIL] {label}: {e}")
        return None


def backup_save_location_rclone(entry, rclone_exe, remote_dest, log_func=None):
    """Upload one save entry via rclone to remote_dest:SteaMidraAllSaves/{location}/{label}/."""
    import subprocess
    import tempfile
    log = log_func or (lambda m: None)
    src = Path(entry["source_path"])
    if not src.exists():
        log(f"[!] Source not found: {src}")
        return False
    label = entry["label"]
    location = entry["location"]
    remote_path = remote_dest.rstrip("/") + f"/SteaMidraAllSaves/{location}/{label}"
    try:
        proc = subprocess.run(
            [
                rclone_exe, "copy", str(src), remote_path,
                "--update",
                "--transfers", "9", "--checkers", "18",
                "--create-empty-src-dirs",
                "--fast-list",
            ],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            log(f"  [FAIL] rclone exit {proc.returncode}: {proc.stderr[:200]}")
            return False
        meta_tmp = Path(tempfile.mkdtemp(prefix="steamidra_meta_"))
        try:
            meta_file = meta_tmp / "steamidra_meta.json"
            meta_file.write_text(
                json.dumps(_make_meta(entry.get("app_id"), entry["game_name"], src, location), indent=2),
                encoding="utf-8",
            )
            subprocess.run(
                [rclone_exe, "copyto", str(meta_file), remote_path + "/steamidra_meta.json",
                 "--no-update-modtime"],
                capture_output=True, text=True, timeout=30,
            )
        finally:
            shutil.rmtree(meta_tmp, ignore_errors=True)
        log(f"  Uploaded: {label} → {remote_path}")
        return True
    except Exception as e:
        log(f"  [FAIL] {label}: {e}")
        return False


def backup_save_location_gdrive(entry, service, backup_root_id, log_func=None, folder_cache=None):
    """Upload one save entry via Google Drive API with smart sync (skip unchanged, update changed)."""
    import tempfile
    from sff.google_drive import get_or_create_folder, upload_folder, upload_file
    log = log_func or (lambda m: None)
    src = Path(entry["source_path"])
    if not src.exists():
        log(f"[!] Source not found: {src}")
        return False
    label = entry["label"]
    location = entry["location"]
    local_fc = dict(folder_cache) if folder_cache is not None else {}
    try:
        loc_cache_key = (location, backup_root_id)
        if loc_cache_key in local_fc:
            loc_folder_id = local_fc[loc_cache_key]
        else:
            loc_folder_id = get_or_create_folder(service, location, backup_root_id)
            if loc_folder_id:
                local_fc[loc_cache_key] = loc_folder_id
        if not loc_folder_id:
            log(f"  [FAIL] Could not create Drive folder for {location}")
            return False
        ok = upload_folder(service, src, loc_folder_id, log_func=log, folder_cache=local_fc, drive_folder_name=label)
        if ok:
            game_folder_id = local_fc.get((label, loc_folder_id))
            if game_folder_id:
                meta_tmp = Path(tempfile.mkdtemp(prefix="steamidra_meta_"))
                try:
                    meta_path = meta_tmp / "steamidra_meta.json"
                    meta_path.write_text(
                        json.dumps(_make_meta(entry.get("app_id"), entry["game_name"], src, location), indent=2),
                        encoding="utf-8",
                    )
                    upload_file(service, meta_path, game_folder_id, log_func=log)
                finally:
                    shutil.rmtree(meta_tmp, ignore_errors=True)
            log(f"  Synced to Drive: {label}")
        if folder_cache is not None:
            folder_cache.update(local_fc)
        return ok
    except Exception as e:
        log(f"  [FAIL] {label}: {e}")
        return False


def scan_backup_root_rclone(rclone_exe, remote_dest):
    """Scan an rclone remote for SteaMidraAllSaves structure.
    Downloads all steamidra_meta.json files at once, then parses them locally.
    Returns same structure as scan_backup_root_local.
    """
    import subprocess
    import tempfile
    remote_root = remote_dest.rstrip("/") + "/SteaMidraAllSaves"
    tmp = Path(tempfile.mkdtemp(prefix="steamidra_scan_"))
    try:
        subprocess.run(
            [
                rclone_exe, "copy", remote_root, str(tmp),
                "--include", "steamidra_meta.json",
                "--fast-list",
                "--transfers", "10",
            ],
            capture_output=True, text=True, timeout=120,
        )
        result = {}
        if not tmp.exists():
            return result
        for loc_dir in sorted(tmp.iterdir()):
            if not loc_dir.is_dir():
                continue
            games = []
            for game_dir in sorted(loc_dir.iterdir()):
                if not game_dir.is_dir():
                    continue
                meta = {}
                meta_file = game_dir / "steamidra_meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                game_remote = remote_root + "/" + loc_dir.name + "/" + game_dir.name
                games.append({
                    "folder_path": game_remote,
                    "folder_name": game_dir.name,
                    "app_id": meta.get("app_id"),
                    "game_name": meta.get("game_name", game_dir.name),
                    "source_path": meta.get("source_path", ""),
                    "backed_up_at": meta.get("backed_up_at", ""),
                    "rclone_path": game_remote,
                })
            if games:
                result[loc_dir.name] = {
                    "folder_path": remote_root + "/" + loc_dir.name,
                    "games": games,
                }
        return result
    except Exception:
        return {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def scan_backup_root_local(backup_root):
    """
    Scan a local SteaMidraAllSaves root folder.
    Returns same structure as google_drive.list_backup_locations.
    """
    root = Path(backup_root) / "SteaMidraAllSaves"
    if not root.exists():
        return {}
    result = {}
    for loc_dir in sorted(root.iterdir()):
        if not loc_dir.is_dir():
            continue
        games = []
        for game_dir in sorted(loc_dir.iterdir()):
            if not game_dir.is_dir():
                continue
            meta = {}
            meta_file = game_dir / "steamidra_meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            games.append({
                "folder_path": str(game_dir),
                "folder_name": game_dir.name,
                "app_id": meta.get("app_id"),
                "game_name": meta.get("game_name", game_dir.name),
                "source_path": meta.get("source_path", ""),
                "backed_up_at": meta.get("backed_up_at", ""),
            })
        result[loc_dir.name] = {"folder_path": str(loc_dir), "games": games}
    return result


def restore_save_entry(game_entry, log_func=None):
    """
    Restore files from a backup game entry to their original source_path.
    game_entry must have 'source_path' and either 'folder_path' (local) or 'folder_id' (GDrive).
    Creates a safety backup of the current saves first.
    """
    log = log_func or (lambda m: None)
    dest = Path(game_entry.get("source_path", ""))
    if not dest:
        log("[FAIL] No source_path in entry — cannot restore.")
        return False

    rclone_path = game_entry.get("rclone_path")
    rclone_exe = game_entry.get("rclone_exe", "").strip()
    folder_id = game_entry.get("folder_id")
    folder_path = game_entry.get("folder_path")

    if rclone_path and rclone_exe:
        import subprocess
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="steamidra_restore_"))
        try:
            log("Downloading from rclone remote...")
            proc = subprocess.run(
                [
                    rclone_exe, "copy", rclone_path, str(tmp),
                    "--exclude", "steamidra_meta.json",
                    "--transfers", "10", "--fast-list",
                ],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                log(f"[FAIL] rclone download failed: {proc.stderr[:200]}")
                return False
            return _do_restore_copy(tmp, dest, log)
        except Exception as e:
            log(f"[FAIL] rclone restore: {e}")
            return False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif folder_id:
        # Google Drive restore — download to temp then copy
        import tempfile
        from sff.google_drive import get_service, download_folder
        service = get_service()
        if not service:
            log("[FAIL] Google Drive not connected.")
            return False
        tmp = Path(tempfile.mkdtemp(prefix="steamidra_restore_"))
        try:
            log("Downloading from Google Drive...")
            if not download_folder(service, folder_id, tmp, log_func=log):
                log("[FAIL] Download failed.")
                return False
            src = tmp
            return _do_restore_copy(src, dest, log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif folder_path:
        src = Path(folder_path)
        if not src.exists():
            log(f"[FAIL] Backup folder not found: {src}")
            return False
        return _do_restore_copy(src, dest, log)
    else:
        log("[FAIL] No folder_path or folder_id in entry.")
        return False


def _do_restore_copy(src, dest, log):
    if dest.exists():
        import time
        safety_ts = time.strftime("%Y%m%d_%H%M%S")
        safety = _BACKUP_ROOT / "pre_restore_all" / f"{dest.name}_{safety_ts}"
        try:
            shutil.copytree(dest, safety, dirs_exist_ok=True)
            log(f"Safety backup → {safety}")
        except Exception as e:
            log(f"Warning: safety backup failed ({e}), proceeding anyway")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        restored = 0
        for f in src.rglob("*"):
            if f.is_file() and f.name != "steamidra_meta.json":
                rel = f.relative_to(src)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                restored += 1
        log(f"Restored {restored} file(s) to {dest}")
        return True
    except Exception as e:
        log(f"[FAIL] Restore copy failed: {e}")
        return False
