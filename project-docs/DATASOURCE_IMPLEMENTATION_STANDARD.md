# Sancho Fetch Data Source Implementation Standard

> **Status: AUTHORITATIVE** - Mandatory contract enforced by `sancho module audit` and `tests/test_datasource_standard.py`.

This document defines the exact checks for every `fetch.<provider>` module.
If a module fails any checklist item below, it is non-compliant.

## 1. Catalog Purpose

- Catalog artifacts are for machine traversal and safe request planning.
- Artifacts are module-local (`src/sancho/templates/modules/<module-id>/...`).
- Audit logic can resolve artifacts from module folders or catalog cache.

## 2. Tier Contract

Every fetch module must declare `catalog_tier` in `module.yaml`:

- `large`: endpoint-family catalog (`catalog.json` + `catalog.meta.json`)
- `small`: schema sample artifact (`schema.sample.json`)

## 3. Required Artifacts

All fetch modules:

- `discovery.py` is required only for `large` modules.

Large tier:

- `catalog.json`
- `catalog.meta.json`
- `discovery.py`

Small tier:

- `schema.sample.json`

Note: runtime filenames such as `main.py`, `api.py`, `transform.py`, `run.py`, or `client.py` are implementation details and are not part of this audit checklist.

## 4. Large-Tier Shape Rules

`catalog.json` must contain:

- `families` as a non-empty list
- each family with required keys:
  - `id`
  - `base_url`
  - `path_templates`
  - `methods`
  - `query_params`

`catalog.meta.json` must contain:

- `generated_at` (non-empty string)
- `discovery.sources` as a non-empty list
- each source with:
  - `url`
  - `status`
  - `fetched_at`

Consistency checks:

- if `stats.family_count` exists, it must equal `len(families)`
- if `indices.<name>` and `stats.<name>_count` both exist, counts must match

## 5. Small-Tier Shape Rules

`schema.sample.json` must contain:

- `provider` (non-empty string)
- `generated_at` (non-empty string)
- `columns` as a non-empty list of objects with:
  - `name`
  - `type`
  - `sample`
- `sample_row` as a non-empty object

Consistency check:

- `sample_row` keys must match `columns[].name` exactly.

## 6. Definition of Done (Hard Gate Checklist)

- [STD-001] `discovery.py` exists for `large` modules; small modules are exempt.
- [STD-002] Primary artifact exists (`catalog.json` for large, `schema.sample.json` for small).
- [STD-003] Secondary artifact exists (`catalog.meta.json` for large, none required for small).
- [STD-004] Evidence exists (`discovery.sources` for large, `sample_row` for small).
- [STD-005] Contract shape is valid (`families` schema or `columns` schema).
- [STD-006] Internal consistency checks pass.
- [STD-007] Provenance fields exist.

Failing any checklist item blocks provider completion and fails automated compliance checks.

## 7. Output Shape Convention (informational)

Most fetch modules return `{dataset_ref, rows, retrieved_at, ...}` so chained
modules can locate the data. This is **convention, not contract** -- `analyze.*`
and `dashboard.*` modules read explicit keys (`records`, `metrics`, `title`)
and don't structurally depend on the standardized shape. New fetch modules
should follow the convention but are free to deviate where the upstream API's
natural output makes more sense.
