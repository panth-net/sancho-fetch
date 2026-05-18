I’d implement the **update architecture as both code and a skill**, but with a strict division:

**Sancho code** should produce safe, boring, inspectable facts: paths, versions, checksums, update previews, cache status, logs, changed files, backups, rollback points.

**Claude/Codex skill** should do the judgment work: read diffs, inspect changed modules, explain what changed in plain English, decide whether user edits should become `custom/**` overrides, and guide the user through update choices.

That fits the direction from the attached transcript: Sancho is the “dumb tool that fetches,” while Claude/Codex is the reasoning agent that plans, decides, repairs, and explains. The transcript also locks in the key requirements: visible `fetched-data/`, logs for debugging, source-shaped cache folders, safe updates, custom modules surviving, and no opaque “all fetched” status. 

Below is the phased implementation plan I’d hand to a developer.

---

# Sancho Fetch implementation plan

## Core product rule

**Sancho Fetch is a visible local data library.**

The user’s visible folder remains the center:

```text
sancho-fetch/
  sancho-workspace/
    source/          # official managed modules
    custom/          # user modules and overrides
    playbooks/       # user workflows
    fetched-data/    # canonical fetched source data, read-only by convention
    analysis-data/   # editable derived work
    outputs/         # reports, dashboards, exports
    logs/            # runs, errors, cache events, repairs
    .env             # API keys and local settings
```

The repo already has the foundation: `source/**` is managed, while `custom/**`, `playbooks/**`, `.env`, `AI_INSTRUCTIONS.md`, and `DATASET_CATALOG.md` are personal; `custom/**` wins at runtime when it has the same module id as a managed source module. 

The main changes are:

1. Rename `data/raw` to `fetched-data`.
2. Add visible logging.
3. Add cache/status/indexing primitives.
4. Add project-copy/export behavior.
5. Add agent-facing skills for `/sancho fetch` and `/sancho update`.
6. Add safe update machinery that checks GitHub/release metadata without requiring users to know Git.
7. Keep the hosted MCP as a stripped demo sampler, not the main product. The hosted README already describes it as fetch-only, stateless, rate-limited, with no caching, no analysis, no dashboards, and no workspace. 

---

# Architectural decision: update should be skill + code

## Why not skill-only?

A skill-only update flow would require Claude/Codex to manually compare folders, infer safe paths, create backups, check versions, and avoid destructive changes. That is too fragile.

## Why not code-only?

A code-only update flow cannot reliably judge the user’s intent if they edited a managed module. It can detect a changed checksum, but it cannot explain: “This looks like your Zillow fix; let’s move it into `custom/fetch/zillow/` before updating.”

## Correct split

```text
Sancho CLI:
  deterministic checks, previews, backups, version comparison, rollback, logs

Claude/Codex skill:
  reasoning, grep/read/diff, user explanation, custom override migration, repair guidance
```

Claude Code skills are a good fit because current Claude Code docs say skills are `SKILL.md` workflows that can be invoked directly as `/skill-name`, have arguments via `$ARGUMENTS`, and load their full instructions only when used. ([Claude API Docs][1]) Codex also supports reusable skills with `SKILL.md`, progressive disclosure, and implicit or explicit activation; Codex additionally reads project `AGENTS.md` guidance before work. ([OpenAI Developers][2])

So Sancho should ship:

```text
.claude/skills/sancho/SKILL.md
.claude/skills/sancho-update/SKILL.md

.agents/skills/sancho/SKILL.md
.agents/skills/sancho-update/SKILL.md

CLAUDE.md
AGENTS.md
```

The skill should call Sancho commands, inspect logs/diffs, and explain choices.

---

# Phase 1 — Rename and lock the workspace contract

## Ticket 1.1 — Rename product language to Sancho / Sancho Fetch

**Goal:** Keep user-facing docs and runtime text on the Sancho naming only.

**Scope:**

* Replace product name with **Sancho** or **Sancho Fetch**.
* Use `sancho-fetch` for the repo folder name and **Sancho Fetch** for product prose.
* Use **Sancho** for CLI/product shorthand.
* Keep internal import package name `sancho`; the Python distribution is `sancho-fetch`.

**Files likely touched:**

* `README.md`
* `README.md`
* `project-docs/*.md`
* `hosting/README.md`
* `hosting/instructions.txt`
* `npm-cli/README.md`
* workspace templates under `src/sancho/templates/workspace/`
* any generated support docs

