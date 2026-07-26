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

import asyncio
import json
import logging
import os
import sys
from contextlib import contextmanager
from tempfile import TemporaryFile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from tqdm import tqdm  # type: ignore

from sff.prompts import prompt_confirm, prompt_text
from sff.secret_store import b64_decrypt
from typing import Literal, Union, overload

if sys.platform == "win32":
    import msvcrt
else:
    class msvcrt:
        kbhit = staticmethod(lambda: False)
        getch = staticmethod(lambda: None)


logger = logging.getLogger(__name__)

MANIFEST_REQUEST_CODE_HEADERS = {
    "User-Agent": "OpenSteamTool/1.0",
}


# httpx supports http/https + socks5 (with httpx-socks). socks4 is NOT
# supported and raises ValueError("Unknown scheme for proxy URL ...") deep
# inside its config layer the moment ANY httpx.Client is built while a
# socks4://, socks5h-without-extras://, or anything else weird is sitting
# in HTTPS_PROXY / HTTP_PROXY / ALL_PROXY. A VPN user (NekoBox, v2rayN, etc)
# tripped this on hubcap's get_hubcap call and the whole download died.
# Sanitise the env once at process start so every later httpx.get path runs
# direct instead of crashing. The user gets a single WARN line in the log
# explaining what happened.
_HTTPX_OK_PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")
_PROXY_ENV_KEYS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                   "https_proxy", "http_proxy", "all_proxy")


def _strip_unsupported_proxy_env():
    for key in _PROXY_ENV_KEYS:
        raw = os.environ.get(key, "")
        if not raw:
            continue
        scheme = raw.split("://", 1)[0].strip().lower() if "://" in raw else ""
        if scheme and scheme not in _HTTPX_OK_PROXY_SCHEMES:
            logger.warning(
                "Unsupported proxy scheme %r in %s, falling back to direct connection",
                scheme, key,
            )
            os.environ.pop(key, None)


_strip_unsupported_proxy_env()


def _httpx_call_safe(call, *args, **kwargs):
    """Run an httpx.* callable, retry once with proxies disabled if the
    httpx config layer rejects an env-detected proxy URL.

    Catches the very specific ValueError httpx raises during Client/AsyncClient
    construction when HTTPS_PROXY contains an unsupported scheme (socks4 etc).
    First call is normal so existing trust_env / mounts still work; retry forces
    trust_env=False so the env proxy is ignored. Real network errors propagate.
    """
    try:
        return call(*args, **kwargs)
    except ValueError as e:
        if "Unknown scheme for proxy URL" not in str(e):
            raise
        logger.warning(
            "httpx rejected proxy env (%s); retrying with direct connection", e
        )
        kwargs = dict(kwargs)
        kwargs["trust_env"] = False
        return call(*args, **kwargs)


@overload
async def get_request(
    url: str,
    type = "text",
    timeout = 10,
    headers = None,
): ...


@overload
async def get_request(
    url: str,
    type: Literal["json"],
    timeout = 10,
    headers = None,
): ...


async def get_request(
    url: str,
    type = "text",
    timeout = 10,
    headers = None,
    *,
    redact_url: bool = False,
):
    log_url = "<redacted>" if redact_url else url
    try:
        try:
            client_cm = httpx.AsyncClient(timeout=timeout)
        except ValueError as e:
            if "Unknown scheme for proxy URL" not in str(e):
                raise
            logger.warning(
                "httpx rejected proxy env (%s); retrying with direct connection", e
            )
            client_cm = httpx.AsyncClient(timeout=timeout, trust_env=False)
        async with client_cm as client:
            logger.debug(f"Making request to {log_url}")
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            try:
                logger.debug(f"Received {len(response.content)} bytes")
                return response.text if type == "text" else response.json()
            except ValueError:
                return
        else:
            # Body redacted when the URL is redacted, otherwise the upstream
            # error page (e.g. openresty 503 HTML) leaks identifying details
            # back into the live log even though the URL itself was masked.
            if redact_url:
                logger.debug(f"Error {response.status_code} (body redacted)")
            else:
                logger.debug(f"Error {response.status_code}: {response.text[:200]}")

    except httpx.RequestError as e:
        logger.debug(f"Request error: {repr(e)}")


def get_request_raw(url):
    while True:
        try:
            return httpx.get(url, timeout=None).content
        except httpx.HTTPError as e:
            print(f"Network error: {repr(e)}")
            if not prompt_confirm("Try again?"):
                return None


async def _wait_for_enter():
    print("If it takes too long, press Enter to cancel the request and input manually...")
    hit = msvcrt.kbhit
    read = msvcrt.getch
    while True:
        ready = hit() and read() == b"\r"
        if ready:
            return
        await asyncio.sleep(0.05)


def get_base_domain(url):
    p = urlparse(url)
    domain = p.netloc
    scheme = p.scheme
    return scheme + "://" + domain


def parse_manifest_request_code(body) -> str | None:
    if body is None:
        return None
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="ignore").strip()
    else:
        text = str(body).strip()
    if text and len(text) <= 64 and text.isdigit():
        return text
    if not text or len(text) > 4096:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    content = data.get("content")
    if content is None:
        return None
    code = str(content).strip()
    if code and len(code) <= 64 and code.isdigit():
        return code
    return None


def _request_code_body(body) -> bool:
    return parse_manifest_request_code(body) is not None


