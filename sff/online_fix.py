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


def _get_credentials_path() -> Path:
    """Get path to credentials file"""
    return root_folder() / CREDENTIALS_FILE


def _read_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Read credentials from file or settings"""
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
    """Save credentials to settings"""
    try:
        set_setting(Settings.ONLINE_FIX_USER, username)
        set_setting(Settings.ONLINE_FIX_PASS, password)
        return True
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}")
        return False


def _detect_archiver() -> Tuple[Optional[str], Optional[str]]:
    """Detect available archiver (WinRAR or 7-Zip)"""
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
    """
    Wait for download to complete with enhanced progress tracking
    
    Features:
    - Real-time size display with progress bar
    - Stall detection (warns if no progress for 10s, fails after 30s)
    - Antivirus blocking detection (fails if no file appears after 5s)
    - Stable file detection (file size unchanged for 3 seconds)
    """
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
                        
                        # Display progress with visual bar
                        if size > 0:
                            size_mb = size / (1024 * 1024)
                            elapsed = time.time() - start
                            speed_mbps = size_mb / elapsed if elapsed > 0 else 0
                            
                            # Create simple progress indicator
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
            
            # Track if download is progressing
            if current_total_size > last_total_size:
                last_size_change_time = time.time()
                last_total_size = current_total_size
                slow_warning_shown = False
            
            elapsed = time.time() - start
            time_since_change = time.time() - last_size_change_time
            
            # Check for no download started (no file after 20 seconds)
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
            
            # Warn about slow download (no progress for 10 seconds)
            if found_any_file and time_since_change >= 10 and not slow_warning_shown:
                slow_warning_shown = True
                print()  # New line
                print(Fore.YELLOW + "⚠ Download seems slow - check your internet connection..." + Style.RESET_ALL)
                print(f"{Fore.CYAN}  Still downloading...{Style.RESET_ALL}", end="", flush=True)
            
            # Fail if download stalled (no progress for 30 seconds)
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
    
    # Timeout reached
    print()  # New line
    print(Fore.RED + f"✗ Download timeout after {max_wait} seconds" + Style.RESET_ALL)
    print(Fore.YELLOW + "  Check your connection and try again." + Style.RESET_ALL)
    return None


def _extract_archive(
    archive_path: Path, target_dir: Path, atype: str, apath: str, password: str = "online-fix.me"
) -> bool:
    """Extract archive to target directory with progress feedback"""
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
    Requires Chrome browser installed.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
    except ImportError as e:
        print(Fore.RED + f"Selenium not installed: {e}" + Style.RESET_ALL)
        print("Install with: pip install selenium")
        print("Chrome browser must be installed.")
        return False

    driver = None
    clean = re.sub(r"[^\w\s]", "", game_name).strip() or game_name.strip() or "unknown"
    search_url = f"{ONLINE_FIX_BASE_URL}/index.php?do=search&subaction=search&story={quote(clean)}"

    print()
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    print(Fore.CYAN + "  INITIALIZING BROWSER" + Style.RESET_ALL)
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    print("Setting up headless Chrome...")
    print()

    opts = Options()
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--mute-audio")
    opts.add_argument("--headless")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_experimental_option("prefs", {
        "download.default_directory": str(temp_dir.absolute()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    try:
        driver = webdriver.Chrome(service=Service(log_output=os.devnull), options=opts)
        print(Fore.GREEN + "✓ Browser ready" + Style.RESET_ALL)
    except Exception as e:
        err_msg = str(e)
        print(Fore.RED + "✗ Chrome driver error" + Style.RESET_ALL)
        print(Fore.YELLOW + "Make sure Chrome browser is installed and up-to-date." + Style.RESET_ALL)
        print(f"Error: {err_msg[:200]}")
        return False

    wait = WebDriverWait(driver, 15)

    try:
        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  SEARCHING FOR GAME" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(f"Game: {game_name}")
        print(f"URL:  {ONLINE_FIX_BASE_URL}")
        print()
        print("Searching...")
        driver.get(search_url)
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))

        print("Analyzing search results...")
        anchors = driver.find_elements(By.TAG_NAME, "a")
        if not anchors:
            print(Fore.RED + "✗ No search results found" + Style.RESET_ALL)
            return False

        game_lower = game_name.lower()
        best = None
        best_r = 0.0
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                txt = (a.text or "").strip().lower()
                if not href or "online-fix.me" not in href or "/page/" in href:
                    continue
                if "/games/" not in href and "/engine/" not in href:
                    continue
                ratio = SequenceMatcher(None, game_lower, txt).ratio()
                if ratio > best_r:
                    best_r = ratio
                    best = a
            except Exception:
                pass

        if not best or best_r < 0.2:
            print(Fore.RED + f"✗ No suitable match found for '{game_name}'" + Style.RESET_ALL)
            return False

        match_text = (best.text or "").strip()
        print(Fore.GREEN + f"✓ Found match: {match_text} (confidence: {best_r*100:.0f}%)" + Style.RESET_ALL)

        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  ACCESSING GAME PAGE" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        driver.execute_script("arguments[0].scrollIntoView(true);", best)
        driver.execute_script("arguments[0].click();", best)
        time.sleep(2)

        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  LOGGING IN" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(f"Username: {username}")
        print("Authenticating...")
        print()
        try:
            wait.until(EC.presence_of_element_located((By.NAME, "login_name")))
            wait.until(EC.presence_of_element_located((By.NAME, "login_password")))
        except TimeoutException:
            print(Fore.RED + "✗ Login form not found" + Style.RESET_ALL)
            return False

        ln = driver.find_element(By.NAME, "login_name")
        lp = driver.find_element(By.NAME, "login_password")
        ln.clear()
        ln.send_keys(username)
        lp.clear()
        lp.send_keys(password)
        try:
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@value='Вход'] | //button[contains(text(),'Вход')]")))
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            driver.execute_script("arguments[0].click();", btn)
        except TimeoutException:
            lp.send_keys(Keys.ENTER)

        print("Looking for download link...")
        download_xpath = "//a[contains(text(),'Скачать фикс с сервера')] | //button[contains(text(),'Скачать фикс с сервера')]"
        short_wait = WebDriverWait(driver, 10)
        try:
            short_wait.until(EC.presence_of_element_located((By.XPATH, download_xpath)))
        except TimeoutException:
            print(Fore.RED + "✗ Download button not found (login may have failed)" + Style.RESET_ALL)
            print(Fore.YELLOW + "Check your credentials." + Style.RESET_ALL)
            return False

        btns = driver.find_elements(By.XPATH, download_xpath)
        if not btns:
            btns = driver.find_elements(By.XPATH, "//a[contains(text(),'Download the fix')] | //button[contains(text(),'Download the fix')]")
        if not btns:
            print(Fore.RED + "✗ Download button not found" + Style.RESET_ALL)
            return False

        print(Fore.GREEN + "✓ Login successful" + Style.RESET_ALL)
        print(Fore.GREEN + "✓ Download link found" + Style.RESET_ALL)
        time.sleep(2)

        dl_btn = btns[0]
        print()
        print(Fore.CYAN + "Initiating download..." + Style.RESET_ALL)
        driver.execute_script("arguments[0].scrollIntoView(true);", dl_btn)
        driver.execute_script("arguments[0].click();", dl_btn)

        try:
            wait.until(lambda d: len(d.window_handles) > 1)
        except TimeoutException:
            pass

        for h in driver.window_handles:
            driver.switch_to.window(h)
            if "uploads.online-fix.me" in driver.current_url.lower():
                break

        time.sleep(1)
        try:
            page_source = driver.page_source or ""
            page_title = driver.title or ""
            if "401 Authorization Required" in page_source or "401 Authorization Required" in page_title:
                print(Fore.RED + "Game no longer supported (401 unauthorized)" + Style.RESET_ALL)
                return False
        except Exception:
            pass

        try:
            wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "Fix Repair")))
        except TimeoutException:
            pass

        fix_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Fix Repair")
        if fix_links:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", fix_links[0])
                driver.execute_script("arguments[0].click();", fix_links[0])
                time.sleep(2)
                try:
                    if "401 Authorization Required" in (driver.page_source or ""):
                        print(Fore.RED + "Fix Repair no longer available (401)" + Style.RESET_ALL)
                        return False
                except Exception:
                    pass
            except Exception:
                pass

        all_links = driver.find_elements(By.TAG_NAME, "a")
        archive_clicked = False
        for lnk in all_links:
            href = lnk.get_attribute("href") or ""
            if "uploads.online-fix.me" in href and any(ext in href.lower() for ext in [".rar", ".zip", ".7z"]):
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", lnk)
                    driver.execute_script("arguments[0].click();", lnk)
                    archive_clicked = True
                    break
                except Exception:
                    pass
        if not archive_clicked:
            for lnk in all_links:
                href = (lnk.get_attribute("href") or "").lower()
                if any(ext in href for ext in [".rar", ".zip", ".7z"]):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", lnk)
                        driver.execute_script("arguments[0].click();", lnk)
                        archive_clicked = True
                        break
                    except Exception:
                        pass
        if not archive_clicked:
            print(Fore.RED + "✗ Archive link (.rar/.zip/.7z) not found on uploads page" + Style.RESET_ALL)
            return False

        print()
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + "  DOWNLOAD PROGRESS" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        downloaded_file = _wait_for_download(temp_dir, max_wait=600)

        if not downloaded_file:
            print(Fore.RED + "Failed to download multiplayer fix." + Style.RESET_ALL)
            return False

        print(Fore.GREEN + f"✓ Downloaded: {downloaded_file.name}" + Style.RESET_ALL)
        if not _extract_archive(downloaded_file, game_folder, atype, apath):
            return False

        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(Fore.GREEN + "  MULTIPLAYER FIX APPLIED SUCCESSFULLY!" + Style.RESET_ALL)
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(f"Game:   {game_name}")
        print(f"Folder: {game_folder}")
        print()
        print(Fore.CYAN + "Next steps:" + Style.RESET_ALL)
        print("1. Launch the game")
        print("2. Look for multiplayer/online options")
        print("3. Enjoy playing online!")
        print()
        print(Fore.YELLOW + "Note: Some games may require additional setup." + Style.RESET_ALL)
        print()
        return True
    except Exception as e:
        logger.error(f"Multiplayer fix error: {e}")
        print(Fore.RED + f"Error: {e}" + Style.RESET_ALL)
        return False
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def prompt_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Prompt user for online-fix.me credentials"""
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
    """
    Download and apply multiplayer fix from online-fix.me (Selenium).

    Args:
        game_name: Name of the game to search for
        game_folder: Path to game installation folder

    Returns:
        True if fix was successfully applied
    """
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
    """Manage online-fix.me credentials"""
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
