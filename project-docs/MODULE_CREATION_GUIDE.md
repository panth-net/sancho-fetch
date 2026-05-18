# Sancho Module Creation Guide For AI Agents

This guide is for AI agents adding new Sancho Fetch modules. Keep module creation explicit, repeatable, and auditable.

Before adding a module, read:

1. `README_ALL_INSTRUCTIONS.md`
2. `AGENTS.md` or `CLAUDE.md` if present at the repo root
3. `project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md`
4. `src/sancho/templates/runtime/AI_INSTRUCTIONS.md`
5. Existing modules under `src/sancho/templates/modules/`

## Current AI Workflow For Adding A Module

Use this workflow now, even before the future `sancho module create`
scaffolder exists.

1. Confirm scope in plain English: provider, geography, likely datasets,
   public/no-key vs keyed access, and whether the user needs one narrow
   dataset or a broad provider catalog.
2. Research the provider from official sources. Use web search for the
   provider homepage, API docs, data catalog, data dictionary, license/terms,
   rate-limit policy, page-size limits, pagination mechanism, and a sample
   endpoint. Prefer official provider docs and platform docs. Do not invent
   endpoints from memory. If no rate-limit statement is published, say that
   explicitly and use conservative throttling plus the largest documented safe
   page size.
3. Identify the platform pattern:
   - `socrata`: Socrata/SODA portals and `/resource/<id>.json` APIs.
   - `arcgis`: ArcGIS REST FeatureServer/MapServer layers and ArcGIS Hub.
   - `dcat`: DCAT/CKAN-style catalogs and metadata feeds.
   - `api`: ordinary documented HTTP APIs.
   - `file_manifest`: stable downloadable files.
   - `report_only`: public pages or reports where Sancho should expose links,
     not pretend there is a clean data API.
4. Pick the closest existing module before writing code. Compare platform,
   tier, key requirement, request shape, output shape, and test strategy.
   Name the exemplar in your notes. If no exemplar is close, keep the new
   module minimal and document why.
5. Choose tier:
   - `small` when the module wraps one dataset, one default endpoint, or a
     narrow public surface. Small modules need `schema.sample.json`.
   - `large` when the module exposes many endpoint families, tables,
     datasets, or parameters. Large modules need `catalog.json`,
     `catalog.meta.json`, and `discovery.py`.
6. Handle credentials explicitly:
   - No key: do not touch env files or `src/sancho/env_keys.py`.
   - Optional or required key: add the module to `src/sancho/env_keys.py`,
     update root `.env.example` and
     `src/sancho/templates/workspace/.env.example` with comments, the exact
     env var names, and the official sign-up URL.
   - Never edit a user's real `.env`. If a key is needed, tell the user to
     paste it into `.env` themselves or use `sancho env open`.
7. Implement the smallest working module in
   `src/sancho/templates/modules/<module-id>/`. Follow the exemplar's file
   layout, boring code style, and output convention
   `{dataset_ref, endpoint, params, rows, raw, retrieved_at}` when it fits.
   For fetch modules with paginated APIs, request the largest documented safe
   page size by default and assume the user wants all matching records unless
   they explicitly ask for a limit. Do not confuse per-request page size with
   a total row cap. Do not silently return only the first page, first thousand,
   or any arbitrary subset. If the provider imposes a hard stop or a full pull
   is unsafe, say so explicitly, return `has_more` / `next_*` metadata, and do
   not claim the dataset is complete.
   Expose `pagination` metadata (`page_size`, total count when available,
   fetched pages, fetched rows, `has_more`, stop reason).
8. Add or update tests:
   - Manifest/schema shape test.
   - Runtime smoke test with mocked HTTP.
   - `find_sources` smoke test for natural-language discoverability.
   - Pagination test proving the module uses the max safe page size and moves
     through pages until complete, a cap, or a documented stop reason.
   - Data-shape test proving real or mocked prompt-shaped requests return the
     expected columns/sample rows, not only that source discovery works.
   - Head preview test when possible: serialize the first five fetched rows
     into a readable string and inspect/assert that it looks like the intended
     dataset, not just a technically valid shape.
   - Live no-key test only when stable and cheap; skip cleanly if network is
     unavailable.
   - Env recommendation tests when a key is added.
9. Write three broad human prompts that should discover or exercise the
   source. Test that `sancho find sources` or the corresponding helper ranks
   the new module for those prompts, then run prompt-shaped sample requests
   and inspect returned row shape, pagination metadata, counts, and the first
   five rows rendered as text when possible. Actually read the head preview for
   semantic sanity: the values should look like the data source the prompt was
   asking for. The prompts should sound like a real user, not a module ID.
10. Run focused verification, then report:
    - files changed
    - exemplar used and why
    - official docs consulted
    - tests run
    - any remaining gap or live-data caveat