# Lowkey don't remember why i wrote it like this.
# It uses a default timeout of 10s but i think it still got stuck?
async def get_gmrc(manifest_id: Union[str, int], silent: bool = False):
    # Yes, I'm aware it's not actually "encrypted" since I included the password
    # Shut up. The point is keeping the host out of the live log + plaintext
    # source so it doesn't get scraped by every random analyzer that runs
    # against SteaMidra. The two HTTPS fallbacks below cover the gmrc
    # downtime window users have been hitting and are also kept encrypted.
    template_url = b64_decrypt(
        b'tkRhMNucVUvrymrfjAL8I0riINm/U76wgUJnmsjiaUs=',
        b'4R66BAMzqmlqisU/9Wwi5bSG2D/zWVuron4mRuw5gCFi+jPxwvqgHOvThx5BpLJAK23I5KABAm7tXlweO3lkEQk5OXrJUjH8zNnyKNv+tYDQE9/8teSpvA==',
    )
    url = template_url.format(manifest_id=manifest_id)

    # HTTPS-first fallback templates. Same wire shape (depot-key
    # request code, plain numeric body), but TLS-encrypted.
    _MIRROR_KEY = b'tkRhMNucVUvrymrfjAL8I0riINm/U76wgUJnmsjiaUs='
    _MIRROR_CTS = [
        b'0Iz+VYuhGtWcKNnwgz026jSlg+p0ai0b1KY6L0CwJjmoe21VRiepEcazuLa24PBss94RPXUyHxyctWq/Jr7geYIG3w9slfT0Xr9l7qosHZs6haacF3uzEgllSgVz',
        b'c2M+yi0x92v30LgEcOPF6L2xtohj1jzyQM22KTVMz+G6l9ibkeD5PY+AbMJCxj6DM+fJ5ZmFSPxTgOQfx8lMHv3VMrOjL+mmpMIJm+te1o4sKPYg',
    ]
    fallback_urls = []
    for ct in _MIRROR_CTS:
        try:
            tpl = b64_decrypt(_MIRROR_KEY, ct)
            fallback_urls.append(tpl.format(manifest_id=manifest_id))
        except Exception:
            continue

    print("Getting request code...")

    headers = {
        "Referer": get_base_domain(url),
        **MANIFEST_REQUEST_CODE_HEADERS,
    }

    # Sanity check on returned bodies. Real responses are an all-digit
    # decimal request code, usually 16-22 chars. Anything else (HTML
    # error page, ad redirect, MITM payload injection) gets rejected
    # before being handed back to the caller. The http gmrc endpoint
    # is the obvious risk since it's not TLS, but applying the same
    # guard to the https fallbacks is free and catches captive-portal
    # injection too.
    result = None

    # --- Primary endpoint ---
    # The encrypted URL is hidden on purpose, no logging it in plain text
    # via the debug log, hence redact_url=True. Already handles "the link
    # leaked into live log" case.
    if sys.platform != "win32":
        result = await get_request(url, headers=headers, redact_url=True)
    else:
        request_task = asyncio.create_task(get_request(url, headers=headers, redact_url=True))
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

    parsed_result = parse_manifest_request_code(result)
    if parsed_result is not None:
        return parsed_result
    if result is not None:
        # gmrc returned something but it's not a valid request code.
        # Treat as failure and let the https fallbacks try.
        logger.debug("gmrc returned non-numeric body, trying https fallbacks")

    # --- HTTPS fallbacks ---
    # Two TLS-encrypted mirrors that serve the same depot-key request code
    # for a given manifest GID. Tried in strict order, one at a time, each
    # with its own connect+read budget so a slow host can't hold the whole
    # cascade. fast-fail to the next on any failure.
    _PER_HOST = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
    for fb_url in fallback_urls:
        fb_headers = {"Referer": get_base_domain(fb_url), **MANIFEST_REQUEST_CODE_HEADERS}
        try:
            fb_result = await get_request(
                fb_url, headers=fb_headers, redact_url=True, timeout=_PER_HOST,
            )
        except Exception:
            fb_result = None
        parsed_fb_result = parse_manifest_request_code(fb_result)
        if parsed_fb_result is not None:
            print("✓ Got request code from HTTPS fallback")
            return parsed_fb_result

    if silent:
        return None

    # --- Fallback: cached manifests / manual ---
    print("\nAlternative sources for pre-fetched manifests:")
    print("  • ManifestHub API key → set in SFF Settings → downloads manifests automatically")
    print("  • ManifestHub site:   https://manifesthub1.filegear-sg.me")
    print("  • ManifestAutoUpdate: search GitHub for 'ManifestAutoUpdate'")
    print("  • Drop your own .manifest + depot key file if you have them.")
    code = prompt_text("Paste the manifest request code (leave blank to skip): ").strip()
    return code or None


def get_game_name(app_id):
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
    headers = None,
    params = None,
    chunk_size = (1024**2) // 2,
):
    temp_f = TemporaryFile()
    try:
        try:
            stream_cm = httpx.stream(
                "GET",
                url,
                headers=headers,
                params=params,
                follow_redirects=True,
                timeout=None,
            )
        except ValueError as e:
            if "Unknown scheme for proxy URL" not in str(e):
                raise
            logger.warning(
                "httpx rejected proxy env (%s); retrying with direct connection", e
            )
            stream_cm = httpx.stream(
                "GET",
                url,
                headers=headers,
                params=params,
                follow_redirects=True,
                timeout=None,
                trust_env=False,
            )
        with stream_cm as response:
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
    headers = None,
    chunk_size = (1024**2) // 2,
    timeout: float | None = 60.0,
):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "GET",
            url,
            headers=headers or {},
            follow_redirects=True,
            timeout=httpx.Timeout(connect=30.0, read=timeout, write=30.0, pool=30.0) if timeout else None,
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
