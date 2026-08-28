# MCP Setup for Sancho Fetch (Local Desktop First, Hosted Optional)

> **Status: AUTHORITATIVE** -- user-facing setup guide for MCP clients.

Last verified against this codebase and current client documentation: August 27, 2026

The server is dual-era per the MCP 2026-07-28 spec: handshake-era clients
(`initialize`, protocol versions 2024-10-07 through 2025-11-25) and modern
stateless clients (`server/discover`, per-request `_meta`) are both served.

This guide is for desktop AI clients that need MCP tools to reach the
user's local Sancho Fetch library. The normal individual-user path is:
install from PyPI (`uv tool install sancho-fetch`), run
`sancho setup`, and use the local
`sancho-workspace` on that computer.

The hosted HTTP MCP path is separate. Use it for workshops, seminars, or
temporary demos where you operate the hosted server yourself.

## Reality Check First

1. Local MCP servers are for desktop/local MCP clients.
2. ChatGPT custom MCP apps/connectors require remote servers, not a user's
   local `localhost`.
3. Claude.ai custom connectors are remote MCP URLs; Claude Desktop supports
   local MCP.
4. Claude Code and Codex can use the installed Sancho skills and the
   registered library pointer without a hosted MCP server.

If your goal is easiest setup, install from PyPI and run `sancho setup`
first. Setup writes desktop MCP config snippets into `sancho-workspace/mcp/`,
safely configures detected supported clients, verifies a direct stdio launch,
and installs Claude/Codex skills. Its ownership record preserves unowned or
edited same-name entries instead of overwriting them.

## Path A: Desktop/Local Library Access

### 1. Install Sancho Fetch

From PyPI (the normal path -- no checkout needed):

```bash
uv tool install sancho-fetch
sancho setup
sancho --help
```

From a source checkout (contributors):

```bash
uv tool install .
sancho setup
sancho --help
```

### 2. Start MCP Against The Local Library

```bash
sancho mcp serve --workspace . --transport stdio
```

This uses the `sancho-workspace` created by setup. If you run it from
another folder, Sancho falls back to the registered library pointer.

Optional quick mode for isolated demos:

```bash
sancho mcp serve --quick --profile broad --transport stdio
```

Quick mode auto-creates a data-bearing workspace under
`~/.sancho/mcp-quick/sancho-workspace` and installs missing profile targets.
Use it when you do not want to use the normal local library. It can contain
fetched data, logs, outputs, custom modules, and `.env`, so uninstall preserves
it by default.

### 3. Configure Desktop Clients

`sancho setup` writes snippets and configures each detected supported client
through the same ownership-aware launch model. You can regenerate snippets at
any time:

```bash
sancho mcp config --client claude-desktop --workspace .
sancho mcp config --client chatgpt-desktop --workspace .
sancho mcp config --client vscode --workspace .
sancho mcp config --client cursor --workspace .
```

For one-client troubleshooting, use its adapter explicitly:

```bash
sancho mcp config --client claude-desktop --workspace . --install
sancho mcp config --client codex --workspace . --install
sancho mcp config --client cursor --workspace . --install
sancho mcp config --client vscode --workspace . --install
```

**Claude Desktop managed-uv candidate:** the repo ships a locally validated MCP
Bundle at
`integrations/claude-desktop/sancho.mcpb`. Its v0.4 managed-uv runtime pins the
same Sancho version as the extension and creates a stable external workspace;
it never stores data inside the replaceable bundle. The first launch needs
network access while the host downloads the pinned package and dependencies.
Extension removal preserves that workspace. Rebuild and validate after source
changes with `python scripts/build_mcpb.py` and
`python scripts/validate_mcpb.py`. Do not describe it as a verified one-click
installer until the clean-host macOS and Windows checks in
`docs/release/MANUAL_VALIDATION.md` have been run on a current Claude Desktop.

**ChatGPT/Codex:** setup uses the supported `codex mcp get/add/remove` CLI and
never rewrites `~/.codex/config.toml` directly. Current local OpenAI surfaces
on the same Codex host share that MCP configuration. If the CLI is absent, the
generated ChatGPT desktop snippet contains the current Settings -> MCP servers
-> Add server STDIO instructions.

Restart the client after changing MCP config.

**VS Code profiles:** setup uses an ownership-aware merge of the selected
profile's `mcp.json`, not the add-only Code CLI. For a non-default profile run
`sancho setup --client vscode --vscode-profile-path <profile-folder>`. Setup
cannot observe Copilot sign-in, first-launch trust, remote-host state, or an
organization policy from the JSON file, so it reports those as client-side
checks instead of claiming a connection.

**Cursor:** the primary adapter atomically merges the owned `sancho` entry in
`~/.cursor/mcp.json`, including `type: "stdio"`, and preserves unrelated or
edited values. The generated snippet also contains a current Cursor install
deeplink as a fallback; opening it is only the start of a user-confirmed flow.

#### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "sancho": {
      "command": "C:\\Users\\you\\.local\\bin\\sancho.exe",
      "args": ["mcp", "serve", "--workspace", "C:\\Users\\you\\Documents\\sancho-fetch\\sancho-workspace", "--transport", "stdio"]
    }
  }
}
```

#### VS Code / Copilot (`.vscode/mcp.json`)

```json
{
  "servers": {
    "sancho": {
      "type": "stdio",
      "command": "sancho",
      "args": ["mcp", "serve", "--workspace", ".", "--transport", "stdio"]
    }
  }
}
```

Generated snippets use absolute `sancho` and workspace paths when Sancho can
find them. If you hand-write a config and `sancho` is not on PATH, copy the
absolute `command` value from any generated snippet in
`sancho-workspace/mcp/*.mcp.json` (or re-run the installer, which puts
`sancho` on PATH).

## Path B: Hosted Web Connector

Use this only when you are operating a remote connector for a workshop,
seminar, or temporary hosted demo.

### 1. Run Sancho Fetch MCP HTTP Server

```bash
sancho mcp serve --quick --profile broad --transport http --host 127.0.0.1 --port 8765
```

Endpoints:

- `http://127.0.0.1:8765/health`
- `http://127.0.0.1:8765/mcp`

### 2. Expose Via Public HTTPS URL

For example with ngrok:

```bash
ngrok http 8765
```

Then use public URLs such as:

- `https://your-subdomain.example/mcp`

### 3. Connect Web Clients

1. Claude.ai: add a remote connector with your HTTPS MCP URL.
2. ChatGPT web apps/connectors: create an app in developer mode and use
   the remote MCP URL.

## No API Key Needed

These providers work immediately with no `.env` configuration:

- World Bank
- Treasury Fiscal Data
- USAspending
- USGS Earthquakes
- FEMA OpenFEMA
- Federal Register
- CMS Data
- NHTSA Recalls

Many others also work without keys. Keyed providers need free credentials
in `sancho-workspace/.env`.

## Quick Prompts Once Connected

1. "List available Sancho Fetch tools and data modules."
2. "Show me top macro indicators using World Bank and FRED."
3. "Pull U.S. housing affordability context from HUD and ACS profile data."
