import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional, Union

import gevent
from steam.client import SteamClient  # type: ignore
from steam.core.msg import MsgProto  # type: ignore
from steam.protobufs.steammessages_publishedfile_pb2 import (
    CPublishedFile_GetDetails_Response,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkshopItemContext:
    client: SteamClient
    workshop_id: int
    "AKA PublishedFileId"


@dataclass
class HContentFile:
    """Modern workshop items with manifest"""
    ugc_id: int


@dataclass
class DirectDownloadUrl:
    """Legacy workshop items with direct download URL"""
    url: str


WorkshopContent = Union[HContentFile, DirectDownloadUrl]


class IUgcIdStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Clean name of the strategy"""
        pass

    @abstractmethod
    def get_content(self, ctx: WorkshopItemContext) -> Optional[WorkshopContent]:
        pass


class StandardUgcIdStrategy(IUgcIdStrategy):

    @property
    def name(self):
        return "Standard"

    def _send_request(self, client: SteamClient, workshop_id: int):
        resp: Any = (  # pyright: ignore[reportUnknownVariableType]
            client.send_um_and_wait(  # pyright: ignore[reportUnknownMemberType]
                "PublishedFile.GetDetails#1",
                {
                    "publishedfileids": [workshop_id],
                    "includetags": False,
                    "includeadditionalpreviews": False,
                    "includechildren": False,
                    "includekvtags": False,
                    "includevotes": False,
                    "short_description": True,
                    "includeforsaledata": False,
                    "includemetadata": False,
                    "language": 0,
                },
                timeout=7,
            )
        )
        if (
            not isinstance(resp, MsgProto)
            or resp.body is None  # pyright: ignore[reportUnknownMemberType]
        ):
            return None
        if not isinstance(
            resp.body,  # pyright: ignore[reportUnknownMemberType]
            CPublishedFile_GetDetails_Response,
        ):
            return None
        details = resp.body.publishedfiledetails
        return details[0]

    _MAX_UGC_RETRIES = 3

    def _get_workshop_items_details(self, ctx: WorkshopItemContext):
        if not ctx.client.logged_on:
            print("Logging in anonymously...", end="", flush=True)
            ctx.client.anonymous_login()
            print(" Done!")
        last_error = None
        for attempt in range(1, self._MAX_UGC_RETRIES + 1):
            try:
                resp = self._send_request(ctx.client, ctx.workshop_id)
                return resp
            except gevent.Timeout as e:
                last_error = e
                if attempt < self._MAX_UGC_RETRIES:
                    print(f"Request timed out. Trying again ({attempt}/{self._MAX_UGC_RETRIES})...")
                    try:
                        ctx.client.anonymous_login()
                    except RuntimeError:
                        pass
                    time.sleep(2)
                else:
                    print(
                        "Request timed out after several attempts. "
                        "Check your internet connection and try again later."
                    )
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("Unexpected: no response and no error")

    def _content_from_details(self, details: Any) -> Optional[WorkshopContent]:
        if not details:
            return None
        if details.file_url:
            return DirectDownloadUrl(details.file_url)
        return HContentFile(details.hcontent_file)

    def get_content(self, ctx: WorkshopItemContext) -> Optional[WorkshopContent]:
        details = self._get_workshop_items_details(ctx)
        return self._content_from_details(details)

    def get_content_and_details(
        self, ctx: WorkshopItemContext
    ) -> tuple[Optional[WorkshopContent], Optional[Any]]:
        """Get content and raw details in one call (avoids duplicate GetDetails)."""
        details = self._get_workshop_items_details(ctx)
        return self._content_from_details(details), details


class UgcIDResolver:
    def __init__(self, strategies: List[IUgcIdStrategy]):
        self.strategies = strategies

    def resolve(self, ctx: WorkshopItemContext) -> tuple[WorkshopContent, str]:
        """Iterates strategies until a UGC ID is found.
        Returns content and strategy name."""
        content, _method, _details = self.resolve_with_details(ctx)
        return content, _method

    def resolve_with_details(
        self, ctx: WorkshopItemContext
    ) -> tuple[WorkshopContent, str, Optional[Any]]:
        """Resolve and return content, method name, and raw details (for time_updated)."""
        for strategy in self.strategies:
            if isinstance(strategy, StandardUgcIdStrategy):
                content, details = strategy.get_content_and_details(ctx)
                if content is not None:
                    return content, strategy.name, details
            else:
                content = strategy.get_content(ctx)
                if content is not None:
                    return content, strategy.name, None
        raise Exception(f"Unable to resolve manifest for depot {ctx.workshop_id}")


def get_workshop_time_updated(ctx: WorkshopItemContext) -> Optional[int]:
    """Get time_updated for a workshop item. Returns None on failure."""
    strategy = StandardUgcIdStrategy()
    try:
        details = strategy._get_workshop_items_details(ctx)
        return getattr(details, "time_updated", None) if details else None
    except Exception:
        return None
