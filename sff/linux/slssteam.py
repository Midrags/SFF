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
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from colorama import Fore, Style

# Guard: this entire module is Linux-only. All public functions return early on non-Linux.
_IS_LINUX = sys.platform == "linux"


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

_SYSTEM_7Z_NAMES = ("7zz", "7z", "7za")
_SYSTEM_TOOL_ENV_DROP = (
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "LD_AUDIT",
    "PYTHONHOME",
    "PYTHONPATH",
    "QT_PLUGIN_PATH",
    "QML2_IMPORT_PATH",
    "APPIMAGE",
    "APPDIR",
    "OWD",
    "ARGV0",
    "APPIMAGE_UUID",
)


def _clean_system_tool_env() -> dict:
    env = os.environ.copy()
    for key in _SYSTEM_TOOL_ENV_DROP:
        env.pop(key, None)
    return env


def _find_7z_tool() -> str | None:
    for name in _SYSTEM_7Z_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def _has_slssteam_payload(extract_dir: Path) -> bool:
    return extract_dir.exists() and any(extract_dir.rglob("SLSsteam.so"))


def _reset_extract_dir(extract_dir: Path) -> None:
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)


def _extract_with_py7zr(archive_path: Path, extract_dir: Path, print_fn=print) -> bool:
    try:
        import py7zr
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=extract_dir)
        return True
    except ImportError:
        print_fn(Fore.YELLOW + "py7zr not available, trying system 7z." + Style.RESET_ALL)
        return False
    except Exception as e:
        print_fn(Fore.YELLOW + f"py7zr extraction failed, trying system 7z: {e}" + Style.RESET_ALL)
        return False


