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

"""
Robust YAML config manager for SLSsteam's config.yaml.

All Qt/QSettings dependencies removed — config path is always passed as an argument.

Features:
- Atomic writes (temp file + os.replace) — crash-safe
- Automatic .bak backups before every modification
- Targeted section edits — only touches the section being modified
- Indentation fixing for AdditionalApps / AppTokens
"""

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

BACKUP_SUFFIX = ".bak"
DEFAULT_FAKE_APPID = "480"  # Spacewar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_user_config_path() -> Path:
    """Get the path to the user's SLSsteam config.yaml file."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg and Path(xdg).is_absolute():
        config_dir = Path(xdg) / "SLSsteam"
    else:
        config_dir = Path.home() / ".config" / "SLSsteam"
    return config_dir / "config.yaml"


def _read_config(config_path: Path, log_missing: bool = False) -> Optional[str]:
    if not config_path.exists():
        if log_missing:
            logger.warning(f"Config file not found at {config_path}")
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return f.read()


def _atomic_write(config_path: Path, content: str) -> bool:
    """Atomically write *content* to *config_path* via a temp file."""
    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_path, config_path)
        return True
    except OSError as e:
        logger.error(f"Failed to atomically write {config_path}: {e}", exc_info=True)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        return False


def _create_backup(config_path: Path) -> bool:
    """Create a .bak backup.  Skips if new file is smaller than existing backup."""
    try:
        if not config_path.exists():
            return False
        backup_path = config_path.with_suffix(BACKUP_SUFFIX)
        if backup_path.exists():
            if config_path.stat().st_size < backup_path.stat().st_size:
                logger.debug("Skipping backup: new file smaller than existing backup")
                return True
        shutil.copy2(config_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to create backup for {config_path}: {e}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Section helpers (regex-based, no yaml.dump)
# ---------------------------------------------------------------------------

def _get_section_start(content: str, pattern: re.Pattern) -> Optional[int]:
    match = pattern.search(content)
    if not match:
        return None
    pos = match.end()
    if pos < len(content) and content[pos] == "\n":
        pos += 1
    return pos


def _get_section_end(content: str, section_start: int, next_key_pattern: re.Pattern) -> int:
    after = content[section_start:]
    m = next_key_pattern.search(after)
    return section_start + m.start() if m else len(content)


def _remove_line_for_match(content: str, match: re.Match) -> str:
    line_start = content.rfind("\n", 0, match.start()) + 1
    if line_start == 0:
        line_start = 0
    line_end = content.find("\n", match.end())
    if line_end == -1:
        line_end = len(content)
    if line_end < len(content) and content[line_end] == "\n":
        line_end += 1
    return content[:line_start] + content[line_end:]


def _remove_matching_entry(
    config_path: Path, pattern: re.Pattern, success_msg: str, error_msg: str
) -> bool:
    try:
        content = _read_config(config_path)
        if content is None:
            return False
        match = pattern.search(content)
        if not match:
            return False
        new_content = _remove_line_for_match(content, match)
        _create_backup(config_path)
        if not _atomic_write(config_path, new_content):
            return False
        logger.info(success_msg)
        return True
    except OSError as e:
        logger.error(error_msg.format(e=e), exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Indentation fixing
# ---------------------------------------------------------------------------

def _fix_additional_apps_indentation(content: str) -> Tuple[str, bool]:
    """Fix indentation of AdditionalApps list items to 2-space."""
    pattern = re.compile(r"^AdditionalApps:\s*$", re.MULTILINE)
    section_start = _get_section_start(content, pattern)
    if section_start is None:
        return content, False

    next_key = re.compile(r"^[A-Za-z]", re.MULTILINE)
    section_end = _get_section_end(content, section_start, next_key)
    section = content[section_start:section_end]

    misaligned = re.compile(r"(^)(\s*)-(\s*)([^\n#]+?)(?=\s*(?:#|$))", re.MULTILINE)
    fixed = misaligned.sub(r"\1  - \4", section)

    if fixed != section:
        return content[:section_start] + fixed + content[section_end:], True
    return content, False


def _get_app_tokens_section(content: str) -> str:
    pattern = re.compile(r"^AppTokens:\s*$", re.MULTILINE)
    start = _get_section_start(content, pattern)
    if start is None:
        return ""
    next_key = re.compile(r"^[A-Za-z][A-Za-z0-9]*:\s*$", re.MULTILINE)
    end = _get_section_end(content, start, next_key)
    return content[start:end]


def _fix_app_tokens_indentation(content: str) -> Tuple[str, bool]:
    """Fix indentation of AppTokens entries to 2-space."""
    pattern = re.compile(r"^AppTokens:\s*$", re.MULTILINE)
    start = _get_section_start(content, pattern)
    if start is None:
        return content, False

    after = content[start:]
    next_key = re.compile(r"^[A-Za-z][A-Za-z0-9]*:\s*$", re.MULTILINE)

    last_token = re.compile(r"^\s*\d+\s*:\s*[^\n]*$", re.MULTILINE)
    matches = list(last_token.finditer(after))
    if matches:
        last_end = matches[-1].end()
        nl = after.find("\n", last_end)
        if nl != -1:
            section_end = start + nl + 1
        else:
            nm = next_key.search(after)
            section_end = start + nm.start() if nm else len(content)
    else:
        nm = next_key.search(after)
        section_end = start + nm.start() if nm else len(content)

    section = content[start:section_end]
    token_re = re.compile(r"(^)(\s*)(\d+)(\s*:\s*[^\n]*)", re.MULTILINE)
    fixed = token_re.sub(r"\1  \3\4", section)

    if fixed != section:
        return content[:start] + fixed + content[section_end:], True
    return content, False


def fix_slssteam_config_indentation(config_path: Path) -> bool:
    """Fix indentation of AdditionalApps and AppTokens entries."""
    try:
        content = _read_config(config_path)
        if content is None:
            return False
        fixed, mod_apps = _fix_additional_apps_indentation(content)
        fixed, mod_tokens = _fix_app_tokens_indentation(fixed)
        if mod_apps or mod_tokens:
            if not _atomic_write(config_path, fixed):
                return False
            logger.info(f"Fixed indentation in {config_path}")
            return True
        return False
    except OSError as e:
        logger.error(f"Failed to fix indentation in {config_path}: {e}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Boolean value update
# ---------------------------------------------------------------------------

def update_yaml_boolean_value(config_path: Path, key: str, value: bool) -> bool:
    """Update a boolean value in YAML config using regex (preserves formatting)."""
    try:
        content = _read_config(config_path)
        if content is None:
            return False
        pat = re.compile(
            r"^(\s*)" + re.escape(key) + r"\s*:\s*(yes|no|true|false|Yes|No|True|False)\b",
            re.MULTILINE,
        )
        match = pat.search(content)
        if not match:
            logger.warning(f"Key '{key}' not found in {config_path}")
            return False
        indent = match.group(1)
        old_val = match.group(2)
        new_val = "yes" if value else "no"
        if old_val.lower() == new_val.lower():
            return False
        replacement = f"{indent}{key}: {new_val}"
        new_content = pat.sub(replacement, content)
        _create_backup(config_path)
        if not _atomic_write(config_path, new_content):
            return False
        logger.info(f"Updated '{key}' to {new_val} in {config_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to update '{key}' in {config_path}: {e}", exc_info=True)
        return False


def ensure_slssteam_api_enabled(config_path: Path) -> bool:
    """Set API: yes in config.yaml."""
    return update_yaml_boolean_value(config_path, "API", True)


# ---------------------------------------------------------------------------
# AdditionalApps
# ---------------------------------------------------------------------------

def _init_config_with_app(config_path: Path, app_id: str, comment: str) -> bool:
    """Create a brand-new config file with a single AdditionalApps entry."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    entry = f"AdditionalApps:\n  - {app_id}"
    if comment:
        entry += f"   # {comment}"
    entry += "\n"
    if _atomic_write(config_path, entry):
        logger.info(f"Created config with AppID '{app_id}' in {config_path}")
        return True
    return False


