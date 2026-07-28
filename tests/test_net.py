"""Unit tests for the shared download/JSON helper in sancho.runtime.net."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from sancho.runtime.net import (
    DownloadResult,
    _backoff_with_jitter,
    _detect_format,
    download_file,
    get_json,
)

pytestmark = pytest.mark.runtime


# ── _detect_format ───────────────────────────────────────────────────────


def test_detect_pdf():
    assert _detect_format(b"%PDF-1.7 rest of file") == "pdf"


def test_detect_xlsx():
    assert _detect_format(b"PK\x03\x04 rest of file") == "xlsx"


def test_detect_html():
    assert _detect_format(b"<html><body>Error</body></html>") == "html"
    assert _detect_format(b"<!DOCTYPE html>") == "html"


def test_detect_json():
    assert _detect_format(b'{"key": "value"}') == "json"
    assert _detect_format(b'[1, 2, 3]') == "json"


def test_detect_csv():
    assert _detect_format(b"name,age,city\nAlice,30,NYC\n") == "csv"


def test_detect_unknown_binary():
    assert _detect_format(b"\x89PNG\r\n\x1a\n") == "unknown"


# ── _backoff_with_jitter ─────────────────────────────────────────────────


def test_backoff_values_increase():
    v0 = _backoff_with_jitter(0, 1.0)
    v2 = _backoff_with_jitter(2, 1.0)
    # attempt 2 should be ~4x base, attempt 0 should be ~1x base (plus jitter)
    assert v0 < 3.0  # 1 * 2^0 + jitter(0,1) = 1..2
    assert v2 > 2.0  # 1 * 2^2 + jitter(0,1) = 4..5


def test_backoff_never_negative():
    for attempt in range(10):
        assert _backoff_with_jitter(attempt, 0.5) >= 0


# ── get_json ─────────────────────────────────────────────────────────────


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_get_json_retries_on_html(mock_sleep: MagicMock, mock_get: MagicMock) -> None:
    html_resp = MagicMock(spec=requests.Response)
    html_resp.status_code = 200
    html_resp.ok = True
    html_resp.text = "<html><body>Error</body></html>"
    html_resp.headers = {"Content-Type": "text/html"}
    html_resp.raise_for_status.return_value = None

    json_resp = MagicMock(spec=requests.Response)
    json_resp.status_code = 200
    json_resp.ok = True
    json_resp.text = '{"data": 42}'
    json_resp.headers = {"Content-Type": "application/json"}
    json_resp.json.return_value = {"data": 42}
    json_resp.raise_for_status.return_value = None

    mock_get.side_effect = [html_resp, json_resp]
    result = get_json("https://example.com/api", max_retries=2)
    assert result == {"data": 42}
    assert mock_get.call_count == 2


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_get_json_retries_on_empty_body(mock_sleep: MagicMock, mock_get: MagicMock) -> None:
    empty_resp = MagicMock(spec=requests.Response)
    empty_resp.status_code = 200
    empty_resp.ok = True
    empty_resp.text = ""
    empty_resp.headers = {"Content-Type": ""}
    empty_resp.raise_for_status.return_value = None

    json_resp = MagicMock(spec=requests.Response)
    json_resp.status_code = 200
    json_resp.ok = True
    json_resp.text = '{"ok": true}'
    json_resp.headers = {"Content-Type": "application/json"}
    json_resp.json.return_value = {"ok": True}
    json_resp.raise_for_status.return_value = None

    mock_get.side_effect = [empty_resp, json_resp]
    result = get_json("https://example.com/api", max_retries=2)
    assert result == {"ok": True}


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_get_json_raises_after_max_retries(mock_sleep: MagicMock, mock_get: MagicMock) -> None:
    html_resp = MagicMock(spec=requests.Response)
    html_resp.status_code = 200
    html_resp.ok = True
    html_resp.text = "<html>Error</html>"
    html_resp.headers = {"Content-Type": "text/html"}
    html_resp.raise_for_status.return_value = None

    mock_get.return_value = html_resp
    with pytest.raises(ValueError, match="HTML instead of JSON"):
        get_json("https://example.com/api", max_retries=1)


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_get_json_detects_xml_specifically(mock_sleep: MagicMock, mock_get: MagicMock) -> None:
    """XML responses should be labeled as XML, not HTML."""
    xml_resp = MagicMock(spec=requests.Response)
    xml_resp.status_code = 200
    xml_resp.ok = True
    xml_resp.text = '<?xml version="1.0"?><root><item>1</item></root>'
    xml_resp.headers = {"Content-Type": "application/xml"}
    xml_resp.raise_for_status.return_value = None

    mock_get.return_value = xml_resp
    with pytest.raises(ValueError, match="XML instead of JSON"):
        get_json("https://example.com/api", max_retries=1)


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_get_json_detects_census_invalid_key(mock_sleep: MagicMock, mock_get: MagicMock) -> None:
    """Census 'Invalid Key' HTML page should surface a specific message."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.text = '<html><head><title>Invalid Key</title></head><body>bad key</body></html>'
    resp.headers = {"Content-Type": "text/html"}
    resp.raise_for_status.return_value = None

    mock_get.return_value = resp
    with pytest.raises(ValueError, match="Census API rejected the key"):
        get_json("https://api.census.gov/data/test", max_retries=1)


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_get_json_includes_status_and_content_type_in_errors(mock_sleep: MagicMock, mock_get: MagicMock) -> None:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.text = "<html>Error</html>"
    resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    resp.raise_for_status.return_value = None

    mock_get.return_value = resp
    with pytest.raises(ValueError, match="text/html") as exc_info:
        get_json("https://example.com/api", max_retries=1)
    assert "HTTP 200" in str(exc_info.value)


# ── download_file ────────────────────────────────────────────────────────


@patch("sancho.runtime.net.requests.get")
def test_download_file_writes_atomically(mock_get: MagicMock, tmp_path: Path) -> None:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.headers = {"content-type": "application/pdf"}
    resp.iter_content.return_value = iter([b"%PDF-1.7 fake pdf content"])
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    result = download_file(
        "https://example.com/report.pdf",
        dest_dir=tmp_path,
    )
    assert result.path.exists()
    assert result.detected_format == "pdf"
    assert result.size_bytes > 0
    assert result.path.read_bytes().startswith(b"%PDF")


@patch("sancho.runtime.net.requests.get")
@patch("time.sleep")
def test_download_file_retries_on_wrong_magic(mock_sleep: MagicMock, mock_get: MagicMock, tmp_path: Path) -> None:
    html_resp = MagicMock(spec=requests.Response)
    html_resp.status_code = 200
    html_resp.ok = True
    html_resp.headers = {"content-type": "text/html"}
    html_resp.iter_content.return_value = iter([b"<html>Not a PDF</html>"])
    html_resp.raise_for_status.return_value = None

    pdf_resp = MagicMock(spec=requests.Response)
    pdf_resp.status_code = 200
    pdf_resp.ok = True
    pdf_resp.headers = {"content-type": "application/pdf"}
    pdf_resp.iter_content.return_value = iter([b"%PDF-1.7 real content"])
    pdf_resp.raise_for_status.return_value = None

    mock_get.side_effect = [html_resp, pdf_resp]
    result = download_file(
        "https://example.com/report.pdf",
        dest_dir=tmp_path,
        expected_magic=b"%PDF",
        max_retries=2,
    )
    assert result.detected_format == "pdf"
    assert mock_get.call_count == 2