**Acceptance criteria:**

* No old-name references remain in user-facing docs or runtime text.
* The README says the final visible repo folder should be called `sancho-fetch`.
* The product promise says: “Install Sancho once, keep your visible `sancho-fetch` folder, use `/sancho` anywhere.”

---

## Ticket 1.2 — Change workspace tree from `data/raw` to `fetched-data`

**Goal:** Make fetched source data visible, understandable, and not hidden behind “raw.”

Current docs and runtime still use `sancho-workspace/data/raw/` as the fetched data location.  The code also constructs `ModuleContext` with `data_raw_path=workspace_root / "data" / "raw"`, so this is a real runtime change, not only a docs rename. 

**New tree:**

```text
sancho-workspace/
  source/
  custom/
  playbooks/
  fetched-data/
  analysis-data/
  outputs/
  logs/
  update-backups/
  AI_INSTRUCTIONS.md
  DATASET_CATALOG.md
  .env.example
  .env
  sancho.yaml
  modules.yaml
  modules.lock.yaml
```

**Implementation notes:**

* Update `src/sancho/constants.py`:

  * remove `data/raw`, `data/refined`, `data/outputs`
  * add `fetched-data`, `analysis-data`, `outputs`, `logs`, `update-backups`
* Update `ModuleContext`:

  * add `fetched_data_path`
  * keep `data_raw_path` temporarily as an alias pointing to `fetched-data` if needed for module compatibility
* Update runtime helpers:

  * `save_raw` / `load_raw` naming can remain internally for now, but output path should be `fetched-data`
  * eventually rename helpers to `save_fetched` / `load_fetched`

**Acceptance criteria:**

* `sancho setup --path . --skip-smoke-check` creates `sancho-workspace/fetched-data/`.
* `sancho fetch sample world_bank --workspace sancho-workspace` writes to `fetched-data/`, not `data/raw/`.
* No new workspace initializes with `data/raw`.
* Existing module code still runs if it uses `context.data_raw_path`.

---

## Ticket 1.3 — Update protected/generated path policy

**Goal:** Prevent GitHub update/pull accidents.

**Update protected paths:**

```text
custom/
playbooks/
fetched-data/
analysis-data/
outputs/
logs/
update-backups/
AI_INSTRUCTIONS.md
DATASET_CATALOG.md
.env
```

Current constants protect `custom/`, `playbooks/`, `AI_INSTRUCTIONS.md`, `DATASET_CATALOG.md`, and `.env`; add the new generated/user paths. 

**Update `.gitignore`:**

```text
sancho-workspace/fetched-data/
sancho-workspace/analysis-data/
sancho-workspace/outputs/
sancho-workspace/logs/
sancho-workspace/update-backups/
sancho-workspace/.env
**/sancho-fetched-data/
```

**Do not ignore:**

```text
sancho-workspace/custom/
sancho-workspace/playbooks/
sancho-workspace/AI_INSTRUCTIONS.md
sancho-workspace/DATASET_CATALOG.md
```

**Acceptance criteria:**

* Fetched data and logs are visible locally but not committed accidentally.
* `custom/**` and `playbooks/**` remain committable/shareable.

---

# Phase 2 — Add global visible-folder registration

## Ticket 2.1 — Add `sancho library register/show/open/repair`

**Goal:** Let users install Sancho globally while keeping modules in the visible `sancho-fetch` folder.

**Commands:**

```text
sancho library register .
sancho library show
sancho library open
sancho library repair
```

**Behavior:**

* `register .` stores a pointer to the visible repo/folder.
* The pointer can live in `~/.sancho/config.yaml`, but only as a pointer.
* Do not create a second hidden workspace.
* If the folder is moved, `sancho library repair` guides the agent/user to re-register.

**Config example:**

```yaml
primary_repo: "/Users/me/GitHub/sancho-fetch"
primary_workspace: "/Users/me/GitHub/sancho-fetch/sancho-workspace"
registered_at: "2026-05-10T..."
```

**Acceptance criteria:**

* From any folder, `sancho library show` displays the visible `sancho-fetch` folder.
* If no library is registered, Sancho says to open the `sancho-fetch` folder and run setup/register.
* Claude/Codex can call one command to find the canonical workspace.

---

## Ticket 2.2 — Add `sancho paths`

**Goal:** Give Claude/Codex maximum visibility with one command.

**Command:**

