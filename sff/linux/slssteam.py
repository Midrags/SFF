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
import shutil
import subprocess
import tempfile
from pathlib import Path

from colorama import Fore, Style

from sff.utils import root_folder

VERSION_FILE = Path.home() / ".local" / "share" / "SteaMidra" / "SLSsteam" / "VERSION"

SLSSTEAM_INSTALL_DIR = Path.home() / ".local" / "share" / "SLSsteam"
SLSSTEAM_CONFIG_DIR = Path.home() / ".config" / "SLSsteam"

FLATPAK_STEAM_DIR = (
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam"
)
FLATPAK_SLSSTEAM_INSTALL_DIR = (
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "SLSsteam"
)
FLATPAK_SLSSTEAM_CONFIG_DIR = (
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".config" / "SLSsteam"
)


def detect_steam_type() -> str:
    """Return 'flatpak' if Flatpak Steam is detected, 'native' otherwise."""
    if FLATPAK_STEAM_DIR.exists():
        return "flatpak"
    return "native"


def get_slssteam_install_dir(steam_type: str) -> Path:
    """Return the SLSsteam .so install directory for the given steam type."""
    if steam_type == "flatpak":
        return FLATPAK_SLSSTEAM_INSTALL_DIR
    return SLSSTEAM_INSTALL_DIR


def get_slssteam_config_dir(steam_type: str) -> Path:
    """Return the SLSsteam config directory for the given steam type."""
    if steam_type == "flatpak":
        return FLATPAK_SLSSTEAM_CONFIG_DIR
    return SLSSTEAM_CONFIG_DIR


