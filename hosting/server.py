"""Hosted MCP server entrypoint.

Thin wrapper around `sancho.mcp.server.serve_http` that:

1. Builds an `MCPPolicy` with the hosted allowlist, stateless mode, instructions
   text, size caps, and nudge footer.
2. Bootstraps a quick-mode workspace under `~/.sancho/mcp-hosted` so the fetch
   modules it needs are actually installed before requests arrive.
3. Installs a subclass of the core HTTP handler that enforces per-IP rate
   limiting and silences request logging.

Run as: ``python hosting/server.py`` (Render invokes this via the Dockerfile).

Local / stdio / non-hosted Sancho Fetch users never import this module.
"""

from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

# Make both `sancho.*` and sibling `limits.py` importable when run directly.
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

from sancho.mcp.hosted_allowlist import HOSTED_PROVIDERS  # noqa: E402
from sancho.mcp.models import MCPPolicy  # noqa: E402
from sancho.mcp.quick import ensure_quick_workspace  # noqa: E402
from sancho.mcp.server import _HttpHandler  # noqa: E402
from sancho.mcp.tooling import _build_context  # noqa: E402

from limits import NUDGE, check_ip  # noqa: E402


INSTRUCTIONS_PATH = _HERE / "instructions.txt"
INSTRUCTIONS_TEXT = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
assert len(INSTRUCTIONS_TEXT) <= 4000, (
    f"hosting/instructions.txt is {len(INSTRUCTIONS_TEXT)} bytes; "
    "some MCP clients truncate the initialize.instructions field above ~4KB."
)

NUDGE_FOOTER = (
    "For unlimited access, install Sancho Fetch locally and point Claude Desktop or "
    "ChatGPT Desktop at the folder: https://github.com/panth-net/sancho-fetch#install-in-one-step"
)


class HostedHandler(_HttpHandler):
    """Subclass of the core handler that adds rate limiting and kills all default access logging."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002, N802
        # Silence default BaseHTTPRequestHandler request-line logging.
        return

    def _client_ip(self) -> str:
        # Render puts the real client IP in X-Forwarded-For; without this we'd
        # rate-limit the Render edge instead of the user.
        xff = self.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0]

    def do_POST(self) -> None:  # noqa: N802
        if not check_ip(self._client_ip()):
            try:
                self.send_error(429, NUDGE)
            except Exception:
                pass
            return
        super().do_POST()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/mcp") or self.path == "/sse":
            if not check_ip(self._client_ip()):
                try:
                    self.send_error(429, NUDGE)
                except Exception:
                    pass
                return
        super().do_GET()


def _verify_allowlist(workspace_root: Path) -> None:
    """Fail loud at boot if any HOSTED_PROVIDERS id doesn't resolve to a real
    installed module. Prevents silent empty catalogs after a refactor."""
    from sancho.modules import discover_modules

    installed = {m.id for m in discover_modules(workspace_root)}
    missing = sorted(HOSTED_PROVIDERS - installed)
    if missing:
        raise RuntimeError(
            f"HOSTED_PROVIDERS contains module ids that are not installed "
            f"in the hosted workspace: {missing}. Update the allowlist or "
            f"add these modules to the quick profile."
        )


def main() -> None:
    try:
        port = int(os.getenv("PORT", "10000"))
        host = os.getenv("HOST", "0.0.0.0")

        # Bootstrap an isolated workspace with the broad profile so all
        # allowlisted fetch modules are installed. Reuses the same helper
        # Claude Desktop quick mode uses.
        quick_state = ensure_quick_workspace(
            profile="broad",
            modules_csv=None,
            quick_home=os.getenv("SANCHO_HOSTED_HOME"),
            sync=False,
            install_targets=True,
        )
        workspace_root = quick_state.workspace_root
        _verify_allowlist(workspace_root)

        policy = MCPPolicy(
            fetch_only=True,
            allowlisted_module_ids=set(HOSTED_PROVIDERS),
            stateless=True,
            max_response_bytes=int(os.getenv("SANCHO_MAX_RESPONSE_BYTES", "2000000")),
            max_request_bytes=int(os.getenv("SANCHO_MAX_REQUEST_BYTES", "100000")),
            instructions=INSTRUCTIONS_TEXT,
            nudge_footer=NUDGE_FOOTER,
        )

        ctx = _build_context(
            workspace_root=workspace_root,
            policy=policy,
            quick_mode=True,
            quick_profile="broad",
            quick_targets=None,
            quick_modules=None,
        )
        HostedHandler.ctx = ctx
        server = ThreadingHTTPServer((host, port), HostedHandler)
        print(f"[hosted] listening on {host}:{port}", file=sys.stderr, flush=True)
        server.serve_forever()
    except Exception as exc:  # fail loud, don't loop-restart silently
        print(
            f"[hosted] FATAL startup: {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