```text
sancho paths
sancho paths --json
```

**Output includes:**

```text
sancho-fetch root
Workspace
Source modules
Custom modules
Fetched data
Logs
Env file
Current project
Project copy target
Registered library status
Git status summary, if available
```

**Acceptance criteria:**

* `sancho paths --json` is machine-readable.
* Plain `sancho paths` is human-readable.
* Claude/Codex can use it before fetch, update, repair, or setup.

---

# Phase 3 — Add fetched-data cache/index/log foundation

## Ticket 3.1 — Implement source-shaped fetched-data layout

**Goal:** Store canonical data by data source and concrete request, not natural-language prompt.

**Example layout:**

```text
sancho-workspace/fetched-data/
  _catalog/
    fetched-data-index.md
    fetched-data-index.csv
    cache-index.jsonl
  census/
    acs_profile/
      2023/
        state/
          GA/
            variables-DP05_0001E-DP05_0079E/
              data.json
              data.csv
              request.yml
              provenance.yml
              content.sha256
              README.md
```

**Rules:**

* Natural language prompt never becomes the canonical cache key.
* Cache key is based on concrete resolved units:

  * provider/module
  * API endpoint
  * params
  * year
  * geography
  * variables
  * version
* Keep old fetched-data records append-only.

**Acceptance criteria:**

* A fetch writes canonical source-shaped folders.
* Every record has `request.yml`, `provenance.yml`, and `content.sha256`.
* Fetched-data index updates after each run.

---

## Ticket 3.2 — Add cache status command

**Goal:** Let Claude/Codex ask Sancho what is known without trusting an opaque “complete” flag.

**Command:**

```text
sancho cache status --module fetch.census.acs_profile --request-json '{"family":"example","params":{}}'
sancho cache status --module fetch.census.acs_profile --json
sancho cache list
sancho cache show <cache-record-id>
```

**Output statuses:**

```text
cached
missing
stale
partial
corrupt
unknown
empty_result
```

**Must include counts:**

```text
requested_units
cached_units
missing_units
stale_units
corrupt_units
empty_units
failed_units
```

**Acceptance criteria:**

* No command returns only `complete: true`.
* Claude gets enough detail to review what is actually missing.
* Partial cache hits are visible and explainable.

---

## Ticket 3.3 — Add visible logs

**Goal:** Make every fetch/update/repair/debug event available to Claude/Codex.

**Folder:**

```text
sancho-workspace/logs/
  README.md
  runs.jsonl
  fetches.jsonl
  cache-events.jsonl
  errors.jsonl
  repairs.jsonl
  latest.md
  errors/
```

**Commands:**

```text
sancho log path
sancho log tail
sancho log tail --errors
sancho log show <run-id>
sancho log search --module fetch.census.acs_profile
sancho log bundle <run-id>
```

**Log fields:**

```yaml
timestamp:
run_id:
event_type:
module_id:
module_path:
module_source: source|custom
workspace_path:
current_project_path:
request_summary:
cache_status:
files_written:
files_copied_to_project:
row_count:
status: success_with_data|success_empty|partial_success|failed|skipped_needs_key
error_message:
repair_packet_path:
sancho_version:
module_version:
```

**Acceptance criteria:**

* Failed fetches write an `errors/<run-id>_error.md` repair packet.
* API keys are never logged, only key names and present/missing status.
* Claude can run `sancho log tail --errors` and see useful debugging context.

---

# Phase 4 — Add project-copy/export behavior

## Ticket 4.1 — Add `sancho-fetched-data` project bundle output

**Goal:** When user invokes Sancho from another project, canonical data stays in the `sancho-fetch` workspace, and a project bundle is copied/exported to the working folder.

**Project layout:**

```text
Some Project/
  sancho-fetched-data/
    2026-05-10-black-population-notable-states/
      README.md
      manifest.yml
      data.csv
      data.parquet
      provenance.yml
      source-cache-links.yml
```

**Rules:**

* Canonical fetched data remains in `sancho-fetch/sancho-workspace/fetched-data`.
* Small/medium data is physically copied.
* Large data gets a pointer bundle by default:

  * README
  * manifest
  * sample rows
  * source links
  * export instructions

**Acceptance criteria:**

* Running from outside the `sancho-fetch` folder creates a project bundle.
* Bundle explains what was reused, fetched, skipped, and copied.
* Large-data behavior avoids filling user drives.

---