def _append_to_additional_apps(content: str, app_id: str, comment: str, match: re.Match) -> str:
    start_pos = match.end()
    remaining = content[start_pos:]
    lines = remaining.split("\n")
    last_item_end = start_pos
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("-"):
            last_item_end = start_pos + sum(len(lines[j]) + 1 for j in range(i + 1))
        elif not stripped or stripped.startswith("#"):
            continue
        else:
            break
    else:
        last_item_end = len(content)

    entry = f"  - {app_id}"
    if comment:
        entry += f"   # {comment}"
    entry += "\n"
    return content[:last_item_end] + entry + content[last_item_end:]


def add_additional_app(config_path: Path, app_id: str, comment: str = "") -> bool:
    """Add an AppID to AdditionalApps in SLSsteam config.yaml."""
    try:
        content = _read_config(config_path)
        if content is None:
            return _init_config_with_app(config_path, app_id, comment)

        fixed, _ = _fix_additional_apps_indentation(content)

        existing = re.compile(rf"^\s*-\s*{re.escape(app_id)}\s*(?:#.*)?$", re.MULTILINE)
        if existing.search(fixed):
            logger.debug(f"AppID '{app_id}' already in AdditionalApps")
            return False

        header = re.compile(r"^AdditionalApps:\s*$", re.MULTILINE)
        match = header.search(fixed)
        if match:
            new_content = _append_to_additional_apps(fixed, app_id, comment, match)
        else:
            entry = f"AdditionalApps:\n  - {app_id}"
            if comment:
                entry += f"   # {comment}"
            entry += "\n"
            new_content = fixed + "\n" + entry

        _create_backup(config_path)
        if not _atomic_write(config_path, new_content):
            return False
        logger.info(f"Added AppID '{app_id}' to AdditionalApps in {config_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to add AppID '{app_id}': {e}", exc_info=True)
        return False


