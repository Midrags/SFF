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

"""Download manager — queue, retry, and persistent history (500 cap)."""

import os
import json
import time
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class DownloadStatus(Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadMode(Enum):
    GREENLUMA = "GreenLuma"


@dataclass
class DownloadItem:
    app_id: int
    game_name: str
    status: DownloadStatus = DownloadStatus.QUEUED
    mode: DownloadMode = DownloadMode.GREENLUMA
    progress: int = 0  # 0-100
    total_bytes: int = 0
    downloaded_bytes: int = 0
    dest_path: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class HistoryEntry:
    app_id: int
    game_name: str
    status: str  # "completed" or "failed"
    mode: str
    size: int = 0
    dest_path: str = ""
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class DownloadHistory:
    """JSON-backed history, auto-trims at 500 entries."""

    MAX_ENTRIES = 500

    def __init__(self):
        self._path = self._get_history_path()
        self._entries: list[HistoryEntry] = []
        self._load()

    @staticmethod
    def _get_history_path() -> Path:
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
        path = base / "SteaMidra" / "download_history.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self):
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._entries = [HistoryEntry.from_dict(e) for e in data]
        except Exception as e:
            logger.warning("Failed to load download history: %s", e)
            self._entries = []

    def _save(self):
        try:
            data = [e.to_dict() for e in self._entries]
            self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save download history: %s", e)

    def add(self, entry: HistoryEntry):
        self._entries.append(entry)
        while len(self._entries) > self.MAX_ENTRIES:
            self._entries.pop(0)
        self._save()

    def get_all(self) -> list[HistoryEntry]:
        return list(self._entries)

    def clear(self):
        self._entries.clear()
        self._save()

    @property
    def count(self) -> int:
        return len(self._entries)


class DownloadManager:
    """Queue-based download manager with retry and persistent history."""

    def __init__(self):
        self._queue: list[DownloadItem] = []
        self._active: Optional[DownloadItem] = None
        self._completed: list[DownloadItem] = []
        self._failed: list[DownloadItem] = []
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self.history = DownloadHistory()

        # callbacks
        self.on_progress: Optional[Callable[[DownloadItem], None]] = None
        self.on_completed: Optional[Callable[[DownloadItem], None]] = None
        self.on_failed: Optional[Callable[[DownloadItem], None]] = None
        self.on_queue_changed: Optional[Callable[[], None]] = None

    def queue_download(
        self,
        app_id: int,
        game_name: str,
        dest_path: str,
        mode: DownloadMode = DownloadMode.GREENLUMA,
        download_func: Optional[Callable] = None,
    ) -> DownloadItem:
        # download_func(app_id, dest_path, progress_callback) -> bool
        item = DownloadItem(
            app_id=app_id,
            game_name=game_name,
            dest_path=dest_path,
            mode=mode,
        )
        item._download_func = download_func

        with self._lock:
            self._queue.append(item)

        if self.on_queue_changed:
            self.on_queue_changed()

        self._start_worker()
        return item

    def cancel_download(self, app_id: int):
        with self._lock:
            # remove from queue
            self._queue = [d for d in self._queue if d.app_id != app_id]

            # cancel active
            if self._active and self._active.app_id == app_id:
                self._cancel_event.set()
                self._active.status = DownloadStatus.CANCELLED

        if self.on_queue_changed:
            self.on_queue_changed()

    def retry_download(self, app_id: int):
        with self._lock:
            for i, item in enumerate(self._failed):
                if item.app_id == app_id:
                    item.status = DownloadStatus.QUEUED
                    item.error = ""
                    item.retry_count = 0
                    self._queue.append(item)
                    self._failed.pop(i)
                    break

        self._start_worker()
        if self.on_queue_changed:
            self.on_queue_changed()

    def _start_worker(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _worker_loop(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._active = None
                    return
                item = self._queue.pop(0)
                self._active = item

            self._cancel_event.clear()
            item.status = DownloadStatus.ACTIVE
            item.started_at = time.time()

            if self.on_queue_changed:
                self.on_queue_changed()

            success = self._execute_download(item)

            if success:
                item.status = DownloadStatus.COMPLETED
                item.completed_at = time.time()
                item.progress = 100
                with self._lock:
                    self._completed.append(item)

                self.history.add(HistoryEntry(
                    app_id=item.app_id,
                    game_name=item.game_name,
                    status="completed",
                    mode=item.mode.value,
                    size=item.total_bytes,
                    dest_path=item.dest_path,
                    timestamp=item.completed_at,
                ))

                if self.on_completed:
                    self.on_completed(item)
            else:
                if item.status != DownloadStatus.CANCELLED:
                    item.status = DownloadStatus.FAILED
                    item.completed_at = time.time()
                    with self._lock:
                        self._failed.append(item)

                    self.history.add(HistoryEntry(
                        app_id=item.app_id,
                        game_name=item.game_name,
                        status="failed",
                        mode=item.mode.value,
                        error=item.error,
                        timestamp=item.completed_at,
                    ))

                    if self.on_failed:
                        self.on_failed(item)

            if self.on_queue_changed:
                self.on_queue_changed()

    def _execute_download(self, item: DownloadItem) -> bool:
        backoff = 2

        for attempt in range(item.max_retries + 1):
            if self._cancel_event.is_set():
                return False

            try:
                if hasattr(item, '_download_func') and item._download_func:
                    def progress_cb(current, total):
                        item.downloaded_bytes = current
                        item.total_bytes = total
                        if total > 0:
                            item.progress = int((current / total) * 100)
                        if self.on_progress:
                            self.on_progress(item)

                    result = item._download_func(item.app_id, item.dest_path, progress_cb)
                    if result:
                        return True
                    else:
                        item.error = "Download function returned False"
                else:
                    item.error = "No download function provided"
                    return False

            except Exception as e:
                item.error = str(e)
                logger.warning(
                    "Download attempt %d/%d for %s failed: %s",
                    attempt + 1, item.max_retries + 1, item.game_name, e
                )

            item.retry_count = attempt + 1

            if attempt < item.max_retries:
                logger.info("Retrying in %ds...", backoff)
                for _ in range(backoff * 10):
                    if self._cancel_event.is_set():
                        return False
                    time.sleep(0.1)
                backoff *= 2

        return False

    # --- status queries ---

    def get_queue(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._queue)

    def get_active(self) -> Optional[DownloadItem]:
        return self._active

    def get_completed(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._completed)

    def get_failed(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._failed)

    @property
    def active_count(self) -> int:
        return (1 if self._active else 0) + len(self._queue)

    def clear_completed(self):
        with self._lock:
            self._completed.clear()
        if self.on_queue_changed:
            self.on_queue_changed()

    def clear_failed(self):
        with self._lock:
            self._failed.clear()
        if self.on_queue_changed:
            self.on_queue_changed()

    # --- external tracking (for flows that manage their own download) ---

    def track_external(self, app_id: int, game_name: str) -> DownloadItem:
        # Register a download that is managed outside the worker queue
        # (e.g. process_lua_full).  Caller updates .progress / .status
        # and must call complete_external() when done.
        item = DownloadItem(
            app_id=app_id,
            game_name=game_name,
            status=DownloadStatus.ACTIVE,
            started_at=time.time(),
        )
        with self._lock:
            self._active = item
        if self.on_queue_changed:
            self.on_queue_changed()
        return item

    def complete_external(self, item: DownloadItem, success: bool = True, error: str = ""):
        item.completed_at = time.time()
        if success:
            item.status = DownloadStatus.COMPLETED
            item.progress = 100
            with self._lock:
                self._completed.append(item)
                if self._active is item:
                    self._active = None
            self.history.add(HistoryEntry(
                app_id=item.app_id,
                game_name=item.game_name,
                status="completed",
                mode=item.mode.value,
                size=item.total_bytes,
                dest_path=item.dest_path,
                timestamp=item.completed_at,
            ))
            if self.on_completed:
                self.on_completed(item)
        else:
            item.status = DownloadStatus.FAILED
            item.error = error
            with self._lock:
                self._failed.append(item)
                if self._active is item:
                    self._active = None
            self.history.add(HistoryEntry(
                app_id=item.app_id,
                game_name=item.game_name,
                status="failed",
                mode=item.mode.value,
                error=error,
                timestamp=item.completed_at,
            ))
            if self.on_failed:
                self.on_failed(item)
        if self.on_queue_changed:
            self.on_queue_changed()
