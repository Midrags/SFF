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

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import gevent
from steam.client import SteamClient  # type: ignore

from sff.cache import get_cache
from sff.structs import DLCTypes, ProductInfo  # type: ignore
import logging

from sff.utils import enter_path

logger = logging.getLogger(__name__)


def get_product_info(provider: "SteamInfoProvider", app_ids):
    """Here for backwards compatibility"""
    return ProductInfo({"apps": provider.get_app_info(app_ids), "packages": {}})


def create_provider_for_current_thread():
    client = SteamClient()
    return SteamInfoProvider(client)


_APP_INFO_TIMEOUTS = (15, 30, 60)
_MAX_APP_INFO_RETRIES = len(_APP_INFO_TIMEOUTS)
_GEVENT_LOCK = threading.Lock()


@dataclass
class _ProductInfoResult:
    info: ProductInfo
    complete: bool


def _steam_transient_errors():
    import socket
    try:
        from steam.exceptions import SteamError  # type: ignore
    except Exception:
        SteamError = ()  # type: ignore[assignment]

    errors = (
        gevent.Timeout,
        socket.timeout,
        ConnectionResetError,
        ConnectionAbortedError,
        ConnectionError,
        EOFError,
        OSError,
    )
    return errors + ((SteamError,) if SteamError else ())  # type: ignore[operator]


def _ensure_client_session(client):
    if client.logged_on:
        return
    print("Logging in anonymously...", end="", flush=True)
    client.anonymous_login()
    print(" Done!")


def _client_state(client):
    return (
        f"logged_on={getattr(client, 'logged_on', None)!r}, "
        f"server={getattr(client, 'current_server_addr', None)!r}"
    )


def _reopen_client_session(client):
    try:
        if getattr(client, "logged_on", False) and hasattr(client, "disconnect"):
            client.disconnect()
            time.sleep(0.5)
    except Exception as e:
        logger.debug("Steam appinfo reconnect disconnect failed: %r", e)
    try:
        client.anonymous_login()
        logger.debug("Steam appinfo reconnect ok (%s)", _client_state(client))
    except Exception as e:
        logger.debug("Steam appinfo reconnect failed: %r (%s)", e, _client_state(client))


def _empty_product_info():
    return ProductInfo({"apps": {}, "packages": {}})


def _request_app_info(client, app_ids, timeout):
    print("Getting app info...")
    logger.debug(
        "Getting info for %s with timeout=%ss (%s)",
        ", ".join([str(x) for x in app_ids]),
        timeout,
        _client_state(client),
    )
    start = time.time()
    info = client.get_product_info(  # pyright: ignore[reportUnknownMemberType]
        apps=list(app_ids),
        timeout=timeout,
    )
    if info is None:
        raise gevent.Timeout(None, "get_product_info returned None")
    logger.debug(f"Product info request took: {time.time() - start}s")
    return ProductInfo(info)


def _get_product_info_result(client, app_ids):
    if len(app_ids) == 0:
        raise ValueError("app_ids cannot be empty.")
    with _GEVENT_LOCK:
        _ensure_client_session(client)
        last_error: Exception | None = None
        transient = _steam_transient_errors()
        for attempt, timeout in enumerate(_APP_INFO_TIMEOUTS, start=1):
            try:
                return _ProductInfoResult(_request_app_info(client, app_ids, timeout), True)
            except transient as e:
                last_error = e
                logger.debug(
                    "App info attempt %s/%s hit %s with timeout=%ss for apps=%s: %r (%s)",
                    attempt,
                    _MAX_APP_INFO_RETRIES,
                    type(e).__name__,
                    timeout,
                    app_ids,
                    e,
                    _client_state(client),
                )
                if attempt < _MAX_APP_INFO_RETRIES:
                    print(
                        f"Request timed out after {timeout}s. "
                        f"Trying again ({attempt}/{_MAX_APP_INFO_RETRIES})..."
                    )
                    _reopen_client_session(client)
                    time.sleep(2)
                    continue
                print(
                    "Steam appinfo timed out after several attempts. "
                    "SteaMidra will use cached/local manifests if available."
                )
                return _ProductInfoResult(_empty_product_info(), False)
        # All retries exhausted without an exception we recognised.
        if last_error is not None:
            logger.warning(f"App info gave up after {_MAX_APP_INFO_RETRIES} attempts: {last_error}")
        return _ProductInfoResult(_empty_product_info(), False)


def _get_product_info(client, app_ids):
    return _get_product_info_result(client, app_ids).info


class SteamInfoProvider:

    def __init__(self, client):
        self.client = client
        self._cache: dict[int, Any] = {}
        self._persistent_cache = get_cache()

    def _cache_key(self, app_id):
        return f"app_info_{app_id}"

    def _load_cached_app(self, app_id) -> bool:
        cached_data = self._persistent_cache.get(self._cache_key(app_id))
        if cached_data is None:
            return False
        self._cache[app_id] = cached_data
        logger.debug(f"Loaded app {app_id} from persistent cache")
        return True

    def _store_app_payloads(self, apps):
        for app_id, app_data in apps.items():
            self._cache[app_id] = app_data
            self._persistent_cache.set(self._cache_key(app_id), app_data)

    def get_app_info(self, app_ids):
        missing = []
        for app_id in app_ids:
            if app_id in self._cache:
                continue
            if not self._load_cached_app(app_id):
                missing.append(app_id)
        if missing:
            result = _get_product_info_result(self.client, missing)
            apps = result.info.get("apps", {})
            valid_ids = set(apps.keys())
            self._store_app_payloads(apps)
            if result.complete:
                invalid_ids = set(missing) - valid_ids
                for app_id in invalid_ids:
                    self._cache[app_id] = False
            else:
                logger.debug(
                    "Steam appinfo fetch incomplete; leaving %s uncached for later retry",
                    sorted(set(missing) - valid_ids),
                )
        else:
            print("Reading app info from cache...")
        return {
            app_id: self._cache.get(app_id, {})
            for app_id in app_ids
            if self._cache.get(app_id, {})
        }

    def get_single_app_info(self, app_id):
        result = self.get_app_info([app_id])
        return result.get(app_id, {})


class ParsedDLC:
    def __init__(
        self,
        depot_id: int,
        dlc_data,
        parent_data,
        local_ids: list[int],
    ):
        self.id = depot_id
        self.name: str = enter_path(dlc_data, "common", "name")
        depots = enter_path(dlc_data, "depots")
        parent_depots = enter_path(
            parent_data, "depots"
        )
        parent_depots_resolved = [
            (x.get("dlcappid") if isinstance(x, dict) else None)
            for x in parent_depots.values()
        ]
        self.release_state = enter_path(dlc_data, "common", "releasestate")
        self.type = (
            (
                DLCTypes.DEPOT
                if depots or str(depot_id) in parent_depots_resolved
                else DLCTypes.NOT_DEPOT
            )
            if self.release_state == "released"
            else DLCTypes.UNRELEASED
        )
        self.in_applist = True if depot_id in local_ids else False
