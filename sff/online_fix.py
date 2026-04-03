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

"""Online-fix.me integration for multiplayer fixes (Selenium)."""

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
from typing import Optional, Tuple
from urllib.parse import quote

from colorama import Fore, Style

from sff.prompts import prompt_confirm, prompt_secret, prompt_select, prompt_text
from sff.storage.settings import Settings, get_setting, set_setting
from sff.utils import root_folder

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = "credentials.json"
ONLINE_FIX_BASE_URL = "https://online-fix.me"


def _extract_game_slug(game_url: str) -> str:
    """Extract game slug from online-fix.me URL."""
    # Example: https://online-fix.me/games/horror/17712-repo-po-seti.html -> repo
    match = re.search(r"/(\d+-)?([\w-]+)\.html", game_url)
    if match:
        slug = match.group(2)
        # Strip common suffixes
        slug = re.sub(r"-(po-seti|kak-igrat-po-seti|online|steam|generic)$", "", slug)
        # If it's just dots (like R.E.P.O), normalize
        if "." in slug:
            slug = slug.replace(".", "")
        return slug.lower()
    return ""


def _safe_click(driver, element):
    """Safely click an element using native click or JS fallback."""
    from selenium.common.exceptions import ElementClickInterceptedException
    try:
        element.click()
    except (ElementClickInterceptedException, Exception):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)


def _find_window_by_url(driver, search_str, timeout=35):
    """Wait for and switch to a window containing the search string in its URL."""
    start_t = time.time()
    while time.time() - start_t < timeout:
        for handle in driver.window_handles:
            try:
                driver.switch_to.window(handle)
                if search_str in driver.current_url:
                    return True
            except Exception:
                pass
        time.sleep(1)
    return False


def _get_credentials_path() -> Path:
    return root_folder() / CREDENTIALS_FILE


def _read_credentials() -> Tuple[Optional[str], Optional[str]]:
    # Try settings first
    username = get_setting(Settings.ONLINE_FIX_USER)
    password = get_setting(Settings.ONLINE_FIX_PASS)

    if username and password:
        return username, password

    # Try credentials.json file
    cred_path = _get_credentials_path()
    if cred_path.exists():
        try:
            with open(cred_path, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
                return data.get("username"), data.get("password")
        except Exception as e:
            logger.warning(f"Failed to read credentials file: {e}")

    return None, None


def _save_credentials(username: str, password: str) -> bool:
    try:
        set_setting(Settings.ONLINE_FIX_USER, username)
        set_setting(Settings.ONLINE_FIX_PASS, password)
        return True
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}")
        return False


