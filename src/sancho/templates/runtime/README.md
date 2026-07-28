# Sancho Fetch Runtime Templates

This folder is framework-managed and may be overwritten by
`sancho update apply`. Place user-owned business logic in `custom/**` and
repeatable workflows in `playbooks/**`.

Key files in this runtime template bundle:

- `ANALYSIS_GUIDE.md`: Polars/DuckDB analysis conventions.
- `DASHBOARD_GUIDE.md`: Dashboard architecture and UI reliability rules.
- `dataset_registry.yaml`: Canonical fetch module registry and provenance seed.

Workspace-root onboarding files are also sourced from this template bundle:

- `AI_INSTRUCTIONS.md`
- `DATASET_CATALOG.md`