## Goal

Add a `sancho module create` scaffolder so new modules are created through one safe path instead of hand-built ad hoc folders.

Proposed command shape:

```bash
sancho module create <module-id>
```

Examples:

```bash
sancho module create fetch.example_provider
sancho module create process.normalize_custom_records
sancho module create analyze.local_summary
sancho module create dashboard.basic_report
```

The scaffolder should ask the questions below, generate the right starter files, and optionally create tests.

## Required Questions

Ask these before writing files:

1. **What type?**
   - `fetch`
   - `process`
   - `analyze`
   - `dashboard`

2. **What pattern?**
   - `api`
   - `file_manifest`
   - `socrata`
   - `dcat`
   - `arcgis`
   - `report_only`

3. **Is it small or large tier?**
   - `small`: one main dataset or narrow endpoint surface
   - `large`: many endpoint families, datasets, tables, or parameters

4. **Does it need an API key?**
   - no key
   - optional key
   - required key
   - key env var name, if known

5. **What dataset refs should it declare?**
   - provider homepage
   - API docs
   - data dictionary
   - terms/license page
   - sample endpoint or dataset URL

6. **Should it create tests?**
   - no tests
   - smoke test only
   - live no-key test
   - live keyed test
   - release-gate/audit test updates

## Generated Files

The scaffolder should create a module folder:

```text
src/sancho/templates/modules/<module-id>/
```

For most modules, generate:

```text
module.yaml
main.py
```

For fetch modules, also generate the files required by the selected pattern and tier.

### API Pattern

Use for ordinary HTTP APIs.

```text
api.py
transform.py
discovery.py
schema.sample.json       # small tier
catalog.json             # large tier
catalog.meta.json        # large tier
```

### File Manifest Pattern

Use for providers that publish downloadable files rather than a request API.

```text
manifest.py
transform.py
discovery.py
schema.sample.json       # small tier
catalog.meta.json        # large tier or source provenance
```

### Socrata Pattern

Use for Socrata/SODA open data portals.

```text
api.py
transform.py
discovery.py
catalog.json
catalog.meta.json
```

### DCAT Pattern

Use for catalog-first portals that expose DCAT or CKAN-like metadata.

```text
api.py
transform.py
discovery.py
catalog.json
catalog.meta.json
```

### ArcGIS Pattern

Use for ArcGIS REST services and feature layers.

Small single-layer ArcGIS modules may use the shared public-source helper:

```text
main.py
schema.sample.json
```

Large ArcGIS provider modules that need catalog traversal should use:

```text
api.py
transform.py
discovery.py
catalog.json
catalog.meta.json
```

### Report-Only Pattern

Use when the provider is documentation, report pages, or manual-reference material and should not pretend to be a direct data API.

```text
main.py
schema.sample.json       # only if there is a stable downloadable sample
catalog.meta.json        # provenance and source refs
```

## `module.yaml` Requirements

Every generated `module.yaml` should include:

```yaml
id: fetch.example_provider
name: Example Provider
type: fetch
description: Short plain-language description.
version: 0.1.0
catalog_tier: small
requires_api_key: false
api_key_env: null
sources:
  - label: Provider API docs
    url: https://example.org/api
```

For non-fetch modules, omit `catalog_tier` unless the module contract requires it.

## Test Generation

When tests are requested, create the smallest useful test first.

Recommended test files:

```text
tests/test_<provider>_phase1.py
tests/test_live_<provider>.py
tests/test_live_keyed.py      # if sharing existing keyed test grouping is cleaner
```

Starter smoke test should check:

1. Module folder exists.
2. `module.yaml` parses.
3. Required tier files exist.
4. `sancho module audit` passes for the module.
5. No-key sample fetch works when the provider supports it.
6. Three broad human prompts discover the module through `sancho find sources`.

Live tests must skip cleanly when network access or required API keys are unavailable.

## Worked Example: Washington DC Open Data

Washington DC Open Data (`opendata.dc.gov`) is an ArcGIS Hub portal. The
default source added as `fetch.dc_open_data` uses the public DC 311 service
requests FeatureServer layer and the ArcGIS `query` operation.

Research findings:

- Open Data DC exposes datasets through direct downloads and APIs.
- The 311 service request dataset is public and no API key is required.
- The ArcGIS layer supports JSON query responses, pagination, statistics,
  and `Query,Extract` capabilities.
- Esri's ArcGIS REST API documents the `where`, `outFields`,
  `resultRecordCount`, and `returnGeometry` query parameters used by the
  module.
- The layer advertises `MaxRecordCount: 1000`, so the module uses
  `resultRecordCount=1000` by default and follows `resultOffset` until the
  matching result set is complete. Caller-supplied caps are for explicit
  limits or tests, not the default user experience.
