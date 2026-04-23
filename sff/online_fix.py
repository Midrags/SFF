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

"""
Online-fix.me integration for multiplayer fixes.
SeleniumBase UC mode for Cloudflare bypass + built-in ad blocking + CDP network blocking.
Smart Matching: dle-content container-scoped link discovery + SequenceMatcher 50% threshold.
Recursive iframe-piercing for download link discovery on the file server.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile as _zipfile
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

import httpx
from colorama import Fore, Style
from tqdm import tqdm

from sff.prompts import prompt_secret, prompt_text
from sff.storage.settings import Settings, get_setting, set_setting
from sff.utils import root_folder

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = "credentials.json"
ONLINE_FIX_BASE_URL = "https://online-fix.me"

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
        os.environ.get("USERNAME", "")
    ),
]


def _sff_dir() -> Path:
    p = Path.home() / ".sff"
    p.mkdir(exist_ok=True)
    return p


def _ensure_chrome_for_testing() -> str:
    """Download Chrome for Testing if not cached (~300 MB, one-time). Returns path or ''."""
    import json as _json
    import platform as _platform

    plat = "win64" if _platform.machine() in ("AMD64", "x86_64") else "win32"
    chrome_exe = _sff_dir() / "chrome-for-testing" / f"chrome-{plat}" / "chrome.exe"
    if chrome_exe.exists():
        return str(chrome_exe)
    logger.info("Chrome for Testing not found — downloading (~300 MB, one-time)...")
    try:
        api = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
        with urllib.request.urlopen(api, timeout=20) as resp:
            data = _json.loads(resp.read())
        downloads = data["channels"]["Stable"]["downloads"].get("chrome", [])
        entry = next((d for d in downloads if d["platform"] == plat), None)
        if not entry:
            logger.debug("Chrome for Testing: no %s download found", plat)
            return ""
        zip_path = _sff_dir() / "chrome-for-testing.zip"
        logger.info("Downloading Chrome for Testing (%s) — this may take a minute...", plat)
        urllib.request.urlretrieve(entry["url"], str(zip_path))
        extract_dir = _sff_dir() / "chrome-for-testing"
        with _zipfile.ZipFile(str(zip_path)) as z:
            z.extractall(str(extract_dir))
        zip_path.unlink(missing_ok=True)
        if chrome_exe.exists():
            logger.info("Chrome for Testing ready: %s", chrome_exe)
            return str(chrome_exe)
    except Exception as exc:
        logger.debug("Chrome for Testing download failed: %s", exc)
    return ""


def _detect_sb_browser() -> tuple:
    """Return (browser_name, binary_path) for SeleniumBase UC mode.
    Preference: frozen EXE bundled Chrome → system Chrome → Chrome for Testing auto-download.
    """
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "chrome-bundled" / "chrome.exe"
        if bundled.exists():
            return "chrome", str(bundled)
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return "chrome", path
    chrome = _ensure_chrome_for_testing()
    if chrome:
        return "chrome", chrome
    return "chrome", ""


def _get_credentials_path() -> Path:
    return root_folder() / CREDENTIALS_FILE


def _read_credentials():
    username = get_setting(Settings.ONLINE_FIX_USER)
    password = get_setting(Settings.ONLINE_FIX_PASS)
    if username and password:
        return username, password
    cred_path = _get_credentials_path()
    if cred_path.exists():
        try:
            with open(cred_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("username"), data.get("password")
        except Exception:
            pass
    return None, None


def _save_credentials(username, password):
    try:
        set_setting(Settings.ONLINE_FIX_USER, username)
        set_setting(Settings.ONLINE_FIX_PASS, password)
        return True
    except Exception:
        return False


def _detect_archiver():
    import shutil as sh
    for p in [sh.which("winrar"), r"C:\Program Files\WinRAR\winrar.exe", r"C:\Program Files (x86)\WinRAR\winrar.exe"]:
        if p and os.path.exists(p):
            return ("winrar", p)
    for p in [sh.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]:
        if p and os.path.exists(p):
            return ("7z", p)
    return (None, None)


def _download_with_session(url, cookies_list, user_agent, save_path):
    """Stream download via HTTPX using browser session cookies.
    Returns HTTP status code (200 = success, 401/etc = server error, 0 = network exception)."""
    try:
        cookies = {c["name"]: c["value"] for c in cookies_list}
        headers = {"User-Agent": user_agent, "Referer": "https://uploads.online-fix.me/"}
        with httpx.stream("GET", url, cookies=cookies, headers=headers, follow_redirects=True, timeout=None) as response:
            if response.status_code != 200:
                print(f"{Fore.RED}✗ File server rejected connection: {response.status_code}{Style.RESET_ALL}")
                return response.status_code
            try:
                total = int(response.headers.get("Content-Length", "0"))
            except (ValueError, TypeError):
                total = 0
            with save_path.open("wb") as f, tqdm(
                desc="Downloading Fix", total=total or None, unit="B",
                unit_scale=True, unit_divisor=1024, miniters=1, colour="green",
            ) as pbar:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    pbar.update(len(chunk))
        return 200
    except Exception as e:
        print(f"{Fore.RED}✗ Download interrupted: {e}{Style.RESET_ALL}")
        return 0


def _run_extraction_with_timeout(cmd, timeout=300):
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return (process.returncode == 0, stdout, stderr, None)
        except subprocess.TimeoutExpired:
            process.kill()
            return (False, None, None, "Timeout")
    except Exception as e:
        return (False, None, None, str(e))


def _extract_archive_with_backup(archive, target, atype, apath, game_name, pwd="online-fix.me"):
    backed_up = []
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="sff_ext_")
        cmd = (
            [apath, "x", f"-p{pwd}", "-y", archive, temp_dir + os.sep]
            if atype == "winrar"
            else [apath, "x", f"-p{pwd}", "-y", f"-o{temp_dir}", archive]
        )
        success, _, _, _ = _run_extraction_with_timeout(cmd)
        if not success:
            return False
        extracted = {}
        for root, _, files in os.walk(temp_dir):
            for f in files:
                ft = os.path.join(root, f)
                rel = os.path.relpath(ft, temp_dir)
                extracted[rel] = ft
        for rel in extracted:
            gp = os.path.join(target, rel)
            if os.path.isfile(gp):
                bk = gp + ".bak"
                try:
                    if not os.path.exists(bk):
                        os.rename(gp, bk)
                        backed_up.append((gp, bk))
                    else:
                        os.remove(gp)
                except Exception:
                    pass
        for rel, src in extracted.items():
            dest = os.path.join(target, rel)
            dest_dir = os.path.dirname(dest)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, dest)
        print(f"{Fore.GREEN}✓ Fix applied successfully!{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Installation error: {e}. Recovering...{Style.RESET_ALL}")
        for o, b in backed_up:
            try:
                if os.path.exists(o):
                    os.remove(o)
                os.rename(b, o)
            except Exception:
                pass
        return False
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _find_archives_recursive(driver):
    """Pierce through all iframes recursively to find .rar/.zip/.7z download links."""
    from selenium.webdriver.common.by import By
    results = []
    exts = [".rar", ".zip", ".7z"]

    def scan_current_frame():
        try:
            links = driver.find_elements(By.TAG_NAME, "a")
            for lnk in links:
                try:
                    href = lnk.get_attribute("href") or ""
                    text = (lnk.text or "").strip().lower()
                    full = urljoin(driver.current_url, href)
                    if any(full.lower().endswith(ext) for ext in exts):
                        if "ofme" in full.lower():
                            continue
                        score = 0
                        if "fix" in full.lower() or "fix" in text:
                            score += 10
                        if "repair" in full.lower() or "repair" in text:
                            score += 10
                        if "generic" in full.lower() or "generic" in text:
                            score += 5
                        results.append((score, full))
                except Exception:
                    pass
        except Exception:
            pass

    scan_current_frame()
    try:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for i in range(len(frames)):
            try:
                driver.switch_to.frame(i)
                results.extend(_find_archives_recursive(driver))
                driver.switch_to.default_content()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass
    return results


_FOLDER_KEYWORDS = ["fix repair", "fix_repair", "repair", "generic", "steam", "patch"]


def _try_enter_subfolder(driver):
    """Click into the best matching subfolder in an Apache directory listing.
    Returns True if a folder was entered, False otherwise."""
    from selenium.webdriver.common.by import By
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        for kw in _FOLDER_KEYWORDS:
            for lnk in links:
                txt = (lnk.text or "").strip().lower()
                href = lnk.get_attribute("href") or ""
                if kw in txt and href.endswith("/") and ".." not in txt:
                    driver.execute_script("arguments[0].click();", lnk)
                    return True
    except Exception:
        pass
    return False


def _close_popup_tabs(driver, keep_handles: set):
    """Close any unexpected tabs (ads/popups). Switch back to last kept tab."""
    for handle in list(driver.window_handles):
        if handle not in keep_handles:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except Exception:
                pass
    remaining = [h for h in driver.window_handles if h in keep_handles]
    if remaining:
        driver.switch_to.window(remaining[-1])


def _run_multiplayer_fix_process(game_name, game_folder, username, password, atype, apath):
    try:
        from seleniumbase import SB
    except ImportError:
        print(Fore.RED + "seleniumbase not installed. Run: pip install seleniumbase" + Style.RESET_ALL)
        return False

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    clean = re.sub(r"[^\w\s]", "", game_name).strip() or game_name.strip() or "unknown"
    search_url = f"{ONLINE_FIX_BASE_URL}/index.php?do=search&subaction=search&story={quote(clean)}"
    THRESHOLD = 0.5

    print()
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    print(Fore.CYAN + "  ONLINE-FIX.ME MULTIPLAYER FIX" + Style.RESET_ALL)
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    print("Detecting Chrome browser...")

    browser, binary = _detect_sb_browser()
    sb_kwargs = dict(uc=True, headless=True, ad_block=True, browser=browser)
    if binary:
        sb_kwargs["binary_location"] = binary

    try:
        with SB(**sb_kwargs) as sb:
            driver = sb.driver

            # CDP: block ad networks at the network level (belt-and-suspenders alongside ad_block=True)
            try:
                driver.execute_cdp_cmd("Network.enable", {})
                driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": [
                    "*doubleclick.net*", "*googlesyndication.com*", "*adservice.google*",
                    "*googletagmanager.com*", "*pagead2.googlesyndication*", "*adnxs.com*",
                    "*adsystem.com*", "*rubiconproject.com*", "*moatads.com*",
                ]})
            except Exception:
                pass

            print(Fore.GREEN + "✓ Browser ready (Cloudflare bypass + ad blocking active)" + Style.RESET_ALL)
            print()

            # ── Step 1: Search ──────────────────────────────────────────
            print(Fore.CYAN + "Searching online-fix.me..." + Style.RESET_ALL)
            initial_handles = set(driver.window_handles)
            sb.uc_open_with_reconnect(search_url, 6)
            _close_popup_tabs(driver, initial_handles | set(driver.window_handles[:1]))

            wait = WebDriverWait(driver, 15)
            try:
                wait.until(EC.presence_of_element_located((By.ID, "dle-content")))
            except Exception:
                pass

            # ── Step 2: Smart matching (dle-content scoped, 50% threshold) ──
            best = None
            best_r = 0.0
            anchors = driver.find_elements(By.CSS_SELECTOR, "div#dle-content a")
            if not anchors:
                anchors = driver.find_elements(By.TAG_NAME, "a")
            for a in anchors:
                try:
                    txt = (a.text or "").strip().lower()
                    href = a.get_attribute("href") or ""
                    if "/page/" in href or "/user/" in href or not txt:
                        continue
                    r = SequenceMatcher(None, game_name.lower(), txt).ratio()
                    if r > best_r:
                        best_r = r
                        best = a
                except Exception:
                    pass

            if not best or best_r < THRESHOLD:
                reason = (
                    f"No match found (best: '{best.text.strip()}' at {best_r*100:.0f}%)"
                    if best else "No results found"
                )
                print(Fore.RED + f"✗ {reason}" + Style.RESET_ALL)
                return False

            print(Fore.GREEN + f"✓ Match: {best.text.strip()} ({best_r*100:.0f}%)" + Style.RESET_ALL)

            # ── Step 3: Navigate to game page ───────────────────────────
            page_handles = set(driver.window_handles)
            driver.execute_script("arguments[0].click();", best)
            time.sleep(2)
            _close_popup_tabs(driver, page_handles | set(driver.window_handles[:1]))

            # ── Step 4: Login if prompted ────────────────────────────────
            if driver.find_elements(By.NAME, "login_name"):
                print(Fore.CYAN + "Logging in..." + Style.RESET_ALL)
                driver.find_element(By.NAME, "login_name").send_keys(username)
                driver.find_element(By.NAME, "login_password").send_keys(password)
                driver.find_element(By.NAME, "login_password").send_keys(Keys.ENTER)
                time.sleep(5)
                _close_popup_tabs(driver, set(driver.window_handles[:1]))

            # ── Step 5: Reach uploads.online-fix.me (3-layer approach) ─────
            print(Fore.CYAN + "Opening file server..." + Style.RESET_ALL)
            xpath = (
                "//a[contains(text(),'Скачать фикс с сервера')] | "
                "//button[contains(text(),'Скачать фикс с сервера')]"
            )
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            except TimeoutException:
                print(Fore.RED + "✗ Download button not found on page." + Style.RESET_ALL)
                return False

            uploads_handle = None
            uploads_direct = None

            # Layer 1 — extract href directly from button (avoids ad popup entirely)
            try:
                href = btn.get_attribute("href") or ""
                if "uploads.online-fix.me" in href.lower():
                    uploads_direct = href
            except Exception:
                pass

            if not uploads_direct:
                src_matches = re.findall(
                    r'https?://uploads\.online-fix\.me/[^\s"\'<>\)]+',
                    driver.page_source,
                )
                if src_matches:
                    uploads_direct = src_matches[0]

            if uploads_direct:
                print(Fore.GREEN + "✓ Uploads URL found directly — bypassing ad popup" + Style.RESET_ALL)
                driver.get(uploads_direct)
                uploads_handle = driver.current_window_handle
                time.sleep(1)
                driver.refresh()
                time.sleep(2)
            else:
                # Layer 2 — click + smart polling 15s; close ONLY confirmed ad tabs
                pre_click_handles = set(driver.window_handles)
                driver.execute_script("arguments[0].click();", btn)

                deadline = time.time() + 15
                while time.time() < deadline and not uploads_handle:
                    time.sleep(0.8)
                    for h in list(driver.window_handles):
                        try:
                            driver.switch_to.window(h)
                            url = driver.current_url or ""
                            if "uploads.online-fix.me" in url.lower():
                                uploads_handle = h
                                break
                            # Close ONLY tabs that are fully loaded, new, and clearly NOT online-fix.me
                            if (
                                h not in pre_click_handles
                                and url
                                and "about:blank" not in url
                                and "chrome-error:" not in url
                                and "online-fix.me" not in url.lower()
                            ):
                                driver.close()
                        except Exception:
                            pass
                    # Return focus to original tab while still searching
                    if not uploads_handle:
                        for h in pre_click_handles:
                            if h in driver.window_handles:
                                try:
                                    driver.switch_to.window(h)
                                except Exception:
                                    pass
                                break

                # Layer 3 — fallback: re-scan all tab sources after polling timeout
                if not uploads_handle:
                    for h in list(driver.window_handles):
                        try:
                            driver.switch_to.window(h)
                            fallback = re.findall(
                                r'https?://uploads\.online-fix\.me/[^\s"\'<>\)]+',
                                driver.page_source or "",
                            )
                            if fallback:
                                uploads_direct = fallback[0]
                                break
                        except Exception:
                            pass
                    if uploads_direct:
                        print(Fore.GREEN + "✓ Uploads URL found in page source (fallback)" + Style.RESET_ALL)
                        driver.get(uploads_direct)
                        uploads_handle = driver.current_window_handle
                    else:
                        print(Fore.RED + "✗ Could not reach file server (ad blocked path, no URL found)." + Style.RESET_ALL)
                        return False

                # Ensure we are focused on the uploads tab
                if uploads_handle and uploads_handle in driver.window_handles:
                    driver.switch_to.window(uploads_handle)

            # ── Step 6: Navigate file server — enter subfolders first, then scan ──
            print(Fore.YELLOW + "⚠ Waiting for file server (up to 30s)..." + Style.RESET_ALL)
            start_wait = time.time()
            archives = []
            browser_401_retries = 0
            while (time.time() - start_wait) < 45:
                src = driver.page_source or ""
                if "401 Authorization Required" in src or "Log in to go to the folder" in src:
                    if browser_401_retries < 3:
                        browser_401_retries += 1
                        print(Fore.YELLOW + f"⚠ 401 on file server — refreshing page (attempt {browser_401_retries}/3)..." + Style.RESET_ALL)
                        driver.refresh()
                        time.sleep(3)
                        continue
                    print(Fore.RED + "✗ Access denied after 3 refresh attempts." + Style.RESET_ALL)
                    return False
                browser_401_retries = 0
                # Enter subdirectory first (Fix Repair, Generic, etc.) before scanning root
                if _try_enter_subfolder(driver):
                    time.sleep(2)
                    continue
                # Scan for archives at current level (OFME files excluded)
                archives = _find_archives_recursive(driver)
                if archives:
                    break
                time.sleep(2)

            if not archives:
                print(Fore.RED + "✗ No archive files found on file server." + Style.RESET_ALL)
                return False

            archives.sort(key=lambda x: x[0], reverse=True)
            target_url = archives[0][1]

            print()
            print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
            print(Fore.CYAN + f"  DOWNLOADING: {unquote(target_url.split('/')[-1])}" + Style.RESET_ALL)
            print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)

            # ── Step 7: Stream download — retry up to 3× on 401 with browser refresh ──
            temp_file = Path(tempfile.gettempdir()) / f"sff_fix_{tempfile.mktemp()[-8:]}.rar"
            downloaded = False
            for attempt in range(3):
                cookies_list = driver.get_cookies()
                user_agent = driver.execute_script("return navigator.userAgent")
                status = _download_with_session(target_url, cookies_list, user_agent, temp_file)
                if status == 200:
                    downloaded = True
                    break
                if status == 401 and attempt < 2:
                    print(Fore.YELLOW + f"⚠ 401 — refreshing session (attempt {attempt + 2}/3)..." + Style.RESET_ALL)
                    driver.refresh()
                    time.sleep(3)
                else:
                    break

            if downloaded:
                success = _extract_archive_with_backup(
                    str(temp_file), str(game_folder), atype, apath, game_name
                )
                if temp_file.exists():
                    temp_file.unlink()
                return success

            return False

    except Exception as e:
        print(Fore.RED + f"✗ Unexpected error: {e}" + Style.RESET_ALL)
        logger.debug("online_fix error", exc_info=True)
        return False


def apply_multiplayer_fix(game_name, game_folder):
    username, password = _read_credentials()
    if not username:
        username = prompt_text("\nOnline-fix Username:")
        password = prompt_secret("Password:")
        if not username:
            return False
        _save_credentials(username, password)
    atype, apath = _detect_archiver()
    if not atype:
        print(Fore.RED + "✗ No archiver found. Install WinRAR or 7-Zip." + Style.RESET_ALL)
        return False
    return _run_multiplayer_fix_process(game_name, game_folder, username, password, atype, apath)