## Ticket 4.2 — Add `sancho export-to-project`

**Command:**

```text
sancho export-to-project --cache-record <id> --project . 
sancho export-to-project --run-id <run-id> --project .
```

**Acceptance criteria:**

* Claude can export an existing cached record without refetching.
* Export records provenance and source-cache links.
* Export does not mutate canonical fetched data.

---

# Phase 5 — Strengthen module discovery for agents

## Ticket 5.1 — Add `sancho module show/files/status`

**Goal:** Let Claude/Codex inspect modules without needing all provider tools loaded.

**Commands:**

```text
sancho inventory --json
sancho module show <module-id>
sancho module files <module-id>
sancho module status <module-id>
sancho module docs <module-id>
```

**Output should include:**

* module id
* type
* version
* source/custom path
* whether custom override is active
* entrypoint
* input schema
* examples
* catalog files
* audit/docs links
* last successful run
* last failed run

The current inventory and module contract already define module manifests and require fields like `id`, `version`, `type`, `entrypoint`, `managed_paths`, `extension_points`, and `dataset_refs`; use those as the base. 

**Acceptance criteria:**

* Claude can inspect `fetch.census.acs_profile` without reading the whole repo.
* `custom/**` override status is explicit.
* Output is available as both Markdown and JSON.

---

## Ticket 5.2 — Add `sancho find sources`

**Goal:** Give Claude/Codex a catalog search primitive, without pretending Sancho is the planner.

**Command:**

```text
sancho find sources "black population race census state ACS"
sancho find sources "everything about Panama" --json
```

**Behavior:**

* Search module manifests, descriptions, dataset refs, catalog metadata, provider docs links, and audit docs.
* Return ranked candidates with reasons.
* Do **not** decide the final plan.

**Acceptance criteria:**

* For “black population race census state ACS,” likely Census modules appear.
* For “Panama country profile economy health governance,” likely country-level modules appear.
* Output says “candidates,” not “selected plan.”

---

# Phase 6 — Fetch execution, failure packets, and soft validation

## Ticket 6.1 — Make Sancho validation safety-only by default

**Goal:** Avoid blocking correct live API usage just because Sancho’s schema/catalog is stale.

Current runtime calls `validate_schema(...)` before module execution.  Keep hard validation for local safety, but make provider/API shape validation soft unless the module explicitly requires it.

**Hard-block only:**

* unsafe paths
* missing workspace
* attempted writes outside allowed folders
* `.env` overwrite
* missing required local files
* corrupt cache records
* destructive update operations
* missing required API key when module cannot run without it

**Soft-warn:**

* unknown provider params
* new API fields
* new endpoint shapes
* new variables
* catalog mismatch

**Acceptance criteria:**

* Sancho can run a request with an unknown-but-user/AI-supplied provider parameter if the module supports pass-through params.
* Soft validation warnings are logged and returned.
* Hard validation still protects files and user data.

---

## Ticket 6.2 — Add repair packets for failed runs

**Goal:** Let Claude/Codex fix modules with maximum context.

**Error packet path:**

```text
sancho-workspace/logs/errors/<run-id>_error.md
```

**Packet contents:**

```text
What failed
Module id
Module path
Source/custom status
Entrypoint
Input payload
Resolved endpoint/URL if available
HTTP status if available
Provider response excerpt
Files written before failure
Cache status before/after
Last successful run
Known docs links
Suggested custom override path
Safe retry command
```

**Acceptance criteria:**

* Every failed fetch produces a repair packet.
* The packet tells Claude/Codex where to patch safely.
* Repair packets never contain API key values.

---

## Ticket 6.3 — Add `sancho repair note`

**Goal:** Record AI repairs durably.

**Command:**

```text
sancho repair note --run-id <run-id> --module <module-id> --summary "..."
```

**Writes:**

* `logs/repairs.jsonl`
* optional module-local `REPAIR_NOTES.md` in `custom/**` if a custom override was created

**Acceptance criteria:**

* A repaired module has a visible history.
* Update checks can show “custom override created because of repair.”

---

# Phase 7 — `/sancho fetch` skill and agent guidance

## Ticket 7.1 — Create Claude Code `/sancho` skill

**Path:**

```text
.claude/skills/sancho/SKILL.md
```

**Install target:**

```text
~/.claude/skills/sancho/SKILL.md
```

