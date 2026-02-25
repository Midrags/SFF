from typing import Callable
from configupdater import ConfigUpdater

from pathlib import Path


def edit_ini_option(
    ini_file: Path, section: str, option: str, converter: Callable[[str], str]
):
    conf = ConfigUpdater()
    conf.read(ini_file)  # pyright: ignore[reportUnknownMemberType]

    old_val = conf[section][option].value
    if old_val is None:
        return

    new_val = converter(old_val)

    conf[section][option].value = new_val

    conf.update_file()
    return new_val