def _extract_with_system_7z(archive_path: Path, extract_dir: Path, print_fn=print) -> bool:
    seven_zip = _find_7z_tool()
    if not seven_zip:
        print_fn(
            Fore.RED
            + "7zz/7z/7za not found. Install 7-Zip for your distro "
              "(Arch/CachyOS: sudo pacman -S 7zip, Debian/Ubuntu: sudo apt install p7zip-full)."
            + Style.RESET_ALL
        )
        return False

    env = _clean_system_tool_env()
    last_stdout = ""
    last_stderr = ""
    last_code = None
    for attempt in range(2):
        try:
            result = subprocess.run(
                [seven_zip, "x", str(archive_path), f"-o{extract_dir}", "-y"],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
        except Exception as e:
            print_fn(Fore.YELLOW + f"7z spawn failed: {e}" + Style.RESET_ALL)
            return False

        last_code = result.returncode
        last_stdout = result.stdout or ""
        last_stderr = result.stderr or ""
        if result.returncode == 0 or _has_slssteam_payload(extract_dir):
            if result.returncode != 0:
                print_fn(Fore.YELLOW + "7z exited non-zero but SLSsteam files were extracted, continuing." + Style.RESET_ALL)
            return True

        stdout_tail = last_stdout[-2048:]
        stderr_tail = last_stderr[-2048:]
        print_fn(
            Fore.YELLOW
            + f"7z exit={result.returncode} archive={archive_path} dest={extract_dir}\n"
            + f"stdout(last 2k): {stdout_tail}\nstderr(last 2k): {stderr_tail}"
            + Style.RESET_ALL
        )
        if attempt == 0:
            import time as _time
            _time.sleep(0.5)

    if "rl_print_keybinding" in last_stderr or "symbol lookup error" in last_stderr:
        print_fn(
            Fore.RED
            + "System 7z failed with a readline symbol error even after cleaning the launch env. "
              "Install/repair the distro 7-Zip package and retry."
            + Style.RESET_ALL
        )
    else:
        print_fn(
            Fore.RED
            + f"Extraction failed and SLSsteam files were not found (last 7z exit={last_code})."
            + Style.RESET_ALL
        )
    return False


def _extract_slssteam_archive(archive_path: Path, extract_dir: Path, print_fn=print) -> bool:
    _reset_extract_dir(extract_dir)
    if _extract_with_py7zr(archive_path, extract_dir, print_fn) and _has_slssteam_payload(extract_dir):
        return True
    _reset_extract_dir(extract_dir)
    return _extract_with_system_7z(archive_path, extract_dir, print_fn)


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


def _remove_pacman_slssteam(print_fn=print) -> None:
    """Remove system-managed slssteam/slssteam-git pacman packages on Arch-like distros.
    Call this only AFTER a fresh archive is already downloaded and ready to install,
    so that a failed GitHub download never leaves the user without SLSsteam."""
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return
    content = os_release.read_text(encoding="utf-8", errors="ignore")
    os_id = ""
    os_id_like = ""
    for line in content.splitlines():
        if line.startswith("ID="):
            os_id = line.split("=", 1)[1].strip().strip('"').lower()
        elif line.startswith("ID_LIKE="):
            os_id_like = line.split("=", 1)[1].strip().strip('"').lower()
    combined = f" {os_id} {os_id_like} "
    is_arch_like = " arch " in combined or " cachyos " in combined
    if not is_arch_like:
        return
    try:
        r = subprocess.run(
            ["pacman", "-Qq"],
            capture_output=True, text=True, timeout=10,
        )
        installed = [p.strip() for p in r.stdout.splitlines()]
        to_remove = [p for p in installed if p in ("slssteam", "slssteam-git")]
        if to_remove:
            print_fn(Fore.YELLOW + f"Removing pacman SLSsteam packages: {' '.join(to_remove)}" + Style.RESET_ALL)
            subprocess.run(["sudo", "pacman", "-Rs", "--noconfirm"] + to_remove, timeout=60)
    except Exception as e:
        print_fn(Fore.YELLOW + f"Could not check/remove Arch SLSsteam packages: {e}" + Style.RESET_ALL)


def check_linux_deps(print_fn=print) -> bool:
    """Install libcurl4:i386 on Debian/Ubuntu if missing.
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
    if not _IS_LINUX:
        return False
    steam_type = detect_steam_type()
    return (get_slssteam_install_dir(steam_type) / "SLSsteam.so").exists()


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
        os.chmod(steam_sh, 0o644)
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


def _setup_config_from_extracted(extract_dir: Path, steam_type: str = "native") -> bool:
    """Copy res/config.yaml from the extracted archive to the SLSsteam config dir.
    No-ops if the config file already exists."""
    config_dir = get_slssteam_config_dir(steam_type)
    config_path = config_dir / "config.yaml"
    if config_path.exists():
        return False
    config_dir.mkdir(parents=True, exist_ok=True)
    template = next(extract_dir.rglob("res/config.yaml"), None) if extract_dir.exists() else None
    if template and template.exists():
        shutil.copy2(template, config_path)
        return True
    return False


def patch_slssteam_config(steam_type: str, print_fn=print) -> bool:
    """Patch SLSsteam config.yaml to enable PlayNotOwnedGames, SafeMode, and notifications.
    Also ensures all required SLSsteam fields exist. Mirrors h3adcr-b's editconfig() function.
    Skips if .headcrabd marker exists."""
    config_dir = get_slssteam_config_dir(steam_type)
    config_path = config_dir / "config.yaml"
    marker = config_dir / ".headcrabd"

    if marker.exists():
        return False  # already patched by headcrab or us
    if not config_path.exists():
        return False

    try:
        import re
        text = config_path.read_text(encoding="utf-8")
        patches = {
            r"^PlayNotOwnedGames:.*": "PlayNotOwnedGames: yes",
            r"^SafeMode:.*":         "SafeMode: no",
            r"^WarnHashMissmatch:.*": "WarnHashMissmatch: yes",
            r"^NotifyInit:.*":       "NotifyInit: yes",
            r"^Notifications:.*":    "Notifications: yes",
        }
        for pattern, replacement in patches.items():
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
        # Ensure all required SLSsteam fields exist in the config
        from sff.linux.yaml_config import _patch_missing_slssteam_fields
        patched = _patch_missing_slssteam_fields(config_path, text)
        if patched is not None:
            text = patched
        config_path.write_text(text, encoding="utf-8")
        marker.write_text("patched by SteaMidra\n", encoding="utf-8")
        print_fn(Fore.GREEN + "SLSsteam config.yaml patched (PlayNotOwnedGames, SafeMode off / WarnHashMissmatch on, Notifications enabled, missing fields filled)." + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.YELLOW + f"Could not patch SLSsteam config.yaml: {e}" + Style.RESET_ALL)
        return False



def get_installed_version() -> str | None:
    """Return the installed SLSsteam version string, or None if not tracked.

    Returns None when neither our VERSION file nor any SLSsteam .so is present.
    Returns a sentinel `"unknown"` when the .so is found but no VERSION file
    exists — covers users who installed via pacman, h3adcr-b, or by hand. The
    sentinel makes the update check trigger and rewrite VERSION on the next
    install, transitioning ad-hoc setups onto our managed update path.
    """
    if VERSION_FILE.exists():
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    # No version file. Detect a foreign install via .so presence.
    for steam_type in ("flatpak", "native"):
        if (get_slssteam_install_dir(steam_type) / "SLSsteam.so").exists():
            return "unknown"
    return None


def check_update_available(print_fn=print) -> dict:
    """Check GitHub for a newer SLSsteam release.
    Returns dict with keys: installed, latest, update_available."""
    if not _IS_LINUX:
        return {"installed": None, "latest": None, "update_available": False}
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
        # update_available when:
        #  - we have a tracked version and it differs from latest, OR
        #  - we found a foreign install (installed == "unknown") so we can
        #    transition it onto our managed path.
        if latest and installed and installed != latest:
            result["update_available"] = True
    except Exception as e:
        print_fn(Fore.YELLOW + f"Could not check for SLSsteam updates: {e}" + Style.RESET_ALL)
    return result


_HEADCRAB_URL = "https://raw.githubusercontent.com/Deadboy666/h3adcr-b/refs/heads/main/headcrab.sh"


def _cr_filter(lines: list[str]) -> list[str]:
    """Strip CloudRedirect-related code from headcrab.sh.

    Removes entire function definitions that reference cloudredirect,
    plus any lines that reference CloudRedirect variables or URLs.
    Also strips the cloudredirect variable declaration so if/else blocks
    that check it don't break syntax.
    """
    out: list[str] = []
    skip_until_end_of_block = 0  # brace depth when we started skipping
    for i, line in enumerate(lines):
        lower = line.lower()
        # Strip variable declarations referencing cloudredirect
        if "cloudredirect" in lower and ('="' in line or "='" in line):
            if "cloudredirectdir" in lower or "flatpakcloudredirectdir" in lower:
                out.append(line)  # keep path variable, strip the value later
                continue
            out.append("# [SteaMidra] CloudRedirect line removed\n")
            continue
        # Strip wget/curl downloads of CR files
        if ("wget" in lower or "curl" in lower) and ("cloud_redirect" in lower or "cloudredirect" in lower):
            out.append("# [SteaMidra] CloudRedirect download blocked\n")
            continue
        # Strip flatpak CR install commands (but NOT directory checks)
        if "flatpak" in lower and ("cloudredirect" in lower or "cloud_redirect" in lower) and "install" in lower:
            out.append("# [SteaMidra] CloudRedirect flatpak blocked\n")
            continue
        # Strip lines calling CR functions directly
        if lower.strip() in ("crinstall", "crinstall;", "wherecr_install", "crconfigcheck"):
            out.append("# [SteaMidra] CloudRedirect call blocked\n")
            continue
        # Strip crconfigcheck and crinstall function calls with ;
        out.append(line)
    return out


def _cleanup_headcrab_zombies():
    """Kill leftover headcrab child processes (dlm, dgsc, wget) that survive script exit."""
    for name in ("dlm", "dgsc", "wget"):
        try:
            subprocess.run(["pkill", "-f", name], timeout=5, capture_output=True)
        except Exception:
            pass


def setup_via_headcrab(steam_path: Path, print_fn=print) -> bool:
    """Download and run headcrab.sh to install SLSsteam. Primary method."""
    if not _IS_LINUX:
        return False
    try:
        import httpx
    except ImportError:
        print_fn(Fore.RED + "httpx not available." + Style.RESET_ALL)
        return False

    print_fn(Fore.CYAN + "\n[headcrab] Downloading headcrab installer..." + Style.RESET_ALL)
    script_path = Path(tempfile.gettempdir()) / "headcrab_install.sh"
    try:
        resp = httpx.get(_HEADCRAB_URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        lines = resp.text.splitlines(keepends=True)
        filtered = _cr_filter(lines)
        script_path.write_text("".join(filtered), encoding="utf-8")
    except Exception as e:
        print_fn(Fore.RED + f"headcrab download failed: {e}" + Style.RESET_ALL)
        return False

    try:
        script_path.chmod(0o755)
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        print_fn(Fore.CYAN + "[headcrab] Running installer (this may take a few minutes)..." + Style.RESET_ALL)
        proc = subprocess.Popen(
            ["bash", str(script_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, cwd=str(script_path.parent),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print_fn(line)
        proc.wait()
        ok = proc.returncode == 0
        _cleanup_headcrab_zombies()
        if ok:
            print_fn(Fore.GREEN + "\n[headcrab] SLSsteam installation completed." + Style.RESET_ALL)
            steam_type = detect_steam_type()
            _setup_config_from_extracted(Path(tempfile.gettempdir()) / "headcrab_extract", steam_type)
            patch_slssteam_config(steam_type, print_fn)
            patch_steam_sh(steam_path, print_fn)
            create_steam_cfg(steam_path, print_fn)
        else:
            print_fn(Fore.YELLOW + f"\n[headcrab] Installer exited with code {proc.returncode}" + Style.RESET_ALL)
        return ok
    except Exception as e:
        print_fn(Fore.RED + f"headcrab failed: {e}" + Style.RESET_ALL)
        return False
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass


_HEADCRAB_RESET_URL = "https://headcrab.pages.dev/reset"
_HEADCRAB_PATCH_URL = "https://headcrab.pages.dev"


def fix_hash_mismatch(steam_path: Path, print_fn=print) -> bool:
    """Fix 'Unknown steamclient.so hash' error by resetting + repatching SLSsteam.

    1. Kill Steam
    2. Run headcrab reset (downgrades Steam bootstrap to compatible version)
    3. Launch Steam briefly (reconfigures bootstrap)
    4. Kill Steam again
    5. Run headcrab install (re-patches SLSsteam)
    6. Re-patch config, steam.sh, steam.cfg

    Follows the headcrab wiki troubleshooting guide.
    """
    if not _IS_LINUX:
        return False
    try:
        import httpx
    except ImportError:
        print_fn(Fore.RED + "httpx not available." + Style.RESET_ALL)
        return False

    steam_type = detect_steam_type()

    # 1. Kill Steam
    print_fn(Fore.CYAN + "\n[hashfix] Stopping Steam..." + Style.RESET_ALL)
    try:
        from sff.linux.steam_process import kill_steam as _kill_steam
        _kill_steam(print_fn)
    except Exception as e:
        print_fn(Fore.YELLOW + f"  Could not kill Steam: {e}" + Style.RESET_ALL)

    # 2. Run headcrab reset (downgrades Steam client bootstrap)
    print_fn(Fore.CYAN + "[hashfix] Running headcrab reset (downgrading Steam bootstrap)..." + Style.RESET_ALL)
    try:
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        proc = subprocess.run(
            ["bash", "-c", f"curl -fsSL {_HEADCRAB_RESET_URL} | bash"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if proc.stdout:
            for line in proc.stdout.splitlines():
                if line.strip():
                    print_fn(line.strip())
        if proc.stderr:
            for line in proc.stderr.splitlines():
                if line.strip():
                    print_fn(Fore.YELLOW + line.strip() + Style.RESET_ALL)
        if proc.returncode != 0:
            print_fn(Fore.YELLOW + f"[hashfix] Reset exited with code {proc.returncode}" + Style.RESET_ALL)
    except Exception as e:
        print_fn(Fore.YELLOW + f"[hashfix] Reset failed: {e}" + Style.RESET_ALL)
        return False

    # 3. Launch Steam briefly to reconfigure bootstrap
    print_fn(Fore.CYAN + "[hashfix] Launching Steam briefly to reconfigure bootstrap..." + Style.RESET_ALL)
    try:
        from sff.linux.steam_process import start_steam as _start_steam
        _start_steam(print_fn)
        print_fn("  Waiting 30 seconds for Steam to initialise...")
        import time as _time
        _time.sleep(30)
    except Exception as e:
        print_fn(Fore.YELLOW + f"  Steam launch failed: {e}" + Style.RESET_ALL)

    # 4. Kill Steam again
    print_fn(Fore.CYAN + "[hashfix] Stopping Steam again..." + Style.RESET_ALL)
    try:
        from sff.linux.steam_process import kill_steam as _kill_steam2
        _kill_steam2(print_fn)
    except Exception:
        pass

    # 5. Run headcrab install to repatch
    print_fn(Fore.CYAN + "[hashfix] Running headcrab install to repatch SLSsteam..." + Style.RESET_ALL)
    try:
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        proc = subprocess.run(
            ["bash", "-c", f"curl -fsSL {_HEADCRAB_PATCH_URL} | bash"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if proc.stdout:
            for line in proc.stdout.splitlines():
                if line.strip():
                    print_fn(line.strip())
        if proc.stderr:
            for line in proc.stderr.splitlines():
                if line.strip():
                    print_fn(Fore.YELLOW + line.strip() + Style.RESET_ALL)
        if proc.returncode != 0:
            print_fn(Fore.YELLOW + f"[hashfix] Repatch exited with code {proc.returncode}" + Style.RESET_ALL)
    except Exception as e:
        print_fn(Fore.YELLOW + f"[hashfix] Repatch failed: {e}" + Style.RESET_ALL)
        return False

    # 6. Re-patch config, steam.sh, steam.cfg
    print_fn(Fore.CYAN + "[hashfix] Re-patching SLSsteam configuration..." + Style.RESET_ALL)
    _cleanup_headcrab_zombies()
    patch_slssteam_config(steam_type, print_fn)
    patch_steam_sh(steam_path, print_fn)
    create_steam_cfg(steam_path, print_fn)

    print_fn(Fore.GREEN + "[hashfix] SLSsteam hash issue fixed. Launch Steam normally." + Style.RESET_ALL)
    return True


def install_from_github(steam_path: Path, print_fn=print) -> bool:
    if not _IS_LINUX:
        return False
    try:
        import httpx
    except ImportError:
        print_fn(Fore.RED + "httpx not available." + Style.RESET_ALL)
        return False

    print_fn("\n[1/4] Checking system dependencies...")
    check_linux_deps(print_fn)
    # Note: Arch pacman SLSsteam removal happens at step [3.5/4], after the archive
    # is verified. This prevents a failed download from leaving the user without SLSsteam.

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

    try:
        if not _extract_slssteam_archive(archive_path, extract_dir, print_fn):
            return False
    except Exception as e:
        # Bare exception log used to be one line. Now print the full traceback
        # tail too because users pasted "Extraction error: " with nothing
        # after it. zipfile / 7z subprocess failures need the full stack.
        import traceback as _tb
        print_fn(Fore.RED + f"Extraction error: {e}\n{_tb.format_exc()[-2048:]}" + Style.RESET_ALL)
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

    print_fn("\n[3.5/4] Removing any system-packaged SLSsteam (Arch only)...")
    _remove_pacman_slssteam(print_fn)

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
    patch_slssteam_config(steam_type, print_fn)
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


def check_and_notify_update(print_fn=print) -> None:
    """Run a background install/upgrade on Linux startup.

    Three branches:
      1. Already up to date  -> no output.
      2. Tracked install but newer release available -> install latest.
      3. Not installed yet (first run, or installed by another tool but no
         VERSION file)  -> install latest. This is the path that fixes the
         common "Game injection manager not configured" message: a fresh user
         had no way to discover the manual setup menu.

    Never raises. Prints what it's doing only when something is actually
    happening, so silent boots stay silent.
    """
    if not _IS_LINUX:
        return
    try:
        info = check_update_available(print_fn=lambda _: None)  # silent fetch
        installed = info.get("installed")
        latest = info.get("latest")

        if not latest:
            # GitHub unreachable. Don't spam an error on every boot.
            return

        from pathlib import Path as _Path
        if detect_steam_type() == "flatpak":
            steam_path = _Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam"
        else:
            steam_path = _Path.home() / ".steam" / "steam"

        if not installed:
            print_fn(
                Fore.CYAN
                + f"SLSsteam not installed. Auto-installing latest ({latest})..."
                + Style.RESET_ALL
            )
            install_from_github(steam_path, print_fn)
            return

        if info.get("update_available"):
            print_fn(
                Fore.YELLOW
                + f"SLSsteam update available: {installed} -> {latest}. Installing automatically..."
                + Style.RESET_ALL
            )
            install_from_github(steam_path, print_fn)
            return

        # Already up to date — say nothing.
    except Exception:
        pass
