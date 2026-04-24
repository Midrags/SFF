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

import hashlib
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from colorama import Fore, Style

from sff.utils import root_folder

SLSSTEAM_INSTALL_DIR = Path.home() / ".local" / "share" / "SLSsteam"
SLSSTEAM_CONFIG_DIR = Path.home() / ".config" / "SLSsteam"


def is_installed() -> bool:
    return (SLSSTEAM_INSTALL_DIR / "SLSsteam.so").exists()


def get_bundle_dir() -> Path:
    return root_folder() / "third_party" / "linux" / "slssteam"


def ensure_default_config() -> bool:
    config_path = SLSSTEAM_CONFIG_DIR / "config.yaml"
    if not config_path.exists():
        SLSSTEAM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        template = get_bundle_dir() / "res" / "config.yaml"
        if template.exists():
            shutil.copy2(template, config_path)
            return True
    return False


def patch_steam_sh(steam_path: Path, print_fn=print) -> bool:
    steam_sh = steam_path / "steam.sh"
    if not steam_sh.exists():
        print_fn(Fore.YELLOW + f"steam.sh not found at {steam_sh}" + Style.RESET_ALL)
        return False

    is_flatpak = ".var/app/com.valvesoftware.Steam" in str(steam_path)
    if is_flatpak:
        flatpak_sls = Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "SLSsteam"
        ld_audit = (
            f"{flatpak_sls}/library-inject.so"
            f":{flatpak_sls}/SLSsteam.so"
        )
    else:
        ld_audit = (
            f"{SLSSTEAM_INSTALL_DIR}/library-inject.so"
            f":{SLSSTEAM_INSTALL_DIR}/SLSsteam.so"
        )

    ld_line = f"export LD_AUDIT={ld_audit}"

    try:
        lines = steam_sh.read_text(encoding="utf-8").splitlines()
        lines = [l for l in lines if "LD_AUDIT" not in l]
        insert_idx = min(10, len(lines))
        lines.insert(insert_idx, ld_line)
        steam_sh.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print_fn(Fore.GREEN + f"Patched steam.sh with LD_AUDIT" + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.RED + f"Failed to patch steam.sh: {e}" + Style.RESET_ALL)
        return False


def create_steam_cfg(steam_path: Path, print_fn=print) -> bool:
    cfg_path = steam_path / "steam.cfg"
    content = "BootStrapperInhibitAll=enable\nBootStrapperForceSelfUpdate=disable\n"
    try:
        cfg_path.write_text(content, encoding="utf-8")
        print_fn(Fore.GREEN + f"Created steam.cfg at {cfg_path}" + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.RED + f"Failed to create steam.cfg: {e}" + Style.RESET_ALL)
        return False


