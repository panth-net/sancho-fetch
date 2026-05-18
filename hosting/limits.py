"""Per-IP rate limiter for the hosted MCP server.

Thread-safe, evicting, monotonic-clock token bucket. In-memory only -- counters
reset on every process restart, which is acceptable for the free-tier Render
deploy and for the threat model (bounded abuse, not persistent attackers).

Used by `hosting/server.py`. Not imported by any code under `src/sancho/`.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

RPM: int = int(os.getenv("SANCHO_IP_RPM", "20"))
MAX_TRACKED_IPS: int = 10_000

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)

NUDGE: str = (
    "Hosted Sancho Fetch is fetch-only and rate-limited. For unlimited access, install "
    "Sancho Fetch locally and point Claude Desktop or ChatGPT Desktop at the folder: "
    "https://github.com/panth-net/sancho-fetch#install-in-one-step"
)


def _prune(dq: deque, now: float, window: float = 60.0) -> None:
    while dq and now - dq[0] > window:
        dq.popleft()


def check_ip(ip: str) -> bool:
    """Return True if the IP may proceed, False if rate-limited."""
    now = time.monotonic()
    with _lock:
        # Bound memory: if tracking more than MAX_TRACKED_IPS unique IPs,
        # drop the oldest half. Crude but O(n) infrequently.
        if len(_hits) > MAX_TRACKED_IPS:
            for key in list(_hits.keys())[: MAX_TRACKED_IPS // 2]:
                _hits.pop(key, None)
        dq = _hits[ip]
        _prune(dq, now)
        if len(dq) >= RPM:
            return False
        dq.append(now)
        return True


__all__ = ["check_ip", "NUDGE", "RPM"]