def remove_additional_app(config_path: Path, app_id: str) -> bool:
    """Remove an AppID from AdditionalApps."""
    pat = re.compile(rf"^\s*-\s*{re.escape(app_id)}\s*(?:#.*)?$", re.MULTILINE)
    return _remove_matching_entry(
        config_path, pat,
        f"Removed AppID '{app_id}' from AdditionalApps",
        f"Failed to remove AppID '{app_id}': {{e}}",
    )


# ---------------------------------------------------------------------------
# AppTokens
# ---------------------------------------------------------------------------

def add_app_token(config_path: Path, app_id: str, token: str) -> bool:
    """Add or update an AppToken in the AppTokens section."""
    try:
        content = _read_config(config_path)
        if content is None:
            return False

        header = re.compile(r"^AppTokens:\s*$", re.MULTILINE)
        if not header.search(content):
            new_entry = f"AppTokens:\n  {app_id}: {token}\n"
            _create_backup(config_path)
            return _atomic_write(config_path, content + new_entry)

        fixed, _ = _fix_app_tokens_indentation(content)
        content = fixed

        section = _get_app_tokens_section(content)
        existing = re.compile(rf"^ {{2}}{re.escape(app_id)}\s*:\s*(.+)$", re.MULTILINE)
        existing_match = existing.search(section)

        if existing_match:
            if existing_match.group(1).strip() == token:
                return False
            tokens_start = content.find("AppTokens:")
            line_start = tokens_start + len("AppTokens:\n") + existing_match.start()
            line_end = line_start + len(existing_match.group(0))
            new_line = f"  {app_id}: {token}"
            new_content = content[:line_start] + new_line + content[line_end:]
            _create_backup(config_path)
            if _atomic_write(config_path, new_content):
                logger.info(f"Updated AppToken for '{app_id}'")
                return True
            return False

        new_token_line = f"  {app_id}: {token}"
        token_line_pat = re.compile(r"(^AppTokens:\n)( {2}\S+:[^\n]*)", re.MULTILINE)
        token_match = token_line_pat.search(content)
        if token_match:
            new_content = (
                content[: token_match.end()] + "\n" + new_token_line + content[token_match.end():]
            )
        else:
            new_content = content.replace("AppTokens:", "AppTokens:\n" + new_token_line, 1)

        _create_backup(config_path)
        if _atomic_write(config_path, new_content):
            logger.info(f"Added AppToken for '{app_id}'")
            return True
        return False
    except OSError as e:
        logger.error(f"Failed to add AppToken '{app_id}': {e}", exc_info=True)
        return False