def _detect_archiver() -> Tuple[Optional[str], Optional[str]]:
    import shutil as sh

    # Check for WinRAR
    for path in [
        sh.which("winrar"),
        r"C:\Program Files\WinRAR\winrar.exe",
        r"C:\Program Files (x86)\WinRAR\winrar.exe",
    ]:
        if path and os.path.exists(path):
            return ("winrar", path)

    # Check for 7-Zip
    for path in [
        sh.which("7z"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]:
        if path and os.path.exists(path):
            return ("7z", path)

    return (None, None)


def _wait_for_download(folder: Path, max_wait: int = 600) -> Optional[Path]:
    start = time.time()
    exts = (".rar", ".zip", ".7z")
    sizes = {}
    stable = {}
    last_size_change_time = time.time()
    last_total_size = 0
    file_found = False
    slow_warning_shown = False
    
    print()  # Start on new line
    
    while (time.time() - start) < max_wait:
        try:
            found_any_file = False
            current_total_size = 0
            
            for f in os.listdir(folder):
                full_path = folder / f
                if not full_path.is_file():
                    continue
                
                lower = f.lower()
                if any(lower.endswith(ext) for ext in exts):
                    found_any_file = True
                    file_found = True
                    try:
                        size = full_path.stat().st_size
                        current_total_size += size
                        
                        # Check if file size is stable (download complete)
                        if f in sizes and sizes[f] == size:
                            stable[f] = stable.get(f, 0) + 1
                            if stable[f] >= 3:  # Stable for 3 seconds
                                size_mb = size / (1024 * 1024)
                                print(f"\r{Fore.GREEN}✓ Download complete: {size_mb:.1f} MB{Style.RESET_ALL}" + " " * 20)
                                print()  # New line
                                return full_path
                        else:
                            stable[f] = 0
                        
                        sizes[f] = size
                        
                        if size > 0:
                            size_mb = size / (1024 * 1024)
                            elapsed = time.time() - start
                            speed_mbps = size_mb / elapsed if elapsed > 0 else 0
                            
                            bar_length = 20
                            filled = int((elapsed % 10) / 10 * bar_length)
                            bar = "█" * filled + "░" * (bar_length - filled)
                            
                            print(
                                f"\r{Fore.CYAN}[{bar}]{Style.RESET_ALL} "
                                f"Downloading... {Fore.YELLOW}{size_mb:.1f} MB{Style.RESET_ALL} "
                                f"({speed_mbps:.2f} MB/s avg)",
                                end="",
                                flush=True
                            )
                    except Exception:
                        pass
            
            if current_total_size > last_total_size:
                last_size_change_time = time.time()
                last_total_size = current_total_size
                slow_warning_shown = False
            
            elapsed = time.time() - start
            time_since_change = time.time() - last_size_change_time
            
            if not file_found and elapsed >= 20:
                print()  # New line
                print(Fore.RED + "✗ No download file detected after 20 seconds" + Style.RESET_ALL)
                print(Fore.YELLOW + "  Possible causes:" + Style.RESET_ALL)
                print(Fore.YELLOW + "  - Antivirus blocking the download. Add an exclusion for this folder:" + Style.RESET_ALL)
                print(Fore.CYAN + f"    {folder}" + Style.RESET_ALL)
                print(Fore.YELLOW + "  - Chrome saved to a different folder (e.g. your Downloads folder)." + Style.RESET_ALL)
                print(Fore.YELLOW + "  - Slow connection; try again." + Style.RESET_ALL)
                logger.error(f"Multiplayer: No download file after {elapsed:.0f}s")
                return None
            
            if found_any_file and time_since_change >= 10 and not slow_warning_shown:
                slow_warning_shown = True
                print()  # New line
                print(Fore.YELLOW + "⚠ Download seems slow - check your internet connection..." + Style.RESET_ALL)
                print(f"{Fore.CYAN}  Still downloading...{Style.RESET_ALL}", end="", flush=True)
            
            if found_any_file and time_since_change >= 30:
                print()  # New line
                print(Fore.RED + f"✗ Download stalled for {time_since_change:.0f} seconds" + Style.RESET_ALL)
                print(Fore.YELLOW + "  Possible causes:" + Style.RESET_ALL)
                print(Fore.YELLOW + "  - Slow internet connection" + Style.RESET_ALL)
                print(Fore.YELLOW + "  - File was quarantined by antivirus" + Style.RESET_ALL)
                print(Fore.YELLOW + "  - Network interruption" + Style.RESET_ALL)
                logger.error(f"Multiplayer: Download stalled for {time_since_change:.0f}s")
                return None
                    
        except Exception as e:
            logger.warning(f"Error checking download folder: {e}")
        
        time.sleep(1)
    
    print()  # New line
    print(Fore.RED + f"✗ Download timeout after {max_wait} seconds" + Style.RESET_ALL)
    print(Fore.YELLOW + "  Check your connection and try again." + Style.RESET_ALL)
    return None


def _extract_archive(
    archive_path: Path, target_dir: Path, atype: str, apath: str, password: str = "online-fix.me"
) -> bool:
    try:
        archive_size_mb = archive_path.stat().st_size / (1024 * 1024)
        
        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  EXTRACTION" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(f"Archive: {archive_path.name} ({archive_size_mb:.1f} MB)")
        print(f"Target:  {target_dir}")
        print(f"Using:   {atype.upper()}")
        print()
        print(Fore.YELLOW + "Extracting files..." + Style.RESET_ALL)

        if atype == "winrar":
            cmd = [apath, "x", f"-p{password}", "-y", str(archive_path), str(target_dir) + os.sep]
        else:  # 7z
            cmd = [apath, "x", f"-p{password}", "-y", f"-o{str(target_dir)}", str(archive_path)]

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        start_time = time.time()
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=300,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        elapsed = time.time() - start_time

        print(Fore.GREEN + f"✓ Extraction complete! ({elapsed:.1f}s)" + Style.RESET_ALL)
        print()
        return True
    except subprocess.TimeoutExpired:
        print()
        print(Fore.RED + "✗ Extraction timeout (>5 minutes)" + Style.RESET_ALL)
        print(Fore.YELLOW + "  The archive may be corrupted or too large." + Style.RESET_ALL)
        return False
    except subprocess.CalledProcessError as e:
        print()
        print(Fore.RED + "✗ Extraction failed" + Style.RESET_ALL)
        if e.returncode == 2:
            print(Fore.YELLOW + "  Archive error - file may be corrupted" + Style.RESET_ALL)
        elif e.returncode == 3:
            print(Fore.YELLOW + "  Wrong password or encrypted archive" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + f"  Error code: {e.returncode}" + Style.RESET_ALL)
        logger.error(f"Extraction error: {e}")
        return False
    except Exception as e:
        print()
        print(Fore.RED + f"✗ Extraction failed: {e}" + Style.RESET_ALL)
        logger.error(f"Extraction error: {e}")
        return False


def _apply_multiplayer_fix_selenium(
    game_name: str,
    game_folder: Path,
    username: str,
    password: str,
    atype: str,
    apath: str,
    temp_dir: Path,
) -> bool:
    """
    Apply multiplayer fix using Selenium.
    Search -> game page -> login -> download -> extract.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
    except ImportError as e:
        print(Fore.RED + f"Selenium not installed: {e}" + Style.RESET_ALL)
        return False

    driver = None
    clean = re.sub(r"[^\w\s]", "", game_name).strip() or game_name.strip()
    search_url = f"{ONLINE_FIX_BASE_URL}/index.php?do=search&subaction=search&story={quote(clean)}"

    print()
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    print(Fore.CYAN + "  INITIALIZING BROWSER" + Style.RESET_ALL)
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    
    opts = Options()
    opts.add_argument("--window-size=1600,1000")
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-popup-blocking")
    
    # Advanced Stealth (v6.0)
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # Realistic User-Agent (Chrome on Windows)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    opts.add_experimental_option("prefs", {
        "download.default_directory": str(temp_dir.absolute()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    try:
        driver = webdriver.Chrome(service=Service(log_output=os.devnull), options=opts)
        # Inject navigator.webdriver override via CDP for deepest stealth
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        print(Fore.GREEN + "✓ Browser ready (Stealth v6.0)" + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"✗ Chrome driver error: {e}" + Style.RESET_ALL)
        return False

    wait = WebDriverWait(driver, 15)

    try:
        # --- SEARCH ---
        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  SEARCHING FOR GAME" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        driver.get(search_url)
        
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.story, div.story")))
        except TimeoutException:
            pass

        anchors = driver.find_elements(By.CSS_SELECTOR, "div.story a, article a")
        if not anchors:
            anchors = driver.find_elements(By.TAG_NAME, "a")

        best = None
        best_r = 0.0
        game_lower = game_name.lower()
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                txt = (a.text or "").strip().lower()
                if not href or "online-fix.me" not in href or "/page/" in href:
                    continue
                if "/games/" not in href:
                    continue
                ratio = SequenceMatcher(None, game_lower, txt).ratio()
                if ratio > best_r:
                    best_r = ratio
                    best = a
            except Exception:
                pass

        if not best or best_r < 0.15: # Lowered threshold slightly for better match tolerance
            print(Fore.RED + f"✗ No suitable match found for '{game_name}'" + Style.RESET_ALL)
            return False

        print(Fore.GREEN + f"✓ Found match: {best.text.strip()} ({best_r*100:.0f}%)" + Style.RESET_ALL)
        game_page_url = best.get_attribute("href")
        _safe_click(driver, best)
        time.sleep(2)

        # --- LOGIN ---
        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  LOGGING IN" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        try:
            if driver.find_elements(By.NAME, "login_name"):
                ln = driver.find_element(By.NAME, "login_name")
                lp = driver.find_element(By.NAME, "login_password")
                ln.send_keys(username)
                lp.send_keys(password)
                btn = driver.find_element(By.XPATH, "//button[contains(text(),'Вход')] | //input[@type='submit' and @value='Вход']")
                _safe_click(driver, btn)
                time.sleep(3)
        except Exception as e:
            logger.warning(f"Login form error: {e}")

        # --- UTILITIES ---
        def sanitize_and_click(element):
            print("Sanitizing element and forcing navigation...")
            scrub_script = """
            (function(el) {
                const attrs = ['onclick', 'onmousedown', 'onmouseup', 'oncontextmenu'];
                attrs.forEach(a => el.removeAttribute(a));
                el.setAttribute('target', '_self');
                el.click();
            })(arguments[0]);
            """
            try:
                driver.execute_script(scrub_script, element)
            except Exception as e:
                print(f"JS Click failed ({e}), falling back to standard click...")
                _safe_click(driver, element)

        def prime_subdomain_safely(url):
            """Sync cookies to subdomain by navigating the current tab sequentially."""
            try:
                parts = url.split("//")[-1].split("/")
                domain = parts[0]
                prime_url = f"https://{domain}/"
                print(f"Priming subdomain: {prime_url}")
                
                # Navigate current tab to subdomain root to set cookies
                driver.get(prime_url)
                time.sleep(3) 
                print("Priming complete. Proceeding to target URL.")
            except Exception as e:
                logger.warning(f"Priming failed: {e}")

        # --- DOWNLOAD FLOW ---
        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  CAPTURING DOWNLOAD LINK" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        
        main_window = driver.current_window_handle
        uploads_btn_xpath = "//a[contains(text(),'Скачать фикс с сервера')] | //button[contains(text(),'Скачать фикс с сервера')] | //a[contains(@class, 'download-link')][contains(text(), 'сервера')]"
        success = False

        try:
            # 1. Locate and Extract Link
            print("Locating primary download button...")
            btn = wait.until(EC.presence_of_element_located((By.XPATH, uploads_btn_xpath)))
            target_url = btn.get_attribute("href")
            
            # --- INTERACTION FLOW
            print("Initiating Click-Until-Open traversal...")
            target_handle = None
            
            # Attempt to click until the correct window opens (bypasses ad-traps)
            for click_attempt in range(4):
                print(f"Triggering download link (Attempt {click_attempt + 1})...")
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(4)
                
                for handle in driver.window_handles:
                    if handle != main_window:
                        driver.switch_to.window(handle)
                        curr_url = driver.current_url.lower()
                        if "uploads.online-fix.me" in curr_url:
                            print(f"Successfully landed on file server: {driver.current_url}")
                            target_handle = handle
                            break
                        else:
                            print(f"Ad-trap detected: {driver.current_url}. Closing...")
                            driver.close()
                
                if target_handle: break
                driver.switch_to.window(main_window)
                time.sleep(1)

            if not target_handle:
                print("Falling back to direct navigation...")
                if target_url:
                    prime_subdomain_safely(target_url)
                    driver.get(target_url)
                    time.sleep(5)
                else:
                    raise Exception("Target download link could not be opened.")

            # --- FILE SERVER TRAVERSAL ---
            # Wait for stabilization
            time.sleep(3)
            
            # Handle 401/403 with Safe-Priming
            if "401" in driver.title or "401" in driver.page_source or "403" in driver.title:
                print(Fore.YELLOW + "Detected 401/403. Running safe-priming patch..." + Style.RESET_ALL)
                curr = driver.current_url
                parts = curr.split("//")[-1].split("/")
                driver.get(f"https://{parts[0]}/")
                time.sleep(3)
                driver.get(curr)
                time.sleep(3)

            # Identification
            print("Checking for 'Fix Repair' folders and archives...")
            final_link = None
            try:
                fix_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Fix Repair")
                if fix_links:
                    print(Fore.CYAN + f"Entering directory: {fix_links[0].text}" + Style.RESET_ALL)
                    driver.execute_script("arguments[0].scrollIntoView(true);", fix_links[0])
                    driver.execute_script("arguments[0].click();", fix_links[0])
                    time.sleep(3)
            except: pass

            # Archive scan
            for attempt in range(3):
                all_links = driver.find_elements(By.TAG_NAME, "a")
                for lnk in all_links:
                    href = (lnk.get_attribute("href") or "").lower()
                    text = (lnk.text or "").lower()
                    if any(ext in href for ext in [".rar", ".zip", ".7z"]):
                        if any(k in text or k in href for k in ["fix", "repair", "ofme"]):
                            final_link = lnk
                            break
                        if not final_link: final_link = lnk
                if final_link: break
                time.sleep(2)
            
            if final_link:
                dl_label = final_link.text or final_link.get_attribute("href").split("/")[-1]
                print(Fore.GREEN + f"✓ Starting final download: {dl_label}" + Style.RESET_ALL)
                driver.execute_script("arguments[0].click();", final_link)
                success = True
            else:
                # v10.0 GIGACHAD FALLBACK: URL Reconstruction
                print(Fore.YELLOW + "Directory listing blocked or empty. Attempting direct URL reconstruction..." + Style.RESET_ALL)
                clean_game = game_name.replace(".", "").replace(" ", "_").strip("_")
                guesses = [
                    f"{clean_game}_Fix_Repair_Steam_V5_Generic.rar",
                    f"{clean_game}_Fix_Repair_Steam_V6_Generic.rar",
                    f"{clean_game}_Fix_Repair_Steam_Generic.rar",
                    f"{clean_game}-OFME.rar"
                ]
                
                # Try to find REPO specific version if possible
                if "REPO" in game_name.upper():
                    guesses.insert(0, "REPO.v0.3.2-OFME.rar")
                    guesses.insert(1, "REPO_Fix_Repair_Steam_V5_Generic.rar")

                base_repo = driver.current_url.rstrip("/")
                if "/Fix Repair" not in base_repo and "/Fix%20Repair" not in base_repo:
                    base_repo += "/Fix%20Repair"

                for g in guesses:
                    g_url = f"{base_repo}/{g}"
                    print(f"Trying reconstructed guess: {g_url}")
                    driver.get(g_url)
                    time.sleep(3)
                    # If the URL is valid, Chrome will start a download and the page will 
                    # either stay the same or show a download progress. 
                    # If it's a 404, we'll see it in title.
                    if "404" not in driver.title and "not found" not in driver.page_source.lower():
                        print(Fore.GREEN + f"✓ Successfully triggered reconstructed download: {g}" + Style.RESET_ALL)
                        success = True
                        break

            if not success:
                # Debug link dump
                print(Fore.YELLOW + "Final Debug: Printing first 15 links on page:" + Style.RESET_ALL)
                all_links = driver.find_elements(By.TAG_NAME, "a")
                for l in all_links[:15]: 
                    print(f"- {l.text} -> {l.get_attribute('href')}")
                raise Exception("No archive found (Listing failed & Reconstruction failed).")

        except Exception as e:
            if not success:
                print(Fore.RED + f"✗ Primary method failed: {e}" + Style.RESET_ALL)
                success = False

        if not success:
            # --- HOSTER FALLBACK (BULLETPROOF) ---
            print(Fore.YELLOW + "Starting hosters fallback..." + Style.RESET_ALL)
            driver.switch_to.window(main_window)
            try:
                # Re-locate button in case of DOM refresh
                h_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Online-Fix Hosters')]")))
                sanitize_and_click(h_btn)
                time.sleep(5)
                
                # Search for the hosters tab
                for h in driver.window_handles:
                    driver.switch_to.window(h)
                    if "hosters.online-fix.me" in driver.current_url:
                        break
                
                print("Selecting best available hoster mirror...")
                wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@class, 'downloadBtn')]")))
                hoster_links = driver.find_elements(By.XPATH, "//a[contains(@class, 'downloadBtn')]")
                if hoster_links:
                    print(Fore.GREEN + f"✓ Selected hoster: {hoster_links[0].get_attribute('href')}" + Style.RESET_ALL)
                    sanitize_and_click(hoster_links[0]) 
                    success = True
                else:
                    print(Fore.RED + "✗ No hoster download buttons found." + Style.RESET_ALL)
            except Exception as e2:
                print(Fore.RED + f"✗ Hoster fallback failed: {e2}" + Style.RESET_ALL)

        # --- WAIT & EXTRACT ---
        if success:
            print()
            print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
            print(Fore.CYAN + "  DOWNLOAD PROGRESS" + Style.RESET_ALL)
            print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
            downloaded_file = _wait_for_download(temp_dir, max_wait=900)

            if downloaded_file:
                print(Fore.GREEN + f"✓ Downloaded: {downloaded_file.name}" + Style.RESET_ALL)
                return _extract_archive(downloaded_file, game_folder, atype, apath)
        
        return False

    except Exception as e:
        logger.error(f"Multiplayer fix error: {e}")
        print(Fore.RED + f"Error: {e}" + Style.RESET_ALL)
        return False
    finally:
        if driver:
            driver.quit()


def prompt_credentials() -> Tuple[Optional[str], Optional[str]]:
    print("\n" + Fore.CYAN + "Online-fix.me Credentials" + Style.RESET_ALL)
    print("Enter your online-fix.me login credentials.")
    print("These will be saved securely for future use.\n")

    username = prompt_text("Username:")
    if not username:
        return None, None

    password = prompt_secret("Password:")
    if not password:
        return None, None

    return username, password


def apply_multiplayer_fix(game_name: str, game_folder: Path) -> bool:
    username, password = _read_credentials()
    if not username or not password:
        username, password = prompt_credentials()
        if not username or not password:
            print(Fore.RED + "Credentials required" + Style.RESET_ALL)
            return False
        if prompt_confirm("Save credentials for future use?"):
            _save_credentials(username, password)

    atype, apath = _detect_archiver()
    if not atype:
        print(Fore.RED + "No archiver found. Please install WinRAR or 7-Zip." + Style.RESET_ALL)
        return False
    print(f"Using {atype} for extraction")

    temp_dir = Path(tempfile.mkdtemp(prefix="sff_online_fix_"))
    try:
        return _apply_multiplayer_fix_selenium(
            game_name, game_folder, username, password, atype, apath, temp_dir
        )
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


def manage_credentials() -> None:
    username, password = _read_credentials()

    if username:
        print(f"\nCurrent username: {Fore.YELLOW}{username}{Style.RESET_ALL}")
        if not prompt_confirm("Update credentials?"):
            return

    username, password = prompt_credentials()
    if username and password:
        if _save_credentials(username, password):
            print(Fore.GREEN + "Credentials saved!" + Style.RESET_ALL)
        else:
            print(Fore.RED + "Failed to save credentials" + Style.RESET_ALL)
