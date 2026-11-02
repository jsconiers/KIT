#!/bin/bash
# uninstall.sh: take Kit out of Claude Code.
# Removes Kit's line from ~/.claude/CLAUDE.md and exactly the entries install.sh added to
# ~/.claude/settings.json (both backed up first), unloads and removes Kit's launchd jobs
# (~/Library/LaunchAgents/com.$USER.kit.*.plist: the brief, the sync, texting Kit, and the rest), and
# removes the links in ~/.local/bin that point into ~/Claude/Agents/kit/.install. Kit's own files in
# ~/Claude/Agents/kit are left alone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # platform/mac within the package
ROOT="$(cd "$HERE/../.." && pwd)"                        # package root
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { printf 'uninstall: python3 not found\n' >&2; exit 1; }

"$PY" "$ROOT/shared/kit_setup.py" deactivate

# Kit's scheduled jobs: unload each one (it may not be loaded), then remove its file.
AGENTS="${KIT_LAUNCHAGENTS:-$HOME/Library/LaunchAgents}"
LAUNCHCTL="${KIT_LAUNCHCTL:-launchctl}"     # tests point this at a stand-in
jobs=0
for plist in "$AGENTS"/com."${USER:-$(id -un)}".kit.*.plist; do
  [ -f "$plist" ] || continue
  "$LAUNCHCTL" bootout "gui/$(id -u)" "$plist" > /dev/null 2>&1 || true
  rm -f "$plist"
  jobs=$((jobs + 1))
done
# Kit's commands on the PATH: only links that point into Kit's own copy, never anything else there.
links=0
for link in "$HOME/.local/bin"/*; do
  [ -L "$link" ] || continue
  case "$(readlink "$link")" in
    "$HOME/Claude/Agents/kit/.install/"*) rm -f "$link"; links=$((links + 1)) ;;
  esac
done
printf 'Removed %s launchd job(s) and %s command link(s) in ~/.local/bin.\n' "$jobs" "$links"

cat <<MSG

Kit's files are still in $HOME/Claude/Agents/kit. To delete them too:
  rm -rf ~/Claude/Agents/kit
To put Kit back:  bash ~/Claude/Agents/kit/.install/platform/mac/install.sh
MSG
