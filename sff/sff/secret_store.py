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

"""Basically machine-specific encryption/decryption so that users
don't accidentally share the sensitive information stored in settings.bin"""

import base64
import os

import keyring
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox

SERVICE = "sff_tool"
KEYNAME = "master_key"


def get_secret_box():
    b64 = keyring.get_password(SERVICE, KEYNAME)
    if b64:
        return SecretBox(base64.b64decode(b64))
    key = os.urandom(SecretBox.KEY_SIZE)
    keyring.set_password(SERVICE, KEYNAME, base64.b64encode(key).decode())
    return SecretBox(key)


def keyring_encrypt(data: str):
    box = get_secret_box()
    blob = box.encrypt(data.encode())  # type: ignore
    return blob


def keyring_decrypt(data: bytes):
    box = get_secret_box()
    try:
        return box.decrypt(data).decode()
    except CryptoError:
        pass


def b64_decrypt(key: bytes, ciphertext: bytes):
    box = SecretBox(base64.b64decode(key))
    plaintext = box.decrypt(base64.b64decode(ciphertext))
    return plaintext.decode()


def b64_encrypt(key: bytes, plaintext: str):
    box = SecretBox(base64.b64decode(key))
    ciphertext = box.encrypt(plaintext.encode())
    return base64.b64encode(ciphertext)


def generate_key_and_ciphertext(plaintext: str):
    key = base64.b64encode(os.urandom(SecretBox.KEY_SIZE))
    ciphertext = b64_encrypt(key, plaintext)
    print("Key: ", key)
    print("Cipher text: ", ciphertext)
    return key, ciphertext
