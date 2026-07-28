# Sancho Fetch

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

A **local-first toolkit for fetching public data** from 120+ government,
international, and open data providers into one visible folder on your
computer. Driven by your local AI assistant (Claude Code, Codex, Cursor,
VS Code, or Claude Desktop) through plain-English requests. Built to stay inspectable --
every fetch lands as a real file with a manifest, a provenance record,
and an integrity hash.

## Before you begin

Sancho requires **Python 3.11 or newer** and an internet connection during
first-time setup. Install Python yourself first, or let the installer's `uv`
package manager download a compatible isolated Python for Sancho. It does not
replace the computer's system Python. **Node.js is optional** and only needed
for the optional npm wrapper. API keys are not required for installation or
the built-in World Bank setup check.

```text
sancho-fetch/
  installers/       double-click installers
  sancho-workspace/
    source/          managed modules
    custom/          your modules and overrides
    playbooks/       your repeatable workflows
    fetched-data/    canonical fetched source data
    analysis-data/   your derived work
    outputs/         reports, dashboards, exports
    logs/            what Sancho did, when, and why
    update-backups/  snapshots before every update
    .env             your API keys
```

## Quick start (non-coders)

The canonical human quick start lives in [`README.md`](README.md) -- open a
folder in your AI app's code mode and paste the one-line setup request; the
AI installs Sancho from PyPI (`uv tool install sancho-fetch`). No repo
download needed. Keep that the single source; don't duplicate the steps
here.

Details worth knowing beyond the README:

- Setup stores a user-level `sancho` command plus a pointer back to the
  visible folder you chose; it does not install a second hidden library at
  `C:\` or another root folder. If you move that folder later, re-run
  `sancho setup --path <new location> --install-claude-desktop` so
  Claude/Codex point at the new location.
- The installer (or agent-run `sancho setup`) checks/installs `uv`, lets `uv`
  choose or download a Python that satisfies Sancho's `>=3.11` requirement,
  installs Sancho, creates the workspace, registers this folder as your
  library, copies the Claude / Codex agent skills to your home folder, writes
  local desktop MCP config snippets (Claude Desktop, ChatGPT desktop, Cursor,
  VS Code), installs Claude Desktop config when supported, and installs a
  built-in sample module as a setup check. In Claude Code those skills are
  invokable as `/sancho <request>` and `/sancho-update`; in Codex they load as
  skills for matching natural-language requests.
- ChatGPT web needs the hosted/remote connector path, not a local folder.
- After setup, Sancho is installed computer-wide. Users no longer need to add
  the `sancho-fetch` folder to future sessions, but they must use a Code
  session: the **Code tab** in Claude Desktop or a **Code chat** in Codex.
  Regular chats cannot access the local Sancho installation.
- If the `sancho-fetch` folder lives in a cloud-synced location (iCloud
  "Desktop & Documents", OneDrive), syncing can slow fetches or evict files
  to the cloud. It works, but if fetches feel slow or files show cloud
  icons, move the folder somewhere purely local and re-run the installer.

## Quick start (developers)

End users install from PyPI (`uv tool install sancho-fetch`); a source
checkout is for contributing and module development.

```bash
# 1. uv (https://docs.astral.sh/uv/) handles Sancho's Python requirement
#    (from a source checkout; end users: uv tool install sancho-fetch)
uv tool install .

# 2. One-shot setup: workspace + library pointer + skills + sample-module check
sancho setup --install-claude-desktop

