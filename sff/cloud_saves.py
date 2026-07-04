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
Cloud saves. Local backup + restore for game save files.

Scans the usual save spots (Documents, AppData, Steam userdata, etc),
copies them to %APPDATA%/SteaMidra/save_backups/, and tags each backup
with a timestamp so users can roll back to a specific point.
"""

import datetime
import hashlib
import os
import sys
import shutil
import logging
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict

_CREATE_NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

from sff.utils import root_folder, sff_data_dir

logger = logging.getLogger(__name__)


def _normalize_path(path_val) -> Path | None:
    if not path_val:
        return None
    try:
        return Path(os.path.expandvars(str(path_val))).expanduser()
    except Exception:
        return None


def _find_game_install_dir(steam_path, app_id):
    try:
        from sff.storage.vdf import get_steam_libs, vdf_load
        libs = get_steam_libs(Path(steam_path))
        for lib in libs:
            acf = lib / "steamapps" / f"appmanifest_{app_id}.acf"
            if acf.is_file():
                data = vdf_load(acf)
                installdir = data.get("AppState", {}).get("installdir", "")
                if installdir:
                    return str(lib / "steamapps" / "common" / installdir)
    except Exception:
        pass
    return None


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
    """one detected save folder for a game"""
    app_id: int
    game_name: str
    save_path: str
    file_count = 0
    total_size = 0
    last_modified = 0.0


@dataclass
class BackupInfo:
    """one snapshot we took, used by the restore UI"""
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
    """root folder where every appid's snapshots live.

    Honours the user-selected `cloud_local_backup_dest` setting from the
    Cloud Saves UI when it points at an existing or creatable folder.
    Falls back to <SteaMidra install>/save_backups/ otherwise. The user
    sets this through the Local-provider folder picker on the Cloud Saves
    tab, and the setting persists across sessions.
    """
    custom = ""
    try:
        from sff.storage.settings import get_setting, Settings
        custom = (get_setting(Settings.CLOUD_LOCAL_BACKUP_DEST) or "").strip()
    except Exception:
        # Settings not loadable yet (early bootstrap) — fall through to default.
        custom = ""
    if custom:
        try:
            p = Path(custom)
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            # Custom path is unwritable (no permission, drive missing).
            # Drop back to the app data dir so the legacy code paths keep working
            # instead of crashing on every backup attempt.
            pass
    backup_dir = sff_data_dir() / "save_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


class CloudSaves:
    """
    Local save backup + restore.

    Snapshots land under %APPDATA%/SteaMidra/save_backups/{appid}/,
    each timestamped so the user can pick which one to restore.

    save_backups/
      {appid}/
        manifest.json
        backup_20260413_120000/
        backup_20260413_130000/
    """

    def __init__(self):
        self.backup_dir = _get_backup_dir()

    def detect_saves(self, app_id, game_name = ""):
        """
        Try to find where a game's saves live.
        Looks through the usual spots for folders that match the appid
        or the game name.
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
        """walk a folder, count files + size, return None if it's empty"""
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
            # Also back up any custom save paths from the manifest (Lies of P, etc.)
            _backed_custom = 0
            try:
                from sff.cloud_save_paths import get_save_paths
                base = _find_game_install_dir(steam_path, app_id)
                if base:
                    for save_path in get_save_paths(app_id, base):
                        sp = Path(save_path)
                        if not sp.exists():
                            continue
                        custom_dest = dest.parent / "custom_saves" / sp.name
                        if sp.is_dir():
                            for cf in sp.rglob("*"):
                                if cf.is_file():
                                    rel = cf.relative_to(sp)
                                    tgt = custom_dest / rel
                                    tgt.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(cf, tgt)
                                    _backed_custom += 1
                        elif sp.is_file():
                            custom_dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(sp, custom_dest)
                            _backed_custom += 1
                if _backed_custom:
                    log(f"✓ Backed up {_backed_custom} custom save file(s)")
            except Exception:
                logger.debug("Custom save path backup skipped", exc_info=True)
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

_BACKUP_ROOT = sff_data_dir() / "save_backups"

_INTERNAL_FOLDERS = frozenset({"_restore_safety", "_steamidra_meta"})


def _is_internal_folder(name: str) -> bool:
    return name in _INTERNAL_FOLDERS


