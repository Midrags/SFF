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

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Tuple

from colorama import Fore, Style

from sff.dotnet_utils import get_dotnet_path
from sff.utils import root_folder

KEYS_TMP = Path(tempfile.gettempdir()) / "mistwalker_keys.vdf"
MANIFESTS_TMP = Path(tempfile.gettempdir()) / "mistwalker_manifests"


def _find_openssl_lib_dir(dotnet_root: str) -> str:
    """Return the directory containing libcrypto.so.3 / libssl.so.3
    from the bundled .NET runtime, if present. DDMod needs these for
    HTTPS depot downloads on distros that don't ship them system-wide.
    """
    import glob as _glob
    pattern = os.path.join(dotnet_root, "shared", "Microsoft.NETCore.App", "*")
    for runtime_dir in sorted(_glob.glob(pattern), reverse=True):
        candidate = os.path.join(runtime_dir)
        libcrypto = os.path.join(candidate, "libcrypto.so.3")
        if os.path.isfile(libcrypto):
            return candidate
    return ""


def _add_bundled_openssl_to_env(env: dict, dotnet_root: str) -> None:
    lib_dir = _find_openssl_lib_dir(dotnet_root)
    if not lib_dir:
        return
    existing = env.get("LD_LIBRARY_PATH", "")
    if lib_dir not in existing.split(os.pathsep) if existing else True:
        env["LD_LIBRARY_PATH"] = f"{lib_dir}{os.pathsep}{existing}" if existing else lib_dir


def get_deps_dir() -> Path:
    return root_folder() / "third_party" / "DDMod"


def get_ddmod_dll() -> Path:
    return get_deps_dir() / "DepotDownloaderMod.dll"


def _copy_manifests_to_temp(steam_path: Path, manifests: dict) -> None:
    MANIFESTS_TMP.mkdir(parents=True, exist_ok=True)

    # Check both depotcache locations — SteaMidra syncs manifests to config/depotcache
    # on Linux, while steamapps/depotcache is the standard Windows location.
    depotcache_candidates = [
        steam_path / "steamapps" / "depotcache",
        steam_path / "config" / "depotcache",
    ]

    for depot_id, manifest_id in manifests.items():
        filename = f"{depot_id}_{manifest_id}.manifest"
        dst = MANIFESTS_TMP / filename
        if dst.exists():
            continue  # already copied
        for depotcache in depotcache_candidates:
            src = depotcache / filename
            if src.exists():
                shutil.copy2(src, dst)
                break

    # Also check the canonical staging folder (where ZIP-based providers
    # like Hubcap / oureveryday / Ryuu drop manifests after extraction).
    # Path.cwd() was wrong on AppImage launches and Web UI workers.
    from sff.utils import manifests_staging_dir
    staging = manifests_staging_dir()
    if staging.exists():
        for depot_id, manifest_id in manifests.items():
            filename = f"{depot_id}_{manifest_id}.manifest"
            src = staging / filename
            dst = MANIFESTS_TMP / filename
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)


