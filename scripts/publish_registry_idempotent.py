"""Publish Registry metadata, treating an already-identical version as success."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REGISTRY = "https://registry.modelcontextprotocol.io"


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _contains(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected)
        )
    return actual == expected


def _public_server(expected: dict[str, Any]) -> dict[str, Any] | None:
    name = urllib.parse.quote(str(expected["name"]), safe="")
    version = urllib.parse.quote(str(expected["version"]), safe="")
    url = f"{REGISTRY}/v0.1/servers/{name}/versions/{version}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Registry detail lookup failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Registry detail lookup failed") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Registry detail response is not an object")
    server = payload.get("server", payload)
    if not isinstance(server, dict):
        raise RuntimeError("Registry detail response has no server object")
    return server


def _expected_public_subset(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: manifest[key]
        for key in (
            "name",
            "title",
            "description",
            "websiteUrl",
            "repository",
            "version",
            "packages",
        )
        if key in manifest
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--publisher", type=Path, default=Path("./mcp-publisher"))
    args = parser.parse_args()
    expected = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(expected, dict):
        raise RuntimeError("Registry manifest must contain an object")
    subset = _expected_public_subset(expected)
    existing = _public_server(expected)
    if existing is not None:
        if not _contains(existing, subset):
            raise RuntimeError("Registry already has this version with different metadata")
        print("Identical Registry version is already public")
        return
    result = subprocess.run(
        [str(args.publisher.resolve()), "publish", str(args.manifest)], check=False
    )
    if result.returncode == 0:
        return
    # A retry can race a prior successful publish. Accept only an exact public
    # subset; otherwise preserve the publisher failure.
    existing = _public_server(expected)
    if existing is not None and _contains(existing, subset):
        print("Publisher reported failure, but the identical Registry version is public")
        return
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
