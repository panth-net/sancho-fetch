#!/usr/bin/env bash
# Sancho Fetch uninstaller for macOS / Linux.
#
# Removes everything `installers/setup.sh` installs:
#   - the `sancho` CLI (via `uv tool uninstall sancho-fetch`)
#   - the library pointer at ~/.sancho/
#   - AI assistant skills at ~/.claude/skills/sancho{,_update}/ and ~/.agents/skills/sancho{,_update}/
#   - the `sancho` MCP server entry from Claude Desktop's config (other entries preserved)
#
# By default, your sancho-workspace/ folder (the visible folder with your
# .env, fetched-data, custom modules, playbooks, outputs, logs) is KEPT.
# Pass --purge to also delete sancho-workspace/.
#
# Flags:
#   --purge   Also delete sancho-workspace/ (your fetched data and .env)
#   --yes     Skip the interactive "are you sure?" prompts
#   --help    Show this message and exit

set -euo pipefail

PURGE=false
ASSUME_YES=false
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=true ;;
    --yes|-y) ASSUME_YES=true ;;
    --help|-h)
      # Print the comment block at the top of this file (skip the shebang
      # and stop at the first non-comment line).
      awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    *)
      echo "Unknown flag: $arg" >&2
      echo "Run 'bash installers/uninstall.sh --help' for usage." >&2
      exit 2
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
workspace_dir="$repo_root/sancho-workspace"

echo "Sancho Fetch uninstaller"
echo "========================"
echo
echo "This will remove the sancho CLI, library pointer, AI skills, and the"
echo "Claude Desktop MCP entry from this computer."
echo
if $PURGE; then
  echo "  --purge: will ALSO delete your sancho-workspace folder:"
  echo "    $workspace_dir"
  echo "  This contains your .env (API keys), fetched-data, custom modules,"
  echo "  playbooks, outputs, and logs. THIS IS DESTRUCTIVE."
else
  echo "  Your sancho-workspace folder will be KEPT:"
  echo "    $workspace_dir"
  echo "  (Pass --purge to delete it too.)"
fi
echo

if ! $ASSUME_YES; then
  printf "Proceed? [y/N] "
  read -r answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "Aborted."; exit 0 ;;
  esac
fi

ok() { echo "  OK  $1"; }
skip() { echo "  --  $1"; }
warn() { echo "  !!  $1"; }

# 1. Uninstall the CLI via uv. Skip silently if uv or the tool is missing.
if command -v uv >/dev/null 2>&1; then
  if uv tool list 2>/dev/null | grep -q '^sancho-fetch'; then
    if uv tool uninstall sancho-fetch >/dev/null 2>&1; then
      ok "Removed sancho CLI (uv tool uninstall sancho-fetch)"
    else
      warn "uv tool uninstall sancho-fetch failed; remove it manually with that command"
    fi
  else
    skip "sancho CLI not installed via uv"
  fi
else
  skip "uv not found; nothing to uninstall via uv"
fi

# 2. Remove the library pointer and the quick MCP workspace.
sancho_home="$HOME/.sancho"
if [ -d "$sancho_home" ]; then
  rm -rf "$sancho_home"
  ok "Removed library pointer ($sancho_home)"
else
  skip "Library pointer not found ($sancho_home)"
fi

# 3. Remove AI assistant skills from ~/.claude/skills and ~/.agents/skills.
removed_any_skill=false
for base in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  for name in sancho sancho-update; do
    target="$base/$name"
    if [ -e "$target" ]; then
      rm -rf "$target"
      ok "Removed AI skill ($target)"
      removed_any_skill=true
    fi
  done
done
if ! $removed_any_skill; then
  skip "No AI skills found under ~/.claude/skills or ~/.agents/skills"
fi

# 4. Surgically remove the `sancho` entry from Claude Desktop's MCP config.
#    Linux uses ~/.config/Claude/, macOS uses ~/Library/Application Support/Claude/.
remove_claude_entry() {
  local config_path="$1"
  [ -f "$config_path" ] || return 1
  python3 - "$config_path" <<'PY' || return 2
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception as exc:  # pragma: no cover - we just report and bail
    print(f"could not parse {p}: {exc}", file=sys.stderr)
    sys.exit(2)
servers = data.get("mcpServers") if isinstance(data, dict) else None
if not isinstance(servers, dict) or "sancho" not in servers:
    sys.exit(1)
del servers["sancho"]
p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
sys.exit(0)
PY
}

claude_macos="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
claude_linux="$HOME/.config/Claude/claude_desktop_config.json"
removed_claude_entry=false
for cfg in "$claude_macos" "$claude_linux"; do
  if [ -f "$cfg" ]; then
    set +e
    remove_claude_entry "$cfg"
    rc=$?
    set -e
    case $rc in
      0) ok "Removed 'sancho' entry from $cfg"; removed_claude_entry=true ;;
      1) skip "No 'sancho' entry in $cfg" ;;
      2) warn "Could not edit $cfg (parse error or python3 missing); remove the sancho entry manually" ;;
    esac
  fi
done
if ! $removed_claude_entry; then
  skip "No Claude Desktop config edits made"
fi

# 5. Optionally remove the workspace.
if $PURGE; then
  if [ -d "$workspace_dir" ]; then
    rm -rf "$workspace_dir"
    ok "Removed workspace ($workspace_dir)"
  else
    skip "Workspace not found ($workspace_dir)"
  fi
elif [ -d "$workspace_dir" ]; then
  echo "  --  Kept workspace ($workspace_dir)"
  echo "      Delete it yourself if you also want to remove your .env and fetched data,"
  echo "      or re-run with: bash installers/uninstall.sh --purge"
fi

echo
echo "Uninstall finished."
echo
echo "If Claude Desktop is open, fully quit and reopen it so the MCP entry change takes effect."
