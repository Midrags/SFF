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
from typing import Any, Optional, cast
from urllib.parse import urljoin

import httpx
import gevent
from colorama import Fore, Style
from steam.client.cdn import CDNClient, ContentServer  # type: ignore
from tqdm import tqdm  # type: ignore

from sff.http_utils import get_gmrc, get_request_raw
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
from sff.structs import (  # type: ignore
    DepotManifestMap,
    LuaParsedInfo,
    ManifestGetModes,
    Settings,
)
from sff.zip import read_nth_file_from_zip_bytes, extract_manifests_from_zip_bytes
from sff.steam_tools_compat import sync_manifest_to_config_depotcache

logger = logging.getLogger(__name__)


class ManifestDownloader:
    def __init__(self, provider: SteamInfoProvider, steam_path: Path, use_hubcap: bool = False):
        self.steam_path = steam_path
        self.provider = provider
        self.use_hubcap = use_hubcap

    def _preseed_depotcache(self) -> int:
        # Copy everything from ./manifests/ into depotcache now so Steam
        # finds them locally and never needs a network call.
        manifests_dir = Path.cwd() / "manifests"
        if not manifests_dir.exists():
            return 0
        depotcache = self.steam_path / "depotcache"
        depotcache.mkdir(exist_ok=True)
        copied = 0
        for mf in manifests_dir.glob("*.manifest"):
            dest = depotcache / mf.name
            shutil.copy2(mf, dest)
            sync_manifest_to_config_depotcache(self.steam_path, dest)
            copied += 1
            logger.debug("Pre-seeded depotcache: %s", mf.name)
        if copied:
            print(
                Fore.CYAN
                + f"Pre-seeded {copied} manifest(s) into depotcache."
                + Style.RESET_ALL
            )
        return copied

    def _write_manifest_to_depotcache(
        self, raw: bytes, depot_id: str, manifest_id: str, decrypt: bool = False, dec_key: str = ""
    ) -> Optional[Path]:
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

    def get_dlc_manifest_status(self, depot_ids: list[int]):
        manifest_ids: dict[int, bool] = {}

        while True:
            app_info = get_product_info(self.provider, depot_ids)  # type: ignore
            for depot_id in depot_ids:
                depots_dict: dict[str, Any] = (
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
    ) -> DepotManifestMap:
        manifest_ids: dict[str, str] = {}
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

        strats: list[IManifestStrategy] = []

        if auto_fetch:
            strats.append(StandardManifestStrategy())
            strats.append(SharedDepotManifestStrategy())
            strats.append(InnerDepotManifestStrategy())
        strats.append(ManualManifestStrategy())

        resolver = ManifestIDResolver(strats)

        for pair in lua.depots:
            depot_id = str(pair.depot_id)

            if not pair.decryption_key:
                logger.debug(f"Skipping {depot_id} because it has no decryption key")
                continue

            manifest, strat = resolver.resolve(context, depot_id)
            if manifest == "":
                # Skip, probably because lua file had a base app ID
                # that also had a decryption key
                continue
            print(f"Depot {depot_id} has manifest {manifest} ({strat})")
            manifest_ids[depot_id] = manifest

        return DepotManifestMap(manifest_ids)

    def get_cdn_client(self, max_retries: int = 5):
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
    ) -> Optional[bytes]:
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
                    + f"✅ Hubcap on-demand: got manifest for depot {depot_id}"
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
    ) -> bool:
        url = (
            f"https://raw.githubusercontent.com/qwe213312/k25FCdfEOoEJ42S6"
            f"/main/{depot_id}_{manifest_id}.manifest"
        )
        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            if resp.status_code == 200 and resp.content:
                target.write_bytes(resp.content)
                print(
                    Fore.GREEN
                    + f"\u2705 GitHub mirror: got manifest for depot {depot_id}"
                    + Style.RESET_ALL
                )
                return True
            if resp.status_code == 404:
                logger.debug(f"GitHub mirror: manifest not found for depot {depot_id}")
            else:
                logger.debug(f"GitHub mirror returned HTTP {resp.status_code} for depot {depot_id}")
        except Exception as e:
            logger.debug(f"GitHub mirror download failed for depot {depot_id}: {e}")
        return False

    def _try_github_manifest_bytes(
        self, app_id: str, depot_id: str, manifest_id: str
    ) -> Optional[bytes]:
        url = (
            f"https://raw.githubusercontent.com/qwe213312/k25FCdfEOoEJ42S6"
            f"/main/{depot_id}_{manifest_id}.manifest"
        )
        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            if resp.status_code == 200 and resp.content:
                print(
                    Fore.GREEN
                    + f"\u2705 GitHub mirror: got manifest for depot {depot_id}"
                    + Style.RESET_ALL
                )
                return resp.content
            if resp.status_code == 404:
                logger.debug(f"GitHub mirror: manifest not found for depot {depot_id}")
            else:
                logger.debug(f"GitHub mirror returned HTTP {resp.status_code} for depot {depot_id}")
        except Exception as e:
            logger.debug(f"GitHub mirror fetch failed for depot {depot_id}: {e}")
        return None

    def _try_manifesthub_combined(
        self, depot_id: str, manifest_id: str, app_id: str
    ) -> Optional[bytes]:
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

    def _log_mirror_coverage(
        self, app_id: str, depot_manifest_pairs: list[tuple[str, str]]
    ) -> int:
        """
        Queries GitHub API for the mirror repo and counts how many of the needed
        {depot_id}_{manifest_id}.manifest files it has. Purely informational.
        """
        needed = {f"{d}_{m}.manifest" for d, m in depot_manifest_pairs}
        try:
            resp = httpx.get(
                "https://api.github.com/repos/qwe213312/k25FCdfEOoEJ42S6/git/trees/main?recursive=1",
                timeout=15,
                headers={"Accept": "application/vnd.github.v3+json"},
                follow_redirects=True,
            )
            if resp.status_code == 200:
                files = {item["path"] for item in resp.json().get("tree", []) if item.get("type") == "blob"}
                count = len(needed & files)
                print(
                    Fore.CYAN
                    + f"GitHub mirror coverage: {count}/{len(needed)} manifests available"
                    + Style.RESET_ALL
                )
                return count
            logger.debug(f"GitHub mirror API returned HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"GitHub mirror coverage check failed: {e}")
        return 0

    def _try_manifesthub(self, depot_id: str, manifest_id: str) -> Optional[bytes]:
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
                    + f"✅ ManifestHub: got manifest for depot {depot_id}"
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
        cdn_client: Optional[CDNClient] = None,
        app_id: str = "",
    ):
        if cdn_client is None:
            cdn_client = self.get_cdn_client()

        if self.use_hubcap:
            # Hubcap path: Hubcap → ManifestHub API → CDN (interactive)
            hubcap_result = self._try_hubcap_generate(depot_id, manifest_id)
            if hubcap_result is not None:
                return hubcap_result
            mh_result = self._try_manifesthub(depot_id, manifest_id)
            if mh_result is not None:
                return mh_result
            req_code = self.resolve_gmrc(manifest_id)
            if req_code is None:
                return None
            cdn_server = cast(ContentServer, cdn_client.get_content_server())
            cdn_server_name = f"http{'s' if cdn_server.https else ''}://{cdn_server.host}"
            manifest_url = urljoin(
                cdn_server_name, f"depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
            )
            logger.debug(f"Download manifest from {manifest_url}")
            return get_request_raw(manifest_url)

        # oureveryday path ─────────────────────────────────────────────────────
        # Step 1: clearnet endpoint only (no Tor yet — ManifestHub runs next)
        req_code = asyncio.run(get_gmrc(manifest_id, silent=True, try_tor=False))
        if req_code is not None:
            cdn_server = cast(ContentServer, cdn_client.get_content_server())
            cdn_server_name = f"http{'s' if cdn_server.https else ''}://{cdn_server.host}"
            manifest_url = urljoin(
                cdn_server_name, f"depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
            )
            logger.debug(f"Download manifest from {manifest_url}")
            result = get_request_raw(manifest_url)
            if result is not None:
                return result

        # Step 2: ManifestHub API + GitHub simultaneously (API preferred)
        if app_id:
            mh_result = self._try_manifesthub_combined(depot_id, manifest_id, app_id)
        else:
            mh_result = self._try_manifesthub(depot_id, manifest_id)
        if mh_result is not None:
            return mh_result

        # Step 3: Tor SOCKS5 (only tried after ManifestHub fully fails)
        req_code = asyncio.run(get_gmrc(manifest_id, silent=True))
        if req_code is not None:
            cdn_server = cast(ContentServer, cdn_client.get_content_server())
            cdn_server_name = f"http{'s' if cdn_server.https else ''}://{cdn_server.host}"
            manifest_url = urljoin(
                cdn_server_name, f"depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
            )
            logger.debug(f"Download manifest from {manifest_url}")
            result = get_request_raw(manifest_url)
            if result is not None:
                return result

        # Step 4 (interactive CDN) handled by the caller
        return None

    def resolve_gmrc(self, manifest_id: str):
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

    def download_workshop_item(self, app_id: str, ugc_id: str):
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
        self, lua: LuaParsedInfo, decrypt: bool = False, auto_manifest: bool = False
    ):
        cdn = self.get_cdn_client()
        manifest_ids = self.get_manifest_ids(lua, auto_manifest)

        # Pre-seed depotcache from ./manifests/ so Steam finds them locally
        self._preseed_depotcache()

        if not self.use_hubcap and lua.app_id:
            pairs = [(d, m) for d, m in manifest_ids.items() if m]
            if pairs:
                self._log_mirror_coverage(lua.app_id, pairs)

        manifest_paths: list[Path] = []
        for pair in lua.depots:
            depot_id = pair.depot_id
            dec_key = pair.decryption_key
            if dec_key == "":
                logger.debug(f"Skipping {depot_id} because it's not a depot")
                continue
            manifest_id = manifest_ids.get(depot_id)
            if manifest_id is None:
                continue
            print(
                Fore.CYAN
                + f"\nDepot {depot_id} - Manifest {manifest_id}"
                + Style.RESET_ALL
            )

            depotcache = self.steam_path / "depotcache"
            depotcache.mkdir(exist_ok=True)
            final_manifest_loc = depotcache / f"{depot_id}_{manifest_id}.manifest"
            possible_saved_manifest = Path.cwd() / f"manifests/{depot_id}_{manifest_id}.manifest"

            # If saved manifest exists (from Morrenus ZIP), refresh depotcache
            if possible_saved_manifest.exists():
                shutil.copy2(str(possible_saved_manifest), final_manifest_loc)
                print(Fore.GREEN + f"  Refreshed from saved manifests: {possible_saved_manifest.name}" + Style.RESET_ALL)
                sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                manifest_paths.append(final_manifest_loc)
                continue

            # Already in depotcache and no fresher copy available
            if final_manifest_loc.exists():
                print(Fore.GREEN + f"  Already in depotcache: {final_manifest_loc.name}" + Style.RESET_ALL)
                sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                manifest_paths.append(final_manifest_loc)
                continue

            # Fetch from network (Morrenus on-demand → ManifestHub → CDN)
            manifest = self.download_single_manifest(
                depot_id, manifest_id, cdn, app_id=lua.app_id
            )

            if manifest:
                # Write to depotcache using the unified helper (handles ZIP + raw)
                written = self._write_manifest_to_depotcache(
                    manifest, depot_id, manifest_id, decrypt, dec_key
                )
                if written:
                    manifest_paths.append(written)
                continue

            if not self.use_hubcap:
                # Last resort: ask user for request code interactively
                print(
                    Fore.YELLOW
                    + f"\nAll automated sources failed for depot {depot_id}. Trying interactive CDN..."
                    + Style.RESET_ALL
                )
                req_code = self.resolve_gmrc(manifest_id)
                if req_code is not None:
                    cdn_server = cast(ContentServer, cdn.get_content_server())
                    cdn_server_name = f"http{'s' if cdn_server.https else ''}://{cdn_server.host}"
                    manifest_url = urljoin(
                        cdn_server_name,
                        f"depot/{depot_id}/manifest/{manifest_id}/5/{req_code}",
                    )
                    last_resort = get_request_raw(manifest_url)
                    if last_resort:
                        written = self._write_manifest_to_depotcache(
                            last_resort, depot_id, manifest_id, decrypt, dec_key
                        )
                        if written:
                            manifest_paths.append(written)

        return manifest_paths
    
    def download_manifests_parallel(
        self, lua: LuaParsedInfo, decrypt: bool = False, auto_manifest: bool = False
    ):
        import time
        start_time = time.time()
        
        worker_count_str = get_setting(Settings.PARALLEL_DOWNLOADS)
        try:
            worker_count = int(worker_count_str) if worker_count_str else 4
            worker_count = max(1, min(worker_count, 10))  # Clamp between 1-10
        except (ValueError, TypeError):
            worker_count = 4
        
        cdn = self.get_cdn_client()
        manifest_ids = self.get_manifest_ids(lua, auto_manifest)

        if not self.use_hubcap and lua.app_id:
            pairs = [(d, m) for d, m in manifest_ids.items() if m]
            if pairs:
                self._log_mirror_coverage(lua.app_id, pairs)
        
        download_tasks = []
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
        
        manifest_paths: list[Path] = []
        depotcache = self.steam_path / "depotcache"
        depotcache.mkdir(exist_ok=True)
        
        def download_task(task):
            depot_id = task['depot_id']
            manifest_id = task['manifest_id']
            dec_key = task['dec_key']
            decrypt_flag = task['decrypt']
            app_id = task.get('app_id', '')
            
            try:
                final_manifest_loc = depotcache / f"{depot_id}_{manifest_id}.manifest"
                
                # Prefer saved manifest (from Morrenus ZIP) over stale depotcache
                possible_saved_manifest = Path.cwd() / f"manifests/{depot_id}_{manifest_id}.manifest"
                if possible_saved_manifest.exists():
                    shutil.copy2(possible_saved_manifest, final_manifest_loc)
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Refreshed from saved")

                if final_manifest_loc.exists():
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Already exists")

                # Steps 1-4 for oureveryday (silent), or full Morrenus chain
                manifest = self.download_single_manifest(
                    depot_id, manifest_id, cdn, app_id=app_id
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
