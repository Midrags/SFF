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

"""Manifest preserver.

Steam wipes `<steam>/depotcache/<depot>_<gid>.manifest` when the user
uninstalls a game from the Steam UI. SteaMidra has its own canonical
copy of every manifest it ever downloaded, sitting in the writable
staging directory next to SteaMidra.exe (`<sff_data>/manifests/`),
because every download path writes to that folder before staging into
depotcache.

Strategy: do NOT make a separate backup. The staging dir IS the backup.
A lightweight watcher checks the two Steam-side caches and, when a
manifest disappears, copies it back from the staging dir if a copy
exists there. Cheap, no extra disk usage, no startup walk.

Public surface:
    start_watcher(steam_path) -> None
    restore_manifest(deleted_path) -> bool

Failures (missing pywin32, missing inotify_simple, missing depotcache,
broken disk) log and continue without raising.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from sff.storage.settings import get_setting
from sff.structs import Settings
from sff.utils import manifests_staging_dir

# Import platform-specific dependencies at module level (not inside threads)
# to avoid importlib race conditions with QtWebEngine initialization.
try:
    import win32con  # noqa: F401
except ImportError:
    win32con = None
try:
    import win32file  # noqa: F401
except ImportError:
    win32file = None
try:
    from inotify_simple import INotify, flags  # noqa: F401
except ImportError:
    INotify = flags = None

logger = logging.getLogger(__name__)


# Per-depotcache watcher threads keyed on the resolved path string.
# Held weakly via plain dict so the GIL keeps lookups consistent.
_WATCHER_THREADS: dict[str, threading.Thread] = {}
_WATCHER_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_preserve_enabled() -> bool:
    """Read MANIFEST_PRESERVE; default ON. Mirror of A9 / A13 patterns."""
    try:
        val = get_setting(Settings.MANIFEST_PRESERVE)
    except Exception:
        return True
    if val is False:
        return False
    if isinstance(val, str) and val.strip().lower() in ("false", "0", "no"):
        return False
    # None / unset / "" / True / "True" all default ON.
    return True


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


# backup_manifest is kept as a no-op shim so existing callers (steam_tools_compat
# in particular) keep working without an import error. The staging dir is the
# canonical store now, populated by the regular download path; we don't need a
# parallel backup tree.
def backup_manifest(
    library: Path,
    appid: int,
    manifest_gid: str,
    source_path: Path,
) -> Optional[Path]:
    return None


def restore_manifest(deleted_path: Path) -> bool:
    """Restore a missing manifest from the staging dir if a copy lives there.

    Returns True when the file was copied back. False on every other case
    (preservation off, staging dir missing, no matching file, copy fails,
    destination is still on disk).
    """
    if not _is_preserve_enabled():
        return False
    try:
        dest = Path(deleted_path)
        if dest.is_file():
            # Some watcher events fire on rename / temporary deletes that
            # complete before we reach this line. If the file is back, leave it.
            return False

        staging = manifests_staging_dir()
        if not staging.is_dir():
            logger.debug("restore_manifest: staging dir missing %s", staging)
            return False

        source = staging / dest.name
        if not source.is_file():
            logger.debug(
                "restore_manifest: no staged copy for %s (looked at %s)",
                dest, source,
            )
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        # Bump mtime to reflect the restore moment so subsequent watcher
        # events on the same path read a fresh timestamp.
        now = time.time()
        try:
            os.utime(dest, (now, now))
        except OSError:
            pass
        logger.info(
            "restore_manifest: restored %s from staging dir", dest,
        )
        return True
    except PermissionError as exc:
        # Steam holds depotcache exclusively while it's running, especially
        # when SteaMidra runs as admin and Steam doesn't. Every restore
        # attempt then raises "Access Denied" / "Accesso negato" / "Accès
        # refusé" depending on locale. Spamming WARN per tick floods the
        # live log panel (vin's case). The condition is normal, the user
        # can't fix it from inside SteaMidra, so log at debug and move on.
        logger.debug("restore_manifest: %s held by Steam (%s)", deleted_path, exc)
        return False
    except Exception as exc:
        logger.warning("restore_manifest failed for %s: %s", deleted_path, exc)
        return False


# --------------------------------------------------------------------------- #
# Watcher loops
# --------------------------------------------------------------------------- #


def _watch_loop_polling(depotcache: Path, stop_event: threading.Event,
                        interval: float = 5.0) -> None:
    """Fallback watcher: poll the folder every `interval` seconds.

    Tracks file existence; whenever a previously-seen file is gone the
    watcher calls restore_manifest. Used on Linux when inotify_simple is
    not installed, and as a safety net everywhere.
    """
    seen: set[str] = set()
    try:
        for entry in depotcache.iterdir():
            if entry.is_file():
                seen.add(entry.name)
    except OSError:
        pass

    while not stop_event.is_set():
        time.sleep(interval)
        try:
            current = {
                entry.name
                for entry in depotcache.iterdir()
                if entry.is_file()
            }
        except OSError:
            continue
        gone = seen - current
        for filename in gone:
            try:
                restore_manifest(depotcache / filename)
            except Exception as exc:
                logger.debug("watcher restore call failed: %s", exc)
        # Re-snapshot AFTER restore so a successful restore does not
        # immediately re-fire on the next pass.
        try:
            seen = {
                entry.name
                for entry in depotcache.iterdir()
                if entry.is_file()
            }
        except OSError:
            pass


def _watch_loop_windows(depotcache: Path, stop_event: threading.Event) -> None:
    """Windows watcher backed by ReadDirectoryChangesW (pywin32).

    Falls back to polling when the package is unavailable.
    """
    if win32con is None or win32file is None:
        logger.info(
            "pywin32 missing; falling back to polling watcher for %s",
            depotcache,
        )
        _watch_loop_polling(depotcache, stop_event)
        return

    try:
        handle = win32file.CreateFile(
            str(depotcache),
            0x0001,  # FILE_LIST_DIRECTORY
            win32con.FILE_SHARE_READ
            | win32con.FILE_SHARE_WRITE
            | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
    except Exception as exc:
        logger.warning(
            "ReadDirectoryChangesW handle failed for %s: %s; falling back to polling",
            depotcache,
            exc,
        )
        _watch_loop_polling(depotcache, stop_event)
        return

    while not stop_event.is_set():
        try:
            results = win32file.ReadDirectoryChangesW(
                handle,
                4096,
                False,  # not recursive
                win32con.FILE_NOTIFY_CHANGE_FILE_NAME
                | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE,
                None,
                None,
            )
        except Exception as exc:
            logger.debug("ReadDirectoryChangesW raised: %s", exc)
            time.sleep(1.0)
            continue
        for action, filename in results:
            # FILE_ACTION_REMOVED == 2, RENAMED_OLD_NAME == 4
            if action in (2, 4):
                try:
                    restore_manifest(depotcache / filename)
                except Exception as exc:
                    logger.debug("watcher restore call failed: %s", exc)


def _watch_loop_linux(depotcache: Path, stop_event: threading.Event) -> None:
    """Linux watcher backed by inotify_simple.

    Falls back to polling when the package is missing.
    """
    if INotify is None or flags is None:
        logger.info(
            "inotify_simple missing; falling back to polling watcher for %s",
            depotcache,
        )
        _watch_loop_polling(depotcache, stop_event)
        return

    try:
        inotify = INotify()
        watch_flags = flags.DELETE | flags.MOVED_FROM
        inotify.add_watch(str(depotcache), watch_flags)
    except Exception as exc:
        logger.warning(
            "inotify_simple add_watch failed for %s: %s; falling back to polling",
            depotcache,
            exc,
        )
        _watch_loop_polling(depotcache, stop_event)
        return

    while not stop_event.is_set():
        try:
            events = inotify.read(timeout=1000)
        except Exception as exc:
            logger.debug("inotify read raised: %s", exc)
            time.sleep(1.0)
            continue
        for event in events:
            try:
                restore_manifest(depotcache / event.name)
            except Exception as exc:
                logger.debug("watcher restore call failed: %s", exc)


def start_watcher(library: Path) -> None:
    """Launch watcher daemon threads for the Steam install root.

    Watches the two cache locations Steam clears on game uninstall:

      * `<steam>/depotcache`
      * `<steam>/config/depotcache`

    The argument name stays `library` for backward compatibility, but
    callers pass the Steam install root, not a per-library root.
    Per-library `steamapps/depotcache` is intentionally NOT watched:
    Steam's uninstall path does not target it the same way and watching
    it would just churn restores against Steam's own writes during a
    fresh install.

    No-ops when MANIFEST_PRESERVE is off, when both cache folders are
    missing, or when a watcher is already running for a path. Failures
    log and continue without raising.
    """
    if not _is_preserve_enabled():
        logger.debug("start_watcher: MANIFEST_PRESERVE off, skipping %s", library)
        return
    try:
        lib = Path(library).resolve()
    except OSError as exc:
        logger.warning("start_watcher: cannot resolve %s: %s", library, exc)
        return

    candidates: list[Path] = [
        lib / "depotcache",
        lib / "config" / "depotcache",
    ]

    started_any = False
    for depotcache in candidates:
        try:
            if not depotcache.is_dir():
                logger.debug(
                    "start_watcher: skipping %s (folder missing)",
                    depotcache,
                )
                continue
        except OSError:
            logger.debug(
                "start_watcher: skipping %s (drive inaccessible)",
                depotcache,
            )
            continue

        key = str(depotcache)
        with _WATCHER_LOCK:
            existing = _WATCHER_THREADS.get(key)
            if existing is not None and existing.is_alive():
                logger.debug(
                    "start_watcher: watcher already running for %s",
                    depotcache,
                )
                continue

            stop_event = threading.Event()
            target = _watch_loop_polling
            if sys.platform == "win32":
                target = _watch_loop_windows
            elif sys.platform.startswith("linux"):
                target = _watch_loop_linux

            thread = threading.Thread(
                target=target,
                args=(depotcache, stop_event),
                name=f"sff-manifest-watcher-{depotcache.parent.name}-{depotcache.name}",
                daemon=True,
            )
            thread._stop_event = stop_event  # type: ignore[attr-defined]
            _WATCHER_THREADS[key] = thread
            thread.start()
            started_any = True
            logger.info("start_watcher: watching %s", depotcache)

    if not started_any:
        logger.info(
            "start_watcher: no depotcache folders found under %s",
            lib,
        )