Claude docs support personal skills under `~/.claude/skills/<skill-name>/SKILL.md` for all projects and project skills under `.claude/skills/<skill-name>/SKILL.md`; arguments after the slash command are available via `$ARGUMENTS`. ([Claude API Docs][1])

**Skill behavior:**

* `/sancho fetch <natural language request>` treats everything after `fetch` as natural language.
* Claude does the reasoning.
* Sancho provides paths, inventory, module search, cache status, execution, logs, and project export.
* Claude must not claim completion until it reviews non-opaque result counts.

**Required skill flow:**

```text
1. Run sancho paths.
2. Run sancho inventory or sancho find sources.
3. Inspect candidate modules.
4. Decide concrete fetch units.
5. Run sancho cache status.
6. Fetch only missing/stale units, unless user asked refresh.
7. Export/copy project bundle.
8. Read logs/result manifest.
9. Summarize reused/fetched/skipped/failed units.
```

**Acceptance criteria:**

* `/sancho fetch black population in a few notable states` works as a natural-language task.
* `/sancho fetch everything about Panama` creates a bounded starter plan, not an infinite fetch.
* The final response includes assumptions and statuses.

---

## Ticket 7.2 — Create Codex skill

**Path:**

```text
.agents/skills/sancho/SKILL.md
```

Codex skills are directories with required `SKILL.md` files and optional scripts/references; Codex can activate them explicitly or implicitly and reads repository/user/admin/system skill locations. ([OpenAI Developers][2])

**Acceptance criteria:**

* Codex can use the same workflow as Claude Code.
* Skill includes references to `AGENTS.md`, `sancho paths`, logs, and repair packets.

---

## Ticket 7.3 — Add `CLAUDE.md` and `AGENTS.md`

**Goal:** Make the repo self-explaining when opened by Claude Code or Codex.

**Must include:**

* User is often nontechnical.
* Check Python 3.11+, `uv`, and Node only if needed.
* Respect `SANCHO_DEVELOPER_MODE`.
* Do not overwhelm user with commands unless developer mode is true.
* Use `sancho paths`.
* Use `sancho inventory` / `sancho find sources`.
* Keep custom work in `custom/**`.
* Do not edit `fetched-data/**`.
* Do not edit `.env` except to help the user open it.
* Read logs before claiming success.
* For repairs, prefer `custom/**` overrides.
* For updates, use `/sancho update` / `sancho update check`, not raw `git pull`, unless contributor mode.

Codex docs explicitly describe `AGENTS.md` as the project instruction mechanism Codex reads before work. ([OpenAI Developers][3])

**Acceptance criteria:**

* Opening repo in Claude/Codex gives the agent enough instructions to set up, fetch, repair, and update safely.
* Docs are concise enough not to crowd context.

---

# Phase 8 — Update engine

## Ticket 8.1 — Add release/module manifest generation

**Goal:** Use GitHub/release files as source of truth without hosting a server.

**Generated file:**

```text
sancho-release-manifest.json
```

**Fields:**

```json
{
  "sancho_version": "0.4.0",
  "workspace_schema_version": 2,
  "generated_at": "...",
  "modules": {
    "fetch.census.acs_profile": {
      "version": "0.2.3",
      "sha": "...",
      "paths": ["source/fetch/fetch.census.acs_profile"],
      "summary": "Updated Census variable discovery"
    }
  }
}
```

**Source options:**

* GitHub release asset
* raw GitHub file
* package-included manifest

**Acceptance criteria:**

* `sancho update check` can compare local modules against public GitHub/release metadata.
* No custom server required.

---

## Ticket 8.2 — Implement `sancho update check`

**Goal:** Give Claude/user a non-destructive status report.

**Command:**

```text
sancho update check
sancho update check --json
```

**Checks:**

* Sancho CLI version
* workspace schema version
* module versions
* module checksums
* managed source local edits
* custom overrides
* fetched-data records created by old module versions
* `.env` existence
* whether generated folders are gitignored
* whether this is a Git clone and whether it is dirty

Existing docs already define `sancho update` as preview-only and `sancho update --accept` as managed-path-only; this ticket makes that user-friendly and machine-readable. 

**Acceptance criteria:**

* Output is grouped by module, not by individual file first.
* Output explicitly says personal/generated paths will not be touched.
* JSON output supports the update skill.

---

## Ticket 8.3 — Implement `sancho update preview`

**Goal:** Show what would change before applying.

**Command:**

