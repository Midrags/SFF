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

"""Steam Workshop collection fetching via Web API."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GET_COLLECTION_DETAILS_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v0001/"
)


def get_collection_children(
    collection_id: int,
    api_key: str,
    timeout: float = 15.0,
) -> list[int]:
    if not api_key:
        logger.warning("No Steam Web API key provided for GetCollectionDetails")
        return []

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                GET_COLLECTION_DETAILS_URL,
                data={
                    "key": api_key,
                    "collectioncount": 1,
                    "publishedfileids[0]": collection_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("GetCollectionDetails failed: %s", e)
        return []

    try:
        details_list = data.get("response", {}).get("collectiondetails", [])
        if not details_list:
            return []
        details = details_list[0]
        children = details.get("children", [])
        result = []
        for child in children:
            pid = child.get("publishedfileid")
            if pid is not None:
                try:
                    result.append(int(pid))
                except (TypeError, ValueError):
                    pass
        return result
    except (KeyError, TypeError, AttributeError) as e:
        logger.warning("Failed to parse GetCollectionDetails response: %s", e)
        return []