def _source_kind(location: str) -> str:
    loc_lower = location.lower()
    if "steam userdata" in loc_lower:
        return "steam_userdata"
    if "ludusavi" in loc_lower:
        return "ludusavi"
    if "custom" in loc_lower:
        return "custom"
    return "emulator"


def _safe_source_key(source_path, location, index, used):
    src = str(source_path or "")
    loc = str(location or Path(src).name or "Save")
    safe = "".join(c if c not in r'\/:*?"<>|' else "_" for c in loc).strip(" ._")
    if not safe:
        safe = "Save"
    digest = hashlib.md5(os.path.normcase(os.path.normpath(src)).encode("utf-8")).hexdigest()[:8]
    base = f"{index + 1:02d}_{safe}_{digest}"[:100]
    candidate = base
    bump = 2
    while candidate.lower() in used:
        suffix = f"_{bump}"
        candidate = base[:100 - len(suffix)] + suffix
        bump += 1
    used.add(candidate.lower())
    return candidate


def _group_save_entries(results: list) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for entry in results:
        aid = entry.get("app_id")
        source_path = str(entry.get("source_path") or "")
        if not source_path:
            continue
        key = f"appid:{aid}" if aid is not None else f"path:{os.path.normcase(os.path.normpath(source_path))}"
        groups.setdefault(key, []).append(entry)

    output = []
    for entries in groups.values():
        first = entries[0]
        sources = []
        seen_paths = set()
        used_storage = set()
        for entry in entries:
            source_path = str(entry.get("source_path") or "")
            norm = os.path.normcase(os.path.normpath(source_path))
            if not source_path or norm in seen_paths:
                continue
            seen_paths.add(norm)
            location = entry.get("location", "Save")
            sources.append({
                "source_path": source_path,
                "kind": _source_kind(str(location)),
                "location": location,
                "folder_name": entry.get("folder_name", ""),
                "file_count": int(entry.get("file_count") or 0),
                "storage_path": _safe_source_key(source_path, location, len(sources), used_storage),
            })
        if not sources:
            continue
        merged = dict(first)
        merged.update({
            "location": "Games",
            "source_path": sources[0]["source_path"],
            "file_count": sum(source.get("file_count", 0) for source in sources),
            "sources": sources,
        })
        output.append(merged)
    return output


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
        sanitized_game_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in game_name)
        label = f"{app_id} - {sanitized_game_name}"
        return app_id, game_name, label
    else:
        sanitized_folder_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in folder_name)
        return None, folder_name, sanitized_folder_name


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

    # Ludusavi manifest — custom save paths for installed Steam games
    if steam_path:
        try:
            from sff.cloud_save_paths import get_save_paths, get_install_dir_candidates
            from sff.storage.vdf import get_steam_libs as _steam_libs, vdf_load as _vdf_load
            steam_root = Path(steam_path)
            libs = _steam_libs(steam_root)
            if steam_root not in libs:
                libs = [steam_root] + list(libs)
            seen_ludusavi_labels = set()
            for lib in libs:
                for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
                    try:
                        appid_str = acf.stem.split("_", 1)[1]
                        if not appid_str.isdigit():
                            continue
                        appid = int(appid_str)
                        if appid == 0:
                            continue
                        data = _vdf_load(acf)
                        game_name = data.get("AppState", {}).get("name", "")
                        installdir = data.get("AppState", {}).get("installdir", "")
                        if not game_name or not installdir:
                            continue
                        base_dir = str(lib / "steamapps" / "common" / installdir)
                        save_paths = get_save_paths(appid, base_dir)
                        if not save_paths:
                            continue
                        safe_game = "".join(c if c not in r'\/:*?"<>|' else "_" for c in game_name)
                        label = f"{appid} - {safe_game}"
                        if label in seen_ludusavi_labels:
                            continue
                        seen_ludusavi_labels.add(label)
                        for sp in save_paths:
                            sp_path = Path(sp)
                            if not sp_path.exists():
                                continue
                            files = [f for f in sp_path.rglob("*") if f.is_file()]
                            if not files:
                                continue
                            results.append({
                                "location": "Ludusavi Manifest",
                                "folder_name": sp_path.name,
                                "app_id": appid,
                                "game_name": game_name,
                                "label": label,
                                "source_path": str(sp_path),
                                "file_count": len(files),
                            })
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Ludusavi manifest scan skipped: %s", e)

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

    # 6.2.4: user-defined custom save paths. Some games store saves
    # outside the Steam userdata tree and the standard emu folders, like
    # Documents\My Games\<title>\ or %APPDATA%\<publisher>\<game>\. The
    # Cloud Saves UI lets users add a path per app id; the scan picks
    # those up here so backup / restore works without modifying the
    # source-of-truth lists. Stored as JSON {"<app_id>": "<path>"}.
    try:
        from sff.storage.settings import get_setting as _get_setting
        from sff.structs import Settings as _Settings
        import json as _json
        raw = _get_setting(_Settings.CLOUD_CUSTOM_SAVE_PATHS) or ""
        custom_map = {}
        if raw:
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    custom_map = parsed
            except Exception:
                custom_map = {}
        for app_id_str, raw_path in custom_map.items():
            if not raw_path:
                continue
            src = _normalize_path(raw_path)
            if not src or not src.exists() or not src.is_dir():
                continue
            files = [f for f in src.rglob("*") if f.is_file()]
            if not files:
                continue
            try:
                app_id_int = int(app_id_str)
            except Exception:
                app_id_int = None
            game_name = src.name
            try:
                from sff.storage.vdf import get_steam_libs as _libs, vdf_load as _vdf
                if app_id_int and steam_path:
                    steam_root = Path(steam_path)
                    libs = _libs(steam_root)
                    if steam_root not in libs:
                        libs = [steam_root] + list(libs)
                    for lib in libs:
                        acf = lib / "steamapps" / f"appmanifest_{app_id_int}.acf"
                        if acf.exists():
                            data = _vdf(acf)
                            n = data.get("AppState", {}).get("name", "")
                            if n:
                                game_name = n
                                break
            except Exception:
                pass
            safe_game_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in game_name)
            label = f"{app_id_int} - {safe_game_name}" if app_id_int else safe_game_name
            results.append({
                "location": "Custom Path",
                "folder_name": src.name,
                "app_id": app_id_int,
                "game_name": game_name,
                "label": label,
                "source_path": str(src),
                "file_count": len(files),
            })
    except Exception as e:
        logger.warning("scan custom save paths: %s", e)

    return _group_save_entries(results)


