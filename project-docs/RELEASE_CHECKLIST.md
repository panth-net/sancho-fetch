# Release Checklist

How a sancho-fetch release reaches PyPI. Normal path: push a version tag and
GitHub Actions does the rest ([`.github/workflows/publish.yml`](../.github/workflows/publish.yml)).

## One-time setup (before the first release)

1. The GitHub repo `panth-net/sancho-fetch` is public with the current code
   pushed.
2. On [pypi.org](https://pypi.org): log in -> **Your account** ->
   **Publishing** -> add a **pending publisher**:
   - PyPI project name: `sancho-fetch`
   - Owner: `panth-net`  Repository: `sancho-fetch`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. On GitHub: repo **Settings -> Environments** -> create an environment
   named `pypi` (optionally add yourself as a required reviewer so every
   publish needs a click of approval).

No API tokens anywhere: the workflow authenticates via OIDC Trusted
Publishing. Do this promptly -- the project name is only reserved once the
pending publisher exists or the first release lands.

## Every release

1. Bump the version in all three places (must match; enforced by
   `tests/test_mcpb_bundle.py`):
   - `pyproject.toml` -> `version = "X.Y.Z"`
   - `src/sancho/__init__.py` -> `__version__ = "X.Y.Z"`
   - `integrations/claude-desktop/manifest.json` -> `"version": "X.Y.Z"`
2. Rebuild the Claude Desktop bundle: `uv run python scripts/build_mcpb.py`
3. Run the suite: `uv run pytest -m "not live and not slow"`
4. Verify the artifacts locally:

   ```bash
   rm -rf dist && uv build
   unzip -l dist/*.whl | grep -c templates/          # expect several hundred
   unzip -l dist/*.whl | grep .env.example           # must be present
   uv run pytest tests/test_release_gate.py -k leak  # credential/identity scan
   ```

   The leak scan covers the shipped source tree; the publish workflow
   re-checks the built wheel itself.

5. Commit, then tag and push:

   ```bash
   git tag vX.Y.Z
   git push origin master --tags
   ```

   The `publish` workflow runs the tests again, rebuilds, re-checks the
   wheel, and uploads to PyPI.
6. Smoke-test from a clean environment once PyPI shows the release:

   ```bash
   uv tool install sancho-fetch
   sancho --version
   ```

## Manual fallback (no GitHub Actions)

```bash
uv run pytest -m "not live and not slow"
rm -rf dist && uv build
uv publish   # prompts for a PyPI API token created at pypi.org/manage/account/token/
```

Prefer the workflow: tokens are long-lived secrets; OIDC publishing has none.

## What users see after a release

- New installs: `uv tool install sancho-fetch` picks up the new version.
- Existing installs: within 14 days `sancho paths` shows the update nudge in
  any Code session; the agent then runs `uv tool upgrade sancho-fetch` and
  `sancho update apply` (workspace migration with backup + rollback).
- `.env` is never touched by any of this; `.env.example` in the workspace is
  refreshed to the new release's key documentation during `update apply`.