def _read_process_output(proc: subprocess.Popen, print_fn, depot_timeout=600) -> None:
    """Read subprocess stdout with a per-depot timeout (default 10 min).

    Spawns a reader thread so a hanging DDMod process doesn't freeze the
    entire download chain. On timeout, kills the process and returns.
    """
    import queue as _q
    import threading as _t
    if not proc.stdout:
        return
    pre_alloc_count = 0
    validate_count = 0
    progress_count = 0
    last_pre_alloc_t = 0.0
    last_progress_t = 0.0
    last_validate_t = 0.0
    last_progress_pct: float = -1.0
    _SUMMARY_INTERVAL = 2.0
    _lineq: _q.Queue = _q.Queue()
    _stop = _t.Event()

    def _reader():
        try:
            for raw_line in proc.stdout:
                if _stop.is_set():
                    break
                _lineq.put(raw_line)
        except ValueError:
            pass
        finally:
            _lineq.put(None)

    _reader_t = _t.Thread(target=_reader, daemon=True)
    _reader_t.start()

    deadline = time.monotonic() + depot_timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print_fn(Fore.RED + f"\n[timeout] Depot download exceeded {depot_timeout}s, killing process" + Style.RESET_ALL)
            _stop.set()
            proc.kill()
            break
        try:
            raw_line = _lineq.get(timeout=min(remaining, 0.5))
        except _q.Empty:
            if proc.poll() is not None:
                _stop.set()
                raw_line = _lineq.get() if not _lineq.empty() else None
                if raw_line is None:
                    break
            else:
                continue
        if raw_line is None:
            break
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        now = time.monotonic()

        if line.startswith("Pre-allocating"):
            pre_alloc_count += 1
            if now - last_pre_alloc_t >= _SUMMARY_INTERVAL:
                print_fn(f"[Pre-allocating files... {pre_alloc_count} so far]")
                last_pre_alloc_t = now
            continue

        lower = line.lower()
        if "validating chunk" in lower or lower.startswith("validated "):
            validate_count += 1
            if now - last_validate_t >= _SUMMARY_INTERVAL:
                print_fn(f"[Validating chunks... {validate_count} so far]")
                last_validate_t = now
            continue

        m = _DDMOD_PROGRESS_RE.match(line)
        if m:
            progress_count += 1
            try:
                pct = float(m.group(1))
            except ValueError:
                pct = -1.0
            crossed_pct = (pct >= 0 and (last_progress_pct < 0
                                         or int(pct) != int(last_progress_pct)))
            elapsed = now - last_progress_t >= _SUMMARY_INTERVAL
            if crossed_pct or elapsed:
                print_fn(line)
                last_progress_pct = pct
                last_progress_t = now
            continue

        print_fn(line)

    _reader_t.join(timeout=3)

    if pre_alloc_count > 0:
        print_fn(f"[Pre-allocation complete: {pre_alloc_count} file(s)]")
    if validate_count > 0:
        print_fn(f"[Validation complete: {validate_count} chunk(s)]")


# DDMod's progress lines always start with optional whitespace, then a
# decimal percent followed by '%'. Tightened to require the percent to
# anchor at the start so we don't match unrelated lines that happen to
# contain a percent (e.g. depot summaries).
_DDMOD_PROGRESS_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%\s")


