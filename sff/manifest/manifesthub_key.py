"""ManifestHub API key cache with auto-renewal (24 h validity)."""

import logging
import os
import re
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional

from sff.prompts import prompt_text

logger = logging.getLogger(__name__)

_KEY_URL = "https://manifesthub1.filegear-sg.me"
_EXPIRY_SECONDS = 86_400  # 24 h


def _key_is_valid() -> bool:
    from sff.storage.settings import get_setting
    from sff.structs import Settings

    key = get_setting(Settings.MANIFESTHUB_API_KEY)
    expiry_str = get_setting(Settings.MANIFESTHUB_KEY_EXPIRY)
    if not key or not expiry_str:
        return False
    try:
        return time.time() < float(expiry_str)
    except (ValueError, TypeError):
        return False


def _save_key(key: str) -> None:
    from sff.storage.settings import set_setting
    from sff.structs import Settings

    set_setting(Settings.MANIFESTHUB_API_KEY, key)
    set_setting(Settings.MANIFESTHUB_KEY_EXPIRY, str(time.time() + _EXPIRY_SECONDS))


def _extract_key_from_html(html: str) -> Optional[str]:
    # UUID first — most common API key format
    m = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        html, re.IGNORECASE,
    )
    if m:
        return m.group(0)

    # Fall back to any long alphanumeric token, skip obvious noise words
    _SKIP = {"cloudflare", "turnstile", "powered", "script", "module", "function",
              "manifest", "steam", "https", "http"}
    for match in re.finditer(r"\b([A-Za-z0-9_\-]{32,128})\b", html):
        candidate = match.group(1)
        if not any(s in candidate.lower() for s in _SKIP):
            return candidate

    return None


def _find_browser() -> Optional[tuple]:
    # Returns (kind, binary_path) where kind is 'chromium', 'edge', or 'firefox'.
    # Opera GX is checked first.
    loc = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("PROGRAMFILES", "C:\\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")

    # Chromium-based — all work with chromedriver; Opera GX first per user preference
    chromium = [
        Path(loc) / "Programs" / "Opera GX" / "opera.exe",
        Path(loc) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(pf86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(loc) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(pf) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(loc) / "Vivaldi" / "Application" / "vivaldi.exe",
        Path(loc) / "Programs" / "Opera" / "opera.exe",
    ]
    for p in chromium:
        if p.exists():
            return ("chromium", str(p))

    # Edge has its own dedicated webdriver so treat it separately
    edge = [
        Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for p in edge:
        if p.exists():
            return ("edge", str(p))

    # Firefox last — geckodriver handled by Selenium Manager
    ff = [
        Path(pf) / "Mozilla Firefox" / "firefox.exe",
        Path(pf86) / "Mozilla Firefox" / "firefox.exe",
    ]
    for p in ff:
        if p.exists():
            return ("firefox", str(p))

    return None


def _make_driver(kind: str, binary: Optional[str], headless: bool):  # type: ignore[return]
    from selenium import webdriver

    if kind == "edge":
        opts = webdriver.EdgeOptions()
        opts.add_argument("--inprivate")
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        return webdriver.Edge(options=opts)

    if kind == "firefox":
        opts = webdriver.FirefoxOptions()
        opts.add_argument("--private-window")
        if headless:
            opts.add_argument("-headless")
        if binary:
            opts.binary_location = binary
        return webdriver.Firefox(options=opts)

    # chromium — covers Chrome, Opera GX, Brave, Vivaldi
    opts = webdriver.ChromeOptions()
    opts.add_argument("--incognito")
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if binary:
        opts.binary_location = binary
    driver = webdriver.Chrome(options=opts)
    # Mask navigator.webdriver so Cloudflare sees a normal browser
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def _try_selenium_fetch() -> Optional[str]:
    try:
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        logger.debug("selenium not available")
        return None

    found = _find_browser()
    if found is None:
        if sys.platform == "win32":
            logger.debug("no browser found on Windows")
            return None
        # non-Windows: let Selenium Manager pick whatever is installed
        candidates = [("chromium", None), ("firefox", None)]
    else:
        candidates = [found]

    def _key_visible(d):  # type: ignore[no-untyped-def]
        return _extract_key_from_html(d.page_source)

    for kind, binary in candidates:
        bname = Path(binary).stem if binary else kind
        # headless first (no window), fall back to visible if Cloudflare rejects
        for headless in (True, False):
            mode = "headless" if headless else "visible"
            driver = None
            try:
                driver = _make_driver(kind, binary, headless)
                print(f"  Fetching ManifestHub key via {bname} ({mode})...")
                driver.get(_KEY_URL)
                WebDriverWait(driver, 20).until(_key_visible)
                key = _extract_key_from_html(driver.page_source)
                if key:
                    print("  ✅ ManifestHub key fetched.")
                    return key
            except Exception as e:
                logger.debug(f"{bname} {mode} failed: {e}")
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

    return None


def get_manifesthub_api_key() -> Optional[str]:
    """Get a valid key, auto-renewing if the 24 h window has passed."""
    from sff.storage.settings import get_setting
    from sff.structs import Settings

    if _key_is_valid():
        return get_setting(Settings.MANIFESTHUB_API_KEY)

    had_key = get_setting(Settings.MANIFESTHUB_API_KEY) is not None
    if had_key:
        print("ManifestHub API key expired. Auto-renewing...")
    else:
        print("Fetching ManifestHub API key automatically...")

    key = _try_selenium_fetch()
    if key:
        _save_key(key)
        return key

    # Browser automation failed — open the page and let the user copy-paste
    print(f"\nAuto-fetch failed. Opening {_KEY_URL} in your browser...")
    print("The page generates a key — copy it and paste it below.")
    webbrowser.open(_KEY_URL)
    pasted = prompt_text(
        "Paste your ManifestHub API key (leave blank to skip): "
    ).strip()
    if pasted:
        _save_key(pasted)
        return pasted

    return None
