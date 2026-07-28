"""Detect the on-disk extension/media-type of an originally-downloaded file.

Used when the cache stores a source's original artifact byte-for-byte: we need
a faithful extension so the public-export layer can decide how to present it.

Detection precedence (highest first):
    1. server media type (Content-Type)
    2. extension parsed from a filename / source URL
    3. magic-byte sniff of the leading bytes
    4. ``.bin`` fallback
"""

from __future__ import annotations

import re

# --- media type <-> extension -------------------------------------------------

_MEDIA_TYPE_TO_EXT: dict[str, str] = {
    "text/csv": "csv",
    "text/tab-separated-values": "tsv",
    "application/json": "json",
    "application/geo+json": "geojson",
    "application/vnd.geo+json": "geojson",
    "application/vnd.google-earth.kml+xml": "kml",
    "application/vnd.google-earth.kmz": "kmz",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/gzip": "gz",
    "application/x-parquet": "parquet",
    "application/vnd.apache.parquet": "parquet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/pdf": "pdf",
    "application/x-netcdf": "nc",
    "text/plain": "txt",
}


def ext_from_media_type(media_type: str | None) -> str:
    if not media_type:
        return ""
    base = str(media_type).split(";", 1)[0].strip().lower()
    return _MEDIA_TYPE_TO_EXT.get(base, "")


def ext_from_filename(name: str | None) -> str:
    if not name:
        return ""
    # Strip query/fragment if a URL was passed.
    candidate = str(name).split("?", 1)[0].split("#", 1)[0].strip()
    match = re.search(r"\.([A-Za-z0-9]{1,8})$", candidate)
    if not match:
        return ""
    ext = match.group(1).lower()
    # Normalize a couple of common aliases.
    if ext in {"jsonl", "ndjson"}:
        return "jsonl"
    return ext


def ext_from_magic(data: bytes | None) -> str:
    """Sniff a few well-known signatures. Returns "" when unknown."""
    if not data:
        return ""
    head = data[:16]
    if head[:4] == b"PK\x03\x04":
        # Zip container: could be xlsx/ods/kmz/shapefile-zip/plain zip.
        # We can't tell sub-type cheaply here; callers refine via filename/media.
        return "zip"
    if head[:4] == b"PAR1" or data[-4:] == b"PAR1":
        return "parquet"
    if head[:2] == b"\x1f\x8b":
        return "gz"
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:8] == b"\x89HDF\r\n\x1a\n":
        return "h5"
    stripped = head.lstrip()
    if stripped[:1] in (b"{", b"["):
        return "json"
    if stripped[:5].lower() == b"<?xml" or stripped[:1] == b"<":
        return "xml"
    return ""


def detect_extension(
    *,
    data: bytes | None = None,
    media_type: str | None = None,
    filename: str | None = None,
) -> str:
    """Best-effort extension (no leading dot) for an original artifact.

    Filename/media-type win over a raw zip sniff because a zip signature is
    shared by xlsx/kmz/ods/shapefile bundles -- the name or content-type
    disambiguates them.
    """
    by_name = ext_from_filename(filename)
    by_media = ext_from_media_type(media_type)
    by_magic = ext_from_magic(data)

    # Prefer the most specific source. A bare "zip" sniff should yield to a
    # filename/media type that names the real container (xlsx, kmz, ...).
    if by_media and by_media != "zip":
        return by_media
    if by_name:
        return by_name
    if by_media:
        return by_media
    if by_magic:
        return by_magic
    return "bin"


def resolve_pending_original(
    original_bytes: bytes | None,
    original_filename: str | None,
    original_media_type: str | None,
) -> tuple[bytes | None, str | None, str | None]:
    """Fill in the original artifact from the run's pending-download channel.

    When a module downloaded a real file earlier this run (via
    ``net.download_file`` or ``net.note_original_bytes``) and didn't pass the
    bytes to ``save_raw`` explicitly, attach them here so the cache stays
    faithful. Returns the (possibly filled) ``(bytes, filename, media_type)``.
    """
    if original_bytes is not None:
        return original_bytes, original_filename, original_media_type
    try:
        from sancho.runtime import request_state as _request_state

        pending = _request_state.take_pending_original()
    except Exception:
        pending = None
    if not pending:
        return original_bytes, original_filename, original_media_type

    data_obj = pending.get("data")
    if isinstance(data_obj, (bytes, bytearray)):
        original_bytes = bytes(data_obj)
    else:
        path_obj = pending.get("path")
        if isinstance(path_obj, str) and path_obj:
            try:
                from pathlib import Path as _Path

                original_bytes = _Path(path_obj).read_bytes()
            except Exception:
                original_bytes = None
    if original_bytes is not None:
        original_filename = original_filename or pending.get("filename")
        original_media_type = original_media_type or pending.get("media_type")
    return original_bytes, original_filename, original_media_type


__all__ = [
    "detect_extension",
    "ext_from_media_type",
    "ext_from_filename",
    "ext_from_magic",
    "resolve_pending_original",
]
