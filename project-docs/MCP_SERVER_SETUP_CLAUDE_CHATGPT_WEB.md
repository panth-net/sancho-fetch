# MCP Setup for Sancho Fetch (Local Desktop First, Hosted Optional)

> **Status: AUTHORITATIVE** -- user-facing setup guide for MCP clients.

Last verified against this codebase: May 18, 2026

This guide is for desktop AI clients that need MCP tools to reach the
user's local Sancho Fetch library. The normal individual-user path is:
download the GitHub folder, run the installer, and use the local
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

If your goal is easiest setup, use the GitHub installer first. It writes
desktop MCP config snippets into `sancho-workspace/mcp/`, installs Claude
Desktop config when supported, and installs the Claude/Codex skills for
slash-command style use.

## Path A: Desktop/Local Library Access

### 1. Install Sancho Fetch From This Repo

```bash
uv tool install .
sancho setup --install-claude-desktop
sancho --help
```

Optional npm launcher path:

```bash
npx --yes --package @sancho/cli sancho mcp serve --workspace . --transport stdio
```

### 2. Start MCP Against The Local Library

```bash
sancho mcp serve --workspace . --transport stdio
```

This uses the `sancho-workspace` created by setup. If you run it from
another folder, Sancho falls back to the registered library pointer.

Optional quick mode for throwaway demos:

```bash
sancho mcp serve --quick --profile broad --transport stdio
```

Quick mode auto-creates a managed workspace under
`~/.sancho/mcp-quick/sancho-workspace` and installs missing profile targets.
Use it when you do not want to use the user's normal local library.

### 3. Configure Desktop Clients

`sancho setup --install-claude-desktop` writes config snippets under
`sancho-workspace/mcp/` and tries to merge the Claude Desktop server entry
into the app config. You can regenerate snippets at any time:

```bash
sancho mcp config --client claude-desktop --workspace .
sancho mcp config --client vscode --workspace .
sancho mcp config --client cursor --workspace .
```

For Claude Desktop, Sancho can merge the server entry into the app config:

```bash
sancho mcp config --client claude-desktop --workspace . --install
```

Restart the client after changing MCP config.

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
      "command": "sancho",
      "args": ["mcp", "serve", "--workspace", ".", "--transport", "stdio"]
    }
  }
}
```

Generated snippets use absolute `sancho` and workspace paths when Sancho can
find them. If you hand-write a config and `sancho` is not on PATH, use
`uvx --from sancho-fetch sancho` as the command pattern.

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
- `http://127.0.0.1:8765/sse`

### 2. Expose Via Public HTTPS URL

For example with ngrok:

```bash
ngrok http 8765
```

Then use public URLs such as:

- `https://your-subdomain.example/mcp`
- `https://your-subdomain.example/sse`

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
