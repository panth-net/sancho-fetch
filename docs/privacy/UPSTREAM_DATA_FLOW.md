# Upstream domain and credential inventory

`upstream-inventory.json` is generated from bundled fetch-module source by:

```bash
uv run python scripts/generate_privacy_inventory.py
```

The generator never opens `.env`. It inventories URL domains and credential
environment-variable names declared in source, then records the standard data
flow: a selected local request goes directly to the selected upstream provider;
the response returns to the local canonical cache and working export. Sancho
does not proxy those requests through a Pantheon Network service.

This is static evidence, not a substitute for each provider's current terms or
privacy policy. Release review must inspect additions/removals and re-run the
generator when modules change.
