# Sancho Fetch Quick Start

This project is **Sancho Fetch**: a local-first toolkit for fetching public
data into a visible folder on your computer, organizing reusable workflows,
and building analysis/dashboard outputs that persist as files.

If you are a person getting started from GitHub, read this file first.

If you are an AI assistant, **do not use this short quick start as your
operating instructions**. Read [`README_ALL_INSTRUCTIONS.md`](README_ALL_INSTRUCTIONS.md)
first, then follow [`AGENTS.md`](AGENTS.md) or [`CLAUDE.md`](CLAUDE.md)
as appropriate for your environment.

## You do not need to be a coder

Sancho is driven by your local AI assistant (Claude Code, Codex, Cursor,
VS Code, or Claude Desktop). You ask in plain English; the AI runs the Sancho commands.
Sancho gives the AI safe, boring, inspectable facts -- paths, manifests,
cache status, logs -- and the AI decides what to fetch and explains the
result.

By default the AI talks back in plain language. No commands, no jargon, no
code dumps. If you want technical detail, flip one switch:

1. Open `.env` in your workspace (any text editor; install [VS Code](https://code.visualstudio.com/) if needed).
2. Find `SANCHO_DEVELOPER_MODE=false`.
3. Change to `true` and save.

If your AI ignores this setting, tell it to read
[`README_ALL_INSTRUCTIONS.md`](README_ALL_INSTRUCTIONS.md) and
`AI_INSTRUCTIONS.md`, then respect `SANCHO_DEVELOPER_MODE`.
The AI should check this safely with `sancho mode --json`; it does not need
to open or read your `.env` file to learn the mode.

## Your `sancho-fetch` folder is your local data library

After setup, your computer has one visible repo folder called `sancho-fetch`
that contains everything Sancho touches:

```text
sancho-fetch/
  installers/       # double-click installers
  sancho-workspace/
    source/          # managed modules (updated by sancho update)
    custom/          # your own modules and overrides
    playbooks/       # your repeatable workflows
    fetched-data/    # canonical fetched source data (read-only by convention)
    analysis-data/   # your derived work
    outputs/         # reports, dashboards, exports
    logs/            # what Sancho did, when, and why
    update-backups/  # snapshots before every update
    .env             # your API keys (never logged, never printed)
```

You should be able to open this folder in Finder/Explorer and recognize
what's inside. Sancho keeps the library visible; OS dotfiles like `.env`
may still be hidden by Finder/File Explorer until you turn on hidden files.

## Fetched data lives in `fetched-data/`

Every time Sancho pulls data, it lands in
`sancho-workspace/fetched-data/<module>/<family>/<request-key>/<timestamp>/`
with five files per record:

- `data.json` -- the actual payload
- `request.yml` -- the exact request that produced it
- `provenance.yml` -- when, by which module version, content hash
- `content.sha256` -- integrity check
- `README.md` -- plain-language explanation

A `_catalog/` folder at the root keeps a running index (`cache-index.jsonl`
+ `fetched-data-index.md` + `.csv`) you can read directly.

**Do not edit `fetched-data/` directly.** It's append-only by convention --
new fetches add new timestamped folders, old records stay put so you can
always reproduce what happened.

## Ask for data, or use the Sancho skills directly

If you're driving Sancho through Claude Code, setup installs personal skills
that Claude exposes as slash commands:

- **`/sancho <plain English>`** -- describe what data you want; the
  AI runs `sancho find sources`, picks modules, checks cache, fetches only
  what's missing, drops a bundle in your project folder, and tells you
  what was reused / fetched / skipped / failed.
- **`/sancho-update`** -- checks for module updates, previews what would
  change, asks before applying, creates a backup, and never runs `git
  pull`. Your custom edits are preserved.

In Codex, the same installed skills are available as agent skills. You can
name Sancho directly or just ask in plain English, such as "get Census and
housing data for Kent County." The skill tells Codex how to find sources,
check cache, fetch data, read logs, and summarize counts.

In Claude Desktop, Cursor, or VS Code, Sancho uses local MCP tools instead
of slash commands. The installer writes MCP config snippets into
`sancho-workspace/mcp/`; your AI can help install the snippet for any
client that was not installed automatically.

For Claude Desktop specifically, the double-click installer tries to add
Sancho to your Claude Desktop config automatically where the OS supports
it. If setup says the config was installed, fully restart Claude Desktop.
If setup says it could not install that config, run
`sancho mcp config --client claude-desktop --workspace . --install` from
the `sancho-fetch` folder, or use the ready-to-copy snippet at
`sancho-workspace/mcp/claude-desktop.mcp.json`.

Once installed, Sancho is registered as your computer-wide local data
library. You can ask from another project folder and the AI can still find
the same `sancho-fetch` workspace.

## Install in one step

Download the GitHub ZIP, unzip/extract it, and move the `sancho-fetch`
folder where you want to keep it before installing. The installer stores a
user-level `sancho` command plus a pointer back to this visible folder; it
does not install a second hidden library at `C:\` or another root folder.
If you move `sancho-fetch` later, re-run the installer so Claude/Codex point
at the new location.

Double-click `installers/Install Sancho.command` (macOS) /
`installers/Install Sancho.bat` (Windows), or run `bash installers/setup.sh`
on Linux. It installs `uv` if missing, lets `uv` choose or download a Python
that satisfies Sancho's `>=3.11` requirement, installs Sancho, creates the
workspace, registers the visible folder as your library, copies the
Claude/Codex skills, writes desktop MCP config snippets, installs the Claude
Desktop config when possible, and installs a built-in sample module as a
setup check.

On macOS, if the `.command` file will not open, right-click it and choose
**Open**. If macOS says it is not executable, run
`chmod +x installers/Install\ Sancho.command` once from the `sancho-fetch`
folder, then open it again.

On macOS, if Finder blocks the downloaded `.command` file, right-click it and
choose **Open**, or open Terminal in `sancho-fetch` and run
`bash installers/setup.sh`.

Developer shortcut from this folder:

```bash
uv tool install .
sancho setup --install-claude-desktop
```

## GitHub is optional

You do not need a GitHub account to use Sancho. Sancho Fetch is just files
on your machine. GitHub is only helpful if you want to:

- Share `custom/` modules or playbooks with teammates.
- Contribute improvements back to the upstream Sancho project.

Even if you have Git installed, Sancho updates via its own safe machinery
(`sancho update check / preview / apply / rollback`), never via raw `git
pull`.

## Managed vs personal -- what `sancho update` touches

When you run `sancho update apply`, Sancho **only** rewrites files under
`source/**` and `modules.lock.yaml`. These are explicitly off-limits:

- `custom/**` -- your overrides win at runtime; never overwritten.
- `playbooks/**` -- your workflows.
- `fetched-data/**`, `analysis-data/**`, `outputs/**`, `logs/**` -- your data.
- `update-backups/**` -- Sancho's safety net.
- `.env` -- your secrets.
- `AI_INSTRUCTIONS.md`, `DATASET_CATALOG.md` -- your notes.

Every update writes a snapshot to `update-backups/<date>-update-NNN/` and
prints a rollback command in case anything goes wrong.

## API keys

Some providers are zero-key (World Bank, USGS, openFDA, ...); others need
free credentials. Sancho never prints or logs values -- only key names.

The easiest path:

1. Tell your AI assistant what data you want, e.g. *"I want housing
   affordability data."*
2. The AI runs `sancho env recommend "<your request>"` and tells you, in
   plain English, which providers handle it, which need a free key, and
   where to sign up. Sign-up URLs and per-key form-field hints come from
   the safe recommendation payload, not from opening your real `.env`.
3. **Don't share the key with the AI.** Paste it straight into `.env`
   yourself. Sancho reads only env-var names, never values.
4. Tell the AI you saved the file. It re-checks and continues.

### Finding `.env` if it looks hidden

Filenames that start with `.` (like `.env` and `.env.example`) are
hidden by default on macOS and Windows. If you can't see them in your
file manager:

- **macOS Finder:** open the Sancho Fetch folder, then press
  `Cmd+Shift+.` (Command + Shift + period) to toggle hidden files.
- **Windows File Explorer:** click **View -> Show -> Hidden items**.
- Or run `sancho env open` to open the right `.env` directly from your editor.

Sancho checks the project-level `.env` as a fallback and lets
`sancho-workspace/.env` override matching names when both files exist.

`.env` is personal and never overwritten by `sancho update`.

## Where to read next

1. [`README_ALL_INSTRUCTIONS.md`](README_ALL_INSTRUCTIONS.md) -- full operator/AI reference.
2. [`CLAUDE.md`](CLAUDE.md) and [`AGENTS.md`](AGENTS.md) -- the rules your
   AI assistant should follow when working in this repo.
3. [`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md) --
   MCP setup for desktop and web AI clients.
4. [`project-docs/MODULE_CREATION_GUIDE.md`](project-docs/MODULE_CREATION_GUIDE.md) --
   module creation workflow for AI agents.
5. [`hosting/README.md`](hosting/README.md) -- only if you want to run a
   public hosted demo endpoint (not the main product).

## License

Sancho Fetch is public-source software under a fair-use community license. You can read it, use it, modify it, and build with it. If Sancho Fetch materially helps fetch or prepare data you share, cite it. Commercial use is free below the community threshold. Larger organizations, white-labeling, hosted resale, and products whose value derives primarily from Sancho Fetch require a paid license.

See [LICENSE](./LICENSE) for full terms.
