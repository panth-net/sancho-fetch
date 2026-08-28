"""Bounded PyPI propagation check used by the resumable release workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--wheel-dir", type=Path)
    args = parser.parse_args()
    expected_wheel = None
    expected_digest = None
    if args.wheel_dir:
        wheels = sorted(args.wheel_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected exactly one local wheel under {args.wheel_dir}")
        expected_wheel = wheels[0]
        expected_digest = hashlib.sha256(expected_wheel.read_bytes()).hexdigest()
    url = f"https://pypi.org/pypi/sancho-fetch/{args.version}/json"
    for attempt in range(1, args.attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.load(response)
            files = payload.get("urls") or []
            wheels = [item for item in files if item.get("packagetype") == "bdist_wheel"]
            if expected_wheel is not None:
                matching = [item for item in wheels if item.get("filename") == expected_wheel.name]
                if matching and matching[0].get("digests", {}).get("sha256") != expected_digest:
                    raise SystemExit("PyPI wheel filename exists with a different SHA-256 digest")
                wheels = matching
            if wheels:
                print(f"PyPI sancho-fetch {args.version} is live with a wheel")
                return
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            pass
        if attempt < args.attempts:
            time.sleep(args.interval)
    raise SystemExit(f"PyPI version {args.version} did not propagate after {args.attempts} attempts")


if __name__ == "__main__":
    main()
