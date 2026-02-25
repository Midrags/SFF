import shutil
from dataclasses import dataclass
from pathlib import Path

from pathvalidate import sanitize_filename

from sff.http_utils import get_game_name
from sff.prompts import prompt_confirm
from sff.storage.vdf import VDFLoadAndDumper, vdf_dump, vdf_load
from sff.structs import LuaParsedInfo
from sff.utils import enter_path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ACFWriter:
    steam_lib_path: Path

    def write_acf(self, lua: LuaParsedInfo):
        acf_file = self.steam_lib_path / f"steamapps/appmanifest_{lua.app_id}.acf"
        do_write_acf = True
        if acf_file.exists():
            do_write_acf = not prompt_confirm(
                ".acf file found. Are you updating a game you already have installed"
                " or is this a new installation?",
                true_msg="I'm updating a game",
                false_msg="This is a new installation (Overwrites the .acf file, i.e., "
                "resets the status of the game)",
            )

        if do_write_acf:
            app_name = get_game_name(lua.app_id)
            app_id_str = str(lua.app_id)
            installdir = sanitize_filename(app_name).replace("'", "")
            acf_contents: dict[str, dict[str, str]] = {
                "AppState": {
                    "appid": app_id_str,
                    "Universe": "1",
                    "name": app_name,
                    "StateFlags": "4",
                    "installdir": installdir,
                    "LastUpdated": "0",
                    "UpdateResult": "0",
                    "SizeOnDisk": "0",
                    "BytesToDownload": "0",
                    "BytesDownloaded": "0",
                }
            }
            vdf_dump(acf_file, acf_contents)
            print(f"Wrote .acf file to {acf_file}")
        else:
            print("Skipped writing to .acf file")


@dataclass
class ConfigVDFWriter:
    steam_path: Path

    def add_decryption_keys_to_config(self, lua: LuaParsedInfo):
        """Adds decryption keys from parsed lua to config.vdf"""
        vdf_file = self.steam_path / "config/config.vdf"
        shutil.copyfile(vdf_file, (self.steam_path / "config/config.vdf.backup"))
        with VDFLoadAndDumper(vdf_file) as vdf_data:
            for pair in lua.depots:
                depot_id = pair.depot_id
                dec_key = pair.decryption_key
                if dec_key == "":
                    logger.debug(f"Skipping {depot_id} because it's not a depot")
                    continue
                print(
                    f"Depot {depot_id} has decryption key {dec_key}... ",
                    end="",
                    flush=True,
                )
                depots = enter_path(
                    vdf_data,
                    "InstallConfigStore",
                    "Software",
                    "Valve",
                    "Steam",
                    "depots",
                    mutate=True,
                    ignore_case=True,
                )
                if depot_id not in depots:
                    depots[depot_id] = {"DecryptionKey": dec_key}
                    print("Added to config.vdf successfully.")
                else:
                    print("Already in config.vdf.")

    def ids_in_config(self, ids: list[int]):
        """Checks if IDs are in config.vdf and returns a
        dict mapping IDs to their existence"""
        vdf_file = self.steam_path / "config/config.vdf"
        data = vdf_load(vdf_file)
        depots = enter_path(
            data,
            "InstallConfigStore",
            "Software",
            "Valve",
            "Steam",
            "depots",
            mutate=True,
            ignore_case=True,
        )
        return {x: (str(x) in depots) for x in ids}
