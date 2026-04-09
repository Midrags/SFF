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

"""Run SteamAutoCrack CLI for the selected game path and app id.

Includes a safety wrapper that backs up game executables before invoking the
CLI and automatically restores them if SteamAutoCrack removes an exe without
producing a patched replacement (a known upstream bug in the unpacker logic).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from sff.strings import STEAM_WEB_API_KEY
from sff.utils import root_folder

# Pre-built self-contained EXE locations (x86, no dotnet runtime needed), checked in order
_EXE_PATHS = [
    "third_party/SteamAutoCrack/cli/SteamAutoCrack.CLI.exe",
    "third_party/Codes to use/SteamAuto Code/SteamAuto/SteamAutoCrack.CLI/publish_x86/SteamAutoCrack.CLI.exe",
    "third_party/Codes to use/SteamAuto Code/SteamAuto/SteamAutoCrack.CLI/bin/x86/Release/net9.0-windows/win-x86/SteamAutoCrack.CLI.exe",
]
# Note: the project targets x86 so dotnet run / dotnet <dll> requires an x86 .NET runtime.
# The self-contained EXE bundles the runtime and works without any dotnet install.


def get_steamauto_cli_path() -> Optional[Path]:
    root = root_folder()
    for subpath in _EXE_PATHS:
        p = root / subpath
        if p.exists():
            return p.resolve()
    return None


def _snapshot_executables(game_path: Path) -> dict[Path, Path]:
    """Create temporary backup copies of every .exe in the game directory.

    Returns a mapping of {original_path: backup_path} so we can restore if
    the cracking tool removes an exe without producing a replacement.
    """
    backups: dict[Path, Path] = {}
    backup_dir = game_path / ".steamidra_exe_backups"
    backup_dir.mkdir(exist_ok=True)
    for exe in game_path.glob("*.exe"):
        dst = backup_dir / exe.name
        shutil.copy2(exe, dst)
        backups[exe] = dst
    return backups


def _verify_and_restore(
    backups: dict[Path, Path],
    print_func: Callable[[str], None],
) -> int:
    """Check that every backed-up exe still exists; restore any that vanished.

    Returns the number of executables that had to be restored.
    """
    restored = 0
    for original, backup in backups.items():
        if not original.exists():
            # The exe was removed without a replacement being created
            if backup.exists():
                shutil.copy2(backup, original)
                print_func(
                    f"[SteaMidra] RESTORED {original.name} — SteamAutoCrack "
                    "removed it without producing a patched version."
                )
                restored += 1
            else:
                print_func(
                    f"[SteaMidra] WARNING: {original.name} was removed and "
                    "backup is also missing. Manual intervention needed."
                )

    # Clean up the backup directory if everything went fine
    if backups:
        backup_dir = next(iter(backups.values())).parent
        try:
            shutil.rmtree(backup_dir)
        except OSError:
            pass  # Non-critical cleanup; ignore
    return restored


def _ensure_config_has_api_key(cli_dir: Path) -> None:
    """Make sure config.json in the CLI directory has the Steam Web API key.

    Without this key, SteamAutoCrack may fail with a "NO LICENSE" error when
    generating Goldberg emulator game info. The key is loaded from strings.py.
    """
    config_path = cli_dir / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            emu_info = data.get("EMUGameInfoConfigs", {})
            current_key = emu_info.get("SteamWebAPIKey", "")
            if not current_key and STEAM_WEB_API_KEY:
                emu_info["SteamWebAPIKey"] = STEAM_WEB_API_KEY
                data["EMUGameInfoConfigs"] = emu_info
                config_path.write_text(
                    json.dumps(data, indent=2), encoding="utf-8"
                )
        except (json.JSONDecodeError, OSError):
            pass  # If config is corrupt, let the CLI regenerate it


def run_steamauto(
    game_path: Path,
    app_id: str,
    *,
    print_func: Callable[[str], None] = print,
) -> int:
    game_path = game_path.resolve()
    cli = get_steamauto_cli_path()
    if cli is None:
        root = root_folder()
        raise FileNotFoundError(
            "SteamAutoCrack CLI not found. Expected:\n"
            f"  {root / _EXE_PATHS[0]}\n"
            "Run: dotnet publish with -r win-x86 --self-contained true "
            "then copy publish_x86/ contents into third_party/SteamAutoCrack/cli/."
        )

    # Ensure the API key is set in the CLI config (prevents NO LICENSE errors)
    _ensure_config_has_api_key(cli.parent)

    # Safety: snapshot all game executables before the CLI touches them
    print_func("[SteaMidra] Backing up game executables before cracking...")
    backups = _snapshot_executables(game_path)
    if backups:
        print_func(f"[SteaMidra] Backed up {len(backups)} executable(s).")
    else:
        print_func("[SteaMidra] No executables found in game directory.")

    cmd = [str(cli), "crack", str(game_path), "--appid", app_id or "0"]
    print_func("Running: " + " ".join(cmd) + "\n")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cli.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print_func(line.rstrip())
    proc.wait()

    # Safety: verify executables survived the process
    restored = _verify_and_restore(backups, print_func)
    if restored > 0:
        print_func(
            f"\n[SteaMidra] WARNING: {restored} executable(s) were restored "
            "because SteamAutoCrack removed them without creating patched "
            "versions. The game files are back to their original state. "
            "The cracking process may not have completed successfully — "
            "try again or use a different method."
        )
    return proc.returncode
