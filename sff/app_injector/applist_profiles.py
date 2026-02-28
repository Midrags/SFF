"""AppList profiles for GreenLuma - manage multiple ID sets to work around the 130/168 limit."""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from sff.storage.settings import get_setting, set_setting
from sff.structs import Settings
from sff.utils import root_folder

logger = logging.getLogger(__name__)

PROFILES_DIR = root_folder(outside_internal=True) / "applist_profiles"
DEFAULT_LIMIT = 134  # GreenLuma 1.7.0 hard limit


def _sanitize_filename(name: str) -> str:
    """Make profile name safe for use as filename. Replaces invalid chars with underscore."""
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = re.sub(r"\s+", "_", sanitized.strip())
    return sanitized or "profile"


def _profile_path(name: str) -> Path:
    """Get the file path for a profile by display name."""
    return PROFILES_DIR / f"{_sanitize_filename(name)}.json"


def get_profile_limit() -> int:
    """Get the AppList limit for profile switch (from settings or default 134)."""
    return _resolve_limit()


def _resolve_limit() -> int:
    """Get the AppList limit from settings, or default 134 for GreenLuma 1.7.0."""
    limit_str = get_setting(Settings.APPLIST_ID_LIMIT)
    if limit_str:
        try:
            n = int(limit_str)
            if n > 0:
                return n
        except (ValueError, TypeError):
            pass
    return DEFAULT_LIMIT


def ensure_profiles_dir() -> Path:
    """Create profiles directory if it does not exist. Returns the path."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR


def list_profiles() -> list[str]:
    """List all profile display names."""
    ensure_profiles_dir()
    names: list[str] = []
    for path in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("name"), str):
                names.append(data["name"])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load profile %s: %s", path.name, e)
    return sorted(names, key=str.lower)


def load_profile(name: str) -> Optional[list[int]]:
    """Load app_ids from a profile. Returns None if profile does not exist or is invalid."""
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


def save_profile(name: str, app_ids: list[int]) -> bool:
    """Save app_ids to a profile. Creates or overwrites. Returns True on success."""
    ensure_profiles_dir()
    path = _profile_path(name)
    data = {"name": name, "app_ids": app_ids}
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        logger.error("Failed to save profile %s: %s", name, e)
        return False


def delete_profile(name: str) -> bool:
    """Delete a profile. Returns True if deleted, False if not found or error."""
    path = _profile_path(name)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError as e:
        logger.error("Failed to delete profile %s: %s", name, e)
        return False


def rename_profile(old_name: str, new_name: str) -> bool:
    """Rename a profile. Returns True on success."""
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
    limit: Optional[int] = None,
) -> tuple[bool, int]:
    """
    Activate a profile by writing its IDs to the AppList folder.
    Truncates to limit (default from settings or 134).
    Returns (success, count_written).
    """
    ids = load_profile(name)
    if ids is None:
        return False, 0

    if limit is None:
        limit = _resolve_limit()

    limited_ids = ids[:limit]
    applist_folder = Path(applist_folder)

    if not applist_folder.exists():
        applist_folder.mkdir(parents=True, exist_ok=True)

    # Remove existing .txt files
    for f in applist_folder.glob("*.txt"):
        if f.stem.isdigit():
            f.unlink(missing_ok=True)

    # Write new files
    for i, app_id in enumerate(limited_ids):
        (applist_folder / f"{i}.txt").write_text(str(app_id), encoding="utf-8")

    return True, len(limited_ids)


def profile_exists(name: str) -> bool:
    """Check if a profile exists."""
    return _profile_path(name).exists()
