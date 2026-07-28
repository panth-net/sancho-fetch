# Analysis Guide (Polars + DuckDB)

This guide defines the default analysis style for Sancho Fetch workspaces.

## Core Flow

1. Ingest fetched data from `fetched-data/` using lazy scans.
2. Keep user-owned reusable analysis components under `custom/analyze/` or
   replayable workflows in `playbooks/`. Treat `source/analyze/` as managed.
3. Write durable derived work to `analysis-data/`.
4. Export clean outputs to `outputs/` or dashboard-ready exports.
5. Feed downstream dashboards from analysis outputs, not directly from raw pulls.

## Polars-First Standard

1. Prefer `pl.scan_parquet` and `pl.scan_csv` over eager reads.
2. Keep data as `LazyFrame` until the output edge.
3. Use expression transforms (`select`, `with_columns`, `filter`, `group_by`, `join`).
4. Enforce dtypes and null handling before export.
5. Validate joins with `validate=` when keys should be one-to-one or one-to-many.

## DuckDB Use Cases

Use DuckDB when SQL is clearer for complex multi-table work, or when direct SQL over many files is faster to reason about.

Interop pattern:

1. Query in DuckDB.
2. Convert via Arrow.
3. Continue shaping in Polars.

## Reusable Component Pattern

For custom analysis modules, split work into composable scripts/functions:

1. `load_*` functions (raw inputs)
2. `build_*` functions (metrics/tables)
3. `export_*` functions (durable outputs)

Keep each component narrowly scoped so future projects can recombine them.

## Useful Polars Operations

- Loading: `scan_parquet`, `scan_csv`
- Selection/typing: `select`, `with_columns`, `cast`, `pl.when`
- Joins: `join`, `join_asof`
- Aggregations: `group_by().agg()`, `n_unique`, `quantile`
- Time logic: `group_by_dynamic`, rolling windows, `over`
- Data quality: `is_null`, `fill_null`, `drop_nulls`, `unique`

## Output Contract

1. Export artifacts should be flat, typed, and documented.
2. Output names should describe business meaning, not notebook steps.
3. Include column metadata where possible for dashboard handoff.
4. Avoid writing ad hoc one-use files when a reusable artifact can be produced.

## Dashboard Handoff

Use this explicit chain when targeting dashboards:

`raw -> analysis -> dashboard-data -> dashboard`

The dashboard layer should read prepared outputs; it should not own business logic transformations.
