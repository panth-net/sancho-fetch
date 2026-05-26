---
name: sancho
description: Sancho Fetch -- answer natural-language data requests by running Sancho CLI commands. Use when the user says "/sancho ..." or asks the agent to pull data through Sancho.
---

# Sancho Fetch -- data fetch skill

You are operating Sancho Fetch, a local-first data library. Sancho is the tool
that fetches and records inspectable facts. The agent is the reasoning operator:
pick modules, decide concrete fetch units, inspect cache, run fetches, read
logs, and summarize results in plain English.

Read `CLAUDE.md` or `AGENTS.md` before doing anything. The root guide is the
shared contract; `README_ALL_INSTRUCTIONS.md` is the full reference.

## Required Flow

1. Check mode before replying with `sancho mode --json`. If the command is
   missing or fails during first setup, default to developer mode off and use
   plain English. Do not open or read `.env` just to determine mode.
2. Run `sancho paths --json` to learn where the workspace lives. If the
   `sancho` command is missing or setup is incomplete and terminal access is
   available, do the setup work yourself from the repo root: run
   `installers\setup.bat` on Windows, run
   `bash installers/setup.sh` on macOS/Linux, or use
   `uv run sancho setup --path . --install-claude-desktop --json` from this
   checkout if the installed CLI is unavailable. Then run `sancho ready --json`
   and retry `sancho paths --json`. If `workspace_source == "none"`, run setup
   or `sancho library register <path-to-sancho-fetch>` yourself. Only ask the
   user for help when the OS blocks execution, permissions fail, or an
   installer window requires human approval.
3. Run `sancho env recommend "<user request>" --json` before fetching. If
   required keys are missing, explain which providers need which env-var names,
   summarize the sign-up hints from `.env.example`, run `sancho env open`, and
   tell the user not to share key values with the agent.
4. Run `sancho find sources "<key terms from $ARGUMENTS>" --json` to get ranked
   module candidates. Treat results as candidates, not as a plan. For broad
   requests, pick a bounded starter set of 5-10 modules.
5. Run `sancho module show <candidate-id> --json` for each promising candidate.
   Inspect manifest, schema, override status, and last-run status. Skip modules
   where `custom_override_active` is true unless the user asked to refresh the
   official source.
6. Decide concrete fetch units. Resolve provider, endpoint, year, geography,
   variables, and request params before running anything.
7. For each concrete unit, build the request object from the module schema and
   catalog. Prefer inline JSON:
   `sancho cache status --module <id> --request-json '<json>' --json`. Use a
   request file only when you need to reuse or inspect the request. Inspect
   `cached`, `missing`, `stale`, `corrupt`, and `empty_result` distinctly.
8. Fetch only missing or stale units with `sancho run <module-id> --workspace
   <ws> --input <input.json>`. If the user asked to refresh, rerun even when
   cached.
9. Export a project bundle when running outside the Sancho Fetch repo. The CLI
   usually does this automatically; for explicit control use
   `sancho export-to-project --cache-record <id> --project .`.
10. Read `sancho log tail --json` before claiming completion. Confirm status
    and row counts. For failures, open `logs/errors/<run-id>_error.md`.
11. Summarize per unit: reused, fetched, skipped, and failed. Never claim all
    fetched without these counts.

## Hard Rules

- Never write to `fetched-data/**`.
- Never open, read, or edit `.env` directly unless helping the user edit keys
  with `sancho env open`. Use `sancho mode --json`, `sancho env check`, and
  `sancho env recommend` for safe structured status. Never print values.
- Never edit `source/**` directly. Repairs go in `custom/<type>/<module>/`.
- Never invent module IDs, request keys, provider names, or paths.
- Never run destructive Git commands. Managed updates use
  `sancho update check / preview / apply / rollback`.
- After any repair, record it with
  `sancho repair note --run-id <id> --module <id> --summary "..."`.

## Broad Requests

For "everything about X", start with 5-10 relevant modules, fetch one
representative request per module, explain the assumptions, and ask before
expanding.

## Failure Handling

Read `logs/errors/<run-id>_error.md` before guessing. For
`status: skipped_needs_key`, name the missing env var and point the user to the
file opened by `sancho env open`; do not ask for the value. For upstream API drift, propose a
`custom/<type>/<id>/` override and record the repair afterward.

The user's natural-language request comes from `/sancho ...`, the prompt, or
`$ARGUMENTS`. Use it to drive `sancho find sources` and the final summary.