def _entry_sources(entry):
    raw_sources = entry.get("sources")
    if isinstance(raw_sources, list) and raw_sources:
        used = set()
        out = []
        for idx, source in enumerate(raw_sources):
            if not isinstance(source, dict):
                continue
            source_path = str(source.get("source_path") or "")
            if not source_path:
                continue
            location = source.get("location") or entry.get("location", "Save")
            storage_path = str(source.get("storage_path") or "")
            if not storage_path:
                storage_path = _safe_source_key(source_path, location, idx, used)
            else:
                used.add(storage_path.lower())
            out.append({
                "source_path": source_path,
                "kind": source.get("kind") or _source_kind(str(location)),
                "location": location,
                "folder_name": source.get("folder_name", ""),
                "file_count": int(source.get("file_count") or 0),
                "storage_path": storage_path,
            })
        if out:
            return out

    source_path = str(entry.get("source_path") or "")
    location = entry.get("location", "Save")
    used = set()
    return [{
        "source_path": source_path,
        "kind": _source_kind(str(location)),
        "location": location,
        "folder_name": entry.get("folder_name", ""),
        "file_count": int(entry.get("file_count") or 0),
        "storage_path": _safe_source_key(source_path, location, 0, used) if source_path else "",
    }]


def _entry_meta(entry, sources):
    first_source = sources[0] if sources else {}
    return {
        "schema_version": 2,
        "app_id": entry.get("app_id"),
        "game_name": entry.get("game_name", ""),
        "source_path": first_source.get("source_path", ""),
        "location": entry.get("location", "Games"),
        "backed_up_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sources": sources,
    }


def _copy_source_to_dest(src, dest, log):
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
    return copied, skipped


