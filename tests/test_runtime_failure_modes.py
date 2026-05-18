"""Runtime failure-mode tests for HttpClient.

Covers: retry exhaustion, invalid JSON responses, cache expiry boundaries,
rate limiting / throttling, and monotonic clock resilience.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from sancho.runtime.http import HttpClient

pytestmark = pytest.mark.runtime


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_ok_response(payload: Any) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _make_error_response(status: int = 500) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.ok = False
    resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return resp


def _make_non_json_response() -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.json.side_effect = ValueError("No JSON object could be decoded")
    resp.raise_for_status.return_value = None
    return resp


def _mock_session(side_effect: Any = None, return_value: Any = None) -> MagicMock:
    session = MagicMock(spec=requests.Session)
    if side_effect is not None:
        session.request.side_effect = side_effect
    elif return_value is not None:
        session.request.return_value = return_value
    return session


# ── Retry exhaustion ─────────────────────────────────────────────────────


@patch("time.sleep")
def test_retry_exhaustion_raises_after_max_retries(mock_sleep: MagicMock) -> None:
    client = HttpClient(max_retries=2, backoff_seconds=0.01, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_error_response(503))

    with pytest.raises(requests.HTTPError, match="503"):
        client.request_json("GET", "https://example.com/api")

    assert client._session.request.call_count == 3  # initial + 2 retries


@patch("time.sleep")
def test_retry_zero_means_single_attempt(mock_sleep: MagicMock) -> None:
    client = HttpClient(max_retries=0, backoff_seconds=0.01, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_error_response(500))

    with pytest.raises(requests.HTTPError):
        client.request_json("GET", "https://example.com/api")

    assert client._session.request.call_count == 1


@patch("time.sleep")
def test_retry_succeeds_on_later_attempt(mock_sleep: MagicMock) -> None:
    client = HttpClient(max_retries=3, backoff_seconds=0.01, rate_limit_per_second=0)
    client._session = _mock_session(
        side_effect=[
            _make_error_response(502),
            _make_error_response(502),
            _make_ok_response({"status": "ok"}),
        ]
    )

    result = client.request_json("GET", "https://example.com/api")
    assert result == {"status": "ok"}
    assert client._session.request.call_count == 3


# ── Invalid JSON ─────────────────────────────────────────────────────────


@patch("time.sleep")
def test_non_json_response_triggers_retry_and_raises(mock_sleep: MagicMock) -> None:
    client = HttpClient(max_retries=1, backoff_seconds=0.01, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_non_json_response())

    with pytest.raises(ValueError, match="No JSON"):
        client.request_json("GET", "https://example.com/api")


# ── Cache expiry boundaries ──────────────────────────────────────────────


def test_cache_returns_live_entry() -> None:
    client = HttpClient(cache_ttl_seconds=300, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_ok_response({"data": 42}))

    first = client.request_json("GET", "https://example.com/data")
    second = client.request_json("GET", "https://example.com/data")

    assert first == second == {"data": 42}
    assert client._session.request.call_count == 1


def test_cache_expires_after_ttl() -> None:
    client = HttpClient(cache_ttl_seconds=10, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_ok_response({"v": 1}))

    client.request_json("GET", "https://example.com/data")

    # Manually expire the cache entry
    for entry in client._cache.values():
        entry.expires_at = time.monotonic() - 1.0

    client._session = _mock_session(return_value=_make_ok_response({"v": 2}))
    result = client.request_json("GET", "https://example.com/data")

    assert result == {"v": 2}


def test_cache_ttl_zero_disables_caching() -> None:
    client = HttpClient(cache_ttl_seconds=0, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_ok_response({"data": 1}))

    client.request_json("GET", "https://example.com/data")
    client.request_json("GET", "https://example.com/data")

    assert client._session.request.call_count == 2
    assert len(client._cache) == 0


# ── Rate limiting / throttling ───────────────────────────────────────────


def test_rate_limiter_delays_rapid_requests() -> None:
    client = HttpClient(rate_limit_per_second=1000, cache_ttl_seconds=0)
    client._session = _mock_session(return_value=_make_ok_response({"ok": True}))

    with patch("time.sleep") as mock_sleep:
        client.request_json("GET", "https://example.com/a")
        client.request_json("GET", "https://example.com/b")

    assert mock_sleep.call_count >= 1


def test_rate_limiter_disabled_at_zero() -> None:
    client = HttpClient(rate_limit_per_second=0, cache_ttl_seconds=0)
    client._session = _mock_session(return_value=_make_ok_response({"ok": True}))

    with patch("time.sleep") as mock_sleep:
        client.request_json("GET", "https://example.com/a")
        client.request_json("GET", "https://example.com/b")

    mock_sleep.assert_not_called()


# ── Monotonic clock resilience ───────────────────────────────────────────


def test_cache_not_fooled_by_backward_clock_jump() -> None:
    """Cache should use monotonic time, so wall-clock jumps don't matter."""
    client = HttpClient(cache_ttl_seconds=300, rate_limit_per_second=0)
    client._session = _mock_session(return_value=_make_ok_response({"cached": True}))

    client.request_json("GET", "https://example.com/data")

    cached = client._cache_get("GET::https://example.com/data::{}::{}")
    assert cached == {"cached": True}


@patch("time.sleep")
def test_rate_limit_no_negative_sleep_after_clock_jump(mock_sleep: MagicMock) -> None:
    """Rate limiter should never pass negative values to time.sleep."""
    client = HttpClient(rate_limit_per_second=5, cache_ttl_seconds=0)
    client._session = _mock_session(return_value=_make_ok_response({"ok": True}))

    # Simulate a scenario where _last_request_ts is far in the future
    client._last_request_ts = time.monotonic() + 1000

    client.request_json("GET", "https://example.com/api")

    for call in mock_sleep.call_args_list:
        assert call[0][0] >= 0, f"Negative sleep detected: {call[0][0]}"


# ── Connection errors ────────────────────────────────────────────────────


@patch("time.sleep")
def test_connection_error_retries_and_raises(mock_sleep: MagicMock) -> None:
    client = HttpClient(max_retries=1, backoff_seconds=0.01, rate_limit_per_second=0)
    client._session = _mock_session(
        side_effect=requests.ConnectionError("Connection refused")
    )

    with pytest.raises(requests.ConnectionError):
        client.request_json("GET", "https://example.com/api")

    assert client._session.request.call_count == 2


@patch("time.sleep")
def test_timeout_error_retries_and_raises(mock_sleep: MagicMock) -> None:
    client = HttpClient(max_retries=1, backoff_seconds=0.01, rate_limit_per_second=0)
    client._session = _mock_session(
        side_effect=requests.Timeout("Request timed out")
    )

    with pytest.raises(requests.Timeout):
        client.request_json("GET", "https://example.com/api")

    assert client._session.request.call_count == 2
