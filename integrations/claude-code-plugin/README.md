# Sancho Fetch Claude Code plugin

This plugin provides the namespaced `/sancho-fetch:sancho` and
`/sancho-fetch:sancho-update` skills and registers the local Sancho MCP server.
It deliberately connects to an existing Sancho Fetch 0.3.0 CLI; it does not
pretend that plugin metadata installs the Python package.

Install the runtime first:

```bash
uv tool install sancho-fetch==0.3.0
sancho setup
```

For local plugin development and validation:

```bash
claude plugin validate --strict integrations/claude-code-plugin
claude --plugin-dir integrations/claude-code-plugin
```

If the CLI is missing or the version is incompatible, the plugin MCP entry
shows an executable-not-found/startup error. Run the two runtime commands above
and then `/reload-plugins`. Removing or disabling this plugin does not remove
the CLI, workspace, fetched data, `.env`, or downloads.