- No reliable public DC-specific per-second rate limit was found. The module
  therefore uses max-sized pages, Sancho's shared HTTP throttle/retry settings,
  and reports that assumption in `pagination.rate_limit_source`.

Exemplar selection:

- Closest local module: `fetch.fema.nri`.
- Why: both are small public ArcGIS FeatureServer query modules, both can use
  `sancho.runtime.public_source.run_public_source`, and both flatten ArcGIS
  `features[].attributes` into rows.
- Not chosen: Socrata modules, because DC Open Data is ArcGIS Hub rather than
  SODA; large provider modules, because this module starts with one stable
  public layer instead of a full catalog crawler.

Human prompt checks to keep:

1. "Show me recent 311 service requests in Washington DC."
2. "Pull DC open data about city service complaints by ward."
3. "I need Washington DC public service request records from the open data portal."

For each prompt, do not stop at source discovery. Inspect a fetched sample:
the rows should include service request ID, service code description, service
type, service order date, ward, and status; the output should include
`shape` and `pagination` metadata; and pagination should fetch beyond the
first page when the count exceeds `resultRecordCount`. When possible, render
the first five rows as a string and actually read them for semantic fit: the
head should look like DC 311 service request records, not just arbitrary JSON.

## Safety Rules

1. Do not overwrite an existing module unless the user explicitly asks.
2. Prefer copying patterns from the closest existing module.
3. Do not invent API endpoints. Use provider docs or discoverable catalogs.
4. Keep generated code minimal and boring.
5. Run focused tests after scaffolding.
6. Update README inventory or pack lists only when the module is actually included in a pack or public surface.

## Scaffolder Acceptance Checklist

The first production-ready `sancho module create` implementation should:

1. Validate module IDs and reject unsafe paths.
2. Ask all required questions interactively.
3. Support non-interactive flags for AI agents and CI.
4. Generate files based on type, pattern, tier, API-key status, dataset refs, and test choice.
5. Refuse accidental overwrites by default.
6. Print next steps in plain language.
7. Run or suggest the focused smoke test.
8. Produce output that passes `python -m pytest tests/test_release_gate.py`.

## Custom Overrides -- Where User and AI Repairs Live

Sancho splits modules into two zones inside `sancho-workspace/`:

- `source/<type>/<sanitize(module_id)>/` -- managed modules installed and
  updated by Sancho. These get rewritten by `sancho update apply`.
- `custom/<type>/<sanitize(module_id)>/` -- your overrides. Anything here
  is **personal**: `sancho update` never touches it, and at runtime a
  custom module with the same `id:` as a source module wins.

When a fetch breaks because of upstream API drift, the right fix is:

1. Don't edit `source/**`. The next `sancho update apply` will overwrite
   your edits.
2. Create a `custom/<type>/<sanitize(module_id)>/` with the same `id:` in
   `module.yaml`. Copy the minimum files you need to override (often just
   the `main.py` or `api.py` that has the bug).
3. Record the repair: `sancho repair note --module <id> --summary "..."`.
   This appends to `logs/repairs.jsonl` and, when a custom override
   exists, drops a timestamped entry into
   `custom/<type>/<module>/REPAIR_NOTES.md` so the history travels with
   the override.

## Contributing a Custom Fix Upstream

If the fix is generally useful:

1. Open a PR against `src/sancho/templates/modules/<module_id>/` with the
   same change you applied in your `custom/` override.
2. Reference the user-facing symptom and the repair-note summary in the
   PR description. Sancho's regression tests cover the contract; live
   tests are skipped in CI without keys.

## What Happens After Upstream Merges

Once your fix lands in a future Sancho release:

1. `sancho update check` shows the official `source/` module is newer
   than your custom override.
2. `sancho custom status` flags the override as `upstream_newer_than_custom`
   and recommends `compare_or_retire`.
3. `sancho module compare <id>` diffs your override against the template
   so you can confirm the upstream change covers your fix.
4. If it does, `sancho custom retire <id>` moves your override to
   `custom/_retired/<name>__<timestamp>/`. **Retirement never deletes** --
   you can recover it if needed.
5. With the override retired, the next `sancho update apply` will install
   the upstream fix into `source/` and the runtime starts using it.

## How to Retire a Custom Override

```bash
sancho custom status                       # see which overrides are stale
sancho module compare <module-id>           # confirm upstream covers your fix
sancho custom retire <module-id>            # move to custom/_retired/
sancho update apply                         # install the upstream version
```

Retired overrides stay in `custom/_retired/` for future reference. Sancho
won't load them at runtime (the `_retired/` prefix excludes them from
module discovery), but you can re-copy any file back into the active
custom path if you ever need to resurrect the fix.