```text
sancho update preview
sancho update preview fetch.census.acs_profile
sancho update preview --json
```

**Preview fields:**

```yaml
module_id:
installed_version:
available_version:
status: current|update_available|review_needed|custom_override_active
files_to_replace:
files_with_local_edits:
personal_paths_touched: []
risk_level:
human_summary:
recommended_action:
```

**Acceptance criteria:**

* Preview refuses to hide local managed edits.
* Preview never includes personal/generated paths as replacement targets.
* Preview can be summarized by Claude in plain English.

---

## Ticket 8.4 — Implement `sancho update apply`

**Goal:** Apply safe managed updates only.

**Command:**

```text
sancho update apply
sancho update apply fetch.census.acs_profile
sancho update apply --safe
```

**Behavior:**

1. Recompute preview.
2. Create backup.
3. Refuse if personal/generated paths would be touched.
4. Refuse if managed source has local edits unless explicitly allowed.
5. Replace selected managed source paths.
6. Update `modules.lock.yaml`.
7. Write update log.
8. Run `sancho doctor --updates`.

**Acceptance criteria:**

* Update cannot touch `custom/**`, `playbooks/**`, `fetched-data/**`, `logs/**`, `.env`, `AI_INSTRUCTIONS.md`, `DATASET_CATALOG.md`, or project folders.
* Update result includes backup id.
* Update result includes rollback command.

---

## Ticket 8.5 — Add update backups and rollback

**Folder:**

```text
sancho-workspace/update-backups/
  2026-05-10-update-001/
    source-before/
    modules.lock.before.yaml
    update-preview.md
    update-result.md
```

**Command:**

```text
sancho update rollback <backup-id>
```

**Acceptance criteria:**

* Rollback restores managed files only.
* Rollback does not touch personal/generated files.
* Rollback writes a log entry.

---

## Ticket 8.6 — Add custom override status and retirement

**Commands:**

```text
sancho custom status
sancho module compare <module-id>
sancho custom retire <module-id>
```

**Behavior:**

* Detect custom modules that shadow source modules.
* Detect when upstream source version is newer than the local custom override.
* `retire` moves custom module to `_retired/`, never deletes.

**Acceptance criteria:**

* If user fixed `fetch.zillow` in `custom/**`, update does not overwrite it.
* If upstream later includes the fix, Sancho can show “official source now updated; compare or retire custom.”
* Retired custom modules are recoverable.

---

## Ticket 8.7 — Add old-module provenance audit

**Command:**

```text
sancho fetched-data audit --old-modules
```

**Goal:** Show which data was fetched with old module versions.

**Acceptance criteria:**

* Every fetched-data record stores:

  * Sancho CLI version
  * module id
  * module version
  * module source: source/custom
  * module path
  * content hash
  * retrieved timestamp
* Audit reports old records without marking them invalid automatically.

---

# Phase 9 — `/sancho update` skill

## Ticket 9.1 — Create Claude Code update skill

**Path:**

```text
.claude/skills/sancho-update/SKILL.md
```

**Invocation examples:**

```text
/sancho-update
/sancho update
Check if Sancho is behind and help me update safely.
```

**Skill flow:**

```text
1. Run sancho paths.
2. Run sancho update check --json.
3. Run sancho update preview --json.
4. Run git status only for context.
5. If managed files have local edits:
   - inspect changed files
   - explain risk
   - offer to move edits to custom override
6. If updates are safe:
   - explain module-level changes
   - ask before apply unless user explicitly asked for safe apply
7. Run sancho update apply --safe.
8. Run sancho doctor --updates.
9. Summarize updated modules, skipped modules, custom overrides, and backup id.
```

**Why skill:** This is exactly where Claude should use grep/read/diff and make judgments. Sancho should provide facts; Claude should reason about whether a user changed a module meaningfully.

**Acceptance criteria:**

* User does not need to run `git pull`.
* Claude explains updates in module-level language.
* Skill never runs destructive Git commands.
* Skill never edits `fetched-data`, `.env`, or `custom` unless migrating a managed edit into a custom override with user approval.

---

## Ticket 9.2 — Create Codex update skill

**Path:**

```text
.agents/skills/sancho-update/SKILL.md
```

**Acceptance criteria:**

* Same update logic as Claude skill.
* Uses `AGENTS.md` as repo-level instruction source.
* Works in a Git clone and in a downloaded ZIP folder.

---

