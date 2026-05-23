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

"""Pixeldrain downloader with the gamedrive.org proxy bypass.

Pixeldrain rate-limits direct downloads. The community-maintained proxy at
https://pixeldrain-bypass.gamedrive.org/ exposes a CDN host that mirrors files
without the limit. We pull the current proxy list, cache it for 24h, then
stream files through it. If the proxy fails we fall back to a direct
pixeldrain API download so a stale proxy never bricks the feature.
"""

from __future__ import annotations

import json
import random
import re
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import httpx
from colorama import Fore, Style

from sff.utils import root_folder

PROXY_LIST_URL = "https://pixeldrain-bypass.gamedrive.org/api/proxy.json"
PROXY_CACHE_TTL_S = 24 * 60 * 60

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_MAGIC = {
    b"Rar!":         ".rar",
    b"7z\xbc\xaf":   ".7z",
    b"PK\x03\x04":   ".zip",
    b"PK\x05\x06":   ".zip",
    b"PK\x07\x08":   ".zip",
}


def _proxy_cache_path() -> Path:
    cache_dir = root_folder() / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "pd_proxy.json"


def _load_cached_proxies() -> tuple[list[str], float]:
    p = _proxy_cache_path()
    if not p.is_file():
        return [], 0.0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ts = float(data.get("ts", 0))
        proxies = data.get("proxies") or []
        if not isinstance(proxies, list):
            return [], 0.0
        return proxies, ts
    except Exception:
        return [], 0.0


