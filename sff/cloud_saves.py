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
from typing import Optional

logger = logging.getLogger(__name__)

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
    file_count: int = 0
    total_size: int = 0
    last_modified: float = 0.0


@dataclass
class BackupInfo:
    """information about a save backup"""
    app_id: int
    game_name: str
    backup_path: str
    timestamp: float = 0.0
    file_count: int = 0
    total_size: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BackupInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _get_backup_dir() -> Path:
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

    def detect_saves(self, app_id: int, game_name: str = "") -> list[SaveInfo]:
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

    def _scan_save_dir(self, path: Path, app_id: int, game_name: str) -> Optional[SaveInfo]:
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

    def backup(self, app_id: int, save_path: str, game_name: str = "", log_func=None) -> Optional[BackupInfo]:
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

    def restore(self, app_id: int, backup_path: str, save_path: str, log_func=None) -> bool:
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
                log(f"Created safety backup before restore")

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

    def get_backups(self, app_id: int) -> list[BackupInfo]:
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

    def delete_backup(self, backup_path: str) -> bool:
        """delete a specific backup"""
        try:
            shutil.rmtree(backup_path)
            logger.info("Deleted backup: %s", backup_path)
            return True
        except Exception as e:
            logger.error("Failed to delete backup: %s", e)
            return False

    def _save_manifest(self, app_id: int, game_name: str, save_path: str, latest: BackupInfo):
        """save per-game manifest with metadata"""
        manifest_path = self.backup_dir / str(app_id) / "manifest.json"
        data = {
            "app_id": app_id,
            "game_name": game_name,
            "save_path": save_path,
            "latest_backup": latest.to_dict(),
        }
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_manifest(self, app_id: int) -> dict:
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
    def list_steam_games(steam_path: str, steam32_id: str) -> list[tuple[int, str]]:
        """
        Enumerate games in Steam userdata for the given Steam32 ID.

        Returns a list of (app_id, game_name) sorted by game name.
        Game names are resolved from steamapps/appmanifest_<appid>.acf when available,
        falling back to the numeric app ID string.
        """
        results: list[tuple[int, str]] = []
        userdata_dir = Path(steam_path) / "userdata" / str(steam32_id)
        if not userdata_dir.exists():
            return results

        # build a name lookup from appmanifest ACF files
        name_map: dict[int, str] = {}
        steamapps_dirs = [
            Path(steam_path) / "steamapps",
        ]
        # also check library folders
        lf_path = Path(steam_path) / "steamapps" / "libraryfolders.vdf"
        if lf_path.exists():
            try:
                text = lf_path.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    line = line.strip().strip('"')
                    if line and (Path(line) / "steamapps").exists():
                        steamapps_dirs.append(Path(line) / "steamapps")
            except Exception:
                pass

        for sd in steamapps_dirs:
            if not sd.exists():
                continue
            for acf in sd.glob("appmanifest_*.acf"):
                try:
                    appid_str = acf.stem.split("_", 1)[1]
                    if not appid_str.isdigit():
                        continue
                    appid = int(appid_str)
                    text = acf.read_text(encoding="utf-8", errors="ignore")
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith('"name"'):
                            name = line.split('"name"', 1)[1].strip().strip('"')
                            name_map[appid] = name
                            break
                except Exception:
                    pass

        try:
            for item in userdata_dir.iterdir():
                if not item.is_dir() or not item.name.isdigit():
                    continue
                app_id = int(item.name)
                if app_id == 0:
                    continue
                remote_dir = item / "remote"
                if not remote_dir.exists():
                    continue
                game_name = name_map.get(app_id, f"App {app_id}")
                results.append((app_id, game_name))
        except PermissionError:
            pass

        results.sort(key=lambda x: x[1].lower())
        return results

    def backup_steam_save(
        self,
        steam_path: str,
        steam32_id: str,
        app_id: int,
        game_name: str,
        dest_folder: str,
        log_func=None,
    ) -> Optional[str]:
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
    ) -> bool:
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
    def _format_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
