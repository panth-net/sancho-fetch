"""Create final Registry metadata only after the public MCPB asset exists."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-url", required=True)
    parser.add_argument("--local-mcpb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    local_digest = hashlib.sha256(args.local_mcpb.read_bytes()).hexdigest()
    base_payload = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = str(base_payload.get("version") or "")
    parsed_asset = urlparse(args.asset_url)
    expected_path = f"/panth-net/sancho-fetch/releases/download/v{version}/sancho.mcpb"
    if (
        parsed_asset.scheme != "https"
        or parsed_asset.netloc != "github.com"
        or parsed_asset.path != expected_path
        or parsed_asset.query
        or parsed_asset.fragment
    ):
        raise RuntimeError(f"MCPB asset URL must be the immutable v{version} GitHub release path")
    with urllib.request.urlopen(args.asset_url, timeout=30) as response:
        public_bytes = response.read()
    public_digest = hashlib.sha256(public_bytes).hexdigest()
    if public_digest != local_digest:
        raise RuntimeError(
            f"public MCPB digest {public_digest} differs from built artifact {local_digest}"
        )

    payload = base_payload
    payload["packages"].append(
        {
            "registryType": "mcpb",
            "identifier": args.asset_url,
            "fileSha256": public_digest,
            "transport": {"type": "stdio"},
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{args.output.name}.", dir=args.output.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, args.output)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    print(json.dumps({"output": str(args.output), "mcpb_sha256": public_digest}, indent=2))


if __name__ == "__main__":
    main()
