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
Smart Matching Hybrid Model: selenium login + container-aware link discovery + recursive frame-piercing.
Includes a strict 50% match threshold to avoid false positives (like "thank you" links).
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

import httpx
from colorama import Fore, Style
from tqdm import tqdm

from sff.prompts import prompt_confirm, prompt_secret, prompt_text
from sff.storage.settings import Settings, get_setting, set_setting
from sff.utils import root_folder

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = "credentials.json"
ONLINE_FIX_BASE_URL = "https://online-fix.me"

def _get_credentials_path(): return root_folder() / CREDENTIALS_FILE

def _read_credentials():
    username = get_setting(Settings.ONLINE_FIX_USER)
    password = get_setting(Settings.ONLINE_FIX_PASS)
    if username and password: return username, password
    cred_path = _get_credentials_path()
    if cred_path.exists():
        try:
            with open(cred_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("username"), data.get("password")
        except Exception: pass
    return None, None

def _save_credentials(username, password):
    try:
        set_setting(Settings.ONLINE_FIX_USER, username); set_setting(Settings.ONLINE_FIX_PASS, password)
        return True
    except Exception: return False

def _detect_archiver():
    """Find a working archive extractor for the current platform.

    Returns ('winrar'|'7z', path) or (None, None). The 'winrar' label drives the
    command-line shape used in _extract_archive_with_backup, so 'unrar' on Linux
    is reported as 'winrar' to share the same flag style.
    """
    import shutil as sh
    if os.name == "nt":
        for p in [sh.which("winrar"), r"C:\Program Files\WinRAR\winrar.exe", r"C:\Program Files (x86)\WinRAR\winrar.exe"]:
            if p and os.path.exists(p): return ("winrar", p)
        for p in [sh.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]:
            if p and os.path.exists(p): return ("7z", p)
        return (None, None)

    # Linux / macOS — prefer 7z (handles rar/zip/7z), fall back to unrar.
    for name in ("7z", "7zz", "7zip"):
        p = sh.which(name)
        if p: return ("7z", p)
    p = sh.which("unrar")
    if p: return ("winrar", p)
    return (None, None)

def _download_with_session(url, cookies_list, user_agent, save_path):
    """Stream download via HTTPX using browser-grade headers."""
    cookies = {c['name']: c['value'] for c in cookies_list}
    headers = {"User-Agent": user_agent, "Referer": "https://uploads.online-fix.me/"}
    for _attempt in range(3):
        try:
            with httpx.stream("GET", url, cookies=cookies, headers=headers, follow_redirects=True, timeout=None) as response:
                if response.status_code in (403, 404):
                    if _attempt < 2:
                        print(f"{Fore.YELLOW}⚠ Server returned {response.status_code}, retrying ({_attempt + 1}/3)...{Style.RESET_ALL}")
                        time.sleep(3)
                        continue
                    print(f"{Fore.RED}✗ Connection rejected by file server: {response.status_code}{Style.RESET_ALL}")
                    return False
                if response.status_code != 200:
                    print(f"{Fore.RED}✗ Connection rejected by file server: {response.status_code}{Style.RESET_ALL}")
                    return False
                try: total = int(response.headers.get("Content-Length", "0"))
                except (ValueError, TypeError): total = 0
                with save_path.open("wb") as f, tqdm(desc="Downloading Fix", total=total or None, unit="B", unit_scale=True, unit_divisor=1024, miniters=1, colour='green') as pbar:
                    for chunk in response.iter_bytes(chunk_size=1024*1024):
                        f.write(chunk); pbar.update(len(chunk))
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Download stream interrupted: {e}{Style.RESET_ALL}"); return False
    return False

def _run_extraction_with_timeout(cmd, timeout=300):
    try:
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            popen_kwargs["startupinfo"] = startupinfo
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(cmd, **popen_kwargs)
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
    try:
        temp_dir = tempfile.mkdtemp(prefix='sff_ext_final_')
        cmd = [apath, "x", f"-p{pwd}", "-y", archive, temp_dir + os.sep] if atype == "winrar" else [apath, "x", f"-p{pwd}", "-y", f"-o{temp_dir}", archive]
        success, stdout, stderr, err = _run_extraction_with_timeout(cmd)
        if not success:
            detail = err
            if not detail and stderr:
                try:
                    detail = stderr.decode(errors="replace").strip().splitlines()[-1] if stderr else ""
                except Exception:
                    detail = "extraction failed"
            print(f"{Fore.RED}✗ Extraction failed via {atype} ({apath}): {detail or 'unknown error'}{Style.RESET_ALL}")
            return False
        extracted = {}
        for root, _, files in os.walk(temp_dir):
            for f in files:
                ft = os.path.join(root, f); rel = os.path.relpath(ft, temp_dir)
                extracted[rel] = ft
        for rel in extracted:
            gp = os.path.join(target, rel)
            if os.path.isfile(gp):
                bk = gp + ".bak"
                try: 
                    if os.path.exists(bk): os.remove(bk)
                    os.rename(gp, bk); backed_up.append((gp, bk))
                except Exception: pass
        for rel, src in extracted.items():
            dest = os.path.join(target, rel); os.makedirs(os.path.dirname(dest), exist_ok=True); shutil.move(src, dest)
        print(f"{Fore.GREEN}✓ Fix applied successfully!{Style.RESET_ALL}"); return True
    except Exception as e:
        print(f"{Fore.RED}✗ Installation error: {e}. Recovering...{Style.RESET_ALL}")
        for o, b in backed_up: 
            try: 
                if os.path.exists(o): os.remove(o)
                os.rename(b, o)
            except Exception: pass
        return False
    finally: shutil.rmtree(temp_dir, ignore_errors=True)

def _find_archives_recursive(driver):
    """Pierce through all frames recursively to find .rar/.zip file links."""
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
                        score = 0
                        if "fix" in full.lower() or "fix" in text: score += 10
                        if "repair" in full.lower() or "repair" in text: score += 10
                        if "generic" in full.lower() or "generic" in text: score += 5
                        results.append((score, full))
                except Exception: pass
        except Exception: pass

    scan_current_frame()
    try:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for i in range(len(frames)):
            try:
                driver.switch_to.frame(i); results.extend(_find_archives_recursive(driver)); driver.switch_to.default_content()
            except Exception:
                try: driver.switch_to.default_content()
                except Exception: pass
    except Exception: pass
    return results

def _run_multiplayer_fix_process(game_name, game_folder, username, password, atype, apath):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver = None; THRESHOLD = 0.5
    try:
        print()
        print(Fore.CYAN + "============================================================" + Style.RESET_ALL)
        print(Fore.CYAN + "  SMART MATCHING ENGINE (NO FALSE POSITIVES)" + Style.RESET_ALL)
        print(Fore.CYAN + "============================================================" + Style.RESET_ALL)
        opts = Options()
        opts.add_argument("--window-size=1280,800"); opts.add_argument("--headless=new")
        opts.add_argument("--log-level=3"); opts.add_argument("--no-sandbox"); opts.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=opts); wait = WebDriverWait(driver, 15)
        print(Fore.GREEN + "✓ Secure engine ready" + Style.RESET_ALL)
        # Searching with explicit Story query
        driver.get(f"https://online-fix.me/index.php?do=search&subaction=search&story={quote(re.sub(r'[^\w\s]', '', game_name))}")
        # QUALITY GATE: Restrict search to dle-content to avoid "thank you" links in footers/sidebars
        try: wait.until(EC.presence_of_element_located((By.ID, "dle-content")))
        except Exception: pass
        best = None; best_r = 0.0
        # Only scan anchors INSIDE the search content area
        anchors = driver.find_elements(By.CSS_SELECTOR, "div#dle-content a")
        if not anchors: 
             # Fallback to the broad search only if container is missing (old site layout)
             anchors = driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            try:
                txt = (a.text or "").strip().lower()
                href = a.get_attribute("href") or ""
                # Skip pagination, profile, and non-game links
                if "/page/" in href or "/user/" in href or not txt: continue
                r = SequenceMatcher(None, game_name.lower(), txt).ratio()
                if r > best_r: best_r = r; best = a
            except Exception: pass
        if not best or best_r < THRESHOLD:
            reason = f"No legitimate results found. Best was '{best.text.strip()}' ({best_r*100:.0f}%)" if best else "No results found"
            print(Fore.RED + f"✗ {reason}. Search likely failed." + Style.RESET_ALL)
            return False
        print(Fore.GREEN + f"✓ Target verified: {best.text.strip()} ({best_r*100:.0f}%)" + Style.RESET_ALL)
        driver.execute_script("arguments[0].click();", best)
        time.sleep(2)
        # Authentication
        if driver.find_elements(By.NAME, "login_name"):
            print(Fore.CYAN + "Authenticating session..." + Style.RESET_ALL)
            driver.find_element(By.NAME, "login_name").send_keys(username)
            driver.find_element(By.NAME, "login_password").send_keys(password)
            driver.find_element(By.NAME, "login_password").send_keys(Keys.ENTER)
            time.sleep(5)
        print(Fore.CYAN + "establishing link to file server..." + Style.RESET_ALL)
        xpath = "//a[contains(text(),'Скачать фикс с сервера')] | //button[contains(text(),'Скачать фикс с сервера')]"
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        btn_href = btn.get_attribute("href") or ""
        archives = []; _dl_cookies = None
        _ua = driver.execute_script("return navigator.userAgent")
        # Optimisation: try pure-httpx path first — follow loot.raxwars.com redirect via httpx.Client
        # (headless Chrome handles it too, but if httpx already has the listing we skip the window step)
        if btn_href:
            try:
                _chrome_cks = {c['name']: c['value'] for c in driver.get_cookies()}
                with httpx.Client(follow_redirects=True, timeout=15) as _client:
                    _r = _client.get(btn_href, cookies=_chrome_cks,
                                     headers={"User-Agent": _ua, "Referer": "https://online-fix.me/"})
                    _final = str(_r.url)
                    logger.debug("Redirect chain final URL [%d]: %s", _r.status_code, _final)
                    if "uploads.online-fix.me" in _final.lower() and _r.status_code == 200:
                        _all_cks = {k: str(v) for k, v in _client.cookies.items()}
                        _dl_cookies = [{'name': k, 'value': v} for k, v in _all_cks.items()]
                        _found = []

                        def _score_archive(url):
                            s = 0
                            u = unquote(url).lower()
                            if "fix" in u: s += 10
                            if "repair" in u: s += 10
                            if "generic" in u: s += 5
                            return s

                        def _parse_listing(html, base):
                            for _pm in re.finditer(r'href="([^"]+\.(?:rar|zip|7z))"', html, re.IGNORECASE):
                                _ph = urljoin(base, _pm.group(1))
                                _found.append((_score_archive(_ph), _ph))

                        # Scan root listing
                        _parse_listing(_r.text, _final)
                        # Also scan any subdirectory whose name contains "fix" or "repair"
                        _subdirs = [s for s in re.findall(r'href="([^"]+/)"', _r.text)
                                    if not s.startswith('../') and s not in ('/', './')]
                        for _sd in _subdirs:
                            if "fix" in unquote(_sd).lower() or "repair" in unquote(_sd).lower():
                                _sd_url = urljoin(_final, _sd)
                                try:
                                    _r2 = _client.get(_sd_url, headers={"User-Agent": _ua, "Referer": _final})
                                    if _r2.status_code == 200:
                                        _parse_listing(_r2.text, _sd_url)
                                except Exception as _e2:
                                    logger.debug("Subdir scan %s: %s", _sd, _e2)
                        if _found:
                            archives = _found
                            print(Fore.GREEN + "✓ Archives found via httpx redirect follow (ad bypassed)" + Style.RESET_ALL)
            except Exception as _e:
                logger.debug("httpx bypass attempt: %s", _e)
        if not archives:
            # Browser path: headless Chrome follows loot.raxwars.com redirect natively
            try:
                driver.execute_script("arguments[0].click();", btn)
            except Exception as _click_err:
                logger.debug("btn click failed: %s", _click_err)
                print(Fore.RED + "✗ Could not click download button." + Style.RESET_ALL)
                return False
            # Wait for new window/tab — but don't crash if it doesn't open
            try:
                WebDriverWait(driver, 8).until(lambda d: len(d.window_handles) > 1)
            except Exception:
                pass  # may open in same tab
            # Switch to the uploads window if it exists
            switched = False
            for h in list(driver.window_handles):
                try:
                    driver.switch_to.window(h)
                    if "uploads.online-fix.me" in driver.current_url.lower():
                        switched = True
                        break
                except Exception:
                    continue
            if not switched:
                # Try current window
                try:
                    if "uploads.online-fix.me" not in driver.current_url.lower():
                        logger.debug("No uploads window found, current URL: %s", driver.current_url)
                except Exception:
                    pass
            logger.debug("File server URL: %s", driver.current_url)
            print(Fore.YELLOW + "⚠ Waiting for Cloudflare/server resolution (up to 30s)..." + Style.RESET_ALL)
            start_wait = time.time()
            while (time.time() - start_wait) < 30:
                # Check for 401 Unauthorized or login screen on server
                src = driver.page_source or ""
                if "401 Authorization Required" in src or "Log in to go to the folder" in src:
                     print(Fore.RED + "✗ Access denied by file server (Session Sync Failed)." + Style.RESET_ALL)
                     return False
                # Refresh on transient 403/404 from the server
                if "403 Forbidden" in src or "404 Not Found" in src:
                    driver.refresh(); time.sleep(2); continue
                archives = _find_archives_recursive(driver)
                if archives: break
                # Navigate to folder if found
                try:
                    folders = driver.find_elements(By.PARTIAL_LINK_TEXT, "Fix Repair")
                    if folders: driver.execute_script("arguments[0].click();", folders[0]); time.sleep(3)
                except Exception: pass
                time.sleep(2)
        if not archives:
            print(Fore.RED + "✗ No download files located. Directory listing might be empty." + Style.RESET_ALL)
            return False
        archives.sort(key=lambda x: x[0], reverse=True); target_url = archives[0][1]
        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + f"  SECURE DOWNLOAD: {unquote(target_url.split('/')[-1])}" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        temp_file = Path(tempfile.gettempdir()) / f"final_{tempfile.mktemp()[-8:]}.rar"
        _download_cks = _dl_cookies if _dl_cookies else driver.get_cookies()
        if _download_with_session(target_url, _download_cks, _ua, temp_file):
            success = _extract_archive_with_backup(str(temp_file), str(game_folder), atype, apath, game_name)
            if temp_file.exists(): temp_file.unlink()
            return success
        return False
    except Exception as e:
        print(Fore.RED + f"✗ Search/Navigation failed: {e}{Style.RESET_ALL}"); return False
    finally:
        if driver: driver.quit()

def apply_multiplayer_fix(game_name, game_folder):
    username, password = _read_credentials()
    if not username:
        username = prompt_text("\nOnline-fix Username:"); password = prompt_secret("Password:")
        if not username: return False
        _save_credentials(username, password)
    atype, apath = _detect_archiver()
    if not atype:
        print(Fore.RED + "✗ No archive tool found. Install 7-Zip or WinRAR to apply the fix." + Style.RESET_ALL)
        return False
    # Pre-flight: verify site is reachable before launching ChromeDriver
    print(Fore.CYAN + "Checking connectivity to online-fix.me..." + Style.RESET_ALL)
    try:
        httpx.get(ONLINE_FIX_BASE_URL, timeout=10, follow_redirects=True)
    except Exception as _conn_err:
        print(Fore.RED + "✗ Cannot reach online-fix.me. Check your internet connection, disable VPN if active, and verify the site is accessible in your browser." + Style.RESET_ALL)
        logger.debug("online-fix.me pre-flight failed: %s", _conn_err)
        return False
    return _run_multiplayer_fix_process(game_name, game_folder, username, password, atype, apath)
