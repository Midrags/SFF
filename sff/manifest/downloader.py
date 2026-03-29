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
from sff.zip import read_nth_file_from_zip_bytes
from sff.steam_tools_compat import sync_manifest_to_config_depotcache

logger = logging.getLogger(__name__)


class ManifestDownloader:
    def __init__(self, provider: SteamInfoProvider, steam_path: Path):
        self.steam_path = steam_path
        self.provider = provider

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

    def _try_morrenus_generate(self, depot_id: str, manifest_id: str) -> Optional[bytes]:
        # Morrenus on-demand generation: first request generates, every request after is cached.
        # Daily limit: 1500 single manifests. Key stored in Settings.MORRENUS_KEY.
        api_key = get_setting(Settings.MORRENUS_KEY)
        if not api_key:
            return None
        url = f"https://manifest.morrenus.xyz/api/v1/generate/manifest?depot_id={depot_id}&manifest_id={manifest_id}"
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
                    + f"✅ Morrenus: got manifest for depot {depot_id}"
                    + Style.RESET_ALL
                )
                return resp.content
            if resp.status_code == 401:
                logger.debug("Morrenus: invalid or missing API key")
            elif resp.status_code == 429:
                print(Fore.YELLOW + "Morrenus: daily limit reached (1500/day)." + Style.RESET_ALL)
            elif resp.status_code == 404:
                logger.debug(f"Morrenus: depot {depot_id} manifest {manifest_id} not found")
            else:
                logger.debug(f"Morrenus returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.debug(f"Morrenus request failed: {e}")
        return None

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
        self, depot_id: str, manifest_id: str, cdn_client: Optional[CDNClient] = None
    ):
        # Morrenus on-demand: fastest when key is set (cached after first gen)
        morrenus_result = self._try_morrenus_generate(depot_id, manifest_id)
        if morrenus_result is not None:
            return morrenus_result

        mh_result = self._try_manifesthub(depot_id, manifest_id)
        if mh_result is not None:
            return mh_result

        if cdn_client is None:
            cdn_client = self.get_cdn_client()
        req_code = self.resolve_gmrc(manifest_id)
        cdn_server = cast(ContentServer, cdn_client.get_content_server())
        cdn_server_name = f"http{'s' if cdn_server.https else ''}://{cdn_server.host}"
        manifest_url = urljoin(
            cdn_server_name, f"depot/{depot_id}/manifest/{manifest_id}/5/{req_code}"
        )

        logger.debug(f"Download manifest from {manifest_url}")
        return get_request_raw(manifest_url)

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

            possible_saved_manifest = (
                Path.cwd() / f"manifests/{depot_id}_{manifest_id}.manifest"
            )
            depotcache = self.steam_path / "depotcache"
            depotcache.mkdir(exist_ok=True)
            final_manifest_loc = (
                depotcache / f"{depot_id}_{manifest_id}.manifest"
            )

            if possible_saved_manifest.exists():
                print("One of the endpoints had a manifest. Skipping download...")
                if not final_manifest_loc.exists():
                    shutil.move(possible_saved_manifest, final_manifest_loc)
                sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                continue
            manifest = self.download_single_manifest(depot_id, manifest_id, cdn)

            if manifest:
                if decrypt:
                    decrypt_and_save_manifest(manifest, final_manifest_loc, dec_key)
                else:
                    extracted = read_nth_file_from_zip_bytes(0, manifest)
                    if not extracted:
                        raise Exception("File isn't a ZIP. This shouldn't happen.")
                    with final_manifest_loc.open("wb") as f:
                        f.write(extracted.read())

                manifest_paths.append(final_manifest_loc)
                sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
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
                'decrypt': decrypt
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
            
            try:
                final_manifest_loc = depotcache / f"{depot_id}_{manifest_id}.manifest"
                
                if final_manifest_loc.exists():
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Already exists")
                
                possible_saved_manifest = Path.cwd() / f"manifests/{depot_id}_{manifest_id}.manifest"
                if possible_saved_manifest.exists():
                    shutil.move(possible_saved_manifest, final_manifest_loc)
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Moved from saved")
                
                manifest = self.download_single_manifest(depot_id, manifest_id, cdn)
                
                if manifest:
                    if decrypt_flag:
                        decrypt_and_save_manifest(manifest, final_manifest_loc, dec_key)
                    else:
                        extracted = read_nth_file_from_zip_bytes(0, manifest)
                        if not extracted:
                            return (False, depot_id, manifest_id, None, "Not a ZIP file")
                        with final_manifest_loc.open("wb") as f:
                            f.write(extracted.read())
                    sync_manifest_to_config_depotcache(self.steam_path, final_manifest_loc)
                    return (True, depot_id, manifest_id, final_manifest_loc, "Downloaded")
                else:
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
