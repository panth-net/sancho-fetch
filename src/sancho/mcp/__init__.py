from typing import Any

from sancho.mcp.config import generate_client_config, write_client_config

__all__ = [
    "generate_client_config",
    "write_client_config",
    "serve_http",
    "serve_stdio",
]


# The server module is heavy and only needed by `sancho mcp serve`; resolve it
# lazily so every other command skips it.
def __getattr__(name: str) -> Any:
    if name in ("serve_http", "serve_stdio"):
        from sancho.mcp import server

        return getattr(server, name)
    raise AttributeError(f"module 'sancho.mcp' has no attribute '{name}'")
