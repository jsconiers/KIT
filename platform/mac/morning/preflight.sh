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

# 1. Claude Code: one tiny headless call, the same path the scheduled runs use. It's a paid call, so
# it goes in the cost ledger (kit-cost, mode "preflight") like every scheduled run.
# While a usage limit is recorded (kit_limits.py), the call is skipped until the reset; when the reset
# time is unknown, it runs once a day to test whether access is back (check --probe).
LIMITS="$KIT/.install/shared/kit_limits.py"
LIMIT_STATE="ok"
if [ -f "$LIMITS" ] && [ "${USAGE_LIMIT_GUARD:-on}" != "off" ]; then
  LIMIT_STATE=$(python3 "$LIMITS" check --probe 2>> "$LOG")
  LIMIT_STATE=${LIMIT_STATE%% *}
fi
if [ "$LIMIT_STATE" = "limited" ]; then
  echo "$(stamp) login check skipped: Claude usage limit recorded (access returns $(python3 "$LIMITS" when 2>/dev/null))" >> "$LOG"
  python3 "$LIMITS" notice > "$LOGDIR/.preflight-limit.txt" 2>/dev/null
  [ -s "$LOGDIR/.preflight-limit.txt" ] && notify "$LOGDIR/usage-limit-notified" "$(cat "$LOGDIR/.preflight-limit.txt")"
  rm -f "$LOGDIR/.preflight-limit.txt"
else
OUTF=$(mktemp "${TMPDIR:-/tmp}/kit-preflight.XXXXXX")
(cd /tmp && perl -e 'alarm shift; exec @ARGV' 120 claude -p "Reply with the single word OK." \
      --model haiku --max-turns 1 --output-format json < /dev/null > "$OUTF" 2> "$OUTF.err")
RC=$?
COST="$KIT/.install/shared/bin/kit-cost"
[ -f "$COST" ] && python3 "$COST" record --mode preflight --rc "$RC" --json-file "$OUTF" --log /dev/null 2>> "$LOG"
OUT=$(cat "$OUTF" "$OUTF.err" 2>/dev/null)
LIMIT_HIT=""
if [ -f "$LIMITS" ] && [ "${USAGE_LIMIT_GUARD:-on}" != "off" ] && [ $RC -ne 0 ]; then
  LIMIT_HIT=$(python3 "$LIMITS" detect --source preflight "$OUTF" "$OUTF.err" 2>> "$LOG")
fi
rm -f "$OUTF" "$OUTF.err"
FIRST=$(print -r -- "$OUT" | head -1 | cut -c1-160)
if [ -n "$LIMIT_HIT" ]; then
  echo "$(stamp) Claude usage limit reached ($LIMIT_HIT): scheduled runs stand down until it resets" >> "$LOG"
  python3 "$LIMITS" notice > "$LOGDIR/.preflight-limit.txt" 2>/dev/null
  [ -s "$LOGDIR/.preflight-limit.txt" ] && notify "$LOGDIR/usage-limit-notified" "$(cat "$LOGDIR/.preflight-limit.txt")"
  rm -f "$LOGDIR/.preflight-limit.txt"
elif [ $RC -eq 0 ] && print -r -- "$OUT" | grep -q 'OK'; then
  echo "$(stamp) login ok" >> "$LOG"
  [ -f "$LIMITS" ] && [ -s "$LOGDIR/usage-limit.json" ] && python3 "$LIMITS" success --source preflight 2>> "$LOG" \
    && echo "$(stamp) usage limit cleared" >> "$LOG"
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
