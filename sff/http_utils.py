import asyncio
import logging
import sys
from contextlib import contextmanager
from tempfile import TemporaryFile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator, Literal, Optional, Union, overload
from urllib.parse import urlparse

import httpx
from tqdm import tqdm  # type: ignore

from sff.prompts import prompt_confirm, prompt_text
from sff.secret_store import b64_decrypt

if sys.platform == "win32":
    import msvcrt
else:
    class msvcrt:
        @staticmethod
        def kbhit():
            return False

        @staticmethod
        def getch():
            return None

if TYPE_CHECKING:
    from tempfile import _TemporaryFileWrapper  # pyright: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)


@overload
async def get_request(
    url: str,
    type: Literal["text"] = "text",
    timeout: int = 10,
    headers: Optional[dict[str, str]] = None,
) -> Union[str, None]: ...


@overload
async def get_request(
    url: str,
    type: Literal["json"],
    timeout: int = 10,
    headers: Optional[dict[str, str]] = None,
) -> Union[dict[Any, Any], None]: ...


async def get_request(
    url: str,
    type: Literal["text", "json"] = "text",
    timeout: int = 10,
    headers: Optional[dict[str, str]] = None,
) -> Union[str, dict[Any, Any], None]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.debug(f"Making request to {url}")
            response = await client.get(url, headers=headers)

        if response.status_code == 200:
            try:
                logger.debug(f"Received {response.content}")
                return response.text if type == "text" else response.json()
            except ValueError:
                return
        else:
            print(f"Error {response.status_code}")
            print(f"Response: {response.text}")

    except httpx.RequestError as e:
        print(f"An error occurred: {repr(e)}")


def get_request_raw(url: str):
    resp = None
    while True:
        try:
            resp = httpx.get(url, timeout=None)
        except httpx.HTTPError as e:
            print(f"Network error: {repr(e)}")
            if prompt_confirm("Try again?"):
                continue
        break
    if resp:
        return resp.content


async def _wait_for_enter():
    print(
        "If it takes too long, press Enter to cancel the request "
        "and input manually..."
    )
    while True:
        if msvcrt.kbhit() and msvcrt.getch() == b"\r":
            return
        await asyncio.sleep(0.05)


def get_base_domain(url: str):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return base_url


def _fetch_gmrc_via_tor(manifest_id: Union[str, int]) -> Union[str, None]:
    # Tries local Tor SOCKS5 (9050/9150) first, then pure-Python torpy.
    # torpy only speaks v2 hidden services; KurO's onion is v3 so that path
    # will fail for now, but the SOCKS path handles v3 fine.
    try:
        import requests as _requests  # already in requirements
    except ImportError:
        logger.debug("requests not available, skipping Tor fetch")
        return None

    onion_url = (
        f"http://xmctrpypzbmakjquef3ph3l3coqfmhbrp6gerqymhmlj2bg7473gmyd"
        f".onion/{manifest_id}"
    )

    # --- Path 1: local Tor daemon / Tor Browser SOCKS5 (supports v3 onion) ---
    for port in (9050, 9150):
        try:
            proxies = {
                "http": f"socks5h://127.0.0.1:{port}",
                "https": f"socks5h://127.0.0.1:{port}",
            }
            resp = _requests.get(onion_url, proxies=proxies, timeout=30)
            if resp.status_code == 200 and resp.text.strip():
                logger.debug(f"Tor GMRC fetch succeeded on port {port}")
                return resp.text.strip()
        except Exception as e:
            logger.debug(f"Tor port {port} unavailable: {e}")

    # --- Path 2: torpy pure-Python Tor circuit (no binary needed) ---
    # Note: torpy only supports v2 hidden services; the KurO onion is v3, so
    # this path will raise an exception for that address.  It is included so
    # that the feature works if a v2 or clearnet fallback URL is ever added.
    try:
        from torpy.http.requests import TorRequests  # type: ignore
        print("  Trying pure-Python Tor (torpy) — building circuit...")
        with TorRequests() as tor_req:
            with tor_req.get_session() as sess:
                resp = sess.get(onion_url, timeout=60)
                if resp.status_code == 200 and resp.text.strip():
                    logger.debug("torpy GMRC fetch succeeded")
                    return resp.text.strip()
    except ImportError:
        logger.debug("torpy not installed; skipping pure-Python Tor path")
    except Exception as e:
        logger.debug(f"torpy failed (v3 onion not supported by torpy): {e}")

    return None


