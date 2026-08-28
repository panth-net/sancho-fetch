---
name: sancho-update
description: Safely check, preview, apply, and roll back Sancho Fetch managed updates through /sancho-fetch:sancho-update.
---

# Sancho Fetch update

This plugin requires `sancho` 0.3.x on PATH. If it is absent, explain that the
plugin connects to an existing CLI and run `uv tool install sancho-fetch==0.3.0`
plus `sancho setup` when terminal access is available.

1. Run `sancho mode --json` and `sancho paths --json`.
2. Run `sancho update check --workspace <workspace> --json`.
3. If the returned package reinstall command is required, run that exact safe
   command and repeat the check.
4. Run `sancho update preview --workspace <workspace> --json` and explain local
   edits, custom overrides, risk, and personal paths before applying.
5. Never use raw Git commands to update managed Sancho content.
6. Apply only after approval or an explicit safe-apply request with
   `sancho update apply --workspace <workspace> --json`.
7. Run `sancho doctor --workspace <workspace> --json`, inspect the update log,
   and report applied/skipped/preserved counts plus the rollback command.

Never edit `.env`, `fetched-data/**`, logs, or personal overrides as part of an
update. If `personal_paths_touched` is non-empty, stop and report a bug.
