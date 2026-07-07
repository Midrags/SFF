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
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import httpx
import gevent
from colorama import Fore, Style
from steam.client.cdn import CDNClient, ContentServer  # type: ignore
from tqdm import tqdm  # type: ignore

from sff.http_utils import (
    MANIFEST_REQUEST_CODE_HEADERS,
    get_gmrc,
    get_request_raw,
    parse_manifest_request_code,
)
from sff.manifest.manifesthub_key import get_manifesthub_api_key
from sff.manifest.crypto import decrypt_and_save_manifest
from sff.manifest.id_resolver import (
    IManifestStrategy,
    InnerDepotManifestStrategy,
    ManifestContext,
    ManifestIDResolver,
    ManualManifestStrategy,
    SharedDepotManifestStrategy,
    StandardManifestStrategy,
)
from sff.prompts import prompt_confirm, prompt_select, prompt_text
from sff.steam_client import SteamInfoProvider, get_product_info
from sff.storage.settings import get_setting
from sff.utils import manifests_staging_dir
from sff.structs import (  # type: ignore
    DepotManifestMap,
    LuaParsedInfo,
    ManifestGetModes,
    Settings,
)
from sff.zip import read_nth_file_from_zip_bytes, extract_manifests_from_zip_bytes

_GITHUB_MANIFEST_REPOS = (
    ("qwe213312/k25FCdfEOoEJ42S6", "qwe213312"),
    ("mejikuhibiniu1/k25FCdfEOoEJ42S6", "mejikuhibiniu1"),
    ("Sainan/k25FCdfEOoEJ42S6", "Sainan"),
)
from sff.steam_tools_compat import sync_manifest_to_config_depotcache
from typing import cast

logger = logging.getLogger(__name__)


class LocalManifestStrategy(IManifestStrategy):
    def __init__(self, downloader):
        self.downloader = downloader

    @property
    def name(self):
        return "Local manifest file"

    def get_manifest_id(self, ctx, depot_id):
        found = self.downloader._find_latest_local_manifest_id(str(depot_id))
        if found is None:
            return None
        manifest_id, path = found
        logger.debug(
            "Local manifest fallback picked %s for depot %s from %s",
            manifest_id,
            depot_id,
            path,
        )
        return manifest_id