def backup_save_location_local(entry, dest_root, log_func=None):
    """
    Backup save paths to dest_root/SteaMidraAllSaves/{label}/.
    Each source lands in its own storage folder under the game folder.
    Returns dest folder path on success, None on failure.
    """
    log = log_func or (lambda m: None)
    label = entry["label"]
    dest_root_norm = _normalize_path(dest_root)
    if not dest_root_norm:
        log(f"[!] Invalid destination root: {dest_root}")
        return None
    dest = dest_root_norm / "SteaMidraAllSaves" / label
    sources = entry.get("sources")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        total_copied = 0
        total_skipped = 0
        meta_sources = []

        for source in _entry_sources(entry):
            src = _normalize_path(source.get("source_path"))
            if not src or not src.exists():
                log(f"  [!] Source not found: {source.get('source_path')}")
                continue
            payload = dest / source.get("storage_path", "")
            c, s = _copy_source_to_dest(src, payload, log)
            total_copied += c
            total_skipped += s
            saved_source = dict(source)
            saved_source["source_path"] = str(src)
            meta_sources.append(saved_source)

        if not meta_sources:
            log(f"  [FAIL] No valid sources to back up: {label}")
            return None

        meta_path = dest / "steamidra_meta.json"
        meta_path.write_text(
            json.dumps(_entry_meta(entry, meta_sources), indent=2),
            encoding="utf-8"
        )
        if total_skipped:
            log(f"  Backed up {total_copied} file(s), skipped {total_skipped} unchanged: {label}")
        else:
            log(f"  Backed up {total_copied} file(s): {label}")
        return str(dest)
    except Exception as e:
        log(f"  [FAIL] {label}: {e}")
        return None


