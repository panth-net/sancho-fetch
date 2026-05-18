---
name: sancho-update
description: Sancho Fetch update -- check, preview, apply, and roll back managed updates without raw Git commands.
---

# Sancho Fetch update skill

You are operating the Sancho update flow. Sancho provides deterministic
check, preview, apply, and rollback primitives. The agent explains changes,
preserves user work, and migrates deliberate managed-file edits into
`custom/<type>/<module>/` before applying upstream updates.

Read `CLAUDE.md` or `AGENTS.md` before doing anything. This works in both a Git
clone and a downloaded ZIP folder; Sancho does not require Git for updates.

## Required Flow

1. Check mode before replying with `sancho mode --json`. If the command is
   missing or fails during first setup, default to developer mode off and use
   plain English. Do not open or read `.env` just to determine mode.
2. Run `sancho paths --json` to confirm the active workspace. If the `sancho`
   command is missing or setup is incomplete and terminal access is available,
   do the setup work yourself from the repo root: run `installers\setup.bat` on Windows, run
   `bash installers/setup.sh` on macOS/Linux, or use
   `uv run sancho setup --path . --install-claude-desktop --json` from this
   checkout if the installed CLI is unavailable. Then run `sancho ready --json`
   and retry `sancho paths --json`. If `workspace_source == "none"`, run setup
   or `sancho library register <path-to-sancho-fetch>` yourself. Only ask the
   user for help when the OS blocks execution, permissions fail, or an
   installer window requires human approval.
3. Run `sancho update check --workspace <ws> --json`. Read every relevant
   field: `modules[].status`, `files_with_local_edits`,
   `custom_override_active`, `env_present`, `gitignore_covers_generated`,
   `is_git_repo`, `git_dirty`, and `personal_paths_touched_by_update`.
4. Run `sancho update preview --workspace <ws> --json` before any apply. For a
   single module, pass the module ID after `preview`. Inspect `risk_level`,
   `recommended_action`, `files_to_replace`, `files_with_local_edits`, and
   `personal_paths_touched`.
5. Optionally run `git status` for read-only context. Never run `git pull`,
   `git fetch`, `git reset`, `git clean`, `git checkout --`, force-push, or any
   destructive Git command.
6. For each module with `files_with_local_edits`, inspect the edited files. If
   the edit looks intentional, propose moving it into `custom/<type>/<module>/`
   before applying and record that with `sancho repair note --module <id>
   --summary "Migrated <file> into custom override before update"`. If it looks
   accidental, ask the user before discarding it.
7. Explain what will change in module-level language. Include updated modules,
   skipped modules, local edits, active custom overrides, and any risk.
8. Ask before applying unless the user explicitly requested a safe apply.
9. Run `sancho update apply --workspace <ws> --json`. Use
   `--allow-local-edits` only when the user approved. Record `backup_id`,
   `backup_dir`, applied/skipped modules, changed paths, and
   `rollback_command`.
10. Run `sancho doctor --workspace <ws> --json` after apply.
11. Read `logs/update-log.jsonl` and
    `update-backups/<backup_id>/update-result.md` before claiming success.
12. Summarize updated, skipped, and preserved items. Include the rollback
    command.

## Hard Rules

- Never run destructive Git commands. No `git pull`, `git reset --hard`,
  `git clean -fd`, `git checkout --`, or force-push.
- Never open, read, or edit `.env` directly unless helping the user edit keys
  with `sancho env open`. Use `sancho mode --json` for mode. Never edit
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