def get_app_tokens(config_path: Path) -> Dict[str, str]:
    """Read all AppTokens from config.yaml."""
    tokens: Dict[str, str] = {}
    try:
        if not config_path.exists():
            return tokens
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        section = _get_app_tokens_section(content)
        for m in re.finditer(r"^\s*(\d+)\s*:\s*(.+)$", section, re.MULTILINE):
            tokens[m.group(1).strip()] = m.group(2).strip()
    except OSError as e:
        logger.error(f"Failed to read AppTokens from {config_path}: {e}", exc_info=True)
    return tokens


# ---------------------------------------------------------------------------
# DlcData
# ---------------------------------------------------------------------------

def _atomic_write_and_log_dlc(
    config_path: Path, content: str, dlc_name: str, dlc_id: str, parent_app_id: str
) -> bool:
    if not _atomic_write(config_path, content):
        return False
    logger.info(f"Added DLC '{dlc_name}' ({dlc_id}) under AppID '{parent_app_id}'")
    return True


def add_dlc_data(
    config_path: Path, parent_app_id: str, dlc_id: str, dlc_name: str = ""
) -> bool:
    """Add a DLC entry to DlcData section."""
    try:
        content = _read_config(config_path, log_missing=True)
        if content is None:
            return False

        dlc_header = re.compile(r"^DlcData:\s*$", re.MULTILINE)
        match = dlc_header.search(content)

        if not match:
            safe_name = f'"{dlc_name}"' if dlc_name else '""'
            new_entry = f"DlcData:\n  {parent_app_id}:\n    {dlc_id}: {safe_name}\n"
            _create_backup(config_path)
            return _atomic_write_and_log_dlc(
                config_path, content + "\n" + new_entry, dlc_name, dlc_id, parent_app_id
            )

        dlc_data_end = match.end()

        parent_pat = re.compile(rf"^(\s*){re.escape(parent_app_id)}:\s*$", re.MULTILINE)
        parent_match = parent_pat.search(content, dlc_data_end)

        safe_name = f'"{dlc_name}"' if dlc_name else '""'

        if not parent_match:
            remaining = content[dlc_data_end:]
            next_key = re.compile(r"^[A-Za-z]", re.MULTILINE)
            nm = next_key.search(remaining)
            insert_pos = dlc_data_end + nm.start() if nm else len(content)
            new_entry = f"  {parent_app_id}:\n    {dlc_id}: {safe_name}\n"
            new_content = content[:insert_pos] + new_entry + content[insert_pos:]
            _create_backup(config_path)
            return _atomic_write_and_log_dlc(
                config_path, new_content, dlc_name, dlc_id, parent_app_id
            )

        parent_line_end = parent_match.end()
        parent_indent = len(parent_match.group(1))
        remaining = content[parent_line_end:]

        next_parent = re.compile(rf"^(\s{{{parent_indent}}})[0-9]", re.MULTILINE)
        nm = next_parent.search(remaining)

        if nm:
            parent_section = remaining[: nm.start()]
            insert_pos = parent_line_end + nm.start()
        else:
            after_dlcdata = content[dlc_data_end:]
            end_m = re.compile(r"^[A-Za-z]", re.MULTILINE).search(after_dlcdata)
            if end_m:
                limit = dlc_data_end + end_m.start() - parent_line_end
                parent_section = remaining[:limit]
                insert_pos = dlc_data_end + end_m.start()
            else:
                parent_section = remaining
                insert_pos = len(content)

        dup_check = re.compile(rf'^\s*{re.escape(dlc_id)}:\s*"', re.MULTILINE)
        if dup_check.search(parent_section):
            logger.debug(f"DLC '{dlc_id}' already exists under AppID '{parent_app_id}'")
            return False

        new_entry = f'{" " * (parent_indent + 2)}{dlc_id}: {safe_name}\n'
        new_content = content[:insert_pos] + new_entry + content[insert_pos:]
        _create_backup(config_path)
        return _atomic_write_and_log_dlc(
            config_path, new_content, dlc_name, dlc_id, parent_app_id
        )
    except OSError as e:
        logger.error(f"Failed to add DLC '{dlc_id}': {e}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# FakeAppIds
# ---------------------------------------------------------------------------

def get_fake_app_ids(config_path: Path, fake_appid: str = "") -> Set[str]:
    """Get all real AppIDs that have a FakeAppId mapping."""
    if not fake_appid:
        fake_appid = DEFAULT_FAKE_APPID
    ids: Set[str] = set()
    try:
        if not config_path.exists():
            return ids
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        header = re.compile(r"^FakeAppIds:\s*$", re.MULTILINE)
        match = header.search(content)
        if not match:
            return ids
        start = match.end()
        after = content[start:]
        next_key = re.compile(r"^[A-Za-z]", re.MULTILINE)
        nm = next_key.search(after)
        section = after[: nm.start()] if nm else after
        entry_re = re.compile(rf"^\s*(\d+)\s*:\s*{re.escape(fake_appid)}", re.MULTILINE)
        for m in entry_re.finditer(section):
            ids.add(m.group(1).strip())
    except OSError as e:
        logger.error(f"Failed to read FakeAppIds: {e}", exc_info=True)
    return ids


def get_fake_appid(config_path: Path, app_id: str) -> Optional[str]:
    """Get the FakeAppId for a specific real AppID."""
    try:
        if not config_path.exists():
            return None
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        header = re.compile(r"^FakeAppIds:\s*$", re.MULTILINE)
        match = header.search(content)
        if not match:
            return None
        start = match.end()
        after = content[start:]
        next_key = re.compile(r"^[A-Za-z]", re.MULTILINE)
        nm = next_key.search(after)
        section = after[: nm.start()] if nm else after
        entry_re = re.compile(rf"^\s*{re.escape(app_id)}\s*:\s*(\d+)", re.MULTILINE)
        m = entry_re.search(section)
        return m.group(1).strip() if m else None
    except OSError as e:
        logger.error(f"Failed to read FakeAppId for '{app_id}': {e}", exc_info=True)
        return None


def add_fake_app_id(
    config_path: Path,
    app_id: str,
    game_name: str = "",
    fake_appid: str = "",
) -> bool:
    """Add an AppID to FakeAppIds (default maps to Spacewar 480)."""
    if not fake_appid:
        fake_appid = DEFAULT_FAKE_APPID
    suffix = "Spacewar" if fake_appid == "480" else "SLSonline"

    try:
        content = _read_config(config_path)
        if content is None:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            entry = f"FakeAppIds:\n  {app_id}: {fake_appid}"
            if game_name:
                entry += f"  # {game_name} -> {suffix}"
            entry += "\n"
            return _atomic_write(config_path, entry)

        existing = re.compile(
            rf"^\s*{re.escape(app_id)}\s*:\s*{re.escape(fake_appid)}", re.MULTILINE
        )
        if existing.search(content):
            return False

        header = re.compile(r"^FakeAppIds:\s*$", re.MULTILINE)
        match = header.search(content)

        entry = f"  {app_id}: {fake_appid}"
        if game_name:
            entry += f"  # {game_name} -> {suffix}"
        entry += "\n"

        if match:
            section_start = match.end()
            if section_start < len(content) and content[section_start] == "\n":
                section_start += 1
            remaining = content[section_start:]
            lines = remaining.split("\n")
            last_entry_end = section_start
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and stripped[0].isdigit():
                    last_entry_end = section_start + sum(len(lines[j]) + 1 for j in range(i + 1))
                elif not stripped or stripped.startswith("#"):
                    continue
                else:
                    break
            else:
                last_entry_end = len(content)
            new_content = content[:last_entry_end] + entry + content[last_entry_end:]
        else:
            new_content = content + "\nFakeAppIds:\n" + entry

        _create_backup(config_path)
        if not _atomic_write(config_path, new_content):
            return False
        logger.info(f"Added AppID '{app_id}' to FakeAppIds in {config_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to add FakeAppId '{app_id}': {e}", exc_info=True)
        return False


def remove_fake_app_id(config_path: Path, app_id: str, fake_appid: str = "") -> bool:
    """Remove an AppID from FakeAppIds."""
    if not fake_appid:
        fake_appid = DEFAULT_FAKE_APPID
    pat = re.compile(
        rf"^\s*{re.escape(app_id)}\s*:\s*{re.escape(fake_appid)}(?:\s*#.*)?$",
        re.MULTILINE,
    )
    return _remove_matching_entry(
        config_path, pat,
        f"Removed AppID '{app_id}' from FakeAppIds",
        f"Failed to remove FakeAppId '{app_id}': {{e}}",
    )
