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

import re
import shutil
import tempfile
import webbrowser
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from colorama import Fore, Style

from sff.online_fix import _extract_archive_with_backup, _detect_archiver
from sff.prompts import prompt_select
from sff.utils import root_folder

HV_JSON_URL = "https://raw.githubusercontent.com/KoriaPolis/HVAuto/main/HV.json"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def get_vbs_cmd_path() -> Path:
    return root_folder() / "third_party" / "hv" / "VBS.cmd"


def fetch_hv_games() -> list[dict]:
    """Fetch the HV.json game list from GitHub. Returns a list of game dicts."""
    try:
        print(Fore.CYAN + "Fetching HV game list from GitHub..." + Style.RESET_ALL)
        resp = httpx.get(HV_JSON_URL, follow_redirects=True, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(Fore.RED + f"Error fetching HV list: {e}" + Style.RESET_ALL)
        return []


def _extract_file_id_from_url(href: str) -> tuple[str, str]:
    """Parse a fix href and return (host_type, file_id).
    host_type is 'buzzheavier', 'vikingfile', or 'pixeldrain'.
    """
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    if "buzzheavier" in host:
        file_id = parsed.path.lstrip("/")
        return "buzzheavier", file_id
    if "vikingfile" in host or "vik1ngfile" in host:
        file_id = parsed.path.lstrip("/f/").lstrip("/")
        return "vikingfile", file_id
    if "pixeldrain" in host or "pixeldra.in" in host:
        # Defer parsing to the pixeldrain module — it handles /u/, /api/file/, etc.
        from sff.pixeldrain import _extract_pixeldrain_id
        pid = _extract_pixeldrain_id(href)
        if pid:
            return "pixeldrain", pid
        return "unknown", href
    return "unknown", href


def _download_buzzheavier(file_id: str, temp_dir: Path) -> "Path | None":
    """Download a file from buzzheavier.com.
    Four-step flow:
      1. GET /{file_id} page to extract the signed token and real filename from HTML.
      2. GET /{file_id}/download?t={token} (Server 1); fall back to &alt=true (Server 2).
      3. Stream the file from the CDN URL returned via Hx-Redirect header.
      4. Validate magic bytes to confirm a real archive was downloaded.
    Returns the Path of the downloaded file, or None on failure."""
    page_url = f"https://buzzheavier.com/{file_id}"
    print(Fore.CYAN + f"Downloading from buzzheavier.com ({file_id})..." + Style.RESET_ALL)

    # Step 1: fetch page to get signed token and real filename
    token = None
    page_fname = f"{file_id}.rar"
    try:
        page_resp = httpx.get(
            page_url,
            headers={"User-Agent": _UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
            timeout=15,
        )
        page_html = page_resp.text
        m_token = re.search(r'hx-get="[^"]*?/download\?t=([^"&]+)', page_html)
        if m_token:
            token = m_token.group(1)
        m_fname = re.search(r'<span[^>]+text-2xl[^>]*>\s*([^<]+)\s*</span>', page_html)
        if m_fname:
            page_fname = m_fname.group(1).strip()
    except Exception as e:
        print(Fore.YELLOW + f"  Could not fetch page: {e}" + Style.RESET_ALL)

    if not token:
        print(
            Fore.YELLOW
            + "buzzheavier: no download token found on page.\n"
            + "Opening the download page in your browser — download it manually."
            + Style.RESET_ALL
        )
        webbrowser.open(page_url)
        return None

    htmx_headers = {
        "User-Agent": _UA,
        "Accept": "*/*",
        "HX-Request": "true",
        "HX-Current-URL": page_url,
        "Referer": page_url,
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Step 2: trigger Server 1, fall back to Server 2
    cdn_url = None
    for alt in (False, True):
        server_label = "Server 2" if alt else "Server 1"
        trigger_suffix = f"?t={token}" + ("&alt=true" if alt else "")
        trigger_url = f"https://buzzheavier.com/{file_id}/download{trigger_suffix}"
        try:
            trigger_resp = httpx.get(trigger_url, headers=htmx_headers, follow_redirects=False, timeout=15)
            url = trigger_resp.headers.get("hx-redirect") or trigger_resp.headers.get("Hx-Redirect")
            if url:
                cdn_url = url
                print(Fore.CYAN + f"  {server_label} ready." + Style.RESET_ALL)
                break
            print(Fore.YELLOW + f"  {server_label}: no redirect, trying next..." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.YELLOW + f"  {server_label} trigger failed: {e}" + Style.RESET_ALL)

    if not cdn_url:
        print(
            Fore.YELLOW
            + "buzzheavier did not return a download URL.\n"
            + "Opening the download page in your browser — download it manually."
            + Style.RESET_ALL
        )
        webbrowser.open(page_url)
        return None

    # Step 3: stream file from CDN URL
    try:
        with httpx.stream(
            "GET",
            cdn_url,
            headers={"User-Agent": _UA, "Accept": "*/*"},
            follow_redirects=True,
            timeout=None,
        ) as resp:
            resp.raise_for_status()

            # Filename: Content-Disposition > page title > fallback
            fname = page_fname
            cd = resp.headers.get("content-disposition", "")
            if cd:
                m = re.search(r'filename\*?=(?:UTF-8\'\'\'?)?"?([^";]+)"?', cd, re.IGNORECASE)
                if m:
                    fname = m.group(1).strip()

            dest_path = temp_dir / fname
            temp_dir.mkdir(parents=True, exist_ok=True)
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with dest_path.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=524288):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 100)
                        print(f"\r  {pct}% ({downloaded // 1048576}MB / {total // 1048576}MB)", end="", flush=True)
            print()
    except httpx.HTTPStatusError as e:
        print(Fore.RED + f"Download failed: HTTP {e.response.status_code}" + Style.RESET_ALL)
        return None
    except Exception as e:
        print(Fore.RED + f"Download error: {e}" + Style.RESET_ALL)
        return None

    # Step 4: validate magic bytes — must be a real archive, not an HTML error page
    _MAGIC = {
        b"Rar!": ".rar",
        b"7z\xbc\xaf": ".7z",
        b"PK\x03\x04": ".zip",
        b"PK\x05\x06": ".zip",
        b"PK\x07\x08": ".zip",
    }
    try:
        with dest_path.open("rb") as f:
            header = f.read(8)
        real_ext = None
        for sig, ext in _MAGIC.items():
            if header.startswith(sig):
                real_ext = ext
                break
        if real_ext is None:
            print(
                Fore.RED
                + "Downloaded file is not a valid archive (received HTML or invalid data).\n"
                + "Opening the download page in your browser — download it manually."
                + Style.RESET_ALL
            )
            dest_path.unlink(missing_ok=True)
            webbrowser.open(page_url)
            return None
        if dest_path.suffix.lower() != real_ext:
            fixed = dest_path.with_suffix(real_ext)
            dest_path.rename(fixed)
            dest_path = fixed
    except Exception as e:
        print(Fore.YELLOW + f"  Archive validation warning: {e}" + Style.RESET_ALL)

    return dest_path


def _download_vikingfile(href: str, dest_path: Path) -> bool:
    """Attempt to download from vikingfile.com using curl_cffi CF bypass.
    Falls back to opening the URL in the system browser."""
    print(Fore.CYAN + "Attempting vikingfile.com download (Cloudflare bypass)..." + Style.RESET_ALL)
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore
        resp = cffi_requests.get(href, impersonate="chrome124", timeout=20, allow_redirects=True)
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and resp.status_code == 200:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(resp.content)
            return True
    except Exception:
        pass

    print(
        Fore.YELLOW
        + "Could not auto-download from vikingfile.com (Cloudflare Turnstile requires manual verification).\n"
        + "Opening the download page in your browser. Download the file, then place it\n"
        + f"in the game folder and run the fix again, or extract it manually."
        + Style.RESET_ALL
    )
    webbrowser.open(href)
    return False


def _copy_vbs_cmd(game_folder: Path) -> bool:
    """Copy VBS.cmd from third_party/hv/ to the game folder."""
    src = get_vbs_cmd_path()
    if not src.exists():
        print(Fore.YELLOW + f"VBS.cmd not found at {src} — skipping." + Style.RESET_ALL)
        return False
    dst = game_folder / "VBS.cmd"
    try:
        shutil.copy2(src, dst)
        print(Fore.GREEN + f"  Copied VBS.cmd to {dst}" + Style.RESET_ALL)
        return True
    except Exception as e:
        print(Fore.YELLOW + f"Could not copy VBS.cmd: {e}" + Style.RESET_ALL)
        return False


def _extract_to_game_folder(archive_path: Path, game_folder: Path, game_name: str) -> bool:
    """Extract a .zip, .7z, or .rar archive into the game folder, then delete it."""
    ext = archive_path.suffix.lower()
    try:
        if ext == ".zip":
            print(Fore.CYAN + "Extracting archive..." + Style.RESET_ALL)
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(game_folder, pwd=b"cs.rin.ru")
            print(Fore.GREEN + "Extraction complete." + Style.RESET_ALL)
            return True
        else:
            archiver_type, archiver_path = _detect_archiver()
            if not archiver_type:
                print(Fore.RED + "No archiver found. Install 7-Zip or WinRAR." + Style.RESET_ALL)
                return False
            return _extract_archive_with_backup(
                str(archive_path), str(game_folder), archiver_type, archiver_path, game_name, pwd="cs.rin.ru"
            )
    finally:
        try:
            archive_path.unlink(missing_ok=True)
        except Exception:
            pass


def apply_hv_fix(game_name: str, game_folder: Path, build_id: str | None = None) -> bool:
    """Full HV fix flow: fetch game list, let user pick, download, extract, copy VBS.cmd."""
    all_games = fetch_hv_games()
    if not all_games:
        return False

    build_id = str(build_id).strip() if build_id else ""
    auto_match = None
    if build_id:
        auto_match = next((g for g in all_games if str(g.get("buildid", "")).strip() == build_id), None)

    if auto_match:
        print(
            Fore.GREEN
            + f"Build ID {build_id} matched: {auto_match['name']}"
            + Style.RESET_ALL
        )
        options = [(f"{auto_match['name']}  [buildid: {auto_match['buildid']}]", auto_match)]
        options += [
            (f"{g['name']}  [buildid: {g['buildid']}]", g)
            for g in sorted(all_games, key=lambda x: x.get("name", ""))
            if g is not auto_match
        ]
    else:
        if build_id:
            print(Fore.YELLOW + f"No match for build ID {build_id}. Select manually." + Style.RESET_ALL)
        options = [
            (f"{g['name']}  [buildid: {g['buildid']}]", g)
            for g in sorted(all_games, key=lambda x: x.get("name", ""))
        ]

    chosen_game = prompt_select(
        "Select the game fix to download:",
        options,
        fuzzy=True,
        max_height=15,
        cancellable=True,
    )
    if chosen_game is None:
        return False

    fixes = chosen_game.get("fixes", [])
    if not fixes:
        print(Fore.RED + "No download links for this game." + Style.RESET_ALL)
        return False

    if len(fixes) == 1:
        chosen_fix = fixes[0]
    else:
        fix_options = [
            (f"{f.get('href', '')}  {' '.join(f.get('badges', []))}", f)
            for f in fixes
        ]
        chosen_fix = prompt_select("Select download source:", fix_options, cancellable=True)
        if chosen_fix is None:
            return False

    href = chosen_fix.get("href", "")
    if not href:
        print(Fore.RED + "No download URL." + Style.RESET_ALL)
        return False

    host_type, file_id = _extract_file_id_from_url(href)
    filename = chosen_fix.get("filename") or f"hv_fix_{chosen_game['buildid']}"
    if not filename or not Path(filename).suffix:
        filename = href.rstrip("/").split("/")[-1] or f"hv_fix_{chosen_game['buildid']}.7z"

    temp_dir = Path(tempfile.mkdtemp(prefix="sff_hv_fix_"))
    archive_path = temp_dir / filename

    try:
        if host_type == "buzzheavier":
            archive_path = _download_buzzheavier(file_id, temp_dir)
            if archive_path is None:
                return False
        elif host_type == "vikingfile":
            ok = _download_vikingfile(href, archive_path)
            if not ok:
                return False
        else:
            print(Fore.YELLOW + f"Unknown host '{host_type}'. Opening in browser." + Style.RESET_ALL)
            webbrowser.open(href)
            return False

        if not archive_path.exists() or archive_path.stat().st_size == 0:
            print(Fore.RED + "Downloaded file is empty or missing." + Style.RESET_ALL)
            return False

        print(Fore.GREEN + f"Downloaded: {archive_path.name} ({archive_path.stat().st_size // 1024} KB)" + Style.RESET_ALL)

        if not _extract_to_game_folder(archive_path, game_folder, game_name):
            return False

        _copy_vbs_cmd(game_folder)

        print()
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(Fore.GREEN + "  HV FIX APPLIED!" + Style.RESET_ALL)
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(f"Game:   {game_name}")
        print(f"Folder: {game_folder}")
        print()
        return True

    except Exception as e:
        print(Fore.RED + f"Error applying HV fix: {e}" + Style.RESET_ALL)
        return False
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
