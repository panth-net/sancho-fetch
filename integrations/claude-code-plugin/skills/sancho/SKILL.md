---
name: sancho
description: Fetch public data through an existing Sancho Fetch CLI. Use for natural-language data requests and /sancho-fetch:sancho.
---

# Sancho Fetch

This plugin requires `sancho` 0.3.x on PATH. If `sancho mode --json` cannot
run, explain the prerequisite and, when terminal access is available, run:

```bash
uv tool install sancho-fetch==0.3.0
sancho setup
```

Then use this flow:

1. Run `sancho mode --json` and use plain English unless developer mode is on.
2. Run `sancho paths --json`; relay any `update_hint` before continuing.
3. Run `sancho env recommend "$ARGUMENTS" --json`. Never read or print `.env`;
   use `sancho env open` for a user who needs to add a named key.
4. Run `sancho find sources "$ARGUMENTS" --json`, then inspect real candidates
   with `sancho module show <id> --json`. Never guess IDs or fields.
5. Resolve coded variables with `sancho module variables`; fetch a broader safe
   slice if the exact code remains uncertain.
6. Run `sancho run <id> --workspace <workspace> --input <input.json>`.
7. Confirm `status`, `cache_status`, and `row_count`. For failures, read the
   referenced repair packet before proposing a `custom/**` override.
8. Report per-unit fetched/reused/skipped/failed counts and only the primary
   working file/folder under `sancho-downloads/` by default.

Hard rules: never edit `fetched-data/**` or `source/**`; never expose `.env`;
never invent identifiers; never use raw Git to update managed content.
