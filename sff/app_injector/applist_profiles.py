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

"""AppList profiles for GreenLuma - manage multiple ID sets to work around the 130/168 limit."""

import json
import logging
import re
from pathlib import Path

from sff.storage.settings import get_setting, set_setting
from sff.structs import Settings
from sff.utils import root_folder

logger = logging.getLogger(__name__)

PROFILES_DIR = root_folder(outside_internal=True) / "applist_profiles"
DEFAULT_LIMIT = None  # No hard limit by default


def _sanitize_filename(name):
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = re.sub(r"\s+", "_", sanitized.strip())
    return sanitized or "profile"


def _profile_path(name):
    return PROFILES_DIR / f"{_sanitize_filename(name)}.json"


def get_profile_limit():
    return _resolve_limit()


def _resolve_limit():
    limit_str = get_setting(Settings.APPLIST_ID_LIMIT)
    if limit_str:
        try:
            n = int(limit_str)
            if n > 0:
                return n
        except (ValueError, TypeError):
            pass
    return None


def ensure_profiles_dir():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR


def list_profiles():
    ensure_profiles_dir()
    names = []
    for path in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("name"), str):
                names.append(data["name"])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load profile %s: %s", path.name, e)
    return sorted(names, key=str.lower)


def load_profile(name):
    path = _profile_path(name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data.get("app_ids")
        if not isinstance(ids, list):
            return None
        return [int(x) for x in ids if isinstance(x, (int, str)) and str(x).isdigit()]
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("Failed to load profile %s: %s", name, e)
        return None


def save_profile(name, app_ids):
    ensure_profiles_dir()
    path = _profile_path(name)
    data = {"name": name, "app_ids": app_ids}
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        logger.error("Failed to save profile %s: %s", name, e)
        return False


def delete_profile(name):
    path = _profile_path(name)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError as e:
        logger.error("Failed to delete profile %s: %s", name, e)
        return False


def rename_profile(old_name, new_name):
    ids = load_profile(old_name)
    if ids is None:
        return False
    if not save_profile(new_name, ids):
        return False
    delete_profile(old_name)  # best-effort cleanup
    return True


def switch_profile(
    name: str,
    applist_folder: Path,
    limit = None,
):
    ids = load_profile(name)
    if ids is None:
        return False, 0

    if limit is None:
        limit = _resolve_limit()

    limited_ids = ids[:limit]
    applist_folder = Path(applist_folder)

    if not applist_folder.exists():
        applist_folder.mkdir(parents=True, exist_ok=True)

    for f in applist_folder.glob("*.txt"):
        if f.stem.isdigit():
            f.unlink(missing_ok=True)

    for i, app_id in enumerate(limited_ids):
        (applist_folder / f"{i}.txt").write_text(str(app_id), encoding="utf-8")

    return True, len(limited_ids)


def profile_exists(name):
    return _profile_path(name).exists()