def _save_cached_proxies(proxies: list[str]) -> None:
    try:
        _proxy_cache_path().write_text(
            json.dumps({"ts": time.time(), "proxies": proxies}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _normalize_proxy(entry: str) -> str | None:
    if not isinstance(entry, str):
        return None
    s = entry.strip()
    if not s:
        return None
    if not re.match(r"^https?://", s, re.IGNORECASE):
        s = "https://" + s
    if not s.endswith("/"):
        s += "/"
    return s


def _fetch_fresh_proxies() -> list[str]:
    try:
        resp = httpx.get(
            PROXY_LIST_URL,
            headers={"User-Agent": _UA, "Cache-Control": "no-store"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            raw = data.get("proxies") or ([data["proxy"]] if isinstance(data.get("proxy"), str) else [])
        elif isinstance(data, list):
            raw = data
        else:
            raw = []
        out = [n for n in (_normalize_proxy(x) for x in raw) if n]
        if out:
            _save_cached_proxies(out)
        return out
    except Exception as e:
        print(Fore.YELLOW + f"  pixeldrain: proxy list fetch failed ({e}), falling back to cache" + Style.RESET_ALL)
        return []


def _get_proxy_list() -> list[str]:
    cached, ts = _load_cached_proxies()
    cache_fresh = bool(cached) and (time.time() - ts) < PROXY_CACHE_TTL_S
    if cache_fresh:
        return cached
    fresh = _fetch_fresh_proxies()
    return fresh or cached


def _pick_proxy() -> str | None:
    proxies = _get_proxy_list()
    if not proxies:
        return None
    return random.choice(proxies) if len(proxies) > 1 else proxies[0]


def _extract_pixeldrain_id(href: str) -> str | None:
    """Pull a pixeldrain file ID out of any common URL shape.

    Supports:
      https://pixeldrain.com/u/<id>
      https://pixeldrain.com/api/file/<id>(/...)?
      https://pixeldra.in/u/<id>
      raw <id>
    Returns None for unsupported URL shapes (lists/dirs handled separately
    once we need them).
    """
    if not href:
        return None
    href = href.strip()

    # raw 8-12 char alphanumeric ID
    if re.fullmatch(r"[A-Za-z0-9]{6,16}", href):
        return href

    parsed = urlparse(href)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if "pixeldrain" not in host and "pixeldra.in" not in host:
        return None

    # /u/<id>
    m = re.match(r"^/u/([A-Za-z0-9]+)/?$", path)
    if m:
        return m.group(1)

    # /api/file/<id>...
    m = re.match(r"^/api/file/([A-Za-z0-9]+)", path)
    if m:
        return m.group(1)

    # /file/<id> (older share form)
    m = re.match(r"^/file/([A-Za-z0-9]+)", path)
    if m:
        return m.group(1)

    return None


def _stream_to_file(url: str, dest_dir: Path, fallback_name: str) -> Path | None:
    """Stream `url` to a file in `dest_dir`. Returns the saved Path or None."""
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": _UA, "Accept": "*/*"},
            follow_redirects=True,
            timeout=None,
        ) as resp:
            resp.raise_for_status()

            fname = fallback_name
            cd = resp.headers.get("content-disposition", "")
            if cd:
                m = re.search(r'filename\*?=(?:UTF-8\'\'\'?)?"?([^";]+)"?', cd, re.IGNORECASE)
                if m:
                    fname = m.group(1).strip()

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / fname

            total = int(resp.headers.get("content-length", 0))
            done = 0
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=524288):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = int(done / total * 100)
                        print(
                            f"\r  {pct}% ({done // 1048576}MB / {total // 1048576}MB)",
                            end="",
                            flush=True,
                        )
            print()
            return dest
    except httpx.HTTPStatusError as e:
        print(Fore.RED + f"  HTTP {e.response.status_code} from {url}" + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"  Stream failed: {e}" + Style.RESET_ALL)
    return None


def _validate_archive(path: Path) -> Path | None:
    """Confirm `path` looks like a real archive. Renames extension if mismatched.
    Returns the (possibly renamed) Path on success, None on failure."""
    try:
        with path.open("rb") as f:
            head = f.read(8)
    except Exception:
        return None

    real_ext = None
    for sig, ext in _MAGIC.items():
        if head.startswith(sig):
            real_ext = ext
            break
    if real_ext is None:
        return None

    if path.suffix.lower() != real_ext:
        new_path = path.with_suffix(real_ext)
        path.rename(new_path)
        return new_path
    return path


def download_pixeldrain(file_id: str, temp_dir: Path) -> Path | None:
    """Download a Pixeldrain file via the gamedrive proxy (with direct fallback).

    Strategy:
      1. Try every known proxy URL (`<proxy>/<file_id>`) in random order.
      2. If all proxies fail, fall back to the direct pixeldrain API.
      3. Validate magic bytes; if HTML/empty, open the source page in a browser
         and bail.
    """
    print(Fore.CYAN + f"Downloading from pixeldrain ({file_id}) via bypass..." + Style.RESET_ALL)

    proxies = _get_proxy_list()
    random.shuffle(proxies)

    fallback_name = f"{file_id}.bin"
    archive: Path | None = None

    for proxy in proxies:
        url = f"{proxy}{file_id}"
        print(Fore.CYAN + f"  proxy: {proxy}" + Style.RESET_ALL)
        archive = _stream_to_file(url, temp_dir, fallback_name)
        if archive and archive.exists() and archive.stat().st_size > 0:
            break
        if archive and archive.exists():
            archive.unlink(missing_ok=True)
        archive = None

    if archive is None:
        # Direct fallback — pixeldrain rate-limits but it's better than nothing.
        direct = f"https://pixeldrain.com/api/file/{file_id}?download"
        print(Fore.YELLOW + "  All proxies failed. Trying direct pixeldrain..." + Style.RESET_ALL)
        archive = _stream_to_file(direct, temp_dir, fallback_name)

    if archive is None or not archive.exists() or archive.stat().st_size == 0:
        print(
            Fore.RED
            + "Could not download from pixeldrain. Opening the share page in your browser."
            + Style.RESET_ALL
        )
        try:
            webbrowser.open(f"https://pixeldrain.com/u/{file_id}")
        except Exception:
            pass
        return None

    validated = _validate_archive(archive)
    if validated is None:
        print(
            Fore.RED
            + "Downloaded file isn't a valid archive (got HTML or junk). "
            + "Opening the share page in your browser."
            + Style.RESET_ALL
        )
        archive.unlink(missing_ok=True)
        try:
            webbrowser.open(f"https://pixeldrain.com/u/{file_id}")
        except Exception:
            pass
        return None

    return validated
