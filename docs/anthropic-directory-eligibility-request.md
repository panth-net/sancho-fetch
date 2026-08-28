# Anthropic Software Directory eligibility preflight

Status: **external confirmation pending**

Sancho's direct MCPB distribution and local Claude Code plugin do not depend on
a Directory listing. Do not submit or promise Directory availability until
Anthropic answers this question in writing:

> Is a local-first Claude Desktop MCPB eligible for the Anthropic Software
> Directory when its user selects among public-data modules that make direct
> requests from the user's computer to third-party government, international,
> and open-data APIs that the extension author does not own? The extension does
> not proxy or resell those APIs, identifies the selected upstream, stores data
> locally, has no Sancho telemetry service, and sends a credential only to the
> selected provider when its API requires one.

Attach the following evidence to the request:

- `docs/PRIVACY.md`
- `docs/privacy/upstream-inventory.json`
- `docs/privacy/UPSTREAM_DATA_FLOW.md`
- the managed-uv MCPB manifest and external-workspace retention behavior

Record the dated response here before directory-specific submission work. A
denial does not block PyPI, direct MCPB distribution, the Claude Code plugin,
or local Codex/client adapters.
