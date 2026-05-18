# @sancho/cli

Sancho Fetch is Python-native. This npm package is a convenience launcher for
people who prefer `npx` or work in JavaScript-heavy environments.

The launcher checks for `uvx`, then runs the Python CLI:

```bash
npx @sancho/cli inventory
npx @sancho/cli init --path . --yes
npx @sancho/cli fetch sample world_bank --workspace sancho-workspace
npx @sancho/cli mcp serve --workspace . --transport stdio
npx --package @sancho/cli sancho-mcp-quick --profile broad
```

For hosted/public MCP usage, use the hosted MCP URL instead of this local
launcher. The npm package is for local workspace workflows.
