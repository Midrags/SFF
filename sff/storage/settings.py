import json
import logging
from pathlib import Path
from typing import Any, Union, cast

import msgpack  # type: ignore

from sff.secret_store import keyring_decrypt, keyring_encrypt
from sff.structs import Settings
from sff.utils import root_folder

logger = logging.getLogger(__name__)

SETTINGS_FILE = root_folder(outside_internal=True) / "settings.bin"
SETTINGS_VERSION = "1.0.0"  # For migration tracking


def load_all_settings() -> dict[Any, Any]:
    """Returns all saved settings as a dict"""
    SETTINGS_FILE.touch(exist_ok=True)
    with SETTINGS_FILE.open("rb") as f:
        data = f.read()
    try:
        settings = (
            cast("dict[Any, Any]", msgpack.unpackb(data))  # type: ignore
            if data
            else {}
        )
    except (ValueError, msgpack.ExcessiveDataError, msgpack.FormatError):
        settings = {}
    
    # Perform migration if needed
    settings = migrate_settings(settings)
    
    return settings


def get_setting(key: Settings):
    # TODO: don't trigger I/O when last used command was also get_setting
    logger.debug(f"get_setting: {key.clean_name}")
    value = load_all_settings().get(key.key_name)
    return keyring_decrypt(value) if (value and key.hidden) else value


def set_setting(key: Settings, value: Union[str, bool]):
    if not isinstance(value, str) and not isinstance(
        value, bool
    ):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("Invalid type used for set_setting")

    logger.debug(f"set_setting: {key.clean_name} -> {str(value)}")
    settings = load_all_settings()
    settings[key.key_name] = (
        keyring_encrypt(value) if key.hidden and isinstance(value, str) else value
    )
    with SETTINGS_FILE.open("wb") as f:
        f.write(msgpack.packb(settings))  # type: ignore


def clear_setting(key: Settings):
    logger.debug(f"clear_setting: {key.clean_name}")
    settings = load_all_settings()
    if key.key_name in settings:
        settings.pop(key.key_name)
        with SETTINGS_FILE.open("wb") as f:
            f.write(msgpack.packb(settings))  # type: ignore


def resolve_advanced_mode() -> bool:
    adv_mode = get_setting(Settings.ADVANCED_MODE)
    if adv_mode is None or isinstance(adv_mode, str):
        adv_mode = False
        set_setting(Settings.ADVANCED_MODE, adv_mode)
    return adv_mode


def export_settings(export_path: Path, include_sensitive: bool = False) -> bool:
    try:
        settings = load_all_settings()
        export_data = {
            "version": SETTINGS_VERSION,
            "settings": {}
        }
        
        for setting in Settings:
            key = setting.key_name
            if key in settings:
                value = settings[key]
                
                if setting.hidden and not include_sensitive:
                    continue
                
                if setting.hidden:
                    if isinstance(value, bytes):
                        try:
                            value = keyring_decrypt(value)
                        except Exception as e:
                            logger.warning(f"Failed to decrypt {key}: {e}")
                            continue
                    elif isinstance(value, str):
                        try:
                            value = keyring_decrypt(value)
                        except Exception as e:
                            pass
                    
                export_data["settings"][key] = value
        
        with export_path.open("w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Settings exported to {export_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to export settings: {e}", exc_info=True)
        return False


def import_settings(import_path: Path) -> tuple[bool, str]:
    try:
        if not import_path.exists():
            return False, f"File not found: {import_path}"
        
        with import_path.open("r", encoding="utf-8") as f:
            import_data = json.load(f)
        
        if "version" not in import_data or "settings" not in import_data:
            return False, "Invalid settings file format: missing version or settings"
        
        if not isinstance(import_data["settings"], dict):
            return False, "Invalid settings file format: settings must be a dictionary"
        
        imported_count = 0
        errors = []
        
        for key, value in import_data["settings"].items():
            setting = None
            for s in Settings:
                if s.key_name == key:
                    setting = s
                    break
            
            if setting is None:
                errors.append(f"Unknown setting: {key}")
                continue
            
            if setting.type == bool and not isinstance(value, bool):
                errors.append(f"{key}: expected bool, got {type(value).__name__}")
                continue
            elif setting.type == str and not isinstance(value, str):
                errors.append(f"{key}: expected str, got {type(value).__name__}")
                continue
            
            try:
                set_setting(setting, value)
                imported_count += 1
            except Exception as e:
                errors.append(f"{key}: {str(e)}")
        
        if errors:
            error_msg = f"Imported {imported_count} settings with errors: " + "; ".join(errors)
            logger.warning(error_msg)
            return True, error_msg
        
        logger.info(f"Successfully imported {imported_count} settings from {import_path}")
        return True, f"Successfully imported {imported_count} settings"
        
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON file: {e}"
    except Exception as e:
        logger.error(f"Failed to import settings: {e}", exc_info=True)
        return False, f"Import failed: {e}"


def migrate_settings(settings: dict[Any, Any]) -> dict[Any, Any]:
    current_version = settings.get("_version", "0.0.0")
    
    if current_version == SETTINGS_VERSION:
        return settings
    
    logger.info(f"Migrating settings from version {current_version} to {SETTINGS_VERSION}")
    settings["_version"] = SETTINGS_VERSION
    with SETTINGS_FILE.open("wb") as f:
        f.write(msgpack.packb(settings))  # type: ignore
    
    return settings