def _calculate_dir_size(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def run_download(
    game_data: dict,
    selected_depots: list,
    dest_path: Path,
    steam_path: Path,
    print_fn=print,
    os_name: str | None = None,
) -> Tuple[bool, int]:
    appid = str(game_data["appid"])
    depots = game_data.get("depots", {})
    manifests = dict(game_data.get("manifests", {}) or {})
    installdir = game_data.get("installdir") or f"App_{appid}"

    # Auto-fill manifests from the staging dir for any selected depot
    # the caller did not pin a manifest for. The staging dir is what
    # ZIP-based providers (Hubcap / oureveryday / Ryuu) drop manifests
    # into after extraction. Without this, DDMod gets called with
    # `-depot N` and no `-manifest N` and falls back to anonymous CDN
    # fetch, which 401s on most owned-game depots and aborts. The user
    # ends up with redists downloaded and zero game files.
    try:
        from sff.utils import manifests_staging_dir
        staging = manifests_staging_dir()
        if staging.exists():
            staged: dict[str, str] = {}
            for f in staging.glob("*.manifest"):
                parts = f.stem.split("_", 1)
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    staged[parts[0]] = parts[1]
            for depot_id in selected_depots:
                key = str(depot_id)
                if key not in manifests and key in staged:
                    manifests[key] = staged[key]
                    print_fn(
                        Fore.CYAN
                        + f"  [staging] picked up manifest {staged[key]} for depot {key}"
                        + Style.RESET_ALL
                    )
    except Exception as exc:
        print_fn(
            Fore.YELLOW
            + f"  [staging] could not scan staging dir ({exc}); continuing without auto-fill"
            + Style.RESET_ALL
        )
    game_data["manifests"] = manifests

    # ── Linux native downloader (no .NET needed) ──────────────────
    if sys.platform.startswith("linux"):
        try:
            from sff.native_downloader import download_depot as _native_dl
            print_fn(Fore.CYAN + "\n[Native] Starting Steam CDN download (no .NET required)" + Style.RESET_ALL)
            all_ok = True
            total_size = 0
            for depot_id in selected_depots:
                depot_id_str = str(depot_id)
                manifest_id = manifests.get(depot_id_str)
                if not manifest_id:
                    print_fn(Fore.YELLOW + f"Depot {depot_id_str}: no manifest, skipping" + Style.RESET_ALL)
                    continue
                key_data = depots.get(depot_id_str, {})
                key = key_data.get("key", "") if isinstance(key_data, dict) else ""
                if not key:
                    print_fn(Fore.YELLOW + f"Depot {depot_id_str}: no key, skipping" + Style.RESET_ALL)
                    continue
                print_fn(
                    Fore.CYAN
                    + f"\n--- Downloading depot {depot_id_str} (native) ---"
                    + Style.RESET_ALL
                )
                try:
                    manifest_path = None
                    if manifest_id:
                        mf = MANIFESTS_TMP / f"{depot_id_str}_{manifest_id}.manifest"
                        if mf.exists():
                            manifest_path = mf
                    ok, size = _native_dl(
                        app_id, depot_id_str, manifest_id, key, download_dir,
                        print_fn=print_fn, os_filter=os_name or "linux",
                        steam_path=steam_path,
                        manifest_path=manifest_path,
                    )
                    if ok:
                        total_size += size
                        print_fn(Fore.GREEN + f"Depot {depot_id_str} downloaded ({size:,} bytes)" + Style.RESET_ALL)
                    else:
                        all_ok = False
                except Exception as e:
                    print_fn(Fore.RED + f"Native download failed for depot {depot_id_str}: {e}" + Style.RESET_ALL)
                    logger.exception("Native downloader: depot %s failed", depot_id_str)
                    all_ok = False
            try:
                KEYS_TMP.unlink(missing_ok=True)
            except Exception:
                pass
            total_size = _calculate_dir_size(download_dir)
            print_fn(Fore.CYAN + f"Total size on disk: {total_size:,} bytes" + Style.RESET_ALL)
            return all_ok, total_size
        except ImportError:
            print_fn(Fore.YELLOW + "[Native] Native downloader not available, falling back to DDMod" + Style.RESET_ALL)
        except Exception as e:
            print_fn(Fore.YELLOW + f"[Native] Init failed ({e}), falling back to DDMod" + Style.RESET_ALL)

    dotnet_path = get_dotnet_path()
    if not dotnet_path:
        print_fn(Fore.RED + ".NET 9 not available. Cannot download." + Style.RESET_ALL)
        return False, 0

    dll_path = get_ddmod_dll()
    if not dll_path.exists():
        print_fn(Fore.RED + f"DepotDownloaderMod.dll not found at {dll_path}" + Style.RESET_ALL)
        return False, 0

    try:
        lines = []
        for depot_id in selected_depots:
            key = depots.get(str(depot_id), {}).get("key", "")
            if key:
                lines.append(f"{depot_id};{key}")
        KEYS_TMP.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        print_fn(Fore.RED + f"Failed to write depot keys: {e}" + Style.RESET_ALL)
        return False, 0

    _copy_manifests_to_temp(steam_path, manifests)

    dotnet_root = os.path.dirname(dotnet_path)
    env = os.environ.copy()
    env["DOTNET_ROOT"] = dotnet_root
    current_path = env.get("PATH", "")
    if dotnet_root not in current_path.split(os.pathsep):
        env["PATH"] = dotnet_root + os.pathsep + current_path

    if sys.platform.startswith("linux"):
        _add_bundled_openssl_to_env(env, dotnet_root)

    download_dir = dest_path / "steamapps" / "common" / installdir
    download_dir.mkdir(parents=True, exist_ok=True)

    MANIFESTS_TMP.mkdir(parents=True, exist_ok=True)
    deps_dir = get_deps_dir()
    total_depots = len(selected_depots)
    all_ok = True
    target_os = (os_name or ("linux" if sys.platform.startswith("linux") else "windows")).lower()

    for i, depot_id in enumerate(selected_depots):
        depot_id_str = str(depot_id)
        manifest_id = manifests.get(depot_id_str)

        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            val = get_setting(Settings.DOWNLOAD_CONCURRENCY)
            max_dl = str(min(max(int(val) if val else 32, 8), 64))
        except Exception:
            max_dl = "32"

        cmd = [
            dotnet_path, str(dll_path),
            "-app", appid,
            "-depot", depot_id_str,
            "-depotkeys", str(KEYS_TMP),
            "-max-downloads", max_dl,
            "-validate",
            "-dir", str(download_dir),
        ]
        if target_os != "all":
            cmd += ["-os", target_os]

        if manifest_id:
            manifest_file = MANIFESTS_TMP / f"{depot_id_str}_{manifest_id}.manifest"
            # Always pass -manifestfile so DDMod writes the manifest there if it
            # doesn't exist yet — this avoids the "No manifest request code" error
            # that occurs when DDMod tries to fetch the manifest from Steam CDN
            # anonymously without a valid session.
            cmd += ["-manifest", str(manifest_id), "-manifestfile", str(manifest_file)]

        print_fn(
            Fore.CYAN
            + f"\n--- Downloading depot {depot_id_str} ({i + 1}/{total_depots}) ---"
            + Style.RESET_ALL
        )

        creation_flags = 0
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW

        max_retries = 2
        attempt = 0
        depot_ok = False
        while attempt <= max_retries and not depot_ok:
            attempt += 1
            if attempt > 1:
                time.sleep(3)
                print_fn(
                    Fore.YELLOW
                    + f"\n[retry] Depot {depot_id_str} attempt {attempt}/{max_retries + 1}"
                    + Style.RESET_ALL
                )
            try:
                popen_kwargs = {
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "text": False,
                    "env": env,
                    "cwd": str(deps_dir),
                }
                if creation_flags:
                    popen_kwargs["creationflags"] = creation_flags

                proc = subprocess.Popen(cmd, **popen_kwargs)
                _read_process_output(proc, print_fn)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    print_fn(
                        Fore.RED + f"\n[timeout] Depot {depot_id_str} did not exit after output ended, killing"
                        + Style.RESET_ALL
                    )
                    proc.kill()
                    proc.wait()

                if proc.returncode != 0:
                    print_fn(
                        Fore.YELLOW
                        + f"Depot {depot_id_str} exited with code {proc.returncode}"
                        + Style.RESET_ALL
                    )
                    if attempt <= max_retries:
                        continue
                    all_ok = False
                else:
                    depot_ok = True
                    print_fn(
                        Fore.GREEN
                        + f"Depot {depot_id_str} downloaded successfully."
                        + Style.RESET_ALL
                    )

            except FileNotFoundError:
                print_fn(
                    Fore.RED
                    + f"ERROR: '{dotnet_path}' not found. Ensure .NET 9 is installed."
                    + Style.RESET_ALL
                )
                all_ok = False
                break
            except (OSError, subprocess.SubprocessError) as e:
                is_winsock = sys.platform == "win32" and isinstance(e, OSError) and getattr(e, "winerror", 0) == 10038
                if is_winsock and attempt <= max_retries:
                    creation_flags = 0
                    time.sleep(5)
                    print_fn(
                        Fore.YELLOW
                        + f"\n[retry] Windows socket handle reset for depot {depot_id_str}"
                        + Style.RESET_ALL
                    )
                    continue
                print_fn(Fore.RED + f"Error downloading depot {depot_id_str}: {e}" + Style.RESET_ALL)
                if attempt <= max_retries:
                    continue
                all_ok = False
                break

    try:
        KEYS_TMP.unlink(missing_ok=True)
    except Exception:
        pass

    size_on_disk = _calculate_dir_size(download_dir)
    print_fn(
        Fore.CYAN
        + f"Total size on disk: {size_on_disk:,} bytes"
        + Style.RESET_ALL
    )

    return all_ok, size_on_disk


def filter_depots_by_os(
    selected_depots: list,
    app_info: dict,
    print_fn=print,
    os_name: str | None = None,
) -> list:
    """Return selected_depots with depots outside the target OS removed.

    Keeps a depot if its oslist is empty/missing (shared content) or contains
    the target OS. Skips depots whose oslist is non-empty and lacks the target.
    Also skips Steam China depots (contain platform-specific bundles not needed
    on global Steam).  Falls back to the original list when app_info is unavailable.
    """
    if not app_info:
        return selected_depots
    target_os = (os_name or ("linux" if sys.platform.startswith("linux") else "windows")).lower()
    depots_section = app_info.get("depots", {}) if isinstance(app_info, dict) else {}

    # Build set of Steam China depot IDs from depots-level and top-level steamchina sections
    steamchina_ids: set[str] = set()
    sc_section = depots_section.get("steamchina", {})
    if isinstance(sc_section, dict):
        steamchina_ids |= {str(k) for k in sc_section if str(k).isdigit()}
    top_sc = app_info.get("steamchina", {}) if isinstance(app_info, dict) else {}
    if isinstance(top_sc, dict):
        steamchina_ids |= {str(k) for k in top_sc if str(k).isdigit()}

    filtered = []
    for depot_id in selected_depots:
        depot_meta = depots_section.get(str(depot_id), {})
        oslist = ""
        category = ""
        realm = ""
        ostype = ""
        depot_name = ""
        if isinstance(depot_meta, dict):
            depot_name = depot_meta.get("name", "") or ""
            config = depot_meta.get("config", {})
            if isinstance(config, dict):
                oslist = config.get("oslist", "") or ""
                category = config.get("category", "") or ""
                realm = config.get("realm", "") or ""
                ostype = config.get("ostype", "") or ""
        if target_os and oslist and target_os not in oslist.lower():
            print_fn(
                Fore.YELLOW
                + f"Skipping depot {depot_id} (oslist={oslist!r}, not {target_os})"
                + Style.RESET_ALL
            )
            continue
        sc_flag = (
            str(depot_id) in steamchina_ids
            or "steamchina" in category.lower()
            or "steamchina" in realm.lower()
            or "steamchina" in ostype.lower()
        )
        if not sc_flag and depot_name:
            name_lc = depot_name.lower()
            name_up = depot_name.upper()
            sc_flag = (
                "steamchina" in name_lc
                or name_up.endswith(" SC")
                or name_up.endswith("_SC")
                or any("\u4e00" <= c <= "\u9fff" for c in depot_name)
            )
        if sc_flag:
            print_fn(
                Fore.YELLOW
                + f"Skipping depot {depot_id} (Steam China: realm={realm!r} category={category!r} name={depot_name!r})"
                + Style.RESET_ALL
            )
            continue
        filtered.append(depot_id)
    return filtered


def move_manifests_to_depotcache(dest_path: Path, manifests_dict: dict, print_fn=print) -> None:
    depotcache = dest_path / "depotcache"
    depotcache.mkdir(parents=True, exist_ok=True)

    if MANIFESTS_TMP.exists():
        for depot_id, manifest_id in manifests_dict.items():
            manifest_filename = f"{depot_id}_{manifest_id}.manifest"
            src = MANIFESTS_TMP / manifest_filename
            dst = depotcache / manifest_filename
            if src.exists():
                try:
                    shutil.move(str(src), str(dst))
                except Exception:
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass

        try:
            shutil.rmtree(MANIFESTS_TMP, ignore_errors=True)
        except Exception:
            pass

    staging = Path.cwd() / "manifests"
    if staging.exists():
        for f in staging.glob("*.manifest"):
            dst = depotcache / f.name
            if not dst.exists():
                try:
                    shutil.copy2(f, dst)
                except Exception:
                    pass

    print_fn(Fore.GREEN + f"Manifests placed in depotcache: {depotcache}" + Style.RESET_ALL)
