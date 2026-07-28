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
INSTRUCTIONS_TEXT = INSTRUCTIONS_PATH.read_text(encoding="utf-8-sig")
assert len(INSTRUCTIONS_TEXT) <= 4000, (
    f"hosting/instructions.txt is {len(INSTRUCTIONS_TEXT)} bytes; "
    "some MCP clients truncate the initialize.instructions field above ~4KB."
)

NUDGE_FOOTER = (
    "For unlimited access, install Sancho Fetch locally and point Claude Desktop or "
    "ChatGPT Desktop at the folder: https://github.com/panth-net/sancho-fetch#get-started-about-5-minutes"
)


def _openapi_spec(base_url: str) -> dict:
    """OpenAPI description of the plain-HTTP facade (GET /tools, POST /call).

    Exists so a ChatGPT GPT "Action" can use the hosted server: free ChatGPT
    accounts cannot add custom MCP connectors (developer mode is Plus+), but
    they CAN use a shared GPT, and GPT Actions speak OpenAPI/REST. The
    organizer imports this URL in the GPT builder; the server fills in its
    own public URL from the request headers.
    """
    from sancho import __version__

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Sancho Fetch Hosted",
            "version": __version__,
            "description": (
                "Fetch-only public-data API (census, health, economic, civic). "
                "Call listTools once to see available tools and their input "
                "schemas, then callTool to fetch data. Read-only; rate-limited."
            ),
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/tools": {
                "get": {
                    "operationId": "listTools",
                    "summary": "List available data-fetch tools and their input schemas",
                    "x-openai-isConsequential": False,
                    "responses": {"200": {"description": "Tool list", "content": {"application/json": {"schema": {"type": "object"}}}}},
                }
            },
            "/call": {
                "post": {
                    "operationId": "callTool",
                    "summary": "Run one data-fetch tool and return the data",
                    "x-openai-isConsequential": False,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string", "description": "Tool name from listTools"},
                                        "arguments": {"type": "object", "description": "Arguments matching the tool's inputSchema"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Tool result", "content": {"application/json": {"schema": {"type": "object"}}}}},
                }
            },
        },
    }


class HostedHandler(_HttpHandler):
    """Subclass of the core handler that adds rate limiting, the OpenAPI
    facade description, and kills all default access logging."""

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

    def _public_base_url(self) -> str:
        host = self.headers.get("x-forwarded-host") or self.headers.get("host") or "localhost"
        default_proto = "http" if host.split(":")[0] in ("localhost", "127.0.0.1") else "https"
        proto = self.headers.get("x-forwarded-proto") or default_proto
        return f"{proto}://{host}"

    def do_POST(self) -> None:  # noqa: N802
        if not check_ip(self._client_ip()):
            try:
                self.send_error(429, NUDGE)
            except Exception:
                pass
            return
        super().do_POST()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/openapi.json":
            self._write_json(200, _openapi_spec(self._public_base_url()))
            return
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

        # Bootstrap an isolated workspace with exactly the allowlisted
        # modules, so HOSTED_PROVIDERS and the installed set can never drift
        # (a named profile once left allowlisted modules uninstalled, which
        # failed the boot check below).
        quick_state = ensure_quick_workspace(
            profile="broad",
            modules_csv=",".join(sorted(HOSTED_PROVIDERS)),
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

