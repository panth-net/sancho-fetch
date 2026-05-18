"""Shared download and JSON-fetch helpers with retry, content sniffing, and atomic writes.

Used by fetch modules that download files (XLSX, CSV, PDF, ZIP) or call JSON
APIs that intermittently return HTML error pages or empty bodies.

Complements ``HttpClient`` in ``http.py`` which handles cached, rate-limited
JSON API calls. ``net.py`` handles the messier cases: file downloads where
the response may be HTML instead of the expected binary, and JSON endpoints
that flake under load.
"""

from __future__ import annotations

import os
import random
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_SANCHO_UA = "SanchoFetch/1.0 (sancho)"


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    content_type: str
    size_bytes: int
    detected_format: str


def _detect_format(first_bytes: bytes) -> str:
    if first_bytes[:4] == b"%PDF":
        return "pdf"
    if first_bytes[:2] == b"PK":
        return "xlsx"
    if first_bytes[:1] == b"<":
        return "html"
    if first_bytes[:1] == b"{" or first_bytes[:1] == b"[":
        return "json"
    try:
        text = first_bytes[:512].decode("utf-8", errors="strict")
        if "," in text and "\n" in text:
            return "csv"
    except UnicodeDecodeError:
        pass
    return "unknown"


def _backoff_with_jitter(attempt: int, base: float) -> float:
    return base * (2 ** attempt) + random.uniform(0, base)


def _is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


def download_file(
    url: str,
    *,
    dest_dir: Path | str,
    filename: str | None = None,
    expected_magic: bytes | None = None,
    ua: str | None = None,
    timeout: float = 60,
    max_retries: int = 3,
    backoff: float = 1.0,
) -> DownloadResult:
    """Download a URL to disk with retries, content sniffing, and atomic writes."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": ua or _BROWSER_UA}

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(
                url, headers=headers, timeout=timeout,
                allow_redirects=True, stream=True,
            )
            if _is_retryable_status(resp.status_code):
                raise requests.HTTPError(
                    f"HTTP {resp.status_code}", response=resp,
                )
            resp.raise_for_status()

            # Read first chunk for magic-byte check
            first_chunk = next(resp.iter_content(chunk_size=8192), b"")
            if not first_chunk:
                raise ValueError("Empty response body")

            detected = _detect_format(first_chunk)

            if expected_magic and not first_chunk.startswith(expected_magic):
                if detected == "html":
                    raise ValueError(
                        f"Expected {expected_magic!r} but got HTML response "
                        f"(first bytes: {first_chunk[:60]!r})"
                    )
                raise ValueError(
                    f"Expected {expected_magic!r} but got {detected} "
                    f"(first bytes: {first_chunk[:20]!r})"
                )

            # Atomic write: temp file then rename
            final_name = filename or url.rsplit("/", 1)[-1].split("?")[0] or "download"
            final_path = dest_dir / final_name

            fd, tmp_path = tempfile.mkstemp(dir=str(dest_dir))
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(first_chunk)
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
                os.replace(tmp_path, str(final_path))
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            ct = resp.headers.get("content-type", "")
            size = final_path.stat().st_size
            return DownloadResult(
                path=final_path, content_type=ct,
                size_bytes=size, detected_format=detected,
            )

        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(_backoff_with_jitter(attempt, backoff))

    assert last_error is not None
    raise last_error


def _classify_unexpected_body(body: str, content_type: str, status: int) -> str:
    """Build a specific, actionable error message for non-JSON responses."""
    head = body[:160]
    # Census API specifically returns an HTML page titled "Invalid Key"
    if "Invalid Key" in body[:500]:
        return (
            "Census API rejected the key (response: 'Invalid Key'). "
            "Verify CENSUS_API_KEY in .env, or re-issue at "
            "https://api.census.gov/data/key_signup.html."
        )
    stripped = body.lstrip()
    if stripped.startswith("<?xml"):
        return (
            f"Got XML instead of JSON (Content-Type: {content_type!r}, HTTP {status}). "
            f"API likely ignored Accept header / format param. "
            f"First 160 chars: {head!r}"
        )
    if stripped.startswith("<"):
        return (
            f"Got HTML instead of JSON (Content-Type: {content_type!r}, HTTP {status}). "
            f"Likely an error page, redirect, or rate-limit block. "
            f"First 160 chars: {head!r}"
        )
    return (
        f"Unexpected non-JSON response (Content-Type: {content_type!r}, HTTP {status}). "
        f"First 160 chars: {head!r}"
    )


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    ua: str | None = None,
    timeout: float = 30,
    max_retries: int = 3,
    backoff: float = 0.5,
) -> Any:
    """Fetch JSON with retries on HTML/XML responses, empty bodies, and server errors.

    Raises ``ValueError`` with a specific, actionable message when the response
    isn't JSON (HTML error page, XML fallback, empty body, Census "Invalid Key"
    page, etc.).
    """
    req_headers = {"Accept": "application/json", "User-Agent": ua or _SANCHO_UA}
    if headers:
        req_headers.update(headers)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(
                url, params=params, headers=req_headers,
                timeout=timeout, allow_redirects=True,
            )
            if _is_retryable_status(resp.status_code):
                raise requests.HTTPError(
                    f"HTTP {resp.status_code}", response=resp,
                )
            resp.raise_for_status()

            body = resp.text.strip()
            content_type = resp.headers.get("Content-Type", "")
            if not body:
                raise ValueError(
                    f"Empty response body (Content-Type: {content_type!r}, "
                    f"HTTP {resp.status_code})"
                )
            if body.startswith("<"):
                raise ValueError(
                    _classify_unexpected_body(body, content_type, resp.status_code),
                )
            return resp.json()

        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(_backoff_with_jitter(attempt, backoff))

    assert last_error is not None
    raise last_error


__all__ = ["DownloadResult", "download_file", "get_json"]
