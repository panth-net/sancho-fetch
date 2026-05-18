# Dashboard Guide

Use this guide when building or extending dashboard outputs. Keep user-owned
dashboard code in `custom/dashboard/` or `outputs/`; treat `source/dashboard/`
as managed.

## Product Principles

1. Keep dashboards information-dense but readable.
2. Show loading, empty, and error states explicitly.
3. Maintain consistent color semantics across charts, maps, filters, and legends.
4. Keep date filtering explicit (apply action over hidden auto-filters).
5. Treat map overlays/popovers as first-class UI elements with reliable layering.

## Data Architecture

Preferred flow:

`raw -> analysis -> dashboard-data -> dashboard`

Dashboards should consume prepared analysis artifacts, not call raw provider APIs directly.

## Component Structure

1. Keep chart components focused (one concern per component).
2. Centralize filter state so interactions cross-filter predictably.
3. Keep data adapters thin and colocated with dashboard code.
4. Isolate visual tokens (colors, spacing, typography) from business logic.

## UX Reliability Rules

1. Never allow blank screens without explanation.
2. Keep scrolling behavior intact even when hiding scrollbars.
3. Validate mobile behavior early; if unsupported, communicate that clearly.
4. Preserve interaction consistency across pages and widget types.

## Tailwind v4 Safety Rule

If using Tailwind v4:

1. Do not add unlayered global resets like `* { margin:0; padding:0; }`.
2. Put base styles in `@layer base` so utility classes keep precedence.
3. Do not duplicate Tailwind utilities in handwritten CSS to patch cascade issues.

## Output Expectations

A dashboard is production-ready when:

1. It loads from stable analysis outputs.
2. It includes clear legends, units, and labeling.
3. It communicates data freshness/provenance.
4. It can be regenerated from the same workflow without manual UI edits.
