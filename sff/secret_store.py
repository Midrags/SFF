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

"""Machine-local secret handling for settings data."""

import base64
import logging
import os
import stat
from pathlib import Path

from sff.utils import sff_data_dir

logger = logging.getLogger(__name__)

SERVICE = "sff_tool"
KEYNAME = "master_key"

_KEYRING_WORKING = True
_KEYRING_WARNED = False
_NACL_AVAILABLE = True

try:
    import keyring
except ImportError:
    keyring = None  # type: ignore
    _KEYRING_WORKING = False

try:
    from nacl.exceptions import CryptoError
    from nacl.secret import SecretBox
except ImportError:
    CryptoError = Exception  # type: ignore
    SecretBox = None  # type: ignore
    _NACL_AVAILABLE = False


def _warn_keyring_once():
    global _KEYRING_WARNED
    if not _KEYRING_WARNED:
        _KEYRING_WARNED = True
        logger.warning(
            "System keyring unavailable, storing encryption key locally. "
            "Install python-keyring or keyrings.alt for desktop keychain "
            "integration. If you are on KDE, enable kwallet. "
            "Temporary fix: pip install --user keyrings.alt"
        )


def _file_key_path() -> Path:
    p = sff_data_dir() / ".sff_encryption_key"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_key_from_file() -> bytes | None:
    p = _file_key_path()
    if p.is_file():
        try:
            return _decode_key_material(p.read_bytes())
        except Exception:
            return None
    return None


def _save_key_to_file(raw_key: bytes):
    p = _file_key_path()
    p.write_bytes(_encode_key_material(raw_key))
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(p), 2)  # FILE_ATTRIBUTE_HIDDEN
        else:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def _decode_key_material(value: bytes | str) -> bytes:
    return base64.b64decode(value)


def _encode_key_material(value: bytes) -> bytes:
    return base64.b64encode(value)


def _create_secret_key() -> bytes:
    return os.urandom(SecretBox.KEY_SIZE)


def _load_or_create_secret_key() -> bytes:
    global _KEYRING_WORKING

    if not _NACL_AVAILABLE:
        raise RuntimeError("PyNaCl not installed. Run: pip install pynacl")

    if _KEYRING_WORKING and keyring is not None:
        try:
            saved_value = keyring.get_password(SERVICE, KEYNAME)
            if saved_value:
                return _decode_key_material(saved_value)
        except Exception as e:
            logger.debug("keyring.get_password failed: %s", e)
            _KEYRING_WORKING = False
            _warn_keyring_once()

    if not _KEYRING_WORKING:
        existing = _load_key_from_file()
        if existing:
            return existing

    key = _create_secret_key()
    _save_key_to_file(key)  # always save file fallback, even if keyring works

    if _KEYRING_WORKING and keyring is not None:
        try:
            keyring.set_password(SERVICE, KEYNAME, _encode_key_material(key).decode("ascii"))
            return key
        except Exception as e:
            logger.debug("keyring.set_password failed: %s", e)
            _KEYRING_WORKING = False
            _warn_keyring_once()

    _save_key_to_file(key)
    return key


def _box_from_encoded_key(key: bytes | str) -> SecretBox:
    return SecretBox(_decode_key_material(key))


def get_secret_box():
    return SecretBox(_load_or_create_secret_key())


def keyring_encrypt(data: str):
    return get_secret_box().encrypt(data.encode("utf-8"))  # type: ignore[no-any-return]


def keyring_decrypt(data: bytes):
    try:
        return get_secret_box().decrypt(data).decode("utf-8")
    except CryptoError:
        return None


def b64_decrypt(key: bytes, ciphertext: bytes):
    plaintext = _box_from_encoded_key(key).decrypt(_decode_key_material(ciphertext))
    return plaintext.decode("utf-8")


def b64_encrypt(key: bytes, plaintext: str):
    ciphertext = _box_from_encoded_key(key).encrypt(plaintext.encode("utf-8"))
    return _encode_key_material(ciphertext)


def generate_key_and_ciphertext(plaintext: str):
    raw_key = _create_secret_key()
    encoded_key = _encode_key_material(raw_key)
    ciphertext = _encode_key_material(SecretBox(raw_key).encrypt(plaintext.encode("utf-8")))
    return encoded_key, ciphertext