# Lowkey don't remember why i wrote it like this.
# It uses a default timeout of 10s but i think it still got stuck?
async def get_gmrc(manifest_id: Union[str, int]) -> Union[str, None]:
    # Yes, I'm aware it's not actually "encrypted" since I included the password
    # Shut up.
    template_url = b64_decrypt(
        b'gzTYiUdY7dR2oFPM+cUEUpSnLYn17uq09F8PATpFKT8=',
        b'rok2PaPQ2T0CF3RZXe+AfytF7i+Yo/kEykq4hnPSSrhRDeESOARdQD4+SzqZqeG5C5U4fAiuEUuPpr1CaXl9V/Xv9EcZdWk1BbyUqCXP8FHkqdGm',
    )
    url = template_url.format(manifest_id=manifest_id)
    print("Getting request code...")

    headers = {
        "Referer": get_base_domain(url),
    }

    result = None

    # --- Primary: main Steamtools endpoint ---
    if sys.platform != "win32":
        result = await get_request(url, headers=headers)
    else:
        request_task = asyncio.create_task(get_request(url, headers=headers))
        cancel_task = asyncio.create_task(_wait_for_enter())

        done, pending = await asyncio.wait(
            {request_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
        )

        if request_task in done:
            result = request_task.result()

        if cancel_task in done:
            if not request_task.done():
                print("Cancelling request...", end="")
                request_task.cancel()

        for t in pending:
            t.cancel()

        try:
            if result is None:
                result = await request_task
        except asyncio.CancelledError:
            print("✅")

    if result is not None:
        return result

    # --- Fallback 1: Auto-Tor via local SOCKS5 proxy (no Tor Browser needed) ---
    onion_url = f"http://xmctrpypzbmakjquef3ph3l3coqfmhbrp6gerqymhmlj2bg7473gmyd.onion/{manifest_id}"
    print("\nMain endpoint unavailable. Trying Tor network automatically...")
    print(f"  Onion: {onion_url}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _fetch_gmrc_via_tor, manifest_id)
    if result is not None:
        print("✅ Got request code via Tor!")
        return result

    print("Tor unavailable (no local Tor daemon on 9050/9150).")
    print("Install Tor daemon: https://www.torproject.org/download/#tor-downloads")
    print("  (Tor Expert Bundle — no browser needed; just run tor.exe)")
    code = prompt_text("Or paste the code manually (leave blank for cached manifest sources): ").strip()
    if code:
        return code

    # --- Fallback 2: cached manifests / manual ---
    print("\nAlternative sources for pre-fetched manifests:")
    print("  • ManifestHub API key → set in SFF Settings → downloads manifests automatically")
    print("  • ManifestHub site:   https://manifesthub1.filegear-sg.me")
    print("  • ManifestAutoUpdate: search GitHub for 'ManifestAutoUpdate'")
    print("  • youxiou.com         (community manifests & depot keys)")
    print("  • Drop your own .manifest + depot key file if you have them.")
    code = prompt_text("Paste the manifest request code (leave blank to skip): ").strip()
    return code or None


def get_game_name(app_id: str) -> str:
    official_info = asyncio.run(
        get_request(
            f"https://store.steampowered.com/api/appdetails/?appids={app_id}",
            "json",
        )
    )
    if official_info:
        app_name = official_info.get(app_id, {}).get("data", {}).get("name")
        if app_name is None:
            app_name = prompt_text(
                "Request succeeded but couldn't find the game name. "
                "Type the name of it: "
            )
    else:
        app_name = prompt_text("Request failed. Type the name of the game: ")
    return app_name


@contextmanager
def download_to_tempfile(
    url: str,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, str]] = None,
    chunk_size: int = (1024**2) // 2,
) -> Generator[Union["_TemporaryFileWrapper[bytes]", None], None, None]:
    temp_f = TemporaryFile()
    try:
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            params=params,
            follow_redirects=True,
            timeout=None,
        ) as response:

            try:
                total = int(response.headers.get("Content-Length", "0"))
            except Exception as e:
                print(f"Could not parse Content-Length header: {e}")
                total = 0
            logger.debug(f"Total size is {total}")
            with tqdm(
                desc="Downloading",
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                miniters=1,
            ) as pbar:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    temp_f.write(chunk)
                    pbar.update(len(chunk))
        temp_f.seek(0)
        yield temp_f
    except httpx.HTTPError as e:
        print(f"Network error: {repr(e)}")
        yield None
    finally:
        temp_f.close()


def download_to_path(
    url: str,
    path: Path,
    headers: Optional[dict[str, str]] = None,
    chunk_size: int = (1024**2) // 2,
) -> bool:
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "GET",
            url,
            headers=headers or {},
            follow_redirects=True,
            timeout=None,
        ) as response:
            response.raise_for_status()
            try:
                total = int(response.headers.get("Content-Length", "0"))
            except (ValueError, TypeError):
                total = 0
            with path.open("wb") as f, tqdm(
                desc="Downloading",
                total=total or None,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                miniters=1,
            ) as pbar:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    f.write(chunk)
                    pbar.update(len(chunk))
        return True
    except httpx.HTTPError as e:
        print(f"Download error: {repr(e)}")
        return False
