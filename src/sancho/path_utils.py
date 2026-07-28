"""Shared, cross-platform-safe path/segment helpers.

The single source of truth for turning arbitrary user/provider text into a
filesystem segment that is:

* lowercase and readable,
* free of Windows/macOS/Linux-invalid characters,
* bounded in length (long values are truncated and given a deterministic hash
  suffix so different long inputs never collide silently),
* never empty.

Used by both the canonical cache (bounded record path segments) and the public
export layer (readable, bounded user-facing filenames).
"""

from __future__ import annotations

import hashlib
import re

DEFAULT_MAX_LEN = 48
DEFAULT_HASH_LEN = 8
_FALLBACK = "dataset"

# Characters that are invalid on Windows (the strictest of the three platforms)
# plus control characters. Everything matched here is replaced with a separator.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_SEP_RUN = re.compile(r"[-_\s.]+")
_NON_WORD = re.compile(r"[^a-z0-9\-]+")
_DASH_RUN = re.compile(r"-{2,}")

# Reserved device names on Windows. A segment equal to one of these (optionally
# with an extension) is unusable, so we prefix it.
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _hash_suffix(value: str, hash_len: int) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[: max(1, hash_len)]


def safe_slug(value: str, *, max_len: int = DEFAULT_MAX_LEN, hash_len: int = DEFAULT_HASH_LEN) -> str:
    """Return a bounded, filesystem-safe, lowercase slug for ``value``.

    Stable: the same input always produces the same output. If the cleaned slug
    exceeds ``max_len`` it is truncated and ``__<hash>`` (derived from the full
    pre-truncation slug) is appended so distinct long inputs stay distinct.
    """
    raw = value if isinstance(value, str) else str(value)
    text = raw.strip().lower()
    text = _UNSAFE.sub("-", text)
    text = _SEP_RUN.sub("-", text)
    text = _NON_WORD.sub("-", text)
    text = _DASH_RUN.sub("-", text)
    text = text.strip("-_.")

    if not text:
        # Preserve *some* signal from a non-empty original (e.g. all-punctuation)
        # via a hash, otherwise fall back to a constant.
        if raw.strip():
            return f"{_FALLBACK}__{_hash_suffix(raw, hash_len)}"
        return _FALLBACK

    if text in _WINDOWS_RESERVED:
        text = f"{text}-file"

    if len(text) > max_len:
        keep = max(1, max_len - hash_len - 2)  # room for "__" + hash
        truncated = text[:keep].strip("-_.") or _FALLBACK
        text = f"{truncated}__{_hash_suffix(text, hash_len)}"

    return text


def safe_filename(label: str, extension: str, *, max_len: int = DEFAULT_MAX_LEN, hash_len: int = DEFAULT_HASH_LEN) -> str:
    """Build ``<safe-label>.<ext>``. The extension is normalized and never
    counted against ``max_len`` (the label is bounded; the extension is added
    after)."""
    slug = safe_slug(label, max_len=max_len, hash_len=hash_len)
    ext = normalize_extension(extension)
    return f"{slug}{ext}" if ext else slug


def normalize_extension(extension: str | None) -> str:
    """Return a leading-dot, lowercase extension (``"CSV"`` -> ``".csv"``).

    Returns ``""`` for falsy/invalid extensions. Strips characters that are not
    alphanumeric so a bogus content-type fragment can't inject path separators.
    """
    if not extension:
        return ""
    ext = str(extension).strip().lower().lstrip(".")
    ext = re.sub(r"[^a-z0-9]+", "", ext)
    return f".{ext}" if ext else ""


_ZIP_JUNK = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}


def is_hidden_relpath(rel_posix: str) -> bool:
    """True for OS metadata/hidden files a user's file manager drops into
    folders (``.DS_Store``, AppleDouble ``._*``, ``Thumbs.db``, dot-prefixed
    parts). Used to keep them out of file listings and diffs."""
    for part in rel_posix.split("/"):
        if part.startswith(".") or part in _ZIP_JUNK:
            return True
    return False


def sanitize_zip_member(member_name: str) -> str | None:
    """Make an archive member path legal on every OS, or None to skip it.

    Zips fetched from the internet (or made on a Mac) contain member names
    that are junk (``__MACOSX/``, ``._file``) or illegal on Windows (``:``,
    trailing dots, reserved stems like ``CON``). Junk returns None; other
    names are minimally repaired per path segment -- readable content names
    are kept, not slugified.
    """
    parts = [p for p in member_name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    cleaned: list[str] = []
    for part in parts:
        if part in _ZIP_JUNK or part.startswith("._") or part == ".DS_Store":
            return None
        safe = _UNSAFE.sub("-", part).rstrip(" .")
        if not safe:
            return None
        stem = safe.split(".", 1)[0].lower()
        if stem in _WINDOWS_RESERVED:
            safe = f"{stem}-file{safe[len(stem):]}"
        cleaned.append(safe)
    return "/".join(cleaned)


def dedupe_name(name: str, taken: set[str]) -> str:
    """Return ``name`` if unused, else ``stem__2.ext`` / ``stem__3.ext`` ...

    ``taken`` is consulted case-insensitively (Windows/macOS are case-insensitive
    filesystems) and updated in place with the chosen name.
    """
    lowered = {t.lower() for t in taken}
    if name.lower() not in lowered:
        taken.add(name)
        return name
    if "." in name:
        stem, dot, ext = name.partition(".")
        ext = f"{dot}{ext}"
    else:
        stem, ext = name, ""
    counter = 2
    while True:
        candidate = f"{stem}__{counter}{ext}"
        if candidate.lower() not in lowered:
            taken.add(candidate)
            return candidate
        counter += 1


__all__ = [
    "safe_slug",
    "safe_filename",
    "normalize_extension",
    "dedupe_name",
    "is_hidden_relpath",
    "sanitize_zip_member",
    "DEFAULT_MAX_LEN",
    "DEFAULT_HASH_LEN",
]
