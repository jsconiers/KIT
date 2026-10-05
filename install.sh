#!/bin/bash
# install.sh: install Kit, your Claude Code agent, on this Mac.
#
#   bash install.sh
#
# Everything Kit needs is copied into ~/Claude/Agents/kit, including this installer, so the
# downloaded copy can be deleted afterward (it offers to do that for you). Outside that folder,
# it adds one line to ~/.claude/CLAUDE.md and some entries to ~/.claude/settings.json, after
# backing both up. Claude Code's auto memory is left alone.
# Safe to re-run: Kit's memory, queue, status, lessons, and preferences are never overwritten.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
die() { printf 'install: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die "install.sh takes no options."

PY="$(command -v python3 || true)"
[ -n "$PY" ] || die "python3 not found. Run: xcode-select --install   then run this installer again."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null \
  || die "python3 didn't run, or it's older than 3.8. If macOS offered to install the command line developer tools, accept, then run this again."
[ -f "$SRC/kit_setup.py" ] && [ -d "$SRC/kit" ] \
  || die "run this from the unzipped kit-agent folder, or from ~/Claude/Agents/kit/.install."
command -v claude > /dev/null 2>&1 \
  || printf 'install: note: Claude Code (claude) is not on your PATH yet. Kit will be ready once it is.\n'

umask 077
"$PY" "$SRC/kit_setup.py" check
"$PY" "$SRC/kit_setup.py" scaffold
"$PY" "$SRC/kit_setup.py" activate
chmod -R go-rwx "$HOME/Claude/Agents/kit"

cat <<MSG

Kit is installed in $HOME/Claude/Agents/kit (only your account can open it).

Next:
  1. Start Claude Code in any folder:   claude
  2. Run /context and check that KIT.md is listed under Memory files.
  3. Say: Kit, introduce yourself.

To take Kit out of Claude Code:  bash ~/Claude/Agents/kit/.install/uninstall.sh
To put it back later:            bash ~/Claude/Agents/kit/.install/install.sh
MSG

# Offer to remove the downloaded installer. Only a folder named kit-agent* directly inside
# ~/Downloads qualifies, and only when someone is at the keyboard to say yes.
case "$SRC" in
  "$HOME/Downloads/"*/*) ;;   # nested deeper than ~/Downloads/<folder>: leave it alone
  "$HOME/Downloads/"kit-agent*)
    if [ -t 0 ] && [ -t 1 ]; then
      printf '\nKit has its own copy of the installer now. Delete the download (%s' "$SRC"
      ZIP="$HOME/Downloads/kit-agent.zip"
      [ -f "$ZIP" ] && printf ' and %s' "$ZIP"
      printf ')? [y/N] '
      answer=""
      read -r answer || answer=""
      case "$answer" in
        y|Y|yes|Yes|YES)
          rm -rf "$SRC"
          [ -f "$ZIP" ] && rm -f "$ZIP"
          printf 'Deleted. Nothing from Kit is left in ~/Downloads.\n' ;;
        *)
          printf 'Kept. You can delete %s whenever you like.\n' "$SRC" ;;
      esac
    fi ;;
esac
exit 0
