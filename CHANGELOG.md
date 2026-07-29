# Changelog

All notable changes to Sancho Fetch are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

To update Sancho, ask your AI to run `sancho update check`, then
`sancho update preview` and `sancho update apply`. Updates back up your
managed files first and can be undone with `sancho update rollback`.

## [Unreleased]

## [0.2.0] - 2026-07-29

### Added

- MCP 2026-07-28 spec support (dual-era): `server/discover`, per-request
  `_meta` protocol versioning with `UnsupportedProtocolVersionError`,
  `resultType` on every result, and `ttlMs`/`cacheScope` freshness hints on
  `tools/list`. The legacy `initialize` handshake keeps working for current
  desktop clients.
- Tool metadata: every MCP tool now carries a `title` and honest
  `annotations` (`readOnlyHint`, `destructiveHint`, `openWorldHint`), and
  `tools/call` returns `structuredContent` alongside the text payload.
- Release gate: every shipped module `input_schema` is validated against the
  JSON Schema 2020-12 metaschema (strict clients reject loose schemas).

### Changed

- Proper JSON-RPC error codes: unknown methods return `-32601`, bad
  params/unknown tools `-32602`, routing-header mismatches `-32020` (was a
  blanket `-32000`).
- The VS Code config snippet now uses the `servers` + `type: "stdio"` shape
  VS Code actually reads, instead of the `mcpServers` shape.

### Removed

- The deprecated HTTP+SSE transport (`GET /sse`, `POST /messages`) and its
  session machinery; Streamable HTTP (`POST /mcp`) is the only HTTP
  transport. `chatgpt-web` snippets no longer advertise an `sse_url`.
- The empty `resources` capability (sancho exposes no resources).
- Legacy LSP-style `Content-Length` stdio framing (a compat shim for an
  early sancho bug; no released client ever needed it).

## [0.1.0] - 2026-07-28

First public release.

### Added

- `sancho` CLI: fetch data from 120+ curated public sources (World Bank, FRED,
  Census, OECD, Eurostat, USGS, FEMA, and more) driven from your AI's code mode.
- Source discovery ranks candidates by whole-word concept matches and reports
  each module's geographic `coverage` (us / global / eu), so agents can steer
  a Brazil query to a global source instead of a US-only one.
- One-command setup (`sancho setup`) that creates a workspace, registers it
  computer-wide, installs agent skills, and writes desktop MCP config snippets.
- MCP server (`sancho mcp serve`) for Claude Desktop, ChatGPT Desktop, Cursor,
  and VS Code.
- Custom modules: drop your own fetchers into `custom/**` and they take
  precedence over the built-in ones at runtime.
- Managed updates with backups: `sancho update check | preview | apply | rollback`.
- One-step uninstall (`installers/uninstall.sh` / `.bat`, plus double-clickable
  versions): removes the CLI, library pointer, AI skills, and the Claude
  Desktop MCP entry. Your `sancho-workspace/` data is kept unless you pass
  `--purge`.
- Every fetch writes a ready-to-open working file to `sancho-downloads/`
  alongside a faithful cached copy of the original response.
- `sancho run` and `sancho fetch run` print a compact summary by default
  (status, cache state, row count, and the primary working-file path); pass
  `--full-output` to print the entire fetched payload.

### Performance

- Trivial commands (`mode`, `paths`, `inventory`) start in ~0.2s: heavy
  dependencies load only for the commands that use them, module manifests are
  parsed with the fast C YAML loader, and the parsed template registry is
  cached per process.
- Re-running an identical request reuses the previously exported working file
  instead of regenerating an identical copy, so cache hits finish in well under
  a second and `sancho-downloads/` no longer accumulates duplicates.
- MCP fetch tools return a run summary with a capped preview (20 rows / 4 KB)
  instead of the full dataset -- the working file holds the data, so large
  fetches no longer flood the AI's context window.
- `sancho env recommend` embeds only the `.env.example` sections for keys that
  are actually missing, and `sancho log tail` omits per-event fields that
  repeat identically in every entry.
- Dataset discovery (`sancho module variables` without `--dataset`) filters
  the catalog by the module's own name tokens and sorts newest-first, so the
  relevant datasets surface instead of decades of unrelated ones.

### Security

- Sancho keeps exactly one env file, `sancho-workspace/.env`. API keys are never
  printed by any command, and no code path writes to `.env` except creating it
  when missing.

[Unreleased]: https://github.com/panth-net/sancho-fetch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/panth-net/sancho-fetch/releases/tag/v0.1.0