def backup_save_location_rclone(entry, rclone_exe, remote_dest, log_func=None):
    """Upload save entry via rclone to remote_dest:SteaMidraAllSaves/{label}/."""
    import subprocess
    import tempfile
    log = log_func or (lambda m: None)
    label = entry["label"]
    remote_path = remote_dest.rstrip("/") + f"/SteaMidraAllSaves/{label}"

    meta_sources = []
    for source in _entry_sources(entry):
        src = _normalize_path(source.get("source_path"))
        if not src or not src.exists():
            log(f"  [!] Source not found: {source.get('source_path')}")
            continue
        sub_path = remote_path + "/" + source.get("storage_path", "")
        proc = subprocess.run(
            [rclone_exe, "copy", str(src), sub_path, "--update",
             "--transfers", "9", "--checkers", "18", "--create-empty-src-dirs", "--fast-list"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=300, **_CREATE_NO_WINDOW,
        )
        if proc.returncode != 0:
            log(f"  [FAIL] rclone for {src.name}: {proc.stderr[:200]}")
            continue
        saved_source = dict(source)
        saved_source["source_path"] = str(src)
        meta_sources.append(saved_source)

    if not meta_sources:
        log(f"  [FAIL] No valid sources to upload: {label}")
        return False

    meta_tmp = Path(tempfile.mkdtemp(prefix="steamidra_meta_"))
    try:
        meta_file = meta_tmp / "steamidra_meta.json"
        meta_file.write_text(
            json.dumps(_entry_meta(entry, meta_sources), indent=2),
            encoding="utf-8",
        )
        subprocess.run(
            [rclone_exe, "copyto", str(meta_file), remote_path + "/steamidra_meta.json",
             "--no-update-modtime"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30, **_CREATE_NO_WINDOW,
        )
    finally:
        shutil.rmtree(meta_tmp, ignore_errors=True)

    log(f"  Uploaded: {label} → {remote_path}")
    return True


def backup_save_location_gdrive(entry, service, backup_root_id, log_func=None, folder_cache=None):
    """Upload save entry via Google Drive API. Uses flat structure: SteaMidra Backups/{label}/."""
    import tempfile
    from sff.google_drive import get_or_create_folder, upload_file_replace, upload_folder, write_backup_meta
    log = log_func or (lambda m: None)
    if service is None:
        log("[!] Google Drive service not available. Reconnect in Settings.")
        return False
    label = entry["label"]
    local_fc = dict(folder_cache) if folder_cache is not None else {}

    meta_sources = []
    try:
        game_folder_id = get_or_create_folder(service, label, backup_root_id)
        if not game_folder_id:
            log(f"  [FAIL] Could not create Drive folder for {label}")
            return False

        for source in _entry_sources(entry):
            src = _normalize_path(source.get("source_path"))
            if not src or not src.exists():
                log(f"  [!] Source not found: {source.get('source_path')}")
                continue
            upload_folder(service, src, game_folder_id, log_func=log,
                          folder_cache=local_fc, drive_folder_name=source.get("storage_path", ""))
            saved_source = dict(source)
            saved_source["source_path"] = str(src)
            meta_sources.append(saved_source)

        if not meta_sources:
            log(f"  [FAIL] No valid sources to upload: {label}")
            return False

        meta = _entry_meta(entry, meta_sources)
        tmp = Path(tempfile.mkdtemp(prefix="steamidra_meta_"))
        try:
            meta_file = tmp / "steamidra_meta.json"
            meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            upload_file_replace(service, meta_file, game_folder_id, log_func=log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        write_backup_meta(
            service,
            backup_root_id,
            "Games",
            label,
            meta,
            log_func=log,
        )
        if folder_cache is not None:
            folder_cache.update(local_fc)
        log(f"  Synced to Drive: {label}")
        return True
    except Exception as e:
        log(f"  [FAIL] {label}: {e}")
        return False


def _parse_game_dir(game_dir, remote_root, prefix_in_remote=""):
    """Parse a single game directory's meta.json and build an entry dict."""
    meta_file = game_dir / "steamidra_meta.json"
    if not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    suffix = prefix_in_remote + game_dir.name if prefix_in_remote else game_dir.name
    game_remote = remote_root + "/" + suffix
    sv = meta.get("schema_version", 1)
    if sv == 2:
        sources = meta.get("sources", [])
        source_path = sources[0]["source_path"] if sources else meta.get("source_path", "")
    else:
        source_path = meta.get("source_path", "")
    return {
        "folder_path": game_remote,
        "folder_name": game_dir.name,
        "app_id": meta.get("app_id"),
        "game_name": meta.get("game_name", game_dir.name),
        "source_path": source_path,
        "sources": meta.get("sources", []),
        "schema_version": sv,
        "backed_up_at": meta.get("backed_up_at", ""),
        "rclone_path": game_remote,
    }


def scan_backup_root_rclone(rclone_exe, remote_dest):
    """Scan an rclone remote for SteaMidraAllSaves structure.
    Downloads all steamidra_meta.json files at once, then parses them locally.
    Scans both new flat layout and legacy Games/ layout.
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
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120, **_CREATE_NO_WINDOW,
        )
        result = {}
        if not tmp.exists():
            return result

        all_games = []

        # New flat layout: SteaMidraAllSaves/<label>/
        for game_dir in sorted(tmp.iterdir()):
            if not game_dir.is_dir() or _is_internal_folder(game_dir.name) or game_dir.name == "Games":
                continue
            parsed = _parse_game_dir(game_dir, remote_root)
            if parsed:
                all_games.append(parsed)

        # Legacy layout: SteaMidraAllSaves/Games/<label>/
        legacy_dir = tmp / "Games"
        if legacy_dir.is_dir():
            for game_dir in sorted(legacy_dir.iterdir()):
                if not game_dir.is_dir() or _is_internal_folder(game_dir.name):
                    continue
                parsed = _parse_game_dir(game_dir, remote_root, prefix_in_remote="Games/")
                if parsed:
                    all_games.append(parsed)

        if all_games:
            result["All Backups"] = {
                "folder_path": remote_root,
                "games": all_games,
            }
        return result
    except Exception:
        return {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_game_dir_local(game_dir):
    """Parse a local game directory's meta.json."""
    meta_file = game_dir / "steamidra_meta.json"
    if not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    sv = meta.get("schema_version", 1)
    if sv == 2:
        sources = meta.get("sources", [])
        source_path = sources[0]["source_path"] if sources else meta.get("source_path", "")
    else:
        source_path = meta.get("source_path", "")
    return {
        "folder_path": str(game_dir),
        "folder_name": game_dir.name,
        "app_id": meta.get("app_id"),
        "game_name": meta.get("game_name", game_dir.name),
        "source_path": source_path,
        "sources": meta.get("sources", []),
        "schema_version": sv,
        "backed_up_at": meta.get("backed_up_at", ""),
    }


def scan_backup_root_local(backup_root):
    """
    Scan a local SteaMidraAllSaves root folder.
    Scans both new flat layout and legacy Games/ layout.
    Returns same structure as google_drive.list_backup_locations.
    """
    root = Path(backup_root) / "SteaMidraAllSaves"
    if not root.exists():
        return {}
    result = {}
    all_games = []

    # New flat layout: SteaMidraAllSaves/<label>/
    for item in sorted(root.iterdir()):
        if not item.is_dir() or _is_internal_folder(item.name) or item.name == "Games":
            continue
        parsed = _parse_game_dir_local(item)
        if parsed:
            all_games.append(parsed)

    # Legacy layout: SteaMidraAllSaves/Games/<label>/
    legacy_dir = root / "Games"
    if legacy_dir.is_dir():
        for item in sorted(legacy_dir.iterdir()):
            if not item.is_dir() or _is_internal_folder(item.name):
                continue
            parsed = _parse_game_dir_local(item)
            if parsed:
                all_games.append(parsed)

    if all_games:
        result["All Backups"] = {"folder_path": str(root), "games": all_games}
    return result


def _restore_game_label(game_entry):
    raw = str(
        game_entry.get("folder_name")
        or game_entry.get("label")
        or game_entry.get("game_name")
        or game_entry.get("app_id")
        or "unknown"
    )
    safe = "".join(c if c not in r'\/:*?"<>|' else "_" for c in raw).strip(" ._")
    return safe or "unknown"


def _safety_root_for_entry(game_entry):
    folder_path = game_entry.get("folder_path")
    if folder_path:
        try:
            p = Path(folder_path).resolve()
            for candidate in (p, *p.parents):
                if candidate.name == "SteaMidraAllSaves":
                    return candidate / "_restore_safety"
        except Exception:
            pass
    return _BACKUP_ROOT / "SteaMidraAllSaves" / "_restore_safety"


def _target_can_be_created(dest):
    if dest.exists():
        return dest.is_dir()
    parent = dest.parent
    while parent and not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent.exists() and os.access(parent, os.W_OK)


def _restore_result(source, ok, message):
    return {
        "source_path": str(source.get("source_path", "")),
        "kind": source.get("kind", "unknown"),
        "location": source.get("location", ""),
        "ok": bool(ok),
        "message": message,
    }


def _payload_for_source(backup_path, source):
    storage_path = str(source.get("storage_path") or "").strip()
    if storage_path:
        return backup_path / storage_path
    source_path = str(source.get("source_path") or "")
    return backup_path / Path(source_path).name


def _ensure_safety_backup(dest_path, safety_base, game_label, timestamp, log):
    if not dest_path.exists():
        return True
    try:
        src_hash = hashlib.md5(str(dest_path).encode("utf-8")).hexdigest()[:8]
        safety = safety_base / timestamp / game_label / src_hash
        safety.mkdir(parents=True, exist_ok=True)
        shutil.copytree(dest_path, safety, dirs_exist_ok=True)
        log(f"Safety backup -> {safety}")
        return True
    except Exception as e:
        log(f"[FAIL] Safety backup failed for {dest_path}: {e}")
        return False


def _copy_restore_payload(src, dest):
    dest.mkdir(parents=True, exist_ok=True)
    restored = 0
    for f in src.rglob("*"):
        if f.is_file() and f.name != "steamidra_meta.json":
            rel = f.relative_to(src)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            restored += 1
    return restored


def _restore_multi_source_entry(backup_dir, sources, log, safety_base, game_label):
    backup_path = Path(backup_dir)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    checks = []
    results = [None] * len(sources)

    for idx, src_info in enumerate(sources):
        if not isinstance(src_info, dict):
            src_info = {"source_path": ""}
        source_path_raw = str(src_info.get("source_path") or "")
        dest = _normalize_path(source_path_raw)
        payload = _payload_for_source(backup_path, src_info)
        if not dest:
            results[idx] = _restore_result(src_info, False, "Invalid source_path.")
            continue
        if not payload.exists():
            results[idx] = _restore_result(src_info, False, f"Backup payload not found: {payload.name}")
            continue
        if not _target_can_be_created(dest):
            results[idx] = _restore_result(src_info, False, "Target path is not writable or creatable.")
            continue
        checks.append((idx, src_info, payload, dest))

    for idx, src_info, payload, dest in checks:
        try:
            if not _ensure_safety_backup(dest, safety_base, game_label, timestamp, log):
                results[idx] = _restore_result(src_info, False, "Safety backup failed.")
                continue
            restored = _copy_restore_payload(payload, dest)
            log(f"Restored {restored} file(s) to {dest}")
            results[idx] = _restore_result(src_info, True, f"Restored {restored} file(s).")
        except Exception as e:
            results[idx] = _restore_result(src_info, False, str(e))

    return [r for r in results if r is not None]


def _restore_summary(results):
    total = len(results)
    ok_count = sum(1 for r in results if r.get("ok"))
    if total <= 0:
        return False, "No save locations were restored."
    msg = f"Restored {ok_count} of {total} save location(s)."
    if ok_count != total:
        failed = [r for r in results if not r.get("ok")]
        details = "; ".join(f"{r.get('source_path', '')}: {r.get('message', '')}" for r in failed)
        if details:
            msg += f" Failures: {details}"
    return ok_count == total, msg


def _schema_version(game_entry):
    raw = game_entry.get("schema_version", 1)
    try:
        return int(raw)
    except Exception:
        return raw


def _download_restore_source(game_entry, log):
    rclone_path = game_entry.get("rclone_path")
    rclone_exe = game_entry.get("rclone_exe", "").strip()
    folder_id = game_entry.get("folder_id")
    folder_path = game_entry.get("folder_path")

    if rclone_path and rclone_exe:
        import subprocess
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="steamidra_restore_"))
        log("Downloading from rclone remote...")
        proc = subprocess.run(
            [rclone_exe, "copy", rclone_path, str(tmp),
             "--exclude", "steamidra_meta.json", "--transfers", "10", "--fast-list"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=300, **_CREATE_NO_WINDOW,
        )
        if proc.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(f"rclone download failed: {proc.stderr[:200]}")
        return tmp, True

    if folder_id:
        import tempfile
        from sff.google_drive import get_service, download_folder
        service = get_service()
        if not service:
            raise RuntimeError("Google Drive not connected.")
        tmp = Path(tempfile.mkdtemp(prefix="steamidra_restore_"))
        log("Downloading from Google Drive...")
        if not download_folder(service, folder_id, tmp, log_func=log):
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError("Download failed.")
        return tmp, True

    if folder_path:
        src = Path(folder_path)
        if not src.exists():
            raise RuntimeError(f"Backup folder not found: {src}")
        return src, False

    raise RuntimeError("No folder_path, rclone_path, or folder_id in entry.")


def restore_save_entry(game_entry, log_func=None):
    """
    Restore files from a backup game entry to their recorded source paths.
    Returns a dict with ok, message, and per-source results.
    """
    log = log_func or (lambda m: None)
    sv = _schema_version(game_entry)
    if sv not in (1, 2):
        msg = f"[FAIL] Unsupported backup schema_version={sv}. Cannot restore."
        log(msg)
        return {"ok": False, "message": msg, "results": []}

    safety_base = _safety_root_for_entry(game_entry)
    game_label = _restore_game_label(game_entry)
    tmp = None
    try:
        src_root, is_tmp = _download_restore_source(game_entry, log)
        tmp = src_root if is_tmp else None

        if sv == 2:
            sources = game_entry.get("sources")
            if not isinstance(sources, list) or not sources:
                msg = "[FAIL] schema_version 2 backup has no sources."
                log(msg)
                return {"ok": False, "message": msg, "results": []}
            results = _restore_multi_source_entry(src_root, sources, log, safety_base, game_label)
        else:
            raw_dest = game_entry.get("source_path")
            dest = _normalize_path(raw_dest) if raw_dest else None
            if not dest:
                msg = "[FAIL] No valid source_path in entry, cannot restore."
                log(msg)
                return {"ok": False, "message": "No valid source_path.", "results": []}
            source = {
                "source_path": str(raw_dest),
                "kind": "legacy",
                "location": game_entry.get("location", ""),
            }
            results = [_do_restore_copy(src_root, dest, log, safety_base, game_label, source)]

        ok, msg = _restore_summary(results)
        log(msg)
        return {"ok": ok, "message": msg, "results": results}
    except Exception as e:
        msg = f"[FAIL] Restore failed: {e}"
        log(msg)
        return {"ok": False, "message": str(e), "results": []}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _do_restore_copy(src, dest, log, safety_base, game_label, source):
    if not _target_can_be_created(dest):
        return _restore_result(source, False, "Target path is not writable or creatable.")
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if not _ensure_safety_backup(dest, safety_base, game_label, timestamp, log):
            return _restore_result(source, False, "Safety backup failed.")
        restored = _copy_restore_payload(src, dest)
        log(f"Restored {restored} file(s) to {dest}")
        return _restore_result(source, True, f"Restored {restored} file(s).")
    except Exception as e:
        log(f"[FAIL] Restore copy failed: {e}")
        return _restore_result(source, False, str(e))
