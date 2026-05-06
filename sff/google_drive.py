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

import io
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_PATH = Path(os.environ.get("APPDATA", "~")) / "SteaMidra" / "gdrive_token.json"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _client_config():
    try:
        from sff._gc import get_ci, get_cs
        return {
            "installed": {
                "client_id": get_ci(),
                "client_secret": get_cs(),
                "auth_uri": _AUTH_URI,
                "token_uri": _TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        }
    except ImportError:
        return None


def is_available():
    try:
        import google.auth  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
        return _client_config() is not None
    except ImportError:
        return False


def is_authenticated():
    if not _TOKEN_PATH.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
        return creds is not None and creds.refresh_token is not None
    except Exception:
        return False


def get_user_email(service):
    try:
        info = service.about().get(fields="user").execute()
        return info.get("user", {}).get("emailAddress", "")
    except Exception:
        return ""


def authorize(log_func=None):
    if is_authenticated():
        if log_func:
            log_func("[OK] Google Drive already connected.")
        return True
    cfg = _client_config()
    if cfg is None:
        if log_func:
            log_func("[!] Google Drive not available in this build.")
        return False
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_config(cfg, _SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, prompt="consent")
        _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        if log_func:
            log_func("[OK] Google Drive connected.")
        return True
    except Exception as e:
        if log_func:
            log_func(f"[FAIL] Google Drive auth failed: {e}")
        return False


def get_service():
    cfg = _client_config()
    if cfg is None:
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not _TOKEN_PATH.exists():
            return None

        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            else:
                return None

        return build("drive", "v3", credentials=creds)
    except Exception as e:
        logger.warning("GDrive get_service failed: %s", e)
        return None


def find_folder(service, name, parent_id="root"):
    escaped = name.replace("'", "\\'")
    q = f"name='{escaped}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    try:
        res = service.files().list(q=q, fields="files(id,name)", pageSize=10).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None
    except Exception as e:
        logger.warning("GDrive find_folder '%s': %s", name, e)
        return None


def get_or_create_folder(service, name, parent_id="root"):
    fid = find_folder(service, name, parent_id)
    if fid:
        return fid
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    import time
    for attempt in range(4):
        try:
            f = service.files().create(body=meta, fields="id").execute()
            return f["id"]
        except Exception as e:
            try:
                from googleapiclient.errors import HttpError
                if isinstance(e, HttpError):
                    if e.resp.status == 409:
                        return find_folder(service, name, parent_id)
                    if e.resp.status == 429:
                        time.sleep(2 ** attempt)
                        continue
            except ImportError:
                pass
            logger.error("GDrive create_folder '%s': %s", name, e)
            return None
    return None


def _list_folder_index(service, parent_id):
    """Return {name: (file_id, size)} for all non-trashed files in a Drive folder."""
    index = {}
    page_token = None
    while True:
        try:
            params = {
                "q": f"'{parent_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
                "fields": "nextPageToken,files(id,name,size)",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            res = service.files().list(**params).execute()
            for f in res.get("files", []):
                index[f["name"]] = (f["id"], int(f.get("size", -1)))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        except Exception as e:
            logger.warning("GDrive _list_folder_index %s: %s", parent_id, e)
            break
    return index


def _upload_file_smart(service, local_path, parent_id, existing_index, log_func=None):
    """Upload a single file using smart sync: skip if same size, update if changed, create if new."""
    from googleapiclient.http import MediaFileUpload
    local_path = Path(local_path)
    if not local_path.exists():
        return False
    name = local_path.name
    local_size = local_path.stat().st_size
    existing = existing_index.get(name)
    if existing and existing[1] == local_size:
        if log_func:
            log_func(f"  Skipped (unchanged): {name}")
        return True
    import time as _time
    for _attempt in range(4):
        try:
            media = MediaFileUpload(str(local_path), resumable=False)
            if existing:
                fid = existing[0]
                service.files().update(fileId=fid, media_body=media).execute()
                if log_func:
                    log_func(f"  Updated: {name}")
            else:
                meta = {"name": name, "parents": [parent_id]}
                service.files().create(body=meta, media_body=media, fields="id").execute()
                if log_func:
                    log_func(f"  Uploaded: {name}")
            return True
        except Exception as e:
            try:
                from googleapiclient.errors import HttpError
                if isinstance(e, HttpError) and e.resp.status == 429:
                    _time.sleep(2 ** _attempt)
                    continue
            except ImportError:
                pass
            if log_func:
                log_func(f"  [FAIL] {name}: {e}")
            return False
    if log_func:
        log_func(f"  [FAIL] {name}: rate-limited after retries")
    return False


def upload_file(service, local_path, parent_id, log_func=None):
    """Upload a single file (creates new; does not check for existing). Use _upload_file_smart for sync."""
    from googleapiclient.http import MediaFileUpload
    local_path = Path(local_path)
    if not local_path.exists():
        return None
    name = local_path.name
    try:
        media = MediaFileUpload(str(local_path), resumable=False)
        meta = {"name": name, "parents": [parent_id]}
        service.files().create(body=meta, media_body=media, fields="id").execute()
        if log_func:
            log_func(f"  Uploaded: {name}")
        return True
    except Exception as e:
        if log_func:
            log_func(f"  [FAIL] {name}: {e}")
        return False


def upload_folder(service, local_folder, parent_id, log_func=None, folder_cache=None, drive_folder_name=None):
    """Recursively upload a folder using smart sync (skip unchanged, update changed, create new)."""
    if folder_cache is None:
        folder_cache = {}
    local_folder = Path(local_folder)
    if not local_folder.exists():
        return False
    folder_name = drive_folder_name or local_folder.name
    cache_key = (folder_name, parent_id)
    folder_id = folder_cache.get(cache_key) or get_or_create_folder(service, folder_name, parent_id)
    if not folder_id:
        return False
    folder_cache[cache_key] = folder_id
    subfolder_index_cache = {folder_id: _list_folder_index(service, folder_id)}
    ok = True
    for item in sorted(local_folder.rglob("*")):
        if item.is_file():
            rel = item.relative_to(local_folder)
            parts = list(rel.parts)
            cur_parent = folder_id
            for part in parts[:-1]:
                sub_key = (part, cur_parent)
                sub_id = folder_cache.get(sub_key) or get_or_create_folder(service, part, cur_parent)
                if not sub_id:
                    ok = False
                    cur_parent = None
                    break
                folder_cache[sub_key] = sub_id
                if sub_id not in subfolder_index_cache:
                    subfolder_index_cache[sub_id] = _list_folder_index(service, sub_id)
                cur_parent = sub_id
            if cur_parent:
                cur_index = subfolder_index_cache.get(cur_parent, {})
                if not _upload_file_smart(service, item, cur_parent, cur_index, log_func):
                    ok = False
    return ok


def list_folder(service, parent_id):
    results = []
    page_token = None
    while True:
        try:
            params = {
                "q": f"'{parent_id}' in parents and trashed=false",
                "fields": "nextPageToken,files(id,name,mimeType,size)",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            res = service.files().list(**params).execute()
            results.extend(res.get("files", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        except Exception as e:
            logger.warning("GDrive list_folder %s: %s", parent_id, e)
            break
    return results


def download_file(service, file_id, local_path, log_func=None):
    from googleapiclient.http import MediaIoBaseDownload
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = service.files().get_media(fileId=file_id)
        with open(local_path, "wb") as fh:
            dl = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = dl.next_chunk()
        if log_func:
            log_func(f"  Downloaded: {local_path.name}")
        return True
    except Exception as e:
        if log_func:
            log_func(f"  [FAIL] Download {local_path.name}: {e}")
        return False


def download_folder(service, folder_id, local_dest, log_func=None):
    local_dest = Path(local_dest)
    local_dest.mkdir(parents=True, exist_ok=True)
    items = list_folder(service, folder_id)
    ok = True
    for item in items:
        if item["mimeType"] == "application/vnd.google-apps.folder":
            sub_dest = local_dest / item["name"]
            if not download_folder(service, item["id"], sub_dest, log_func):
                ok = False
        else:
            if not download_file(service, item["id"], local_dest / item["name"], log_func):
                ok = False
    return ok


_BACKUP_ROOT_NAME = "SteaMidra Backups"


def get_backup_root(service):
    return get_or_create_folder(service, _BACKUP_ROOT_NAME, "root")


def list_backup_locations(service):
    root_id = find_folder(service, _BACKUP_ROOT_NAME, "root")
    if not root_id:
        return {}
    result = {}
    for loc_item in list_folder(service, root_id):
        if loc_item["mimeType"] != "application/vnd.google-apps.folder":
            continue
        loc_name = loc_item["name"]
        games = []
        for game_item in list_folder(service, loc_item["id"]):
            if game_item["mimeType"] != "application/vnd.google-apps.folder":
                continue
            meta = _fetch_meta_from_folder(service, game_item["id"])
            games.append({
                "folder_id": game_item["id"],
                "folder_name": game_item["name"],
                "app_id": meta.get("app_id"),
                "game_name": meta.get("game_name", game_item["name"]),
                "source_path": meta.get("source_path", ""),
                "backed_up_at": meta.get("backed_up_at", ""),
            })
        result[loc_name] = {"folder_id": loc_item["id"], "games": games}
    return result


def _fetch_meta_from_folder(service, folder_id):
    items = list_folder(service, folder_id)
    for item in items:
        if item["name"] == "steamidra_meta.json":
            try:
                content = service.files().get_media(fileId=item["id"]).execute()
                return json.loads(content)
            except Exception:
                pass
    return {}
