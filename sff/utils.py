"""Miscellaneous stuff used across various files"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional, Union

import vdf  # type: ignore

logger = logging.getLogger(__name__)


def root_folder(outside_internal: bool = False):
    is_frozen = getattr(sys, "frozen", False)
    
    if is_frozen:
        # Running as compiled EXE
        exe_dir = Path(sys.executable).resolve().parent
        
        # For frozen EXE, both internal and external paths are the same
        # Everything (settings, c folder, static, third_party) is in the EXE directory
        return exe_dir
    else:
        # Running as Python script
        # __file__ is in sff/ subfolder, so parent.parent gets us to Maintool/
        root = Path(__file__).resolve().parent.parent
        
        if outside_internal:
            return root
        return root


def enter_path(
    obj: Union[vdf.VDFDict, dict[Any, Any]],
    *paths: Union[int, str],
    mutate: bool = False,
    ignore_case: bool = False,
    default: Optional[Any] = None,
) -> Any:
    """
    Walks or creates nested dicts in a VDFDict/dict.
    Returns an empty dict-like if not found.
    `default` key only works when `mutate` is False.
    """
    current = obj
    for key in paths:
        if isinstance(key, int):
            try:
                current = current[key]  # pyright: ignore[reportUnknownVariableType]
            except IndexError:
                return type(current)()
            continue
        original_key = key
        if ignore_case:
            key = key.lower()

        key_map = {}
        for x in current:  # pyright: ignore[reportUnknownVariableType]
            if ignore_case and isinstance(x, str):
                key_map[x.lower()] = x
            else:
                key_map[x] = x

        if key in key_map:
            current = current[  # pyright: ignore[reportUnknownVariableType]
                key_map[key]
            ]
        else:
            if not mutate:
                return default if default else type(current)()
            # create a new key that's the same type as current
            new_node = type(current)()
            current[original_key] = new_node
            current = new_node

    return current  # pyright: ignore[reportUnknownVariableType]
