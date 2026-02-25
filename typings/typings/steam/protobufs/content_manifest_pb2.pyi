from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ContentManifestPayload(_message.Message):
    __slots__ = ("mappings",)
    class FileMapping(_message.Message):
        __slots__ = ("filename", "size", "flags", "sha_filename", "sha_content", "chunks", "linktarget")
        class ChunkData(_message.Message):
            __slots__ = ("sha", "crc", "offset", "cb_original", "cb_compressed")
            SHA_FIELD_NUMBER: _ClassVar[int]
            CRC_FIELD_NUMBER: _ClassVar[int]
            OFFSET_FIELD_NUMBER: _ClassVar[int]
            CB_ORIGINAL_FIELD_NUMBER: _ClassVar[int]
            CB_COMPRESSED_FIELD_NUMBER: _ClassVar[int]
            sha: bytes
            crc: int
            offset: int
            cb_original: int
            cb_compressed: int
            def __init__(self, sha: _Optional[bytes] = ..., crc: _Optional[int] = ..., offset: _Optional[int] = ..., cb_original: _Optional[int] = ..., cb_compressed: _Optional[int] = ...) -> None: ...
        FILENAME_FIELD_NUMBER: _ClassVar[int]
        SIZE_FIELD_NUMBER: _ClassVar[int]
        FLAGS_FIELD_NUMBER: _ClassVar[int]
        SHA_FILENAME_FIELD_NUMBER: _ClassVar[int]
        SHA_CONTENT_FIELD_NUMBER: _ClassVar[int]
        CHUNKS_FIELD_NUMBER: _ClassVar[int]
        LINKTARGET_FIELD_NUMBER: _ClassVar[int]
        filename: str
        size: int
        flags: int
        sha_filename: bytes
        sha_content: bytes
        chunks: _containers.RepeatedCompositeFieldContainer[ContentManifestPayload.FileMapping.ChunkData]
        linktarget: str
        def __init__(self, filename: _Optional[str] = ..., size: _Optional[int] = ..., flags: _Optional[int] = ..., sha_filename: _Optional[bytes] = ..., sha_content: _Optional[bytes] = ..., chunks: _Optional[_Iterable[_Union[ContentManifestPayload.FileMapping.ChunkData, _Mapping]]] = ..., linktarget: _Optional[str] = ...) -> None: ...
    MAPPINGS_FIELD_NUMBER: _ClassVar[int]
    mappings: _containers.RepeatedCompositeFieldContainer[ContentManifestPayload.FileMapping]
    def __init__(self, mappings: _Optional[_Iterable[_Union[ContentManifestPayload.FileMapping, _Mapping]]] = ...) -> None: ...

class ContentManifestMetadata(_message.Message):
    __slots__ = ("depot_id", "gid_manifest", "creation_time", "filenames_encrypted", "cb_disk_original", "cb_disk_compressed", "unique_chunks", "crc_encrypted", "crc_clear")
    DEPOT_ID_FIELD_NUMBER: _ClassVar[int]
    GID_MANIFEST_FIELD_NUMBER: _ClassVar[int]
    CREATION_TIME_FIELD_NUMBER: _ClassVar[int]
    FILENAMES_ENCRYPTED_FIELD_NUMBER: _ClassVar[int]
    CB_DISK_ORIGINAL_FIELD_NUMBER: _ClassVar[int]
    CB_DISK_COMPRESSED_FIELD_NUMBER: _ClassVar[int]
    UNIQUE_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    CRC_ENCRYPTED_FIELD_NUMBER: _ClassVar[int]
    CRC_CLEAR_FIELD_NUMBER: _ClassVar[int]
    depot_id: int
    gid_manifest: int
    creation_time: int
    filenames_encrypted: bool
    cb_disk_original: int
    cb_disk_compressed: int
    unique_chunks: int
    crc_encrypted: int
    crc_clear: int
    def __init__(self, depot_id: _Optional[int] = ..., gid_manifest: _Optional[int] = ..., creation_time: _Optional[int] = ..., filenames_encrypted: _Optional[bool] = ..., cb_disk_original: _Optional[int] = ..., cb_disk_compressed: _Optional[int] = ..., unique_chunks: _Optional[int] = ..., crc_encrypted: _Optional[int] = ..., crc_clear: _Optional[int] = ...) -> None: ...

class ContentManifestSignature(_message.Message):
    __slots__ = ("signature",)
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    signature: bytes
    def __init__(self, signature: _Optional[bytes] = ...) -> None: ...