# 3. Pull your first dataset (no API key needed)
sancho fetch sample world_bank
```

Data lands under `sancho-workspace/fetched-data/fetch.world_bank/...`. To
pre-stage a themed bundle of modules, add a starter pack:

```bash
sancho add pack.global_economic
sancho doctor --fix --json
```

Add API keys when you're ready (zero-key for World Bank, USGS, openFDA, etc.):

```bash
sancho env open census   # opens .env, prints which env vars Census needs
sancho env check         # reports which providers are ready (names only, never values)
```

**Windows note:** PowerShell handles path arguments better than Git Bash
when paths start with `/`.

## What it does

- **Find sources** -- `sancho find sources "black population census state ACS"` returns ranked module candidates for a natural-language query, including any custom modules in your workspace. Your AI picks the plan.
- **Fetch with provenance** -- every fetch writes `data.json` + `request.yml` + `provenance.yml` + `content.sha256` + `README.md` to a canonical `fetched-data/<module>/<family>/<request_key>/<timestamp>/` folder. Cache hits are deterministic; re-fetches are append-only.
- **Public working output** -- every fetch writes a ready-to-open file into your project's `sancho-downloads/` folder: a clean table becomes an Excel `.xlsx` (string codes like FIPS "01003" stay text; >200k rows falls back to complete CSV; `exports.tabular_format: csv` opts into raw UTF-8-SIG CSV), and KML/GeoJSON/original sources keep their natural format (never force-converted at the cost of information). The canonical cache also keeps the original downloaded file byte-for-byte. The command JSON returns `primary_output_path` + `output_paths`; assistants report the primary path only.
- **Repair packets** -- every failure writes a `logs/errors/<run-id>_error.md` with HTTP status, response excerpt, traceback, files written, last successful run, docs links, suggested override path, and a safe-retry command.
- **Safe updates** -- `sancho update check / preview / apply / rollback`. Never runs `git pull`. Never touches `custom/`, `playbooks/`, `fetched-data/`, `analysis-data/`, `outputs/`, `logs/`, `update-backups/`, `.env`, `AI_INSTRUCTIONS.md`, or `DATASET_CATALOG.md`. Every apply creates a backup with a printed rollback command.
- **High-level MCP tools** -- `sancho_paths`, `sancho_mode`, `sancho_inventory`, `sancho_find_sources`, `sancho_module_show`, `sancho_cache_status`, `sancho_fetch_run`, `sancho_export_to_project`, `sancho_log_tail`, `sancho_log_show`, `sancho_env_open`, `sancho_env_recommend`, `sancho_update_check`, `sancho_update_preview`, `sancho_custom_status`, `sancho_fetched_data_audit`. Auto-registered when MCP runs against a real workspace.

## For AI assistants -- read this BEFORE replying to the user

Most users of Sancho Fetch are **not coders**. Before responding, run
`sancho mode --json`. It returns only `{"developer_mode": false}` or
`{"developer_mode": true}` and does not expose `.env` contents. If the command
is unavailable during first setup, default to developer mode off and use plain
English. To change the mode when the user asks, run `sancho mode --set on` or
`sancho mode --set off`; it rewrites only the `SANCHO_DEVELOPER_MODE` line in
the workspace `.env` and never prints other values.

- **`SANCHO_DEVELOPER_MODE=false` (default):** plain English, guided by intent rather than a blanket ban on technical content. The goal is that the user never feels they must understand Python, terminals, or Sancho internals to get their data. Skip plumbing that adds nothing (commands you ran, env-var names, diffs), but always share what helps the user act: the primary file path so they can open their data, and a short plain-language explanation -- a small code or error excerpt is fine -- when something breaks or takes longer than expected. Run setup/fetch commands yourself when possible; only ask the user for help when OS permissions, execution policy, or an installer approval prompt blocks you.
- **`SANCHO_DEVELOPER_MODE=true`:** technical detail is welcome. Commands, paths, diffs, env vars, and code are okay.

The short shared agent contract lives in [`CLAUDE.md`](CLAUDE.md) and
[`AGENTS.md`](AGENTS.md) at the project root. The full operator reference is
this file. Skill source files live under `src/sancho/templates/agent_skills/`
and setup installs them into the user's home-folder assistant skill locations.

If the user asks you to add a new data source or module, read
[`project-docs/MODULE_CREATION_GUIDE.md`](project-docs/MODULE_CREATION_GUIDE.md)
before writing files. It explains how to research official provider docs,
choose the closest existing module to copy from, handle API keys safely,
and test three broad human prompts after implementation.

After setup, read workspace-root `AI_INSTRUCTIONS.md` for workspace-specific
guidance.

## Local-first model

Default data flow:

`fetched-data/` -> `analysis-data/` -> `outputs/`

After setup, keep durable custom logic in `custom/**` and `playbooks/**`
(see [`examples/housing_affordability.playbook.yaml`](examples/housing_affordability.playbook.yaml)
for a worked playbook);
treat `source/**` as Sancho-managed and updatable.

Continue below for technical details and AI operator guidance.

## License

Sancho Fetch code is licensed under the Apache License 2.0.

Documentation and guides are licensed under CC BY 4.0 unless otherwise noted.

The Sancho name, Sancho Fetch name, logo, and brand assets are protected separately. The Apache License 2.0 does not grant trademark or brand rights.

See:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [LICENSE-DOCS.md](LICENSE-DOCS.md)
- [INTENDED_USE.md](INTENDED_USE.md)

Brand-use guidance lives in [NOTICE](NOTICE).

## AI Operator Reference

This section is the detailed operator guide for AI agents working in this repo.

### AI Onboarding Order

1. This file: `README_ALL_INSTRUCTIONS.md`.
2. [`AGENTS.md`](AGENTS.md) or [`CLAUDE.md`](CLAUDE.md), depending on the agent.
3. [`project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md`](project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md) for module audit contract.
4. [`project-docs/MODULE_CREATION_GUIDE.md`](project-docs/MODULE_CREATION_GUIDE.md) when adding or changing modules.
5. [`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md) for MCP transport/client setup.
6. After setup, read workspace-root `AI_INSTRUCTIONS.md` and `DATASET_CATALOG.md`.

### AI Operating Contract

Use this contract:

1. **Claude/Codex does the reasoning. Sancho provides inspectable facts.**
   Sancho gives you paths, manifests, cache status, logs, repair packets,
   update previews. You pick modules, decide concrete fetch units, and
   explain results in plain English.
2. **Never claim completion without checking result counts.**
   For a single run the run JSON is the evidence: confirm `status`,
   `cache_status`, and that `row_count` is non-zero where you expected
   data. Run `sancho log tail --json --limit 5 --module <id>` for
   playbooks / multi-unit runs or when a run failed. Don't trust an
   opaque "complete" flag.
   Then report the **primary path only** -- `Primary file:` / `Primary
   folder:` from `primary_output_path`. Don't surface the canonical cache
   path, manifest, provenance, or run ID unless the user asks, on error, or
   in developer mode.
3. **For broad requests, fetch bounded starter bundles.** For "everything
   about X", pick 5-10 modules at most, pull one representative request
   from each, and ask the user before expanding.
4. **For ambiguous requests, make assumptions visible.** Tell the user
   what you assumed (which states count as "notable", which year you
   defaulted to, which variables). Don't hide judgment calls.
5. **For repairs, prefer `custom/**` overrides.** Don't edit `source/**`
   directly -- updates will overwrite it. Create `custom/<type>/<module>/`
   and record what you did with `sancho repair note ...`.
6. **For updates, use the Sancho update flow.** Never `git pull`,
   `git reset --hard`, or any destructive Git command. Use
   `sancho update check / preview / apply / rollback`.
7. **Build durable artifacts, not chat-only output.** Save reusable logic
   in `source/`, `custom/`, and `playbooks/`. Fetched data goes in
   `fetched-data/`. Provenance lands in `provenance.yml` and
   `logs/runs.jsonl`.
8. **Respect ownership boundaries.** Personal paths
   (`custom/**`, `playbooks/**`, `fetched-data/**`, `analysis-data/**`,
   `outputs/**`, `logs/**`, `update-backups/**`, `.env`,
   `AI_INSTRUCTIONS.md`, `DATASET_CATALOG.md`) are never auto-rewritten.
9. **Show small results inline; don't dump large datasets into chat.**
   Use your discretion: a quick answer or a small table (under ~100 rows)
   is fine to show directly unless the user says otherwise. For larger
   datasets, preview at most a few rows if asked; otherwise report the
   path and counts.

The agent skill sources under `src/sancho/templates/agent_skills/` encode this
contract for Sancho fetch and update workflows. Setup installs them into the
user's home-folder assistant skill locations. In Claude Code they appear as
`/sancho` and `/sancho-update`; in Codex they are skills that can trigger from
matching natural-language requests.

### Hosting a Public Remote MCP Endpoint (Optional)

For a hosted remote-MCP sampler (separate from normal local usage), see [`hosting/README.md`](hosting/README.md).

### MCP vs Direct Codebase Access

Use direct codebase access when the AI can read/write local files and run Sancho Fetch CLI directly.

Use MCP when you need:

1. Desktop dataset access without manual workspace setup (`sancho mcp serve --quick`).
2. Stable tool protocol across MCP clients.
3. Read-only fetch-focused access for lightweight calls.
4. Optional remote connector hosting for web clients.

Which clients speak local vs remote MCP changes over time, so don't assume
it from memory. For current client support, transports, and endpoint
details, use:
[`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md)

## API Keys

Most fetch modules use free public APIs. Some are zero-key, some require free credentials.
Store keys in `.env` after setup. Sancho keeps exactly one env file,
`sancho-workspace/.env`, so keys and `sancho mode` always live in the same
place. Open it with `sancho env open` rather than hunting for it.

| Env var | Provider | Used by | Get it |
|---|---|---|---|
| `DATA_GOV_API_KEY` | api.data.gov (umbrella key) | `fetch.fbi.crime`, `fetch.fec`, `fetch.regulations.dockets`, `fetch.nrel.alt_fuel_stations`, `fetch.college_scorecard.schools`, `fetch.usda.fooddata_search` | https://api.data.gov/signup/ |
| `FRED_API_KEY` | Federal Reserve (FRED) | `fetch.fred.series` | https://fred.stlouisfed.org/docs/api/api_key.html |
| `BLS_API_KEY` | Bureau of Labor Statistics (optional, improves quotas) | `fetch.bls`, `fetch.atus` | https://data.bls.gov/registrationEngine/ |
| `BEA_API_KEY` | Bureau of Economic Analysis | `fetch.bea.nipa_table` | https://apps.bea.gov/API/signup/ |
| `CENSUS_API_KEY` | US Census Bureau | `fetch.census.acs_profile` | https://api.census.gov/data/key_signup.html |
| `CONGRESS_API_KEY` | Congress.gov | `fetch.congress.bills` | https://api.congress.gov/sign-up/ |
| `HUD_API_TOKEN` | HUD USER | `fetch.hud.fmr` | https://www.huduser.gov/hudapi/public/register |
| `NOAA_API_TOKEN` | NOAA Climate Data Online | `fetch.noaa.cdo` | https://www.ncdc.noaa.gov/cdo-web/token |
| `EIA_API_KEY` | US Energy Information Admin | `fetch.eia.series` | https://www.eia.gov/opendata/register.php |
| `AQS_API_KEY` + `AQS_EMAIL` | EPA AQS API | `fetch.epa.aqs_annual` | https://aqs.epa.gov/aqsweb/documents/data_api.html |
| `AIRNOW_API_KEY` | EPA AirNow API | `fetch.airnow` | https://docs.airnowapi.org/account/request/ |
| `DOL_API_KEY` | US Department of Labor API | `fetch.dol.osha_inspections` | https://developer.dol.gov/beginners-guide/ |
| `USPTO_API_KEY` | USPTO Open Data Portal | `fetch.uspto.application` | https://data.uspto.gov/apis/getting-started |
| `USDA_NASS_API_KEY` | USDA Quick Stats | `fetch.usda.quickstats` | https://quickstats.nass.usda.gov/api |
| `SODA_API_KEY_ID` + `SODA_API_KEY_SECRET` | Socrata / Tyler Data & Insights (optional, raises rate limits) | `fetch.nyc_open_data`, `fetch.cdc`, `fetch.socrata.*` | https://evergreen.data.socrata.com/signup |

**No key required** for: USGS earthquakes, Federal Register, SEC EDGAR (contact email recommended), ClinicalTrials.gov, openFDA, CMS, Treasury Fiscal Data, USAspending, FEMA OpenFEMA, EPA ECHO, CFPB, World Bank, FDIC, DOJ press releases, GSA CALC, NAEP, Open Payments, NHTSA Recalls.

### Setting keys

After setup, use `sancho env open` to open the right `.env` file. Sancho can
read keys from the project-level `.env`, while `sancho-workspace/.env` remains
available for workspace-specific overrides. A template `.env.example` lives in
the workspace.

Setup normally creates `.env` from `.env.example`. If `.env` is missing, run
`sancho env open`; it creates the correct file from the template and opens it.
To do it manually, copy `.env.example` in the same folder, keep the original
template, and name the copy `.env`.

**Heads-up: these files are hidden by default.** Filenames that start with a dot (`.env`, `.env.example`) are hidden on macOS and Windows. If you don't see them in your file explorer, turn on hidden files first:

- **macOS Finder:** open the Sancho Fetch folder, then press `Cmd + Shift + .` to toggle hidden files.
- **Windows File Explorer:** open the Sancho Fetch folder, click the **View** menu -> **Show** -> **Hidden items**.
- Or run `sancho env open` to open the right `.env` directly from your editor.

**Filling it in:** open `.env` and paste in your keys:

```bash
FRED_API_KEY=your_key_here
DATA_GOV_API_KEY=your_key_here
# ...
```

You don't need every key -- only the ones for the data sources you want to use. The table above shows which keys unlock which sources and where to register for each. Many sources need no key at all.

`.env` is personal and never overwritten by `sancho update`.

## MCP Surface

MCP is separate from normal local workspace usage. Use it when exposing Sancho Fetch through an MCP client or hosting a public MCP endpoint.

For hosted/public MCP, see [`hosting/README.md`](hosting/README.md).

For local desktop MCP experiments:

```bash
sancho mcp config --client claude-desktop --quick --profile broad
```

## Starter Data Packs

Packs bundle related modules into one install (`sancho add pack.<name>`).
This table names each pack and its focus; get the authoritative member list
from `sancho packs --json` or `sancho inventory --json` -- module IDs must
come from Sancho output, never from documentation. The generated
provider-by-provider support matrix lives in
[`project-docs/SUPPORT_MATRIX.md`](project-docs/SUPPORT_MATRIX.md).

| Pack | Focus |
|---|---|
| `pack.core_federal` | Legacy core federal sources |
| `pack.federal_extended` | Legacy extended federal sources |
| `pack.civic_socrata` | Legacy civic Socrata sources |
| `pack.federal_research` | Legacy research-oriented federal sources |
| `pack.global_economic` | Macro and development indicators |
| `pack.us_housing` | Housing affordability and permits |
| `pack.public_health` | Broad public-health bundle |
| `pack.health_equity` | Equity and social context |
| `pack.health_environment` | Environmental health and resilience |
| `pack.health_surveys` | Health surveys and public-use data |
| `pack.healthcare_access` | Providers, access, and coverage |
| `pack.health_access_helpers` | Public reference/access pages without restricted-source wrappers |
| `pack.environment_climate` | Climate, air, energy, hazards |
| `pack.civic_transparency` | Policy, regulation, spending transparency |
| `pack.provider_kits` | Legacy provider-kit bundle |
| `pack.global_governance` | Democracy, rule of law, corruption, peace |
| `pack.global_development` | Development indices, aid, climate vulnerability |
| `pack.global_data_hubs` | Cross-cutting data platforms |
| `pack.global_surveys` | Survey microdata and catalogs |
| `pack.international_core` | Best-of curated international set |
| `pack.geospatial` | Satellite, boundaries, earth science |

## Workspace Contract

`sancho-workspace/` always contains managed `source/**` and user-owned `custom/**` + `playbooks/**`.

- Managed (Sancho Fetch may update): `source/**`, `modules.lock.yaml`
- Personal (never auto-overwritten): `custom/**`, `playbooks/**`, `.env`, `AI_INSTRUCTIONS.md`, `DATASET_CATALOG.md`

## Core CLI Surface

- `sancho setup [--path .] [--install-claude-desktop] [--skip-smoke-check] [--no-register] [--json]`
- `sancho ready [--workspace .] [--json]`
- `sancho init [--path .] [--yes]` (low-level workspace init; normal users should use `sancho setup`)
- `sancho inventory [--json]`
- `sancho packs [--json]`
- `sancho providers [--json]`
- `sancho paths [--json]`
- `sancho mode [--workspace .] [--json]`
- `sancho library register|show|open|repair`
- `sancho add <module-id|pack-id> [--workspace .] [--discover]` -- optional; `sancho run` auto-installs a bundled module on first use, so `add` is only needed to pre-stage a pack or force discovery
- `sancho update check [--workspace .] [--json]`
- `sancho update preview [module-id] [--workspace .] [--json]`
- `sancho update apply [module-id] [--workspace .] [--allow-local-edits] [--json]`
- `sancho update rollback <backup-id> [--workspace .] [--json]`
- `sancho run <playbook-or-module> [--workspace .] [--input <input.json>]`
- `sancho fetch sample <provider> [--workspace .] [--json]`
- `sancho fetch catalog <provider> [--workspace .]`
- `sancho fetch run <provider> --path <api-path> [--workspace .] [--base <alias>] [--method <verb>] [--param k=v ...] [--params '{"k":"v"}'] [--body '{"k":"v"}']`
- `sancho module catalog refresh <module-id> [--offline]`
- `sancho module audit [--json]`
- `sancho module show|files|status|docs <module-id> [--workspace .] [--json]`
- `sancho module variables <module-id> [--dataset <id>] [--search "<concept>"] [--code <CODE>] [--limit <n>] [--refresh] [--workspace .] [--json]` -- resolve real variable/field codes from a dataset's dictionary instead of guessing; omit `--dataset` to list datasets
- `sancho module compare <module-id> [--workspace .] [--json]`
- `sancho cache status --module <module-id> [--request-json '<json>'|--request-file <request.yml>] [--max-age-seconds <n>] [--workspace .] [--json]`
- `sancho cache list [--module <module-id>] [--workspace .] [--json]`
- `sancho cache show <record-id> [--workspace .] [--json]`
- `sancho log path [--workspace .]`
- `sancho log tail [--errors] [--module <module-id>] [--limit <n>] [--workspace .] [--json]`
- `sancho log show <run-id> [--workspace .] [--json]`
- `sancho log search [--module <module-id>] [--query <text>] [--workspace .] [--json]`
- `sancho find sources "<query>" [--limit <n>] [--type fetch] [--json]`
- `sancho env open [provider] [--workspace .]`
- `sancho env check [--workspace .] [--json]`
- `sancho env recommend "<query>" [--limit <n>] [--workspace .] [--json]`
- `sancho export-to-project (--cache-record <id>|--run-id <id>) [--project .] [--workspace .] [--label <text>] [--json]`
- `sancho repair note --module <module-id> --summary "<text>" [--run-id <id>] [--workspace .] [--json]`
- `sancho custom status [--workspace .] [--json]`
- `sancho custom retire <module-id> [--workspace .] [--json]`
- `sancho fetched-data audit --old-modules [--workspace .] [--json]`
- `sancho doctor [--fix] [--json]`
- `sancho export`
- `sancho mcp serve [--workspace <path>]`
- `sancho mcp serve --quick [--profile lean|balanced|broad] [--modules <csv>] [--quick-home <path>] [--sync]`
- `sancho mcp config --client <name> [--workspace <path>] [--transport stdio|http] [--install]`
- `sancho mcp config --client <name> --quick [--profile ...] [--modules <csv>] [--quick-home <path>] [--sync]`

## Large-Tier Provider Example

```bash
sancho add fetch.world_bank --workspace .
sancho fetch catalog world_bank --workspace .
sancho fetch run world_bank --workspace . --base v2 \
  --path /country/all/indicator/SP.POP.TOTL \
  --param format=json --param per_page=1000
```

`--param k=v` is repeatable. `--params '{...}'` JSON is also supported.

## Additional Docs

- Human onboarding: [`README.md`](README.md)
- Data source standard: [`project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md`](project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md)
- Module creation guide: [`project-docs/MODULE_CREATION_GUIDE.md`](project-docs/MODULE_CREATION_GUIDE.md)
- MCP setup (desktop + web): [`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md)
- Provider matrix (generated): [`project-docs/SUPPORT_MATRIX.md`](project-docs/SUPPORT_MATRIX.md)
