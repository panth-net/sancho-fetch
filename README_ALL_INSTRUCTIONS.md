# Sancho Fetch

[![License: Sancho Fetch Fair Community 1.0](https://img.shields.io/badge/license-Sancho%20Fetch%20Fair%20Community%201.0-blue)](LICENSE)

A **local-first toolkit for fetching public data** from 120+ government,
international, and open data providers into one visible folder on your
computer. Driven by your local AI assistant (Claude Code, Codex, Cursor,
VS Code, or Claude Desktop) through plain-English requests. Built to stay inspectable --
every fetch lands as a real file with a manifest, a provenance record,
and an integrity hash. No black boxes.

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

Download the GitHub ZIP, unzip/extract it, and move the `sancho-fetch`
folder where you want to keep it before installing. The installer stores a
user-level `sancho` command plus a pointer back to this visible folder; it
does not install a second hidden library at `C:\` or another root folder.
If you move `sancho-fetch` later, re-run the installer so Claude/Codex point
at the new location.

Open the `installers/` folder and double-click:

- **macOS:** `installers/Install Sancho.command`
- **Windows:** `installers/Install Sancho.bat`

On Linux, open a terminal in `sancho-fetch` and run `bash installers/setup.sh`.
On macOS, if Finder blocks the downloaded `.command` file, right-click it and
choose **Open**, or run `bash installers/setup.sh` from Terminal. If the file
is not executable, run `chmod +x installers/Install\ Sancho.command` once and
open it again.

The installer checks/installs `uv`, lets `uv` choose or download a Python
that satisfies Sancho's `>=3.11` requirement, installs Sancho, creates the
workspace, registers this folder as your library, copies the Claude / Codex
agent skills to your home folder, writes local desktop MCP config snippets,
installs Claude Desktop config when supported, and installs a built-in sample
module as a setup check. In Claude Code those skills are invokable as
`/sancho <request>` and `/sancho-update`; in Codex they load as skills for
matching natural-language requests.

Then open this folder in Claude Code / Codex / Cursor / VS Code and ask the
AI to pull data for you. Claude Desktop and other desktop MCP clients also
work after their local MCP config is installed; the double-click installer
handles Claude Desktop automatically where possible. ChatGPT web needs the
hosted/remote connector path, not a local folder. The short human quick start
is [`README.md`](README.md).

## Quick start (developers)

```bash
# 1. uv (https://docs.astral.sh/uv/) handles Sancho's Python requirement
uv tool install .

# 2. One-shot setup: workspace + library pointer + skills + sample-module check
sancho setup --install-claude-desktop

# 3. Pull your first dataset (no API key needed)
sancho fetch sample world_bank
```

Add API keys when you're ready (zero-key for World Bank, USGS, openFDA, etc.):

```bash
sancho env open census   # opens .env, prints which env vars Census needs
sancho env check         # reports which providers are ready (names only, never values)
```

## What it does

- **Find sources** -- `sancho find sources "black population census state ACS"` returns ranked module candidates for a natural-language query. Your AI picks the plan.
- **Fetch with provenance** -- every fetch writes `data.json` + `request.yml` + `provenance.yml` + `content.sha256` + `README.md` to a canonical `fetched-data/<module>/<family>/<request_key>/<timestamp>/` folder. Cache hits are deterministic; re-fetches are append-only.
- **Project bundles** -- running Sancho from another project drops a `sancho-fetched-data/<date>-<slug>/` folder next to your work, copied (small/medium) or pointer-bundled (large) so you don't fill your drive.
- **Repair packets** -- every failure writes a `logs/errors/<run-id>_error.md` with HTTP status, response excerpt, traceback, files written, last successful run, docs links, suggested override path, and a safe-retry command.
- **Safe updates** -- `sancho update check / preview / apply / rollback`. Never runs `git pull`. Never touches `custom/`, `playbooks/`, `fetched-data/`, `analysis-data/`, `outputs/`, `logs/`, `update-backups/`, `.env`, `AI_INSTRUCTIONS.md`, or `DATASET_CATALOG.md`. Every apply creates a backup with a printed rollback command.
- **High-level MCP tools** -- `sancho_paths`, `sancho_mode`, `sancho_inventory`, `sancho_find_sources`, `sancho_module_show`, `sancho_cache_status`, `sancho_fetch_run`, `sancho_export_to_project`, `sancho_log_tail`, `sancho_log_show`, `sancho_env_open`, `sancho_env_recommend`, `sancho_update_check`, `sancho_update_preview`, `sancho_custom_status`, `sancho_fetched_data_audit`. Auto-registered when MCP runs against a real workspace.

## Manual setup (alternative to the installer)

If you'd rather walk through it yourself:

```bash
# uv -- https://docs.astral.sh/uv/
uv --version

# Install Sancho from the repo root
uv tool install .

# Workspace + library pointer + AI skills + MCP snippets
sancho setup --install-claude-desktop

# Pull a dataset (zero-key)
sancho fetch sample world_bank
```

You should see data under
`sancho-workspace/fetched-data/fetch.world_bank/...`.

**Windows note:** PowerShell handles path arguments better than Git Bash
when paths start with `/`.

**Optional npm alias** (thin wrapper over `uvx --from sancho-fetch sancho`):

```bash
npx @sancho/cli inventory
npx @sancho/cli setup
npx @sancho/cli fetch sample world_bank --workspace sancho-workspace
```

## For AI assistants -- read this BEFORE replying to the user

Most users of Sancho Fetch are **not coders**. Before responding, run
`sancho mode --json`. It returns only `{"developer_mode": false}` or
`{"developer_mode": true}` and does not expose `.env` contents. If the command
is unavailable during first setup, default to developer mode off and use plain
English.

- **`SANCHO_DEVELOPER_MODE=false` (default):** use plain language. Do not paste commands, code, file paths, env-var names, or diffs unless asked. Run setup/fetch commands yourself when possible; only ask the user for help when OS permissions, execution policy, or an installer approval prompt blocks you.
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

After setup, keep durable custom logic in `custom/**` and `playbooks/**`;
treat `source/**` as Sancho-managed and updatable.

Continue below for technical details and AI operator guidance.

## License

Sancho Fetch is public-source software under a fair-use community license. You can read it, use it, modify it, and build with it. If Sancho Fetch materially helps fetch or prepare data you share, cite it. Commercial use is free below the community threshold. Larger organizations, white-labeling, hosted resale, and products whose value derives primarily from Sancho Fetch require a paid license.

See [LICENSE](LICENSE) for full terms.

## README (FOR AI LLMs)

This section is the detailed operator guide for AI agents working in this repo.

### AI Onboarding Order

1. This file: `README_ALL_INSTRUCTIONS.md`.
2. [`AGENTS.md`](AGENTS.md) or [`CLAUDE.md`](CLAUDE.md), depending on the agent.
3. [`project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md`](project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md) for module audit contract.
4. [`project-docs/MODULE_CREATION_GUIDE.md`](project-docs/MODULE_CREATION_GUIDE.md) when adding or changing modules.
5. [`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md) for MCP transport/client setup.
6. After setup, read workspace-root `AI_INSTRUCTIONS.md` and `DATASET_CATALOG.md`.

### AI Mindset Contract (Codified Here)

Do not rely on external repos for mindset. Use this contract:

1. **Claude/Codex does the reasoning. Sancho provides inspectable facts.**
   Sancho gives you paths, manifests, cache status, logs, repair packets,
   update previews. You pick modules, decide concrete fetch units, and
   explain results in plain English.
2. **Never claim completion without checking logs and result counts.**
   Run `sancho log tail --json` after a fetch; confirm `status` is
   `success_with_data` or `success_empty` and that `row_count` is
   non-zero where you expected data. Don't trust an opaque "complete"
   flag.
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

The agent skill sources under `src/sancho/templates/agent_skills/` encode this
contract for Sancho fetch and update workflows. Setup installs them into the
user's home-folder assistant skill locations. In Claude Code they appear as
`/sancho` and `/sancho-update`; in Codex they are skills that can trigger from
matching natural-language requests.

### Why Teams Use Sancho Fetch

1. Local-first workspace with strict managed vs personal boundaries.
2. Reusable modules/playbooks instead of one-off scripts.
3. AI-friendly structure with inspectable files.
4. First-class CLI and MCP surfaces for the same workspace.

### Hosting a Public Remote MCP Endpoint (Optional)

For a hosted remote-MCP sampler (separate from normal local usage), see [`hosting/README.md`](hosting/README.md).

### MCP vs Direct Codebase Access

Use direct codebase access when the AI can read/write local files and run Sancho Fetch CLI directly.

Use MCP when you need:

1. Desktop dataset access without manual workspace setup (`sancho mcp serve --quick`).
2. Stable tool protocol across MCP clients.
3. Read-only fetch-focused access for lightweight calls.
4. Optional remote connector hosting for web clients.

### MCP Scope Reality Check (April 22, 2026)

1. Localhost MCP is for desktop/local MCP clients (Claude Desktop, VS Code, Cursor).
2. ChatGPT MCP apps/connectors are remote-server based (not localhost).
3. ChatGPT MCP app usage is web-only currently.
4. Claude.ai custom connectors are remote MCP URLs; local MCP is via Claude Desktop.

For setup and endpoint details, use:
[`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md)

## API Keys

Most fetch modules use free public APIs. Some are zero-key, some require free credentials.
Store keys in workspace `.env` after setup.

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

After setup, a `.env` file is created at `sancho-workspace/.env`. A template `.env.example` lives alongside it.

**Heads-up: these files are hidden by default.** Filenames that start with a dot (`.env`, `.env.example`) are hidden on macOS and Windows. If you don't see them in your file explorer, turn on hidden files first:

- **macOS Finder:** open the `sancho-workspace/` folder, then press `Cmd + Shift + .` to toggle hidden files.
- **Windows File Explorer:** open the `sancho-workspace/` folder, click the **View** menu -> **Show** -> **Hidden items**.
- Or open `sancho-workspace/.env` directly from your editor without toggling anything.

**Filling it in:** open `.env` and paste in your keys:

```bash
FRED_API_KEY=your_key_here
DATA_GOV_API_KEY=your_key_here
# ...
```

You don't need every key -- only the ones for the data sources you want to use. The table above shows which keys unlock which sources and where to register for each. Many sources need no key at all.

`.env` is personal and never overwritten by `sancho update`.

## Quickstart (Local Core)

### First pull in two commands (no API key)

```bash
sancho setup --install-claude-desktop
sancho fetch sample world_bank
```

Real World Bank population data lands in `sancho-workspace/fetched-data/fetch.world_bank/`.

### Full workspace with a starter pack

```bash
sancho setup --install-claude-desktop
sancho add pack.global_economic
sancho doctor --fix --json
```

Windows note: prefer PowerShell over Git Bash for path arguments that start with `/`.

## MCP Surface

MCP is separate from normal local workspace usage. Use it when exposing Sancho Fetch through an MCP client or hosting a public MCP endpoint.

For hosted/public MCP, see [`hosting/README.md`](hosting/README.md).

For local desktop MCP experiments:

```bash
sancho mcp config --client claude-desktop --quick --profile broad
```

## Starter Data Packs

This table is intentionally explicit so AI assistants can see what Sancho Fetch
can install without opening another file. The generated provider-by-provider
support matrix lives in [`project-docs/SUPPORT_MATRIX.md`](project-docs/SUPPORT_MATRIX.md).

| Pack | Focus | Includes |
|---|---|---|
| `pack.core_federal` | Legacy core federal sources | `fetch.census.acs_profile`, `fetch.bls`, `fetch.bea.nipa_table`, `fetch.fred.series`, `fetch.hud.fmr` |
| `pack.federal_extended` | Legacy extended federal sources | `fetch.census.acs_profile`, `fetch.bls`, `fetch.bea.nipa_table`, `fetch.fred.series`, `fetch.hud.fmr`, `fetch.treasury.fiscal_data`, `fetch.usaspending.awards`, `fetch.congress.bills`, `fetch.federal_register.documents`, `fetch.regulations.dockets`, `fetch.usgs.earthquakes`, `fetch.noaa.cdo`, `fetch.eia.series`, `fetch.fbi.crime`, `fetch.nhtsa.recalls`, `fetch.fema.openfema`, `fetch.cdc`, `fetch.cms.data`, `fetch.usda.quickstats` |
| `pack.civic_socrata` | Legacy civic Socrata sources | `fetch.socrata.dataset`, `fetch.socrata.chicago_crimes`, `fetch.nyc_open_data`, `fetch.socrata.sf_building_permits`, `fetch.socrata.la_crime`, `fetch.socrata.seattle_building_permits` |
| `pack.federal_research` | Legacy research-oriented federal sources | `fetch.college_scorecard.schools`, `fetch.naep.adhoc_data`, `fetch.dol.osha_inspections`, `fetch.epa.echo_facilities`, `fetch.epa.aqs_annual`, `fetch.fdic.institutions`, `fetch.fec`, `fetch.gsa_calc.ceiling_rates`, `fetch.uspto.application`, `fetch.cfpb.complaints`, `fetch.usda.fooddata_search`, `fetch.sec.company_submissions`, `fetch.clinical_trials.studies`, `fetch.fda.drug_events`, `fetch.doj.press_releases`, `fetch.nrel.alt_fuel_stations`, `fetch.open_payments.datasets`, `fetch.world_bank` |
| `pack.global_economic` | Macro and development indicators | `fetch.world_bank`, `fetch.fred.series`, `fetch.bea.nipa_table`, `fetch.bls`, `fetch.treasury.fiscal_data`, `fetch.usaspending.awards` |
| `pack.us_housing` | Housing affordability and permits | `fetch.hud.fmr`, `fetch.census.acs_profile`, `fetch.nyc_open_data`, `fetch.socrata.sf_building_permits`, `fetch.socrata.seattle_building_permits` |
| `pack.public_health` | Broad public-health bundle | `fetch.ahrq.meps`, `fetch.ahrq.nhqdr`, `fetch.ahrq.sdoh`, `fetch.airnow`, `fetch.atsdr.eji`, `fetch.atsdr.svi`, `fetch.atus`, `fetch.brfss`, `fetch.cdc`, `fetch.cdc.biomonitoring`, `fetch.cdc.birth_defects`, `fetch.cdc.heat_events`, `fetch.cdc.mmwr`, `fetch.cdc.nhanes`, `fetch.cdc.nhis`, `fetch.cdc.nsfg`, `fetch.cdc.nvss`, `fetch.cdc.nwss`, `fetch.cdc.places`, `fetch.cdc.ssun`, `fetch.cdc.tracking`, `fetch.cdc.vaxview`, `fetch.cdc.wisqars`, `fetch.cdc.wonder`, `fetch.cejst`, `fetch.census.acs_profile`, `fetch.census.cps`, `fetch.census.decennial`, `fetch.census.htops`, `fetch.census.onthemap_em`, `fetch.census.sipp`, `fetch.cms.data`, `fetch.cms.cciio`, `fetch.cms.marketplace_reports`, `fetch.cms.medicaid`, `fetch.cms.synpuf`, `fetch.clinical_trials.studies`, `fetch.dol.naws`, `fetch.ed.crdc`, `fetch.epa.aqs_annual`, `fetch.epa.echo_facilities`, `fetch.epa.ejscreen`, `fetch.epa.enviroatlas`, `fetch.epa.iris`, `fetch.epa.smart_location`, `fetch.epa.tri`, `fetch.fema.nri`, `fetch.fda.drug_events`, `fetch.hhs.poverty_guidelines`, `fetch.hrsa.ahrf`, `fetch.hrsa.hpsa`, `fetch.hrsa.nsch`, `fetch.hrsa.uds`, `fetch.hud.hdx_homelessness`, `fetch.naep.adhoc_data`, `fetch.noaa.cmra`, `fetch.noaa.nws`, `fetch.open_payments.datasets`, `fetch.umich.nanda`, `fetch.usda.food_access`, `fetch.usda.food_security`, `fetch.usda.fooddata_search` |
| `pack.health_equity` | Equity and social context | `fetch.ahrq.sdoh`, `fetch.atsdr.eji`, `fetch.atsdr.svi`, `fetch.cejst`, `fetch.census.acs_profile`, `fetch.census.decennial`, `fetch.census.htops`, `fetch.ed.crdc`, `fetch.epa.ejscreen`, `fetch.hhs.poverty_guidelines`, `fetch.hud.hdx_homelessness`, `fetch.umich.nanda`, `fetch.usda.food_access` |
| `pack.health_environment` | Environmental health and resilience | `fetch.airnow`, `fetch.cdc.heat_events`, `fetch.cdc.nwss`, `fetch.cdc.tracking`, `fetch.epa.aqs_annual`, `fetch.epa.echo_facilities`, `fetch.epa.enviroatlas`, `fetch.epa.iris`, `fetch.epa.smart_location`, `fetch.epa.tri`, `fetch.fema.nri`, `fetch.noaa.cmra`, `fetch.noaa.nws` |
| `pack.health_surveys` | Health surveys and public-use data | `fetch.ahrq.meps`, `fetch.atus`, `fetch.brfss`, `fetch.cdc.nhanes`, `fetch.cdc.nhis`, `fetch.cdc.nsfg`, `fetch.census.cps`, `fetch.census.sipp`, `fetch.hrsa.nsch` |
| `pack.healthcare_access` | Providers, access, and coverage | `fetch.ahrq.nhqdr`, `fetch.cdc.places`, `fetch.cms.cciio`, `fetch.cms.data`, `fetch.cms.marketplace_reports`, `fetch.cms.medicaid`, `fetch.cms.synpuf`, `fetch.hrsa.ahrf`, `fetch.hrsa.hpsa`, `fetch.hrsa.uds`, `fetch.open_payments.datasets` |
| `pack.health_access_helpers` | Public reference/access pages without restricted-source wrappers | `fetch.nih.usrds`, `fetch.nlm.vsac` |
| `pack.environment_climate` | Climate, air, energy, hazards | `fetch.noaa.cdo`, `fetch.usgs.earthquakes`, `fetch.epa.aqs_annual`, `fetch.airnow`, `fetch.epa.echo_facilities`, `fetch.eia.series`, `fetch.nrel.alt_fuel_stations`, `fetch.fema.openfema` |
| `pack.civic_transparency` | Policy, regulation, spending transparency | `fetch.congress.bills`, `fetch.federal_register.documents`, `fetch.regulations.dockets`, `fetch.usaspending.awards`, `fetch.fec`, `fetch.sec.company_submissions`, `fetch.cfpb.complaints`, `fetch.gsa_calc.ceiling_rates`, `fetch.doj.press_releases` |
| `pack.provider_kits` | Legacy provider-kit bundle | `fetch.world_bank`, `fetch.nyc_open_data`, `fetch.fec`, `fetch.cdc`, `fetch.bls` |
| `pack.global_governance` | Democracy, rule of law, corruption, peace | `fetch.vdem`, `fetch.wgi`, `fetch.wjp_rule_of_law`, `fetch.rsf_press_freedom`, `fetch.ti_cpi`, `fetch.fsi`, `fetch.gpi`, `fetch.un_egdi` |
| `pack.global_development` | Development indices, aid, climate vulnerability | `fetch.undp_hdr`, `fetch.sdg_index`, `fetch.oecd_sdmx`, `fetch.oecd_dac_crs`, `fetch.iati`, `fetch.imf_cdis`, `fetch.nd_gain` |
| `pack.global_data_hubs` | Cross-cutting data platforms | `fetch.owid_charts`, `fetch.owid_catalog`, `fetch.overture_maps` |
| `pack.global_surveys` | Survey microdata and catalogs | `fetch.wvs`, `fetch.pew`, `fetch.atus`, `fetch.brfss` |
| `pack.international_core` | Best-of curated international set | `fetch.world_bank`, `fetch.vdem`, `fetch.wgi`, `fetch.undp_hdr`, `fetch.ti_cpi`, `fetch.owid_charts`, `fetch.oecd_sdmx` |
| `pack.geospatial` | Satellite, boundaries, earth science | `fetch.natural_earth`, `fetch.earthengine`, `fetch.planetary_computer`, `fetch.earthdata`, `fetch.overture_maps` |

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
- `sancho add <module-id|pack-id> [--workspace .] [--discover]`
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