def check_linux_deps(print_fn=print) -> bool:
    """Install libcurl4:i386 on Debian/Ubuntu if missing (mirrors h3adcr-b InstallDebianDeps).
    Returns True if deps are OK. Non-fatal on failure."""
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return True
    content = os_release.read_text(encoding="utf-8", errors="ignore")
    os_id = ""
    os_id_like = ""
    for line in content.splitlines():
        if line.startswith("ID="):
            os_id = line.split("=", 1)[1].strip().strip('"').lower()
        elif line.startswith("ID_LIKE="):
            os_id_like = line.split("=", 1)[1].strip().strip('"').lower()

    combined = f" {os_id} {os_id_like} "
    is_debian_like = " debian " in combined or " ubuntu " in combined
    if not is_debian_like:
        print_fn(
            Fore.YELLOW
            + f"Distro '{os_id}' is not Debian/Ubuntu-based. Skipping automatic libcurl install.\n"
            + "If SLSsteam fails to load, install the 32-bit libcurl package for your distro manually."
            + Style.RESET_ALL
        )
        return True

    pkg_name = "libcurl4"
    try:
        r = subprocess.run(
            ["apt-cache", "search", "--names-only", "^libcurl4t64$"],
            capture_output=True, text=True, timeout=15,
        )
        if "libcurl4t64" in r.stdout:
            pkg_name = "libcurl4t64"
    except Exception:
        pass
    target_pkg = f"{pkg_name}:i386"

    try:
        r = subprocess.run(
            ["dpkg", "-s", target_pkg],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            print_fn(Fore.GREEN + f"{target_pkg} already installed." + Style.RESET_ALL)
            return True
    except Exception:
        pass

    print_fn(Fore.YELLOW + f"{target_pkg} not found. Installing (requires sudo)..." + Style.RESET_ALL)
    try:
        arch_check = subprocess.run(
            ["dpkg", "--print-foreign-architectures"],
            capture_output=True, text=True, timeout=10,
        )
        if "i386" not in arch_check.stdout:
            print_fn("Adding i386 architecture...")
            subprocess.run(["sudo", "dpkg", "--add-architecture", "i386"], timeout=30)
            subprocess.run(["sudo", "apt-get", "update", "-qq"], timeout=120)
    except Exception as e:
        print_fn(Fore.YELLOW + f"Could not add i386 architecture: {e}" + Style.RESET_ALL)

    try:
        proc = subprocess.Popen(["sudo", "apt-get", "install", "-y", target_pkg])
        proc.wait()
        if proc.returncode == 0:
            print_fn(Fore.GREEN + f"{target_pkg} installed successfully." + Style.RESET_ALL)
            return True
        print_fn(
            Fore.YELLOW
            + f"Failed to install {target_pkg} (exit {proc.returncode}).\n"
            + f"SLSsteam may not work correctly. Install manually: sudo apt-get install {target_pkg}"
            + Style.RESET_ALL
        )
        return False
    except Exception as e:
        print_fn(
            Fore.YELLOW
            + f"Could not install {target_pkg}: {e}\n"
            + f"Install manually: sudo apt-get install {target_pkg}"
            + Style.RESET_ALL
        )
        return False


def _disable_path_injection(steam_type: str, print_fn=print) -> None:
    """Rename old path-based injection file if present (h3adcr-b DisableSLSsteamPath logic)."""
    install_dir = get_slssteam_install_dir(steam_type)
    old_path = install_dir / "path" / "steam"
    if old_path.exists():
        try:
            old_path.rename(str(old_path) + ".bak")
            print_fn(Fore.YELLOW + f"Renamed old path injection: {old_path}" + Style.RESET_ALL)
        except Exception as e:
            print_fn(Fore.YELLOW + f"Could not rename old path injection: {e}" + Style.RESET_ALL)


def is_installed() -> bool:
    steam_type = detect_steam_type()
    return (get_slssteam_install_dir(steam_type) / "SLSsteam.so").exists()


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

    steam_type = detect_steam_type()
    install_dir = get_slssteam_install_dir(steam_type)
    ld_audit = f"{install_dir}/library-inject.so:{install_dir}/SLSsteam.so"
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
    patch_steam_sh(steam_path, print_fn)
    create_steam_cfg(steam_path, print_fn)
    print_fn(Fore.GREEN + "SLSsteam installed successfully." + Style.RESET_ALL)
    return True


def _setup_config_from_extracted(extract_dir: Path, steam_type: str = "native") -> bool:
    """Set up SLSsteam config from extracted archive's res/config.yaml.
    Falls back to bundled template if not found. No-ops if user config exists."""
    config_dir = get_slssteam_config_dir(steam_type)
    config_path = config_dir / "config.yaml"
    if config_path.exists():
        return False
    config_dir.mkdir(parents=True, exist_ok=True)
    template = next(extract_dir.rglob("res/config.yaml"), None) if extract_dir.exists() else None
    if template and template.exists():
        shutil.copy2(template, config_path)
        return True
    fallback = get_bundle_dir() / "res" / "config.yaml"
    if fallback.exists():
        shutil.copy2(fallback, config_path)
        return True
    return False



def get_installed_version() -> str | None:
    """Return the installed SLSsteam version string, or None if not tracked."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip() or None
    return None


def check_update_available(print_fn=print) -> dict:
    """Check GitHub for a newer SLSsteam release.
    Returns dict with keys: installed, latest, update_available."""
    installed = get_installed_version()
    result = {"installed": installed, "latest": None, "update_available": False}
    try:
        import httpx
        resp = httpx.get(
            "https://api.github.com/repos/AceSLS/SLSsteam/releases/latest",
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "")
        result["latest"] = latest
        if installed and latest and installed != latest:
            result["update_available"] = True
    except Exception as e:
        print_fn(Fore.YELLOW + f"Could not check for SLSsteam updates: {e}" + Style.RESET_ALL)
    return result


def install_from_github(steam_path: Path, print_fn=print) -> bool:
    try:
        import httpx
    except ImportError:
        print_fn(Fore.RED + "httpx not available." + Style.RESET_ALL)
        return False

    print_fn("\n[1/4] Checking system dependencies...")
    check_linux_deps(print_fn)

    steam_type = detect_steam_type()
    install_dir = get_slssteam_install_dir(steam_type)
    print_fn(f"Detected Steam type: {steam_type}")

    print_fn("\n[2/4] Fetching latest SLSsteam release from GitHub...")
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

    print_fn("\n[3/4] Extracting SLSsteam...")
    extract_dir = Path(tempfile.gettempdir()) / "slssteam_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    seven_zip = shutil.which("7z") or shutil.which("7za")
    if not seven_zip:
        print_fn(Fore.RED + "7z/7za not found. Install p7zip-full: sudo apt-get install p7zip-full" + Style.RESET_ALL)
        archive_path.unlink(missing_ok=True)
        return False

    try:
        result = subprocess.run(
            [seven_zip, "x", str(archive_path), f"-o{extract_dir}", "-y"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            if not (extract_dir / "bin").exists():
                print_fn(Fore.RED + "Extraction failed and bin/ dir not found." + Style.RESET_ALL)
                return False
            print_fn(Fore.YELLOW + "7z exited non-zero but bin/ found — continuing." + Style.RESET_ALL)
    except Exception as e:
        print_fn(Fore.RED + f"Extraction error: {e}" + Style.RESET_ALL)
        return False
    finally:
        archive_path.unlink(missing_ok=True)

    bin_dir = extract_dir / "bin"
    if not bin_dir.exists() or not (bin_dir / "SLSsteam.so").exists():
        bin_dirs = list(extract_dir.rglob("bin"))
        bin_dir = next((d for d in bin_dirs if (d / "SLSsteam.so").exists()), None)
    if not bin_dir or not (bin_dir / "SLSsteam.so").exists():
        print_fn(Fore.RED + "SLSsteam.so not found in extracted archive." + Style.RESET_ALL)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    _disable_path_injection(steam_type, print_fn)

    print_fn("\n[4/4] Installing SLSsteam .so files...")
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        for so_name in ("library-inject.so", "SLSsteam.so"):
            src_so = bin_dir / so_name
            if src_so.exists():
                shutil.copy2(src_so, install_dir / so_name)
                print_fn(Fore.GREEN + f"  Installed {so_name}" + Style.RESET_ALL)
            else:
                print_fn(Fore.YELLOW + f"  {so_name} not found in bin/ — skipping." + Style.RESET_ALL)
    except Exception as e:
        print_fn(Fore.RED + f"Install error: {e}" + Style.RESET_ALL)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    _setup_config_from_extracted(extract_dir, steam_type)
    patch_steam_sh(steam_path, print_fn)
    create_steam_cfg(steam_path, print_fn)

    version = data.get("tag_name", "unknown")
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(version, encoding="utf-8")

    shutil.rmtree(extract_dir, ignore_errors=True)

    print_fn(
        Fore.GREEN
        + f"\nSLSsteam {version} installed successfully!"
        + Style.RESET_ALL
        + "\n"
        + Fore.YELLOW
        + "NOTE: When launching Steam you will see 'wrong ELF class: ELFCLASS32' messages.\n"
        + "These are completely normal — 64-bit processes reject the 32-bit .so, which is\n"
        + "expected behavior. SLSsteam works via Steam's 32-bit processes and is active.\n"
        + "\nPlease launch Steam to activate SLSsteam and generate its config file."
        + Style.RESET_ALL
    )
    return True


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
            data_yaml = yaml.safe_load(resp.text)
            hashes = []
            for entries in data_yaml.get("SafeModeHashes", {}).values():
                if isinstance(entries, list):
                    for entry in entries:
                        parts = str(entry).strip().split()
                        if parts:
                            hashes.append(parts[0])
            if hashes and sha256 not in hashes:
                result["mismatch"] = True
    except Exception:
        pass

    return result
