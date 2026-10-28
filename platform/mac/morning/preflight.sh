#!/bin/zsh
# preflight.sh: before Kit's scheduled runs, check that Claude Code can run and that each connector
# named in PREFLIGHT_CONNECTORS (config) is signed in. Each problem reaches the owner once per lapse,
# through deliver.py, so there's time to fix it before the runs fail. Runs from
# com.USER.kit.preflight at 06:45 and 15:45; run it by hand any time. Log: .install/logs/preflight.log.
#
# Long-lived login (optional): a token from `claude setup-token`, stored in the login Keychain as
# "kit-claude-token", is used here the same way run.sh uses it.
KIT="$HOME/Claude/Agents/kit"
SHAREDIR="$KIT/.install/shared/morning"
LOGDIR="$KIT/.install/logs"
LOG="$LOGDIR/preflight.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p "$LOGDIR"
[ -f "$SHAREDIR/config" ] && source "$SHAREDIR/config"
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  KIT_TOKEN=$(security find-generic-password -s kit-claude-token -w 2>/dev/null) \
    && [ -n "$KIT_TOKEN" ] && export CLAUDE_CODE_OAUTH_TOKEN="$KIT_TOKEN"
  unset KIT_TOKEN
fi
stamp() { date '+%Y-%m-%d %H:%M'; }

# notify STATEFILE MESSAGE: deliver the message once per lapse (the state file marks it sent).
notify() {
  [ -f "$1" ] && return 0
  local f="$LOGDIR/.preflight-msg.txt"
  print -r -- "$2" > "$f"
  python3 "$KIT/.install/shared/deliver.py" --mode preflight --text "$f" >> "$LOG" 2>&1 && date > "$1"
  rm -f "$f"
}

# Optional: rebuild the command catalog, if this install has the kit-catalog command.
command -v kit-catalog >/dev/null && kit-catalog 2>&1 | sed "s/^/$(stamp) /" >> "$LOG"

# 1. Claude Code: one tiny headless call, the same path the scheduled runs use.
OUT=$(cd /tmp && perl -e 'alarm shift; exec @ARGV' 120 claude -p "Reply with the single word OK." \
      --model haiku --max-turns 1 --output-format text < /dev/null 2>&1)
RC=$?
FIRST=$(print -r -- "$OUT" | head -1 | cut -c1-160)
if [ $RC -eq 0 ] && print -r -- "$OUT" | grep -q 'OK'; then
  echo "$(stamp) login ok" >> "$LOG"
  if [ -f "$LOGDIR/login-lapsed" ]; then
    rm -f "$LOGDIR/login-lapsed"
    echo "$(stamp) login restored" >> "$LOG"
  fi
elif print -r -- "$OUT" | grep -q -i -E 'not logged in|/login|oauth|invalid api key|authenticat'; then
  echo "$(stamp) LOGGED OUT: $FIRST" >> "$LOG"
  notify "$LOGDIR/login-lapsed" "Kit · Claude Code is logged out, so Kit's scheduled runs will fail. To fix it at the computer: open Terminal, run claude, and type /login."
else
  echo "$(stamp) login check inconclusive (rc $RC): $FIRST" >> "$LOG"
fi

# 2. Connectors that need the owner's sign-in now and then (OAuth), from PREFLIGHT_CONNECTORS.
for C in ${=PREFLIGHT_CONNECTORS:-}; do
  ST=$(cd /tmp && perl -e 'alarm shift; exec @ARGV' 60 claude mcp get "$C" < /dev/null 2>&1 | grep -i 'status')
  if print -r -- "$ST" | grep -q -i 'needs authentication'; then
    echo "$(stamp) $C connector needs sign-in" >> "$LOG"
    notify "$LOGDIR/signin-$C" "Kit · The $C connector needs you to sign in. At the computer: run claude, type /mcp, choose $C, and authenticate."
  elif print -r -- "$ST" | grep -q -i 'connected'; then
    rm -f "$LOGDIR/signin-$C"
  fi
done
