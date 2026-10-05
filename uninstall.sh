#!/bin/bash
# uninstall.sh: take Kit out of Claude Code.
# Removes Kit's line from ~/.claude/CLAUDE.md and exactly the entries install.sh added to
# ~/.claude/settings.json. Both files are backed up first. Kit's own files in
# ~/Claude/Agents/kit are left alone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { printf 'uninstall: python3 not found\n' >&2; exit 1; }

"$PY" "$HERE/kit_setup.py" deactivate

cat <<MSG

Kit's files are still in $HOME/Claude/Agents/kit. To delete them too:
  rm -rf ~/Claude/Agents/kit
To put Kit back:  bash ~/Claude/Agents/kit/.install/install.sh
MSG
