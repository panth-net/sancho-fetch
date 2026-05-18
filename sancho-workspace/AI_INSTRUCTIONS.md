# AI Instructions

This workspace is for reusable local data work. Prefer durable files over
chat-only output.

## Communication Style

Run `sancho mode --json` before replying. It returns only
`{"developer_mode": false}` or `{"developer_mode": true}`.

- `false` or missing: use plain English. Do not paste commands, paths,
  env-var names, code, or diffs unless the user asks.
- `true`: technical detail is welcome.

Never open `.env` just to determine mode, and never print secret values from
`.env`. If a provider needs a key, explain what the key is for and use
`sancho env open` to let the user edit the file.

## What To Read First

1. `DATASET_CATALOG.md`
2. `modules.yaml`
3. `source/_runtime/ANALYSIS_GUIDE.md`
4. `source/_runtime/DASHBOARD_GUIDE.md`

## Working Rules

1. Run `sancho paths --json` first when workspace location is unclear.
2. Use `sancho find sources "<topic>" --json` or `sancho inventory --json`
   before choosing modules. Do not guess module IDs.
3. Keep user-owned logic in `custom/**` and repeatable flows in `playbooks/**`.
   Treat `source/**` as managed.
4. Do not edit `fetched-data/**`, `source/**`, `.env`, logs, or update backups
   directly.
5. After fetches, read `sancho log tail --json` before claiming success.

## Data Flow

`fetched-data/` -> `analysis-data/` -> `outputs/`

For dashboards:

`raw -> analysis -> dashboard-data -> dashboard`

Dashboards should read prepared outputs, not raw provider APIs.

## Done Means

1. Inputs and assumptions are documented.
2. Results are reproducible from local files or a playbook.
3. Outputs are clearly named and machine-readable.
4. Fetch results are summarized with reused, fetched, skipped, and failed counts.
