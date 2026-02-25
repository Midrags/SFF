import base64
import io
import struct
import zlib
from pathlib import Path

from colorama import Fore, Style
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from steam.protobufs.content_manifest_pb2 import (
    ContentManifestMetadata,
    ContentManifestPayload,
    ContentManifestSignature,
)

from sff.zip import read_nth_file_from_zip_bytes

# Magic numbers
PROTOBUF_PAYLOAD_MAGIC = 0x71F617D0
PROTOBUF_METADATA_MAGIC = 0x1F4812BE
PROTOBUF_SIGNATURE_MAGIC = 0x1B81B817
PROTOBUF_ENDOFMANIFEST_MAGIC = 0x32C415AB


def decrypt_filename(b64_encrypted_name: str, key_bytes: bytes) -> str:
    """Decrypts a filename

    Args:
        b64_encrypted_name (str): The encrypted filename
        key_bytes (bytes): The decryption key in bytes

    Returns:
        str: The decrypted filename
    """
    try:
        decoded_data = base64.b64decode(b64_encrypted_name)

        # The first 16 bytes are an encrypted IV.
        # Decrypt it with ECB to get the real IV.
        cipher_ecb = AES.new(key_bytes, AES.MODE_ECB)  # type: ignore
        iv = cipher_ecb.decrypt(decoded_data[:16])

        # The rest of the data is the actual ciphertext.
        ciphertext = decoded_data[16:]

        # Decrypt the ciphertext using the real IV and CBC mode.
        cipher_cbc = AES.new(key_bytes, AES.MODE_CBC, iv)  # type: ignore
        decrypted_padded = cipher_cbc.decrypt(ciphertext)

        # Unpad and clean up the result.
        unpadded = unpad(decrypted_padded, AES.block_size)
        return unpadded.rstrip(b"\x00").decode("utf-8")
    except Exception:
        # If decryption fails for any reason, return the original string
        return b64_encrypted_name


def view_manifest(manifest_file: bytes):
    """Decrypts a manifest file, given a decryption key

    Args:
        encrypted_file (io.BytesIO): The encrypted manifest file
        output_filepath (Path): Where you want the decrypted file to go
        dec_key (str): The decryption key as a hex string
    """

    stream = io.BytesIO(manifest_file)

    magic, payload_length = struct.unpack("<II", stream.read(8))
    if magic != PROTOBUF_PAYLOAD_MAGIC:
        raise ValueError("Bad payload magic")
    payload_bytes = stream.read(payload_length)

    magic, metadata_length = struct.unpack("<II", stream.read(8))
    if magic != PROTOBUF_METADATA_MAGIC:
        raise ValueError("Bad metadata magic")
    metadata_bytes = stream.read(metadata_length)

    magic, metadata_length = struct.unpack("<II", stream.read(8))
    if magic != PROTOBUF_SIGNATURE_MAGIC:
        raise ValueError("Bad signature magic")
    signature_bytes = stream.read(metadata_length)

    original_payload = ContentManifestPayload()
    original_payload.ParseFromString(payload_bytes)

    print(f"{len(original_payload.mappings)} file mappings found.")

    print("PAYLOAD")
    for mapping in original_payload.mappings:
        print(f"\n---\nName: {mapping.filename}\n"
              f"Size: {mapping.size}\n"
              f"Flags: {mapping.flags}\n"
              f"SHA filename: {mapping.sha_filename.hex()}\n"
              f"SHA content: {mapping.sha_content.hex()}\n"
              f"Chunk count: {len(mapping.chunks)}\n"
              "---\n")
        for nth, chunk in enumerate(mapping.chunks):
            print(f"Chunk #{nth+1}")
            print(f"SHA: {chunk.sha.hex()}\n"
                  f"CRC: {hex(chunk.crc)[2:]}\n"
                  f"Offset: {chunk.offset}\n"
                  f"CB Original: {chunk.cb_original}\n"
                  f"CB Compressed: {chunk.cb_compressed}")
    # Update and re-serialize the metadata
    metadata = ContentManifestMetadata()
    metadata.ParseFromString(metadata_bytes)
    print("METADATA")
    print(f"\n---\nDepot ID: {metadata.depot_id}\n"
          f"Manifest ID: {metadata.gid_manifest}\n"
          f"Creation Time: {metadata.creation_time}\n"
          f"Encrypted: {metadata.filenames_encrypted}\n"
          f"CB Disk Original: {metadata.cb_disk_original}\n"
          f"CB Disk Compressed: {metadata.cb_disk_compressed}\n"
          f"Unique Chunks: {metadata.unique_chunks}\n"
          f"CRC (Encrypted): {hex(metadata.crc_encrypted)[2:]}\n"
          f"CRC (Clear): {hex(metadata.crc_clear)[2:]}\n"
          "---\n")
    signature = ContentManifestSignature()
    signature.ParseFromString(signature_bytes)
    print(
        f"Signature: {signature.signature.hex() if signature.signature else 'Missing'}"
    )


