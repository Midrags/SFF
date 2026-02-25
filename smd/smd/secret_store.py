"""Basically machine-specific encryption/decryption so that users
don't accidentally share the sensitive information stored in settings.bin"""

import base64
import os

import keyring
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox

SERVICE = "smd_tool"
KEYNAME = "master_key"


def get_secret_box():
    """Reads or generates the master key stored in keyring and then
    returns a SecretBox with that key"""
    b64 = keyring.get_password(SERVICE, KEYNAME)
    if b64:
        return SecretBox(base64.b64decode(b64))
    key = os.urandom(SecretBox.KEY_SIZE)
    keyring.set_password(SERVICE, KEYNAME, base64.b64encode(key).decode())
    return SecretBox(key)


def keyring_encrypt(data: str):
    """Encrypts text"""
    box = get_secret_box()
    blob = box.encrypt(data.encode())  # type: ignore
    return blob


def keyring_decrypt(data: bytes):
    """Returns none if it failed to decrypt (e.g. master key changed)"""
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
