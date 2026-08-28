#!/usr/bin/env bash
# Checkout convenience wrapper for Sancho's shared, ownership-aware uninstall.
#
# Normal cleanup:
#   bash installers/uninstall.sh
#
# Explicitly purge one workspace (data deletion):
#   bash installers/uninstall.sh --purge-workspace \
#     --workspace /exact/path/to/sancho-workspace --workspace-id UUID --yes
#
# This wrapper never removes the CLI itself. The shared command prints
# `uv tool uninstall sancho-fetch` last, after integrations are detached.

set -euo pipefail

if ! command -v sancho >/dev/null 2>&1; then
  echo "The Sancho CLI is required so ownership can be checked safely." >&2
  echo "Install the checkout first with: bash installers/setup.sh" >&2
  exit 1
fi

exec sancho uninstall "$@"