def decrypt_and_save_manifest(
    encrypted_file: bytes, output_filepath: Path, dec_key: str
):
    """Decrypts a manifest file, given a decryption key

    Args:
        encrypted_file (io.BytesIO): The encrypted manifest file
        output_filepath (Path): Where you want the decrypted file to go
        dec_key (str): The decryption key as a hex string
    """
    # Check if it's a ZIP file, then extract the first file
    if x := read_nth_file_from_zip_bytes(0, encrypted_file):
        stream = x
    else:
        stream = io.BytesIO(encrypted_file)

    magic, payload_length = struct.unpack("<II", stream.read(8))
    if magic != PROTOBUF_PAYLOAD_MAGIC:
        raise ValueError("Bad payload magic")
    payload_bytes = stream.read(payload_length)

    magic, metadata_length = struct.unpack("<II", stream.read(8))
    if magic != PROTOBUF_METADATA_MAGIC:
        raise ValueError("Bad metadata magic")
    metadata_bytes = stream.read(metadata_length)

    original_payload = ContentManifestPayload()
    original_payload.ParseFromString(payload_bytes)

    print(
        f"Decrypting {len(original_payload.mappings)} file mappings... ",
        end="",
        flush=True,
    )

    # Decrypt filenames
    key_bytes = bytes.fromhex(dec_key)
    new_mappings: list[ContentManifestPayload.FileMapping] = []
    for mapping in original_payload.mappings:
        new_mapping = ContentManifestPayload.FileMapping()
        new_mapping.CopyFrom(mapping)

        # Decrypt filename and linktarget if they exist
        new_mapping.filename = decrypt_filename(mapping.filename, key_bytes)
        if mapping.linktarget:
            new_mapping.linktarget = decrypt_filename(mapping.linktarget, key_bytes)

        new_mappings.append(new_mapping)
    print("Done!")

    # Create the new payload object with the sorted, decrypted data
    fixed_payload = ContentManifestPayload()
    fixed_payload.mappings.extend(new_mappings)

    # Serialize the new payload and recalculate crc_clear
    fixed_payload_bytes = fixed_payload.SerializeToString()
    length_bytes = struct.pack("<I", len(fixed_payload_bytes))
    data_to_checksum = length_bytes + fixed_payload_bytes
    new_crc = zlib.crc32(data_to_checksum) & 0xFFFFFFFF
    print(f"Recalculated CRC-32 checksum of decrypted data: {hex(new_crc)[2:]}")

    # Update and re-serialize the metadata
    metadata = ContentManifestMetadata()
    metadata.ParseFromString(metadata_bytes)
    metadata.crc_clear = new_crc
    metadata.filenames_encrypted = False  # Mark the filenames as decrypted
    fixed_metadata_bytes = metadata.SerializeToString()

    # Some users don't have a depotcache folder (e.g. new installation)
    output_filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write the new manifest file
    with open(output_filepath, "wb") as f:
        f.write(struct.pack("<II", PROTOBUF_PAYLOAD_MAGIC, len(fixed_payload_bytes)))
        f.write(fixed_payload_bytes)

        f.write(struct.pack("<II", PROTOBUF_METADATA_MAGIC, len(fixed_metadata_bytes)))
        f.write(fixed_metadata_bytes)

        f.write(struct.pack("<II", PROTOBUF_SIGNATURE_MAGIC, 0))
        f.write(struct.pack("<I", PROTOBUF_ENDOFMANIFEST_MAGIC))
    print(
        Fore.BLUE
        + f"Manifest created at: {output_filepath.resolve()}"
        + Style.RESET_ALL
    )


if __name__ == "__main__":
    file_a = Path(r"C:\GAMES\Steam\depotcache\1392821_4740032384826825263.manifest")
    with file_a.open("rb") as f:
        print(f"Reading {file_a.name}")
        view_manifest(f.read())