def install_bundled(steam_path: Path, print_fn=print) -> bool:
    bundle = get_bundle_dir()
    setup_sh = bundle / "setup.sh"
    if not setup_sh.exists():
        print_fn(Fore.RED + f"setup.sh not found at {setup_sh}" + Style.RESET_ALL)
        return False

    try:
        setup_sh.chmod(0o755)
        proc = subprocess.Popen(
            [str(setup_sh), "install"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(bundle),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print_fn(line)
        proc.wait()
        if proc.returncode != 0:
            print_fn(Fore.RED + f"SLSsteam setup.sh exited with code {proc.returncode}" + Style.RESET_ALL)
            return False
    except Exception as e:
        print_fn(Fore.RED + f"SLSsteam install error: {e}" + Style.RESET_ALL)
        return False

    ensure_default_config()
    _copy_so_to_flatpak(steam_path, print_fn)
    patch_steam_sh(steam_path, print_fn)
    create_steam_cfg(steam_path, print_fn)
    version_file = Path.home() / ".local" / "share" / "SteaMidra" / "SLSsteam" / "VERSION"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text("bundled", encoding="utf-8")
    print_fn(Fore.GREEN + "SLSsteam installed successfully." + Style.RESET_ALL)
    return True


def install_from_github(steam_path: Path, print_fn=print) -> bool:
    try:
        import httpx
    except ImportError:
        print_fn(Fore.RED + "httpx not available." + Style.RESET_ALL)
        return False

    print_fn("Fetching latest SLSsteam release from GitHub...")
    try:
        resp = httpx.get(
            "https://api.github.com/repos/AceSLS/SLSsteam/releases/latest",
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        asset_url = None
        for asset in data.get("assets", []):
            if "SLSsteam-Any" in asset["name"] and asset["name"].endswith(".7z"):
                asset_url = asset["browser_download_url"]
                break
        if not asset_url:
            print_fn(Fore.RED + "SLSsteam-Any.7z not found in release assets." + Style.RESET_ALL)
            return False

        print_fn(f"Downloading {asset_url}...")
        archive_path = Path(tempfile.gettempdir()) / "SLSsteam-Any.7z"
        with httpx.stream("GET", asset_url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with archive_path.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print_fn(Fore.RED + f"Download error: {e}" + Style.RESET_ALL)
        return False

    extract_dir = Path(tempfile.gettempdir()) / "slssteam_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)

    seven_zip = shutil.which("7z") or shutil.which("7za")
    if not seven_zip:
        print_fn(Fore.RED + "7z/7za not found. Install p7zip to extract SLSsteam." + Style.RESET_ALL)
        archive_path.unlink(missing_ok=True)
        return False

    try:
        result = subprocess.run(
            [seven_zip, "x", str(archive_path), f"-o{extract_dir}", "-y"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print_fn(Fore.RED + "Extraction failed." + Style.RESET_ALL)
            return False
    except Exception as e:
        print_fn(Fore.RED + f"Extraction error: {e}" + Style.RESET_ALL)
        return False
    finally:
        archive_path.unlink(missing_ok=True)

    setup_sh = next(extract_dir.rglob("setup.sh"), None)
    if not setup_sh:
        print_fn(Fore.RED + "setup.sh not found in extracted archive." + Style.RESET_ALL)
        return False

    try:
        setup_sh.chmod(0o755)
        proc = subprocess.Popen(
            [str(setup_sh), "install"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(setup_sh.parent),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print_fn(line)
        proc.wait()
        success = proc.returncode == 0
    except Exception as e:
        print_fn(Fore.RED + f"setup.sh error: {e}" + Style.RESET_ALL)
        success = False
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    if success:
        ensure_default_config()
        _copy_so_to_flatpak(steam_path, print_fn)
        patch_steam_sh(steam_path, print_fn)
        create_steam_cfg(steam_path, print_fn)
        version = data.get("tag_name", "unknown")
        version_file = Path.home() / ".local" / "share" / "SteaMidra" / "SLSsteam" / "VERSION"
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(version, encoding="utf-8")
        print_fn(Fore.GREEN + f"SLSsteam {version} installed from GitHub." + Style.RESET_ALL)

    return success


def check_steamclient_hash() -> dict:
    steamclient = Path.home() / ".steam" / "steam" / "ubuntu12_32" / "steamclient.so"
    result = {"found": False, "hash": None, "mismatch": False}
    if not steamclient.exists():
        return result

    try:
        data = steamclient.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        result["found"] = True
        result["hash"] = sha256
    except Exception:
        return result

    try:
        import httpx
        import yaml
        resp = httpx.get(
            "https://raw.githubusercontent.com/AceSLS/SLSsteam/refs/heads/main/res/updates.yaml",
            timeout=10, follow_redirects=True,
        )
        if resp.status_code == 200:
            data = yaml.safe_load(resp.text)
            safe_hashes = data.get("SafeModeHashes", {}) if isinstance(data, dict) else {}
            all_hashes = {
                h for bucket in safe_hashes.values()
                if isinstance(bucket, list) for h in bucket
            }
            if all_hashes and sha256 not in all_hashes:
                result["mismatch"] = True
    except Exception:
        pass

    return result


def _copy_so_to_flatpak(steam_path: Path, print_fn=print) -> bool:
    """Copy .so files to Flatpak sandbox path if Steam is Flatpak."""
    if ".var/app/com.valvesoftware.Steam" not in str(steam_path):
        return False
    dest = Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "SLSsteam"
    dest.mkdir(parents=True, exist_ok=True)
    for fname in ("SLSsteam.so", "library-inject.so"):
        src = SLSSTEAM_INSTALL_DIR / fname
        if src.exists():
            try:
                shutil.copy2(src, dest / fname)
            except Exception as e:
                print_fn(Fore.YELLOW + f"Could not copy {fname} to Flatpak path: {e}" + Style.RESET_ALL)
    return True


def check_update_available() -> dict:
    """Check if a newer SLSsteam version is available on GitHub.

    Returns dict: {installed, installed_version, update_available, latest_version}
    """
    result = {
        "installed": is_installed(),
        "installed_version": None,
        "update_available": False,
        "latest_version": None,
    }
    version_file = Path.home() / ".local" / "share" / "SteaMidra" / "SLSsteam" / "VERSION"
    if version_file.exists():
        result["installed_version"] = version_file.read_text(encoding="utf-8").strip()
    try:
        import httpx
        resp = httpx.get(
            "https://api.github.com/repos/AceSLS/SLSsteam/releases/latest",
            timeout=10, follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "")
            result["latest_version"] = latest
            if result["installed_version"] and latest and result["installed_version"] != latest:
                result["update_available"] = True
    except Exception:
        pass
    return result


def api_send(command: str) -> bool:
    """Send command to running SLSsteam via named pipe."""
    if sys.platform != "linux":
        return False
    try:
        with open("/tmp/SLSsteam.API", "w") as f:
            f.write(command)
            f.flush()
        return True
    except OSError:
        return False
