# AGENTS.md -- Sancho Fetch agent guidance

This root guide is intentionally shared by Claude, Codex, and other agents.
Keep `CLAUDE.md`, `AGENTS.md`, `README_ALL_INSTRUCTIONS.md`, and
`src/sancho/templates/agent_skills/**` aligned when changing operator rules.

Read this before doing anything in this repo. The user is often not a coder.
Default to plain English unless `sancho mode --json` reports
`{"developer_mode": true}` or the user asks for technical detail.

## What Sancho Is

Sancho Fetch is a local-first data library. After setup, the visible
`sancho-fetch/` folder contains `sancho-workspace/` with managed modules in
`source/**`, personal work in `custom/**` and `playbooks/**`, fetched records in
`fetched-data/**`, derived work in `analysis-data/**`, exports in `outputs/**`,
logs in `logs/**`, and update backups in `update-backups/**`. The CLI is
`sancho`.

Sancho produces inspectable facts: paths, manifests, cache status, logs, repair
packets, update previews, and exports. The agent reasons about plans, explains
changes, chooses bounded fetch units, and migrates user edits when needed.
Sancho is not the planner.

## First Steps

1. Check mode before replying with `sancho mode --json`. If the command is
   missing or fails during first setup, default to developer mode off and use
   plain English. Do not open or read `.env` just to determine mode.
2. Run `sancho paths --json` to find the active workspace. If the `sancho`
   command is missing or setup is incomplete and terminal access is available,
   do the setup work yourself from the repo root: run `installers\setup.bat` on Windows, run
   `bash installers/setup.sh` on macOS/Linux, or use
   `uv run sancho setup --path . --install-claude-desktop --json` from this
   checkout if the installed CLI is unavailable. Then run `sancho ready --json`
   and retry `sancho paths --json`. If `workspace_source == "none"`, run
   setup or `sancho library register <path-to-sancho-fetch>` yourself. Only ask
   the user for help when the OS blocks execution, permissions fail, or an
   installer window requires human approval.
3. Use `sancho inventory --json` or `sancho find sources "<text>" --json` to
   pick modules. Never guess module IDs, request keys, or paths.
4. For fetches, follow the installed Sancho skill. Source copies live in
   `src/sancho/templates/agent_skills/`. Always read `sancho log tail --json`
   before claiming success.
5. For updates, follow the installed Sancho update skill. Never update managed
   modules through raw Git.

## Hard Rules

- Do not edit `fetched-data/**`. It is the canonical record store.
- Do not open, read, or edit `.env` directly unless helping the user edit keys
  with `sancho env open`. Use `sancho mode --json`, `sancho env check`, and
  `sancho env recommend` for safe structured status. Never print values.
- Do not edit `source/**` directly. Use `custom/<type>/<module>/` overrides;
  `custom/**` wins at runtime.
- Do not auto-rewrite personal paths: `custom/**`, `playbooks/**`,
  `fetched-data/**`, `analysis-data/**`, `outputs/**`, `logs/**`,
  `update-backups/**`, `.env`, `AI_INSTRUCTIONS.md`, or `DATASET_CATALOG.md`.
- Do not run destructive Git commands such as `git pull`, `git reset --hard`,
  `git clean -fd`, force-push, or `git checkout --` to update Sancho-managed
  content. Use `sancho update check / preview / apply / rollback`.
- Do not claim completion without per-unit counts. Read `logs/runs.jsonl` or
  `sancho log tail --json` and report reused, fetched, skipped, and failed.
- Do not invent module IDs, request keys, provider names, or filesystem paths.
  Derive them from Sancho output.

## Standard Reach-For Commands

| Command | Purpose |
|---|---|
| `sancho setup --install-claude-desktop` | One-shot workspace, library pointer, skills, MCP snippets, and sample module setup. |
| `sancho ready --json` | One-command readiness check: CLI, workspace, library pointer, skills, MCP snippets, and sample module. |
| `sancho doctor --fix --json` | Structured AI repair status and safe retry data. |
| `sancho mode --json` | Safe developer-mode flag only: `{"developer_mode": false}`. |
| `sancho paths --json` | Every relevant path and the active workspace source. |
| `sancho inventory --json` | All built-in providers and packs. |
| `sancho find sources "<text>" --json` | Ranked candidates for a natural-language query. |
| `sancho env recommend "<text>" --json` | Provider/key readiness for a request without reading key values. |
| `sancho env open` | Open the right `.env` without printing values. |
| `sancho module show <id> --json` | Manifest, schema, override status, and last run. |
| `sancho cache status --module <id> --request-json '<json>' --json` | Per-unit cache status for an inline concrete request. |
| `sancho fetch sample world_bank --json` | Parseable zero-key onboarding fetch with run ID, written files, and counts. |
| `sancho run <id> --workspace <ws> --input <input.json>` | Execute one module. |
| `sancho log tail --json` | Recent run events and statuses. |
| `sancho log show <run-id>` | Every event and repair packet pointer for one run. |
| `sancho export-to-project --cache-record <id> --project .` | Bundle a cache record into the current project. |
| `sancho repair note --run-id <id> --module <id> --summary "..."` | Record durable repair history. |
| `sancho update check / preview / apply / rollback` | Safe managed updates with backups. |
| `sancho custom status --json` | Inspect active custom overrides. |
| `sancho fetched-data audit --old-modules --json` | Audit canonical fetched-data records produced by older module versions. |

## Fetch Failure Handling

Every failed run writes `sancho-workspace/logs/errors/<run-id>_error.md`. Read
that repair packet before guessing. It includes status, response excerpt,
traceback, files written before failure, last successful run, docs links,
suggested override path, and a safe retry command.

- Missing API key (`status: skipped_needs_key`): name the env var and tell the
  user to add it through `sancho env open`. Do not ask for or accept the value.
- Upstream API drift: propose a `custom/<type>/<module>/` override. Do not edit
  `source/**`.
- After any fix: record it with `sancho repair note ...` so future updates have
  history.

## Setup Expectations

Only surface these when `sancho mode --json` reports developer mode on, setup
breaks, or the user asks for technical detail:

- Python 3.11+
- `uv`
- Optional Node 18+ for the npm wrapper at `npm-cli/`

The detailed operator reference is `README_ALL_INSTRUCTIONS.md`.
