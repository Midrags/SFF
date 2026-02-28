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
    """Fetch child workshop item IDs from a Steam Workshop collection.

    Uses Steam Web API GetCollectionDetails. No login required.

    Args:
        collection_id: The published file ID of the collection.
        api_key: Steam Web API key.
        timeout: Request timeout in seconds.

    Returns:
        List of publishedfileid for each child. Empty if not a collection,
        API error, or no children.
    """
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
