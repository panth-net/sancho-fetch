---
name: sancho-update
description: Sancho Fetch update -- check, preview, apply, and roll back managed updates without raw Git commands.
---

# Sancho Fetch update skill

You are operating the Sancho update flow. Sancho provides deterministic
check, preview, apply, and rollback primitives. The agent explains changes,
preserves user work, and migrates deliberate managed-file edits into
`custom/<type>/<module>/` before applying upstream updates.

Read `CLAUDE.md` or `AGENTS.md` before doing anything. Sancho never requires
raw Git commands. How new versions arrive depends on
`package.install_source` from `sancho update check`:

- `"package"` (the normal case -- installed from PyPI): you run
  `uv tool upgrade sancho-fetch`, which pulls the newest release. No
  folder, no Git, nothing for the user to download.
- `"checkout"` (developers working from the repository): the user pulls new
  commits with GitHub Desktop, then you reinstall the `sancho` command from
  that checkout when `update check` says so.

Either way, `sancho update apply` migrates the workspace afterwards.

## Required Flow

1. Check mode before replying with `sancho mode --json`. If the command is
   missing or fails during first setup, default to developer mode off and use
   plain English. Do not open or read `.env` just to determine mode.
2. Run `sancho paths --json` to confirm the active workspace. If the payload
   contains `update_hint`, relay it to the user in one plain sentence before
   continuing. If the `sancho` command is missing, fails, or lacks current
   commands such as `setup`, `paths`, `ready`, or `mode`, and terminal access
   is available, do the setup work yourself: run
   `uv tool install sancho-fetch`, then
   `sancho setup --path <the folder the user is working in> --install-claude-desktop --json`.
   (Working from a source checkout instead? Run `installers\setup.bat` on
   Windows or `bash installers/setup.sh` on macOS/Linux from the repo root.)
   Then run `sancho ready --json` and retry `sancho paths --json`. If
   `workspace_source == "none"`, run setup or
   `sancho library register <path-to-workspace-folder>` yourself. Only ask the
   user for help when the OS blocks execution, permissions fail, or an
   installer window requires human approval.
3. Run `sancho update check --workspace <ws> --json`. Read every relevant
   field: `package.install_source`, `package.reinstall_needed`,
   `modules[].status`, `files_with_local_edits`, `custom_override_active`,
   `env_present`, `gitignore_covers_generated`, `is_git_repo`, `git_dirty`,
   and `personal_paths_touched_by_update`.
4. If `package.reinstall_needed` is true, the installed `sancho` command is
   out of date. Run the exact `package.reinstall_command` yourself -- for
   `install_source == "package"` that is `uv tool upgrade sancho-fetch`; for
   `"checkout"` it is an `uv tool install --force ...` on the checkout path.
   Then re-run `sancho update check` and continue with the fresh output.
5. Run `sancho update preview --workspace <ws> --json` before any apply. For a
   single module, pass the module ID after `preview`. Inspect `risk_level`,
   `recommended_action`, `files_to_replace`, `files_with_local_edits`, and
   `personal_paths_touched`.
6. Optionally run `git status` for read-only context. Never run `git pull`,
   `git fetch`, `git reset`, `git clean`, `git checkout --`, force-push, or any
   destructive Git command.
7. For each module with `files_with_local_edits`, inspect the edited files. If
   the edit looks intentional, propose moving it into `custom/<type>/<module>/`
   before applying and record that with `sancho repair note --module <id>
   --summary "Migrated <file> into custom override before update"`. If it looks
   accidental, ask the user before discarding it.
8. Explain what will change in module-level language. Include updated modules,
   skipped modules, local edits, active custom overrides, and any risk.
9. Ask before applying unless the user explicitly requested a safe apply.
10. Run `sancho update apply --workspace <ws> --json`. Use
   `--allow-local-edits` only when the user approved. Record `backup_id`,
   `backup_dir`, applied/skipped modules, changed paths, and
   `rollback_command`.
11. Run `sancho doctor --workspace <ws> --json` after apply.
12. Read `logs/update-log.jsonl` and
    `update-backups/<backup_id>/update-result.md` before claiming success.
13. Summarize updated, skipped, and preserved items. Include the rollback
    command.

## Hard Rules

- Never run destructive Git commands. No `git pull`, `git reset --hard`,
  `git clean -fd`, `git checkout --`, or force-push.
- Never open, read, or edit `.env` directly unless helping the user edit keys
  with `sancho env open`. Updates never touch `.env`; if one ever would,
  stop and report it as a bug. Use `sancho mode --json` for mode. Never edit
  `fetched-data/**`, `logs/**`, or `custom/**` except when explicitly
  migrating a managed edit into a custom override with user approval.
- Never call `sancho update apply` without first running
  `sancho update preview`.
- Never claim "updated" without inspecting the result files and update log.
- If `personal_paths_touched` is non-empty, stop and report it as a bug. The
  safe update path should not touch personal/generated files.

## Rollback

If apply goes wrong, use the recorded rollback command:
`sancho update rollback <backup-id> --workspace <ws>`. Then rerun
`sancho doctor --workspace <ws>` and report the restored state.

`$ARGUMENTS` may contain a module filter such as `fetch.census.acs_profile`.
Pass that filter through to `sancho update preview` and `sancho update apply`.
