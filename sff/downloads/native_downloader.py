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

"""Native Steam CDN depot downloader — no .NET, no DDMod, pure Python.

Replaces ``dotnet DepotDownloaderMod.dll`` on Linux by downloading
depot content directly from Steam CDN servers over HTTPS.  Uses the
existing ``steam`` Python library for anonymous Steam login and CDN
server discovery, then fetches manifests and content chunks with
plain HTTP, handling AES-256-CBC decryption and LZMA/Zstd
decompression in-process.

The Steam CDN protocol is publicly documented by Valve and
re-implemented in dozens of open-source tools (SteamKit2,
DepotDownloader, SteamCMD).  Every line here is original Python
written against those protocol specs.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import struct
import time
import zipfile
import zlib
from pathlib import Path
from typing import Callable

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAYLOAD_MAGIC = 0x71F617D0
METADATA_MAGIC = 0x1F4812BE
SIGNATURE_MAGIC = 0x1B81B817
END_MAGIC = 0x32C415AB

_CDN_TIMEOUT = 60.0
# Full passes over the host pool per chunk: one main pass plus one
# requeue round (after any deny-triggered token re-mints).
_MAX_CHUNK_ROUNDS = 2
# Steam CDN deny blobs (invalid/foreign token, missing chunk on that
# edge) are a few hundred bytes; real chunks are far larger. Used only
# to label diagnostics — decryption still decides correctness.
_DENY_BLOB_MAX_BYTES = 65536


class _ChunkError(Exception):
    """A chunk failed on every host. Carries per-attempt diagnostics."""

    def __init__(self, report: list):
        super().__init__("chunk failed on all hosts")
        self.report = report

_REQUEST_CODE_FALLBACKS = (
    ("https://manifest.steam.run/api/manifest/{}", "json", "content"),
    ("http://gmrc.wudrm.com/manifest/{}", "text", None),
)

# ---------------------------------------------------------------------------
# AES-256 symmetric decrypt (Valve depot encryption)
#   — first 16 bytes = AES-256-ECB(IV)
#   — remaining bytes = AES-256-CBC(body, IV)
# ---------------------------------------------------------------------------

def _aes_symmetric_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) < 16:
        raise ValueError("ciphertext too short for AES")
    iv_block = ciphertext[:16]
    body = ciphertext[16:]
    ecb = AES.new(key, AES.MODE_ECB)
    iv = ecb.decrypt(iv_block)
    cbc = AES.new(key, AES.MODE_CBC, iv=iv)
    return unpad(cbc.decrypt(body), 16)


# ---------------------------------------------------------------------------
# Manifest decoding
# ---------------------------------------------------------------------------

def _unzip_single(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return zf.read(zf.namelist()[0])


def _decrypt_filename(encoded: str, key: bytes) -> str:
    import base64
    stripped = "".join(c for c in encoded if not c.isspace())
    raw = base64.b64decode(stripped)
    plain = _aes_symmetric_decrypt(raw, key)
    end = plain.find(0)
    return (plain[:end] if end >= 0 else plain).decode("utf-8")


def decode_manifest(raw_manifest: bytes, depot_key: bytes) -> dict:
    """Decrypt and parse a depot manifest, returning a plain dict."""
    from steam.protobufs.content_manifest_pb2 import (  # type: ignore
        ContentManifestMetadata,
        ContentManifestPayload,
    )

    if raw_manifest[:4] == b"PK\x03\x04":
        raw_manifest = _unzip_single(raw_manifest)

    buf = io.BytesIO(raw_manifest)

    def _section(magic: int) -> bytes:
        m, l = struct.unpack("<II", buf.read(8))
        if m != magic:
            raise ValueError(f"section magic 0x{m:08X} != 0x{magic:08X}")
        return buf.read(l)

    payload_bytes = _section(PAYLOAD_MAGIC)
    meta_bytes = _section(METADATA_MAGIC)
    _section(SIGNATURE_MAGIC)

    end = struct.unpack("<I", buf.read(4))[0]
    if end != END_MAGIC:
        raise ValueError(f"end magic 0x{end:08X}")

    payload = ContentManifestPayload()
    payload.ParseFromString(payload_bytes)
    meta = ContentManifestMetadata()
    meta.ParseFromString(meta_bytes)

    fn_encrypted = meta.filenames_encrypted

    mappings = []
    for m in payload.mappings:
        fn = m.filename or ""
        if fn_encrypted and fn:
            fn = _decrypt_filename(fn, depot_key)
        chunks = []
        for ch in m.chunks:
            chunks.append({
                "sha": ch.sha.hex() if ch.sha else "",
                "offset": ch.offset or 0,
                "cb_original": ch.cb_original or 0,
                "cb_compressed": ch.cb_compressed or 0,
            })
        mappings.append({
            "filename": fn,
            "size": m.size or 0,
            "flags": m.flags or 0,
            "chunks": chunks,
        })

    return {"mappings": mappings}


# ---------------------------------------------------------------------------
# Chunk decompression
# ---------------------------------------------------------------------------

def _decompress_vz1(data: bytes) -> bytes:
    """VZ1 = LZMA1 raw + CRC32 footer.  Mirrors valve's on-disk format.

    Layout: | 3 header 'VZa' | 4 skip | 5 LZMA props | body | 10 footer |
    Footer:  | 4 CRC32 LE | 4 uncompressed size LE | 2 'zv' |
    """
    import lzma
    if len(data) < 22 or data[:3] != b"VZa" or data[-2:] != b"zv":
        raise ValueError("invalid VZ1 container")

    lzma_filter = lzma._decode_filter_properties(lzma.FILTER_LZMA1, data[7:12])
    decomp = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[lzma_filter])

    body_end = len(data) - 10
    lzma_body = data[12:body_end]
    expected_crc, expected_size = struct.unpack("<II", data[body_end:body_end + 8])

    out = decomp.decompress(lzma_body, max_length=expected_size)
    if len(out) != expected_size:
        raise ValueError(f"VZ1 size {len(out)} != {expected_size}")
    actual = zlib.crc32(out) & 0xFFFFFFFF
    if actual != expected_crc:
        raise ValueError(f"VZ1 CRC 0x{actual:08X} != 0x{expected_crc:08X}")
    return out


def _decompress_vzstd(data: bytes) -> bytes:
    """VSZTD = Zstd with CRC32 verification.

    Layout: | 4 'VSZa' | 4 CRC32 LE | body | 4 CRC32 LE | 8 size LE | 3 'zsv' |
    """
    HDR, TRL = 8, 15
    if len(data) < HDR + TRL or data[:4] != b"VSZa" or data[-3:] != b"zsv":
        raise ValueError("invalid VSZTD container")
    hdr_crc = struct.unpack("<I", data[4:8])[0]
    trl_start = len(data) - TRL
    ftr_crc = struct.unpack("<I", data[trl_start:trl_start + 4])[0]
    expected_size = struct.unpack("<Q", data[trl_start + 4:trl_start + 12])[0]
    if hdr_crc != ftr_crc:
        raise ValueError(f"VSZTD CRC 0x{hdr_crc:08X} != 0x{ftr_crc:08X}")
    compressed = data[HDR:trl_start]
    try:
        import zstandard
        out = zstandard.decompress(compressed, max_output_size=expected_size)
    except ImportError:
        import subprocess, tempfile
        ti = tempfile.NamedTemporaryFile(suffix=".zst", delete=False)
        to_ = tempfile.NamedTemporaryFile(suffix=".raw", delete=False)
        ti.write(compressed); ti.close(); to_.close()
        subprocess.run(["zstd", "-d", "-f", "-o", to_.name, ti.name],
                       capture_output=True, timeout=60)
        out = Path(to_.name).read_bytes()
        os.unlink(ti.name); os.unlink(to_.name)
    if len(out) != expected_size:
        raise ValueError(f"VSZTD size {len(out)} != {expected_size}")
    actual = zlib.crc32(out) & 0xFFFFFFFF
    if actual != hdr_crc:
        raise ValueError(f"VSZTD CRC 0x{actual:08X} != 0x{hdr_crc:08X}")
    return out


def _decompress_chunk(data: bytes) -> bytes:
    if data[:3] == b"VZa":
        return _decompress_vz1(data)
    if data[:4] == b"VSZa":
        return _decompress_vzstd(data)
    raise ValueError(f"unknown chunk magic: {data[:4].hex()}")


# ---------------------------------------------------------------------------
# CDN helpers
# ---------------------------------------------------------------------------

def _fetch_manifest_code_external(manifest_gid: int) -> int | None:
    for tmpl, mode, field in _REQUEST_CODE_FALLBACKS:
        url = tmpl.format(manifest_gid)
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code != 200:
                continue
            body = resp.text.strip()
            if mode == "json":
                import json
                data = json.loads(body)
                val = str(data.get(field or "", "")).strip()
                if val.isdigit():
                    return int(val)
            elif mode == "text" and body.isdigit():
                return int(body)
        except Exception:
            continue
    return None


def _resolve_request_code(
    cdn_client,
    app_id: int, depot_id: int, manifest_id: int,
    print_fn: Callable,
) -> int:
    try:
        code = cdn_client.get_manifest_request_code(
            app_id=app_id, depot_id=depot_id, manifest_gid=manifest_id,
        )
        if code:
            return code
    except Exception:
        pass
    print_fn("[native] Steam refused request code, trying external providers...")
    code = _fetch_manifest_code_external(manifest_id)
    if code:
        print_fn("[native] Got request code from external provider")
        return code
    raise RuntimeError(f"No manifest request code for depot {depot_id}")


_CDN_SERVERLIST_URL = (
    "https://api.steampowered.com/IContentServerDirectoryService/"
    "GetServersForSteamPipe/v1/"
)
# Well-known Steam CDN hosts that resolve globally. Used only when both
# the Steam client's server list and the public webapi endpoint fail.
_FALLBACK_CDN_HOSTS = ("steampipe.akamaized.net", "cs.steampowered.com")


def _normalize_cdn_server(s) -> dict:
    """Normalize a CDN server entry (ContentServer object or dict) into a
    plain dict with host/vhost/https_support/NumEntries keys."""
    if isinstance(s, dict):
        host = str(s.get("host") or "")
        return {
            "host": host,
            "vhost": str(s.get("vhost") or host),
            "https_support": str(s.get("https_support") or ""),
            "NumEntries": int(s.get("NumEntries") or s.get("num_entries_in_client_list") or 1),
        }
    host = str(getattr(s, "host", "") or "")
    return {
        "host": host,
        "vhost": str(getattr(s, "vhost", "") or host),
        "https_support": str(getattr(s, "https_support", "") or ""),
        "NumEntries": int(getattr(s, "NumEntries", 1) or 1),
    }


def _fetch_cdn_servers_via_webapi(cell_id=0) -> list:
    """Fetch the CDN server list from the public Steam webapi with httpx.

    The steam client's CDNClient fetches this list over the bundled
    requests/gevent stack, which stalls inside the AppImage (issue #144)
    even though the endpoint answers in ~0.3s standalone. httpx is the
    same stack the chunk downloads already use successfully.
    """
    try:
        resp = httpx.get(
            _CDN_SERVERLIST_URL,
            params={"cell_id": int(cell_id or 0), "max_servers": 20},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.debug("CDN server list webapi HTTP %s", resp.status_code)
            return []
        servers = (resp.json().get("response") or {}).get("servers") or []
        out = []
        for s in servers:
            if not isinstance(s, dict) or not s.get("host"):
                continue
            out.append({
                "host": str(s["host"]),
                "vhost": str(s.get("vhost") or s["host"]),
                "https_support": str(s.get("https_support") or ""),
                "NumEntries": int(s.get("num_entries_in_client_list") or 1),
            })
        logger.debug("CDN server list via webapi: %d host(s)", len(out))
        return out
    except Exception as e:
        logger.debug("CDN server list webapi fetch failed: %s", e)
        return []


def _get_cdn_servers(cdn_client, cell_id=0) -> list:
    """Return a list of CDN server dicts, trying sources in order:

    1. the Steam client's CDNClient list (may be a deque of
       ContentServer objects, not a list — normalize it),
    2. the public GetServersForSteamPipe webapi endpoint via httpx,
    3. a small hard-coded list of well-known hosts.
    """
    try:
        raw = cdn_client.servers
        if raw:
            servers = [_normalize_cdn_server(s) for s in raw]
            servers = [s for s in servers if s.get("host")]
            if servers:
                logger.debug("CDN server list via Steam client: %d host(s)", len(servers))
                return servers
    except Exception:
        pass
    servers = _fetch_cdn_servers_via_webapi(cell_id)
    if servers:
        return servers
    logger.warning("CDN server list: using hard-coded fallback hosts %r", _FALLBACK_CDN_HOSTS)
    return [
        {"host": h, "vhost": h, "https_support": "", "NumEntries": 1}
        for h in _FALLBACK_CDN_HOSTS
    ]


def _download_file(url: str, timeout: float = _CDN_TIMEOUT) -> bytes | None:
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _normalize_manifest_path(filename: str) -> str | None:
    r"""Normalize a manifest filename into a safe POSIX-style relative path.

    Steam manifests store paths with Windows backslash separators. On
    Linux a backslash is a legal filename character, so joining the raw
    name once created single flat files like ``Some\File\Name.exe``
    instead of subdirectories. Returns the normalized relative path, or
    None when the path is empty or tries to escape via ``..``.
    """
    if not filename:
        return None
    cleaned = str(filename).replace("\\", "/")
    parts = []
    for part in cleaned.split("/"):
        part = part.strip()
        if not part or part in (".",):
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def download_depot(
    app_id: int | str,
    depot_id: int | str,
    manifest_id: int | str,
    depot_key: str,
    output_dir: Path | str,
    *,
    print_fn: Callable = print,
    os_filter: str = "",
    steam_path: Path | str | None = None,
    manifest_bytes: bytes | None = None,
    manifest_path: Path | str | None = None,
) -> tuple[bool, int]:
    """Download one Steam depot directly from CDN (no .NET).

    If *manifest_bytes* or *manifest_path* is provided the manifest is
    used directly (no CDN manifest fetch), which is required when the
    Steam account does not own the game.  The manifest content is
    AES-256-CBC encrypted by Valve and will be decrypted in-process.
    """
    app_id = int(app_id)
    depot_id = int(depot_id)
    manifest_gid = int(manifest_id)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    key_bytes = bytes.fromhex(depot_key)
    if len(key_bytes) != 32:
        raise ValueError(f"depot key must be 32 bytes, got {len(key_bytes)}")

    # ── Steam connection ──────────────────────────────────
    from steam.client import SteamClient  # type: ignore
    from steam.client.cdn import CDNClient  # type: ignore

    client = SteamClient()
    try:
        client.anonymous_login()
    except Exception:
        time.sleep(2)
        client.anonymous_login()

    cdn = CDNClient(client)
    servers = _get_cdn_servers(cdn, cell_id=getattr(cdn, "cell_id", 0) or 0)
    if not servers:
        client.disconnect()
        return False, 0

    # ── CDN server pool + per-host auth tokens ────────────
    # Steam CDN auth tokens are per-host: a token minted for one host is
    # rejected (deny blob) by the others. The old code minted a single
    # token and applied it to every host, deterministically killing the
    # chunks routed to non-token hosts (issue #144). Mint lazily per
    # host; re-mint once after a deny so revoked/expired tokens recover.
    server_hosts: list[str] = []
    host_scheme: dict[str, str] = {}
    for s in servers:
        host = s.get("host", "") if isinstance(s, dict) else str(s)
        if not host or host in server_hosts:
            continue
        server_hosts.append(host)
        host_scheme[host] = "https" if s.get("https_support") == "mandatory" else "http"
    if not server_hosts:
        server_hosts = ["steampipe.akamaized.net"]
        host_scheme["steampipe.akamaized.net"] = "http"

    tokens: dict[str, str] = {}
    token_reset: set[str] = set()

    def _get_token(host: str, reset: bool = False) -> str:
        if reset and host in tokens:
            tokens.pop(host, None)
        if host not in tokens:
            try:
                t = cdn.get_auth_token(app_id=app_id, depot_id=depot_id, host=host)
                tokens[host] = t or ""
                logger.debug("auth token for %s: %s", host, "ok" if t else "empty")
            except Exception as e:
                logger.debug("auth token for %s failed: %s", host, e)
                tokens[host] = ""
        return tokens[host]

    # Primary token (first host that grants) — used for the manifest URL.
    auth_token = ""
    for host in server_hosts:
        auth_token = _get_token(host)
        if auth_token:
            break

    print_fn(
        "[native] CDN servers: %d host(s) (%s%s)"
        % (
            len(server_hosts),
            ", ".join(server_hosts[:4]),
            "..." if len(server_hosts) > 4 else "",
        )
    )

    # ── Manifest (local or CDN) ────────────────────────────
    if manifest_path:
        manifest_bytes = Path(manifest_path).read_bytes()
    if manifest_bytes:
        print_fn(f"[native] Using provided manifest ({len(manifest_bytes)} bytes)")

    if manifest_bytes is None or len(manifest_bytes) == 0:
        # ── Request code ──────────────────────────────────
        request_code = _resolve_request_code(cdn, app_id, depot_id, manifest_gid, print_fn)

        # ── Download manifest from CDN ────────────────────
        last_err = ""
        for s in servers:
            host = s.get("host", "") if isinstance(s, dict) else str(s)
            if not host:
                continue
            scheme = "https" if isinstance(s, dict) and s.get("https_support") == "mandatory" else "http"
            url = f"{scheme}://{host}/depot/{depot_id}/manifest/{manifest_gid}/5/{request_code}{auth_token}"
            data = _download_file(url)
            if data:
                manifest_bytes = data
                print_fn(f"[native] Manifest from {host}")
                break
            last_err = f"HTTP error from {host}"

        if manifest_bytes is None or len(manifest_bytes) == 0:
            client.disconnect()
            print_fn(f"[native] Manifest download failed: {last_err}")
            return False, 0

    # ── Decrypt manifest ──────────────────────────────────
    try:
        manifest = decode_manifest(manifest_bytes, key_bytes)
    except Exception as e:
        client.disconnect()
        print_fn(f"[native] Manifest decrypt failed: {e}")
        return False, 0

    mappings = manifest.get("mappings", [])
    total_chunks = sum(len(m.get("chunks", [])) for m in mappings)
    total_size = sum(m.get("size", 0) for m in mappings)
    print_fn(f"[native] {len(mappings)} files, {total_chunks} chunks, {total_size:,} bytes")

    # ── Build flat chunk list + pre-verify ─────────────────
    # Each entry: (sha, offset, cb_original, file_path)
    all_flat: list[tuple[str, int, int, Path]] = []
    os_filtered_count = 0

    for mapping in mappings:
        filename = _normalize_manifest_path(mapping.get("filename", ""))
        flags = mapping.get("flags", 0)
        if flags & 0x40 or not filename:
            continue
        if os_filter and os_filter != "all":
            lo = filename.lower()
            if os_filter == "linux":
                if lo.endswith((".dll", ".exe")):
                    os_filtered_count += 1; continue
                if "/win" in lo and "/window" not in lo:
                    os_filtered_count += 1; continue
            elif os_filter == "windows":
                if lo.endswith((".so", ".dylib")):
                    os_filtered_count += 1; continue
                if re.search(r"/(linux|osx|mac)/", lo):
                    os_filtered_count += 1; continue

        file_path = output_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_size = mapping.get("size", 0)
        if file_size and not file_path.exists():
            try:
                with open(file_path, "wb") as f:
                    f.truncate(file_size)
            except OSError:
                pass

        for chunk in mapping.get("chunks", []):
            sha = chunk.get("sha", "")
            if not sha:
                continue
            all_flat.append((sha, chunk.get("offset", 0),
                             chunk.get("cb_original", 0), file_path))

    # ── Pre-verify: SHA1-check existing chunks ───────────
    verified_sha: set[str] = set()
    for sha, offset, cb_original, fpath in all_flat:
        try:
            if not fpath.exists():
                continue
            fsize = fpath.stat().st_size
            if offset + cb_original > fsize:
                continue
            with open(fpath, "rb") as vf:
                vf.seek(offset)
                disk_data = vf.read(cb_original)
            if hashlib.sha1(disk_data).hexdigest() == sha:
                verified_sha.add(sha)
        except OSError:
            continue

    pending = [(s, o, c, p) for s, o, c, p in all_flat if s not in verified_sha]
    skipped = len(verified_sha)
    if skipped:
        print_fn(f"[native] {skipped}/{total_chunks} chunks already on disk (skipping)")

    if not pending:
        client.disconnect()
        print_fn(f"[native] Depot {depot_id} fully cached: {skipped} chunks, 0 downloaded")
        return True, total_size

    # ── Chunk -> preferred host assignment (rotation) ─────
    host_for_chunk: dict[str, str] = {}
    host_idx = 0
    for sha, _, _, _ in pending:
        host_for_chunk[sha] = server_hosts[host_idx % len(server_hosts)]
        host_idx += 1

    # ── Shared HTTP client (keep-alive pooling) ───────────
    import concurrent.futures
    import threading

    http_client = httpx.Client(
        timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
        limits=httpx.Limits(max_keepalive_connections=64, max_connections=128),
        follow_redirects=True,
    )

    done_lock = threading.Lock()
    total_done = [0]
    total_bytes = [0]
    fatal_error = [None]

    reports_lock = threading.Lock()
    chunk_reports: dict[str, list] = {}

    def _report_for_sha(sha: str) -> list:
        with reports_lock:
            return chunk_reports.setdefault(sha, [])

    def _download_one_chunk(sha: str, offset: int, cb_original: int, fpath: Path) -> int:
        """Downloads one chunk across the full host pool.

        Tries every host (rotated so the preferred host goes first),
        using that host's own auth token. A chunk must fail on EVERY
        host before it is reported. Returns bytes written, or raises
        _ChunkError carrying per-attempt diagnostics.
        """
        if fatal_error[0] is not None:
            return -1

        start = host_for_chunk.get(sha, server_hosts[0])
        try:
            start_i = server_hosts.index(start)
        except ValueError:
            start_i = 0
        order = server_hosts[start_i:] + server_hosts[:start_i]

        for round_no in range(_MAX_CHUNK_ROUNDS):
            for host in order:
                if fatal_error[0] is not None:
                    raise _ChunkError(_report_for_sha(sha))
                scheme = host_scheme.get(host, "http")
                token = _get_token(host, reset=host in token_reset)
                url = f"{scheme}://{host}/depot/{depot_id}/chunk/{sha}{token}"
                t0 = time.time()
                status = None
                size = 0
                outcome = "?"
                try:
                    resp = http_client.get(url)
                    status = resp.status_code
                    content = resp.content or b""
                    size = len(content)
                    if status == 200 and content:
                        try:
                            dec = _aes_symmetric_decrypt(content, key_bytes)
                            raw = _decompress_chunk(dec)
                            if hashlib.sha1(raw).hexdigest() != sha:
                                outcome = "sha-mismatch"
                            else:
                                with open(fpath, "r+b") as f:
                                    f.seek(offset)
                                    f.write(raw)
                                n = len(raw)
                                with done_lock:
                                    total_bytes[0] += n
                                    total_done[0] += 1
                                return n
                        except Exception as e:
                            outcome = f"decrypt-fail({type(e).__name__})"
                    else:
                        outcome = f"http-{status}"
                except Exception as e:
                    outcome = f"conn-err({type(e).__name__})"

                elapsed = time.time() - t0
                _report_for_sha(sha).append({
                    "host": host, "status": status, "size": size,
                    "outcome": outcome, "elapsed": round(elapsed, 2),
                })
                logger.debug("[native] chunk %s host %s -> %s (%dB, %.1fs)",
                             sha[:16], host, outcome, size, elapsed)
                # A tiny 200 that fails to decrypt is the CDN deny blob
                # (foreign/expired token): re-mint and retry next round.
                if size and size < _DENY_BLOB_MAX_BYTES and outcome.startswith("decrypt-fail"):
                    token_reset.add(host)
                if outcome.startswith("http-401") or outcome.startswith("http-403"):
                    token_reset.add(host)
            if round_no < _MAX_CHUNK_ROUNDS - 1:
                time.sleep(min(0.5 * (2 ** round_no), 10.0))
        raise _ChunkError(_report_for_sha(sha))

    # ── Concurrent chunk download ─────────────────────────
    try:
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings
        val = get_setting(Settings.DOWNLOAD_CONCURRENCY)
        MAX_WORKERS = min(max(int(val) if val else 32, 8), 64)
    except Exception:
        MAX_WORKERS = 32
    print_fn(f"[native] Downloading {len(pending)} chunks ({MAX_WORKERS} concurrent)...")

    failures: dict[str, list] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for sha, offset, cb_original, fpath in pending:
            fut = executor.submit(_download_one_chunk, sha, offset, cb_original, fpath)
            futures[fut] = sha

        total = len(pending)
        for fut in concurrent.futures.as_completed(futures):
            sha = futures[fut]
            try:
                fut.result()
            except _ChunkError as e:
                failures[sha] = e.report
            except Exception as e:
                failures[sha] = [{
                    "host": "?", "status": None, "size": 0,
                    "outcome": f"unexpected({type(e).__name__})", "elapsed": 0.0,
                }]

            if total_done[0] % 100 == 0 or total_done[0] == total:
                pct = (total_done[0] / total) * 100
                print_fn(f"\r[native] {total_done[0]}/{total} chunks ({pct:.0f}%) | {skipped} cached | {total_bytes[0]:,} B")

    http_client.close()
    client.disconnect()

    if failures:
        fatal_error[0] = "chunk failures"  # bail any stragglers fast
        print_fn(
            f"[native] Failed {len(failures)} chunk(s) after {_MAX_CHUNK_ROUNDS} round(s) "
            f"across {len(server_hosts)} host(s):"
        )
        for sha, report in list(failures.items())[:10]:
            details = ", ".join(
                f"{r.get('host')}={r.get('status')}/{r.get('outcome')}({r.get('size')}B)"
                for r in report
            ) or "no attempts"
            print_fn(f"[native]   {sha[:16]}... {details}")
        if len(failures) > 10:
            print_fn(f"[native]   ... and {len(failures) - 10} more")
        return False, total_bytes[0]

    print_fn(f"[native] Depot {depot_id} done: {total_bytes[0]:,} bytes ({skipped} cached, {total} downloaded)")
    return True, total_bytes[0]
