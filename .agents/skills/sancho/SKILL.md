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
   payload contains `update_hint`, relay it to the user in one plain sentence
   before continuing. If the `sancho` command is missing, fails, or lacks
   current commands such as `setup`, `paths`, `ready`, or `mode`, and terminal
   access is available, do the setup work yourself: run
   `uv tool install sancho-fetch`, then
   `sancho setup --path <the folder the user is working in> --install-claude-desktop --json`.
   (Working from a source checkout instead? Run `installers\setup.bat` on
   Windows or `bash installers/setup.sh` on macOS/Linux from the repo root.)
   Then run `sancho ready --json`
   and retry `sancho paths --json`. If `workspace_source == "none"`, run setup
   or `sancho library register <path-to-workspace-folder>` yourself. Only ask
   the user for help when the OS blocks execution, permissions fail, or an
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
   variables, and request params before running anything. Don't fabricate
   variable/field/series codes from memory (e.g. Census `DP05_0047E`, BLS series
   IDs). Instead, retrieve the module's **codebook** and let YOUR judgment pick
   the codes: run
   `sancho module variables <id> [--dataset <ds>] --search "<concept>" --json`.
   It returns candidate code/label entries (fetching + caching a live dictionary
   for code-based providers, surfacing the bundled or documented codes otherwise).
   **`--search` is only a retrieval filter to get a manageable slice -- it is not
   the decision.** Read the returned `label`/`concept` of each candidate and
   choose the code(s) that actually match the user's intent; do not assume the
   first row is correct. Broaden or drop `--search` (or raise `--limit`) if the
   right code might not be in the slice. **Getting the data is the priority --
   never refuse or return nothing because a code is unresolved.** If you still
   can't pin an exact code, fetch the broadest safe slice instead of guessing:
   for a Census table, request the whole group with
   `variables: ["NAME", "group(DP05)"]` and label every returned column from the
   dictionary. Deliver the data, and note plainly any field you couldn't label.
7. Fetch with `sancho run <module-id> --workspace <ws> --input <input.json>`,
   building the request object from the module schema and catalog. Reuse is
   automatic: an identical request fetched within the last 24h is served from
   the local cache (no API call), so never pre-gate a run with
   `sancho cache status` -- just run. (`cache status` exists for inspecting
   the cache state of a large multi-unit plan, not as a required step.) When
   the user wants the newest data, add `"refresh": true` to the input (or
   `"cache": {"max_age_seconds": 0}`) to force a fresh fetch. The run JSON
   reports `cache_status` (`reused_cache` vs `fetched_api`) so you can tell
   the user what happened. You also do **not** need to `sancho add` first --
   `sancho run` auto-installs the module from the bundled templates on first
   use. Only run `sancho add` to pre-stage a pack.
8. Public working output is created automatically: every fetch writes the
   user's actual file under `sancho-downloads/` (Excel `.xlsx` when the data is a clean
   table, the natural/original format otherwise). For explicit control use
   `sancho export-to-project --cache-record <id> --project .`. The command JSON
   returns `primary_output_path` and `output_paths`.
9. Confirm completion from the run JSON itself: `status`, `cache_status`, and
   `row_count` are the evidence for a single run. Read
   `sancho log tail --json --limit 5 --module <id>` only for playbooks /
   multi-unit runs, or when a run failed or looks wrong. For failures, open
   `logs/errors/<run-id>_error.md`.
10. Summarize per unit: reused, fetched, skipped, and failed. Never claim all
    fetched without these counts.

## Reporting results

After a successful fetch, show the user the **primary path only**:

```
Done — fetched/reused <count> dataset(s).

Primary file:
<absolute path>
```

Use `Primary folder:` when the output is a folder (multiple datasets, or a
single dataset with companion files). Do **not** show the canonical cache path,
manifest, provenance, or run ID by default — only when the user asks, on error,
or in developer mode. If the run reports a large copied file, pass along the
size + space-reclaim notice. Sancho keeps a faithful canonical cache (original
files byte-for-byte; API responses as JSON) — the public file is the working
copy the user opens.

Use your discretion on pasting data into chat: a quick answer or a small
table (under ~100 rows) is fine to show inline unless instructed otherwise.
Do not dump large fetched datasets into chat — preview at most a few rows
if asked; otherwise report the path and counts.

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