# Phase 10 — MCP surface refinement

## Ticket 10.1 — Add high-level MCP tools for agents

**Goal:** Make Sancho usable through MCP without exposing 131 provider tools as the primary UX.

Current codebase has local CLI and MCP support, and docs position MCP as a first-class supported surface for AI clients.  MCP itself is designed to connect AI applications like Claude or ChatGPT to external systems, tools, data sources, and workflows. ([Claude API Docs][4])

**Expose high-level tools:**

```text
sancho_paths
sancho_inventory
sancho_find_sources
sancho_module_show
sancho_cache_status
sancho_fetch_run
sancho_export_to_project
sancho_log_tail
sancho_log_show
sancho_env_open
sancho_update_check
sancho_update_preview
sancho_custom_status
```

**Acceptance criteria:**

* Claude Desktop can ask Sancho for module/search/cache/update info.
* Provider-specific tools can remain available, but are not the main user mental model.
* Hosted MCP remains limited and does not pretend to support local cache/workspace behavior.

---

# Phase 11 — Env and setup polish

## Ticket 11.1 — Add `sancho env open/check`

**Commands:**

```text
sancho env open
sancho env open zillow
sancho env check
```

**Behavior:**

* Opens `sancho-workspace/.env` in default editor.
* If provider passed, show exact key names required.
* Never prints secret values.

**Acceptance criteria:**

* Claude can say “I opened your Sancho key file.”
* User never needs shell `export`/`setx` for normal use.

---

## Ticket 11.2 — Add setup command and installer scripts

**Commands/files:**

```text
sancho setup
installers/Install Sancho.command
installers/Install Sancho.bat
installers/setup.sh
installers/setup.bat
```

**Checks:**

* Python 3.11+
* `uv`
* Node 18+ only when npm/npx/JS helper path is used
* Claude Code skill install
* Codex skill install
* MCP config where applicable
* library registration
* no-key smoke test

Current README already tells agents to check Python, `uv`, and use the repo through AI coding agents; extend that into an executable setup flow. 

**Acceptance criteria:**

* Nontechnical user can open folder and say “set this up.”
* Setup registers the visible `sancho-fetch` folder.
* Setup installs global skills where possible.
* Setup runs a no-key smoke test.

---

# Phase 12 — Tests

## Ticket 12.1 — Workspace contract tests

**Test cases:**

* `sancho setup` creates new tree.
* `sancho doctor --fix --json` repairs missing `fetched-data`, `logs`, `outputs`.
* Old `data/raw` is not created for new workspaces.
* Protected/generated paths are not overwritten.

---

## Ticket 12.2 — Cache/index tests

**Test cases:**

* cache miss writes source-shaped fetched-data record.
* cache hit does not refetch.
* partial coverage reports missing units.
* corrupted hash reports `corrupt`.
* empty result reports `success_empty`, not `success_with_data`.

---

## Ticket 12.3 — Project export tests

**Test cases:**

* small dataset copies fully to `sancho-fetched-data`.
* large dataset creates pointer bundle.
* manifest includes source-cache links and assumptions.
* export does not mutate canonical fetched-data.

---

## Ticket 12.4 — Logging and repair packet tests

**Test cases:**

* successful run writes `runs.jsonl` and `fetches.jsonl`.
* failed run writes `errors.jsonl` and repair packet.
* logs do not contain API key values.
* `sancho log tail --errors` works cross-platform.

---

## Ticket 12.5 — Update safety tests

The current repo already treats update safety as a required high-signal test category.  Expand it.

**Test cases:**

* `update check` is non-mutating.
* `update preview` is non-mutating.
* `update apply --safe` only touches managed paths.
* update refuses when local managed edits exist.
* custom modules are never overwritten.
* fetched-data/logs/.env are never touched.
* backup is created.
* rollback restores only managed files.
* custom override status detects shadowing.

---

## Ticket 12.6 — Skill fixture tests

**Goal:** The skills are product code. Test them lightly.

**Test cases:**

* `SKILL.md` files exist.
* Claude skill has `$ARGUMENTS`.
* Update skill tells agent not to run destructive Git commands.
* Codex skill has required `name` and `description`.
* `AGENTS.md` includes update/fetch/repair rules.

---

# Phase 13 — Docs and developer handoff

## Ticket 13.1 — Update README.md

**Must explain:**

