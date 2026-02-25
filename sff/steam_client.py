import json
import time
from typing import Any, Union

import gevent
from steam.client import SteamClient  # type: ignore

from sff.cache import get_cache
from sff.structs import DLCTypes, ProductInfo  # type: ignore
import logging

from sff.utils import enter_path

logger = logging.getLogger(__name__)


def get_product_info(provider: "SteamInfoProvider", app_ids: list[int]) -> ProductInfo:
    """Here for backwards compatibility"""
    return ProductInfo({"apps": provider.get_app_info(app_ids), "packages": {}})


_MAX_APP_INFO_RETRIES = 3


def _get_product_info(client: SteamClient, app_ids: list[int]) -> ProductInfo:
    if len(app_ids) == 0:
        raise ValueError("app_ids cannot be empty.")
    if not client.logged_on:
        print("Logging in anonymously...", end="", flush=True)
        client.anonymous_login()
        print(" Done!")
    last_error = None
    for attempt in range(1, _MAX_APP_INFO_RETRIES + 1):
        try:
            print("Getting app info...")
            logger.debug(f"Getting info for {', '.join([str(x) for x in app_ids])}")
            start = time.time()
            info = client.get_product_info(  # pyright: ignore[reportUnknownMemberType]
                app_ids
            )
            # only none when app_ids is empty, which never happens
            assert info is not None
            logger.debug(f"Product info request took: {time.time() - start}s")
            return ProductInfo(info)
        except gevent.Timeout as e:
            last_error = e
            if attempt < _MAX_APP_INFO_RETRIES:
                print(f"Request timed out. Trying again ({attempt}/{_MAX_APP_INFO_RETRIES})...")
                try:
                    client.anonymous_login()
                except RuntimeError:
                    pass
                time.sleep(2)
            else:
                print(
                    "Request timed out after several attempts. "
                    "Check your internet connection and Steam status, then try again later."
                )
                raise


class SteamInfoProvider:
    """Wrapper for SteamClient to handle API calls and caching."""

    def __init__(self, client: SteamClient):
        self.client = client
        self._cache: dict[int, Any] = {}
        """A cache of app IDs and their data taken
        from the `apps` key of `get_product_info`.
        Values are False if it's not a base app ID"""
        self._persistent_cache = get_cache()

    def get_app_info(self, app_ids: list[int]) -> dict[int, Any]:
        # Check persistent cache first
        missing = []
        for app_id in app_ids:
            if app_id not in self._cache:
                # Try persistent cache
                cache_key = f"app_info_{app_id}"
                cached_data = self._persistent_cache.get(cache_key)
                if cached_data is not None:
                    self._cache[app_id] = cached_data
                    logger.debug(f"Loaded app {app_id} from persistent cache")
                else:
                    missing.append(app_id)
        
        if missing:
            info = _get_product_info(self.client, missing)
            apps: dict[int, Any] = info.get("apps", {})
            valid_ids = set(apps.keys())
            invalid_ids = set(missing) - valid_ids
            
            # Update both in-memory and persistent cache
            for app_id, app_data in apps.items():
                self._cache[app_id] = app_data
                cache_key = f"app_info_{app_id}"
                self._persistent_cache.set(cache_key, app_data)
            
            for app_id in invalid_ids:
                self._cache[app_id] = False
        else:
            print("Reading app info from cache...")

        return {
            app_id: self._cache.get(app_id, {})
            for app_id in app_ids
            if self._cache.get(app_id, {})
        }

    def get_single_app_info(self, app_id: int) -> dict[str, Any]:
        result = self.get_app_info([app_id])
        return result.get(app_id, {})


class ParsedDLC:
    def __init__(
        self,
        depot_id: int,
        dlc_data: dict[str, Any],
        parent_data: dict[str, Any],
        local_ids: list[int],
    ):
        self.id = depot_id
        self.name: str = enter_path(dlc_data, "common", "name")
        depots = enter_path(dlc_data, "depots")
        parent_depots: dict[str, Union[dict[str, Any], str]] = enter_path(
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