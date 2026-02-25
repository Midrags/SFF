from pathlib import Path
import shutil
import subprocess
from typing import Union

from smd.structs import OSType
from smd.utils import root_folder


def run_fzf(choices: Union[list[str], Path], os_type: OSType):
    if isinstance(choices, list):
        choices_str = "\n".join(choices)
    else:
        with choices.open(encoding="utf-8") as f:
            choices_str = f.read()

    cmd = []
    if os_type == OSType.LINUX:
        fzf_path = shutil.which("fzf")
        if fzf_path is None:
            print(
                "You don't have fzf installed. Please install it and try this again."
            )
            return
        cmd = [fzf_path]
    elif os_type == OSType.WINDOWS:
        cmd = [root_folder() / "third_party/fzf/fzf.exe"]
    proc = subprocess.run(
        cmd,
        input=choices_str,
        capture_output=True,
        encoding="utf-8",
    )
    return proc.stdout.strip("\n")
