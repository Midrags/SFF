"""Run SteamAutoCrack CLI for the selected game path and app id."""

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

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
    return proc.returncode