class ManifestDownloader:
    def __init__(self, provider, steam_path, use_hubcap = False):
        self.steam_path = steam_path
        self.provider = provider
        self.use_hubcap = use_hubcap

    def _manifest_search_dirs(self):
        dirs = [
            manifests_staging_dir(),
            self.steam_path / "depotcache",
            self.steam_path / "config" / "depotcache",
        ]
        seen = set()
        out = []
        for directory in dirs:
            key = str(directory).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(directory)
        return out

    def _newest_existing(self, paths):
        existing = [p for p in paths if p.exists()]
        if not existing:
            return None

        def _mtime(path):
            try:
                return path.stat().st_mtime
            except OSError:
                return 0

        return max(existing, key=_mtime)

    def _find_exact_local_manifest(self, depot_id: str, manifest_id: str):
        name = f"{depot_id}_{manifest_id}.manifest"
        return self._newest_existing([directory / name for directory in self._manifest_search_dirs()])

    def _find_latest_local_manifest_id(self, depot_id: str):
        candidates = []
        for directory in self._manifest_search_dirs():
            if not directory.exists():
                continue
            for mf in directory.glob(f"{depot_id}_*.manifest"):
                parts = mf.stem.split("_", 1)
                if len(parts) == 2 and parts[0] == depot_id and parts[1].isdigit():
                    candidates.append((parts[1], mf))
        if not candidates:
            return None

        def _mtime(item):
            try:
                return item[1].stat().st_mtime
            except OSError:
                return 0

        return max(candidates, key=_mtime)

    def _copy_local_manifest_to_depotcache(self, source: Path, depot_id: str, manifest_id: str):
        depotcache = self.steam_path / "depotcache"
        depotcache.mkdir(parents=True, exist_ok=True)
        dest = depotcache / f"{depot_id}_{manifest_id}.manifest"
        if source.resolve() != dest.resolve():
            shutil.copy2(source, dest)
        sync_manifest_to_config_depotcache(self.steam_path, dest)
        return dest

    def _cleanup_live_stale_manifests(self, manifest_ids):
        removed = 0
        live_dirs = (self.steam_path / "depotcache", self.steam_path / "config" / "depotcache")
        for depot_id, correct_manifest_id in manifest_ids.items():
            if not depot_id or not correct_manifest_id:
                continue
            for directory in live_dirs:
                if not directory.exists():
                    continue
                for mf in directory.glob(f"{depot_id}_*.manifest"):
                    parts = mf.stem.split("_", 1)
                    if len(parts) != 2 or parts[1] == str(correct_manifest_id):
                        continue
                    try:
                        mf.unlink()
                        removed += 1
                        logger.debug("Removed stale live manifest: %s", mf)
                    except OSError:
                        pass
        if removed:
            print(
                Fore.YELLOW
                + f"Cleaned up {removed} stale same-depot manifest(s) from Steam depotcache."
                + Style.RESET_ALL
            )

    def _preseed_depotcache(self, manifest_ids=None):
        if not manifest_ids:
            logger.debug("Preseed skipped: no exact manifest map")
            return 0
        copied = 0
        for depot_id, manifest_id in manifest_ids.items():
            source = self._find_exact_local_manifest(str(depot_id), str(manifest_id))
            if source is None:
                continue
            self._copy_local_manifest_to_depotcache(source, str(depot_id), str(manifest_id))
            copied += 1
            logger.debug("Pre-seeded depotcache: %s_%s.manifest", depot_id, manifest_id)
        if copied:
            print(
                Fore.CYAN
                + f"Pre-seeded {copied} manifest(s) into depotcache."
                + Style.RESET_ALL
            )
        return copied

    def _write_manifest_to_depotcache(
        self, raw: bytes, depot_id: str, manifest_id: str, decrypt: bool = False, dec_key: str = ""
    ):
        # Write raw manifest bytes to depotcache and config/depotcache.
        # Handles both ZIP-wrapped (CDN) and raw (ManifestHub/GitHub) formats.
        depotcache = self.steam_path / "depotcache"
        depotcache.mkdir(exist_ok=True)
        dest = depotcache / f"{depot_id}_{manifest_id}.manifest"
        if decrypt and dec_key:
            decrypt_and_save_manifest(raw, dest, dec_key)
        else:
            extracted = read_nth_file_from_zip_bytes(0, raw)
            if extracted:
                # CDN response is ZIP-wrapped
                dest.write_bytes(extracted.read())
            else:
                # ManifestHub / GitHub already return raw manifest bytes
                dest.write_bytes(raw)
        if dest.exists():
            sync_manifest_to_config_depotcache(self.steam_path, dest)
            return dest
        return None

    def get_dlc_manifest_status(self, depot_ids):
        manifest_ids = {}
        while True:
            app_info = get_product_info(self.provider, depot_ids)  # type: ignore
            for depot_id in depot_ids:
                depots_dict = (
                    app_info.get("apps", {}).get(depot_id, {}).get("depots", {})
                )
                manifest = (
                    depots_dict.get(str(depot_id), {})
                    .get("manifests", {})
                    .get("public", {})
                    .get("gid")
                )
                if manifest is not None:
                    print(f"Depot {depot_id} has manifest {manifest}")
                manifest_file = (
                    self.steam_path / f"depotcache/{depot_id}_{manifest}.manifest"
                )
                manifest_ids[depot_id] = manifest_file.exists()
            break
        return manifest_ids

    def get_manifest_ids(
        self, lua: LuaParsedInfo, auto: bool = False
    ):
        manifest_ids = {}
        app_id = int(lua.app_id)
        if not auto:
            mode = prompt_select(
                "How would you like to obtain the manifest ID?",
                list(ManifestGetModes),
            )
            auto_fetch = mode == ManifestGetModes.AUTO
        else:
            auto_fetch = True
        main_app_data = {}
        if auto_fetch:
            main_app_data = self.provider.get_single_app_info(app_id)
        context = ManifestContext(
            app_id=app_id,
            app_data=main_app_data,
            provider=self.provider,
            auto=auto_fetch,
        )
        strats = []
        if auto_fetch:
            strats.append(StandardManifestStrategy())
            strats.append(SharedDepotManifestStrategy())
            strats.append(InnerDepotManifestStrategy())
            strats.append(LocalManifestStrategy(self))
        strats.append(ManualManifestStrategy())
        resolver = ManifestIDResolver(strats)
        use_pins = get_setting(Settings.USE_MANIFEST_PINS)
        pin_map = getattr(lua, "manifest_overrides", {}) or {}
        for pair in lua.depots:
            depot_id = str(pair.depot_id)
            if not pair.decryption_key:
                logger.debug(f"Skipping {depot_id} because it has no decryption key")
                continue
            if use_pins and depot_id in pin_map:
                pinned_gid = pin_map[depot_id]
                print(f"Depot {depot_id} using pinned manifest {pinned_gid} (Lua pin)")
                manifest_ids[depot_id] = pinned_gid
                continue
            manifest, strat = resolver.resolve(context, depot_id)
            if manifest == "":
                # Skip, probably because lua file had a base app ID
                # that also had a decryption key
                continue
            print(f"Depot {depot_id} has manifest {manifest} ({strat})")
            manifest_ids[depot_id] = manifest
        return DepotManifestMap(manifest_ids)

    def get_cdn_client(self, max_retries = 5):
        for attempt in range(max_retries):
            try:
                cdn = CDNClient(self.provider.client)
                return cdn
            except gevent.Timeout:
                if attempt < max_retries - 1:
                    print(f"CDN Client timed out. Retrying ({attempt + 1}/{max_retries})...")
                else:
                    raise RuntimeError("CDN Client timed out after maximum retries.") from None

    def _try_hubcap_generate(
        self, depot_id: str, manifest_id: str
    ):
        # Hubcap Manifest on-demand API: generates per-manifest, cached after first hit.
        # Limit: 1500/day. Returns raw manifest bytes (NOT zip-wrapped).
        api_key = get_setting(Settings.HUBCAP_KEY)
        if not api_key:
            return None
        url = (
            f"https://hubcapmanifest.com/api/v1/generate/manifest"
            f"?depot_id={depot_id}&manifest_id={manifest_id}"
        )
        try:
            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=60,
                follow_redirects=True,
            )
            if resp.status_code == 200 and resp.content:
                print(
                    Fore.GREEN
                    + f"[OK] Hubcap on-demand: got manifest for depot {depot_id}"
                    + Style.RESET_ALL
                )
                return resp.content
            if resp.status_code == 401:
                logger.debug("Hubcap on-demand: invalid or missing API key")
            elif resp.status_code == 429:
                print(Fore.YELLOW + "Hubcap: daily limit reached (1500/day)." + Style.RESET_ALL)
            elif resp.status_code == 404:
                logger.debug(
                    f"Hubcap: depot {depot_id} manifest {manifest_id} not found"
                )
            else:
                logger.debug(
                    f"Hubcap returned HTTP {resp.status_code}: {resp.text[:200]}"
                )
        except Exception as e:
            logger.debug(f"Hubcap request failed: {e}")
        return None

    def _try_github_manifest_direct(
        self, app_id: str, depot_id: str, manifest_id: str, target: Path
    ):
        for repo, label in _GITHUB_MANIFEST_REPOS:
            url = (
                f"https://raw.githubusercontent.com/{repo}"
                f"/main/{depot_id}_{manifest_id}.manifest"
            )
            try:
                resp = httpx.get(url, timeout=30, follow_redirects=True)
                if resp.status_code == 200 and resp.content:
                    target.write_bytes(resp.content)
                    print(
                        Fore.GREEN
                        + f"\u2705 GitHub mirror ({label}): got manifest for depot {depot_id}"
                        + Style.RESET_ALL
                    )
                    return True
                if resp.status_code == 404:
                    continue
                logger.debug(f"GitHub mirror ({label}) returned HTTP {resp.status_code} for depot {depot_id}")
            except Exception as e:
                logger.debug(f"GitHub mirror ({label}) download failed for depot {depot_id}: {e}")
        return False

    def _try_github_manifest_bytes(
        self, app_id: str, depot_id: str, manifest_id: str
    ):
        for repo, label in _GITHUB_MANIFEST_REPOS:
            url = (
                f"https://raw.githubusercontent.com/{repo}"
                f"/main/{depot_id}_{manifest_id}.manifest"
            )
            try:
                resp = httpx.get(url, timeout=30, follow_redirects=True)
                if resp.status_code == 200 and resp.content:
                    print(
                        Fore.GREEN
                        + f"\u2705 GitHub mirror ({label}): got manifest for depot {depot_id}"
                        + Style.RESET_ALL
                    )
                    return resp.content
                if resp.status_code == 404:
                    continue
                logger.debug(f"GitHub mirror ({label}) returned HTTP {resp.status_code} for depot {depot_id}")
            except Exception as e:
                logger.debug(f"GitHub mirror ({label}) fetch failed for depot {depot_id}: {e}")
        return None

    def _try_manifesthub_combined(
        self, depot_id: str, manifest_id: str, app_id: str
    ):
        """
        Fire ManifestHub API and GitHub mirror simultaneously.
        Returns the data from whichever endpoint finishes fastest and succeeds.
        """
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(self._try_manifesthub, depot_id, manifest_id): "API",
                pool.submit(self._try_github_manifest_bytes, app_id, depot_id, manifest_id): "GitHub"
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    if result is not None:
                        logger.debug(f"Depot {depot_id}: {name} returned manifest {manifest_id} fastest.")
                        # cancel the other one (though ThreadPoolExecutor doesn't strictly cancel running threads,
                        # python futures will be marked to not execute if they haven't started)
                        for f in futures:
                            f.cancel()
                        return result
                except Exception as e:
                    logger.debug(f"{name} failed in _try_manifesthub_combined: {e}")
        return None

    def _try_mirror_endpoints(self, depot_id, manifest_id):
        """Hit the 3 GMRC mirrors to get a request code, then download
        from Steam's fixed CDN (steampipe.akamaized.net). HTTPS first,
        HTTP last. No Steam CDN client needed, the code works directly.
        """
        _MIRROR_URLS = (
            (f"https://manifest.opensteamtool.com/{manifest_id}", "manifest.opensteamtool.com"),
            (f"https://manifest.steam.run/api/manifest/{manifest_id}", "steam.run"),
            (f"http://gmrc.wudrm.com/manifest/{manifest_id}", "wudrm"),
        )
        for url, label in _MIRROR_URLS:
            try:
                resp = httpx.get(
                    url,
                    headers=MANIFEST_REQUEST_CODE_HEADERS,
                    timeout=12,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    req_code = parse_manifest_request_code(resp.text)
                else:
                    req_code = None
                if req_code is not None:
                    logger.debug(f"Mirror {label} returned request code for manifest {manifest_id}")
                    cdn_url = f"http://steampipe.akamaized.net/depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
                    result = get_request_raw(cdn_url)
                    if result is None:
                        cdn_url_https = f"https://steampipe.akamaized.net/depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
                        result = get_request_raw(cdn_url_https)
                    if result is not None:
                        logger.debug(f"Mirror {label} download succeeded for depot {depot_id}")
                        return result
                logger.debug(
                    f"Mirror {label} had no usable request code "
                    f"(HTTP {getattr(resp, 'status_code', 'unknown')})"
                )
            except Exception as e:
                logger.debug(f"Mirror {label} request failed: {e}")
        return None

    def _try_manifesthub(self, depot_id, manifest_id):
        # Hits the ManifestHub API; key is auto-fetched and renewed as needed.
        api_key = get_manifesthub_api_key()
        if not api_key:
            return None
        url = (
            f"https://api.manifesthub1.filegear-sg.me/manifest"
            f"?apikey={api_key}&depotid={depot_id}&manifestid={manifest_id}"
        )
        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            if resp.status_code == 200 and resp.content:
                print(
                    Fore.GREEN
                    + f"[OK] ManifestHub: got manifest for depot {depot_id}"
                    + Style.RESET_ALL
                )
                return resp.content
            if resp.status_code == 403:
                print(
                    Fore.YELLOW
                    + "ManifestHub: API key expired or invalid (keys last 24h)."
                      " Renew at https://manifesthub1.filegear-sg.me — update in SFF Settings."
                    + Style.RESET_ALL
                )
            elif resp.status_code == 404:
                logger.debug(f"ManifestHub: depot {depot_id} manifest {manifest_id} not cached")
            else:
                logger.debug(f"ManifestHub returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.debug(f"ManifestHub request failed: {e}")
        return None

    def download_single_manifest(
        self,
        depot_id: str,
        manifest_id: str,
        cdn_client = None,
        app_id = "",
    ):
        if self.use_hubcap:
            # Hubcap path: Hubcap → ManifestHub API → CDN (interactive)
            hubcap_result = self._try_hubcap_generate(depot_id, manifest_id)
            if hubcap_result is not None:
                return hubcap_result
            mh_result = self._try_manifesthub(depot_id, manifest_id)
            if mh_result is not None:
                return mh_result
            # CDN is dead, skip resolve_gmrc + CDN download.
            # ManifestHub already tried above, fall through to GitHub.
            logger.debug(f"Hubcap path for depot {depot_id}: all sources failed")
            return None
        # oureveryday path ─────────────────────────────────────────────────────
        # Step 1: Try the 3 GMRC mirrors
        #          directly. Each returns a request code; we pull the manifest
        #          from Steam CDN with it. HTTPS before HTTP.
        # Step 2: Fall back to the 3 GitHub raw mirror repos.
        # Step 3: ManifestHub API (auto-prompts for key if none cached).
        # Step 4: Encrypted GMRC endpoint + CDN (last resort).
        # Step 1: Hit the 3 mirror endpoints
        #          to get a request code and download from steampipe CDN.
        mirror_result = self._try_mirror_endpoints(depot_id, manifest_id)
        if mirror_result is not None:
            return mirror_result
        # Step 2: Try all 3 GitHub raw manifest mirrors in sequence.
        #          Each hosts the same k25FCdfEOoEJ42S6 manifest set.
        try:
            gh_result = self._try_github_manifest_bytes(app_id, depot_id, manifest_id)
            if gh_result is not None:
                return gh_result
        except Exception as e:
            logger.debug("oureveryday github fallback failed: %s", e)
        # Step 3: Try ManifestHub API. Returns None silently if no key
        #          is set so we fall through to the last step.
        mh_result = self._try_manifesthub(depot_id, manifest_id)
        if mh_result is not None:
            return mh_result
        # Step 4: Last resort — encrypted GMRC endpoint for a request
        #          code, then download from steampipe CDN.
        req_code = asyncio.run(get_gmrc(manifest_id, silent=True))
        if req_code is not None:
            pipe_url = f"http://steampipe.akamaized.net/depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
            result = get_request_raw(pipe_url)
            if result is not None:
                return result
        return None

    def resolve_gmrc(self, manifest_id):
        while True:
            req_code = asyncio.run(get_gmrc(manifest_id))
            if req_code is not None:
                print(f"Request code is: {req_code}")
                break
            if prompt_confirm(
                "Request code endpoint died. Would you like to try again?",
                false_msg="No (Manually input request code)",
            ):
                continue
            req_code = prompt_text(
                "Paste the Manifest Request Code here:",
                validator=lambda x: x.isdigit(),
            )
            break
        return req_code

    def download_workshop_item(self, app_id, ugc_id):
        manifest = self.download_single_manifest(app_id, ugc_id)
        if manifest:
            extracted = read_nth_file_from_zip_bytes(0, manifest)
            if not extracted:
                raise Exception("File isn't a ZIP. This shouldn't happen.")
            depotcache = self.steam_path / "depotcache"
            depotcache.mkdir(exist_ok=True)
            final_manifest_loc = (
                depotcache / f"{app_id}_{ugc_id}.manifest"
            )
            with final_manifest_loc.open("wb") as f:
                f.write(extracted.read())

    def download_manifests(
        self, lua: LuaParsedInfo, decrypt: bool = False, auto_manifest: bool = False,
        manifest_override: dict = None
    ):
        if manifest_override is not None:
            manifest_ids = DepotManifestMap(manifest_override)
        else:
            manifest_ids = self.get_manifest_ids(lua, auto_manifest)
        self._preseed_depotcache(manifest_ids)
        self._cleanup_live_stale_manifests(manifest_ids)
        # Build dec_key lookup from lua.depots (used when manifest_override bypasses the normal loop).
        dec_key_map = {pair.depot_id: pair.decryption_key for pair in lua.depots if pair.decryption_key}
        # Determine which (depot_id, manifest_id, dec_key) triples to process.
        # When manifest_override is provided, iterate it directly so that ALL user-selected
        # manifests are attempted — even depots whose Lua entry has dec_key=="" (which the
        # normal loop would silently skip).  In that case, key lookup falls back to "".
        if manifest_override is not None:
            loop_items = [
                (depot_id, manifest_id, dec_key_map.get(depot_id, ""))
                for depot_id, manifest_id in manifest_override.items()
            ]
        else:
            loop_items = [
                (pair.depot_id, manifest_ids.get(pair.depot_id), pair.decryption_key)
                for pair in lua.depots
                if pair.decryption_key != "" and manifest_ids.get(pair.depot_id) is not None
            ]
        manifest_paths = []
        for depot_id, manifest_id, dec_key in loop_items:
            if manifest_id is None:
                continue
            print(
                Fore.CYAN
                + f"\nDepot {depot_id} - Manifest {manifest_id}"
                + Style.RESET_ALL
            )
            depotcache = self.steam_path / "depotcache"
            depotcache.mkdir(parents=True, exist_ok=True)
            final_manifest_loc = depotcache / f"{depot_id}_{manifest_id}.manifest"
            local_manifest = self._find_exact_local_manifest(str(depot_id), str(manifest_id))
            if local_manifest is not None:
                written = self._copy_local_manifest_to_depotcache(
                    local_manifest, str(depot_id), str(manifest_id)
                )
                if local_manifest == final_manifest_loc:
                    print(Fore.GREEN + f"  Already in depotcache: {final_manifest_loc.name}" + Style.RESET_ALL)
                else:
                    print(Fore.GREEN + f"  Refreshed from local manifest: {local_manifest.name}" + Style.RESET_ALL)
                manifest_paths.append(written)
                continue
            # Fetch from network (Morrenus on-demand → ManifestHub → CDN)
            manifest = self.download_single_manifest(
                depot_id, manifest_id, app_id=lua.app_id
            )
            if manifest:
                # Write to depotcache using the unified helper (handles ZIP + raw)
                written = self._write_manifest_to_depotcache(
                    manifest, depot_id, manifest_id, decrypt, dec_key
                )
                if written:
                    manifest_paths.append(written)
                continue
        return manifest_paths

    def download_manifests_parallel(
        self, lua: LuaParsedInfo, decrypt: bool = False, auto_manifest: bool = False,
        manifest_override: dict = None
    ):
        import time
        start_time = time.time()
        worker_count_str = get_setting(Settings.PARALLEL_DOWNLOADS)
        try:
            worker_count = int(worker_count_str) if worker_count_str else 4
            worker_count = max(1, min(worker_count, 10))  # Clamp between 1-10
        except (ValueError, TypeError):
            worker_count = 4
        if manifest_override is not None:
            manifest_ids = DepotManifestMap(manifest_override)
        else:
            manifest_ids = self.get_manifest_ids(lua, auto_manifest)
        self._preseed_depotcache(manifest_ids)
        self._cleanup_live_stale_manifests(manifest_ids)
        # Build dec_key lookup from lua.depots (see download_manifests for explanation).
        dec_key_map_p = {pair.depot_id: pair.decryption_key for pair in lua.depots if pair.decryption_key}
        download_tasks = []
        if manifest_override is not None:
            # Iterate override directly — do NOT skip depots with empty keys.
            for depot_id, manifest_id in manifest_override.items():
                download_tasks.append({
                    'depot_id': depot_id,
                    'manifest_id': manifest_id,
                    'dec_key': dec_key_map_p.get(depot_id, ""),
                    'decrypt': decrypt,
                    'app_id': lua.app_id,
                })
        else:
            for pair in lua.depots:
                depot_id = pair.depot_id
                dec_key = pair.decryption_key
                if dec_key == "":
                    logger.debug(f"Skipping {depot_id} because it's not a depot")
                    continue
                manifest_id = manifest_ids.get(depot_id)
                if manifest_id is None:
                    continue
                download_tasks.append({
                    'depot_id': depot_id,
                    'manifest_id': manifest_id,
                    'dec_key': dec_key,
                    'decrypt': decrypt,
                    'app_id': lua.app_id,
                })
        if not download_tasks:
            print(Fore.YELLOW + "No manifests to download" + Style.RESET_ALL)
            return []
        print(Fore.CYAN + f"\nDownloading {len(download_tasks)} manifests with {worker_count} workers..." + Style.RESET_ALL)
        manifest_paths = []
        depotcache = self.steam_path / "depotcache"
        depotcache.mkdir(parents=True, exist_ok=True)
        def download_task(task):
            depot_id = task['depot_id']
            manifest_id = task['manifest_id']
            dec_key = task['dec_key']
            decrypt_flag = task['decrypt']
            app_id = task.get('app_id', '')
            try:
                final_manifest_loc = depotcache / f"{depot_id}_{manifest_id}.manifest"
                local_manifest = self._find_exact_local_manifest(str(depot_id), str(manifest_id))
                if local_manifest is not None:
                    written = self._copy_local_manifest_to_depotcache(
                        local_manifest, str(depot_id), str(manifest_id)
                    )
                    if local_manifest == final_manifest_loc:
                        return (True, depot_id, manifest_id, written, "Already exists")
                    return (True, depot_id, manifest_id, written, "Refreshed from local")
                if final_manifest_loc.exists():
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Already exists")
                # Steps 1-4 for oureveryday (silent), or full Morrenus chain
                manifest = self.download_single_manifest(
                    depot_id, manifest_id, app_id=app_id
                )
                if manifest:
                    if decrypt_flag:
                        decrypt_and_save_manifest(manifest, final_manifest_loc, dec_key)
                    else:
                        extracted = read_nth_file_from_zip_bytes(0, manifest)
                        if extracted:
                            with final_manifest_loc.open("wb") as f:
                                f.write(extracted.read())
                        else:
                            # ManifestHub (API or GitHub) returns raw bytes, not ZIP-wrapped
                            final_manifest_loc.write_bytes(manifest)
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Downloaded")
                # Step 5 (interactive CDN) cannot run in parallel mode; report failure
                return (False, depot_id, manifest_id, None, "Download failed")
            except Exception as e:
                logger.error(f"Error downloading {depot_id}_{manifest_id}: {e}", exc_info=True)
                return (False, depot_id, manifest_id, None, str(e))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(download_task, task): task for task in download_tasks}
            with tqdm(total=len(download_tasks), desc="Downloading", unit="manifest") as pbar:
                for future in as_completed(futures):
                    success, depot_id, manifest_id, path, status = future.result()
                    if success:
                        print(Fore.GREEN + f"✓ Depot {depot_id} - Manifest {manifest_id}: {status}" + Style.RESET_ALL)
                        if path:
                            manifest_paths.append(path)
                    else:
                        print(Fore.RED + f"✗ Depot {depot_id} - Manifest {manifest_id}: {status}" + Style.RESET_ALL)
                    pbar.update(1)
        elapsed = time.time() - start_time
        print(Fore.CYAN + f"\nCompleted {len(manifest_paths)}/{len(download_tasks)} downloads in {elapsed:.2f}s" + Style.RESET_ALL)
        return manifest_paths
