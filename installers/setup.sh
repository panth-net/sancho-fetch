#!/usr/bin/env bash
# Sancho Fetch installer for macOS / Linux.
# Bootstraps uv, lets uv provide a compatible Python, installs Sancho, and runs
# `sancho setup` in the repo folder.

set -euo pipefail

fail() {
  echo
  echo "ERROR: $1"
  echo "Installer stopped. Fix the issue above, then run this installer again."
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

echo "Sancho Fetch installer"
echo "======================"
echo
echo "Setting up your Sancho Fetch library at:"
echo "  $repo_root"
echo

if [ ! -f "$repo_root/pyproject.toml" ]; then
  fail "This installer must run from an extracted sancho-fetch folder. If you downloaded a ZIP, unzip it first."
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "  ...  Installing the Python package manager (uv)..."
  if ! command -v curl >/dev/null 2>&1; then
    fail "curl is not installed. Install curl, then run: bash installers/setup.sh"
  fi
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    fail "Could not install uv. Check your internet connection and try again."
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uv >/dev/null 2>&1; then
  fail "uv was installed, but it is not available in this window yet. Close this terminal and run the installer again."
fi
echo "  OK  Package manager (uv) ready"

echo "  ...  Installing Sancho..."
install_log="$(mktemp)"
if uv tool install . >"$install_log" 2>&1; then
  rm -f "$install_log"
elif grep -Eiq "already installed|already exists|executable.*exists" "$install_log"; then
  cat "$install_log"
  rm -f "$install_log"
  echo "  ...  Existing Sancho install found. Refreshing it from this folder..."
  uv tool uninstall sancho-fetch >/dev/null 2>&1 || true
  if ! uv tool install .; then
    fail "uv could not refresh Sancho from this folder."
  fi
else
  cat "$install_log"
  rm -f "$install_log"
  fail "uv could not install Sancho from this folder. Sancho needs Python 3.11 or newer; uv normally downloads a compatible Python automatically."
fi
uv_tool_bin="$(uv tool dir --bin)" || fail "uv installed Sancho, but the tool bin directory could not be found."
export PATH="$uv_tool_bin:$HOME/.local/bin:$PATH"
sancho_cmd="$uv_tool_bin/sancho"
if [ ! -x "$sancho_cmd" ]; then
  sancho_cmd="$(command -v sancho || true)"
fi
if [ -z "$sancho_cmd" ]; then
  fail "Sancho installed, but the sancho command could not be found. Close this window, open a new terminal, and run: sancho setup --path \"$repo_root\""
fi
echo "  OK  Sancho installed"

echo "  ...  Creating your workspace and registering it..."
if ! "$sancho_cmd" setup --path "$repo_root" --install-claude-desktop; then
  fail "sancho setup failed."
fi

echo
echo "Installer finished."
echo
echo "What's next:"
echo
echo "  1. Open Claude Code / Codex / Cursor / VS Code pointed at this folder,"
echo "     and just describe the data you want. The AI runs Sancho for you."
echo "     ChatGPT web needs the hosted/remote connector path, not a local folder."
echo "     If setup said Claude Desktop config was installed, fully restart Claude Desktop."
echo "     If setup said it could not install Claude Desktop automatically, use:"
echo "       sancho mcp config --client claude-desktop --workspace \"$repo_root\" --install"
echo "     or the generated snippet under sancho-workspace/mcp/."
echo
echo "  2. Your API keys live in:"
echo "       $repo_root/sancho-workspace/.env"
echo "     This file is HIDDEN by default."
echo "     - On Mac: open the sancho-workspace folder in Finder,"
echo "       press Cmd+Shift+. (Command + Shift + period) to show hidden files."
echo "     - On Windows: in File Explorer, View -> Show -> Hidden items."
echo "     - Or just ask your AI to open it for you."
echo
echo "  3. You do NOT need to be a coder. The AI speaks in plain English"
echo "     unless you change SANCHO_DEVELOPER_MODE=true inside .env."