* “You do not need to be a coder.”
* “Your `sancho-fetch` folder is your local data library.”
* “Fetched data lives in `fetched-data/`.”
* “Do not edit fetched-data directly.”
* “Use `/sancho fetch ...`.”
* “Use `/sancho update`.”
* “GitHub account optional, helpful for contributing.”

---

## Ticket 13.2 — Update README_ALL_INSTRUCTIONS.md for AI assistants

**Must explain:**

* Claude/Codex does reasoning.
* Sancho provides tools, paths, modules, cache, logs, updates.
* Never claim completion without checking logs/result counts.
* For broad requests, fetch bounded starter bundles.
* For ambiguous requests, make assumptions visible.
* For repair, prefer `custom/**`.
* For updates, use Sancho update flow instead of raw `git pull`.

---

## Ticket 13.3 — Update MODULE_CREATION_GUIDE

**Must explain:**

* Custom modules live in `custom/**`.
* Source modules live in `source/**`.
* Custom wins at runtime.
* User/Claude repairs should usually create a custom override.
* How to contribute custom fix upstream.
* What happens after upstream merge.
* How to retire a custom override.

---

## Ticket 13.4 — Update hosted MCP docs

**Must clarify:**

* Hosted MCP is demo/classroom/sampler.
* Hosted MCP has no local cache.
* Hosted MCP cannot access user’s `sancho-fetch` folder.
* Full product requires local install.

This aligns with the existing hosted README, which already says hosted MCP is stripped down and intended to nudge users toward local install. 

---

# Phase 14 — Final folder move

## Ticket 14.1 — Copy current folder into final `sancho-fetch` folder

**Timing:** Last step, after implementation and tests.

**User requirement:** After these changes, copy/paste everything from the current folder into a new repo folder called **sancho-fetch**.

**Steps:**

1. Ensure all docs/code refer to Sancho/Sancho Fetch.
2. Ensure new workspace contract is implemented.
3. Ensure tests pass.
4. Copy current project into final folder:

```text
sancho-fetch/
```
and you 
5. Run setup/init/doctor from the new folder.
6. Register the new visible library:

```text
sancho library register .
```

7. Run smoke test.
8. Confirm global skill points to the new `sancho-fetch` folder.

**Acceptance criteria:**

* No references to the old folder path remain in config.
* `sancho paths` points to `sancho-fetch`.
* `/sancho fetch ...` works from another folder.
* `/sancho update` checks the new folder.

---

# Recommended implementation order

I would not start with update logic. I’d start with the visible folder contract and logs, because every later feature depends on paths and provenance.

1. **Workspace rename/tree:** `fetched-data`, `logs`, `outputs`, protected paths.
2. **`sancho paths` + library registration:** make agents location-aware.
3. **Logging:** runs/errors/repair packets.
4. **Fetched-data cache/index:** source-shaped canonical records.
5. **Project export/copy:** current-folder bundles.
6. **Module discovery commands:** `find sources`, `module show`, `module files`.
7. **Fetch skill:** `/sancho fetch`.
8. **Update engine:** check/preview/apply/backup/rollback.
9. **Update skill:** `/sancho update`.
10. **Setup/env polish.**
11. **Docs/tests.**
12. **Final move to `sancho-fetch`.**

---

# One implementation principle to give the developer

Do not make Sancho “smart” in places where Claude/Codex should reason.

Sancho should say:

```text
Here are the modules.
Here are the paths.
Here is the cache status.
Here are the exact records found/missing/stale.
Here is what I ran.
Here are the files written.
Here are the logs.
Here are the update candidates.
Here are the changed managed files.
```

Claude/Codex should say:

```text
This request means Census ACS.
These states are the right interpretation of “notable.”
This cache satisfies two parts but not the third.
This managed edit should become a custom override.
This update is safe to apply.
This failure needs a docs check and module repair.
```

That is the clean architecture: **Sancho is the durable local toolbelt; Claude/Codex is the reasoning operator.**

[1]: https://docs.anthropic.com/en/docs/claude-code/slash-commands "Extend Claude with skills - Claude Code Docs"
[2]: https://developers.openai.com/codex/skills "Agent Skills – Codex | OpenAI Developers"
[3]: https://developers.openai.com/codex/guides/agents-md "Custom instructions with AGENTS.md – Codex | OpenAI Developers"
[4]: https://docs.anthropic.com/en/docs/agents-and-tools/mcp "What is the Model Context Protocol (MCP)? - Model Context Protocol"


