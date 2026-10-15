#!/bin/zsh
# Kit's scheduled runs, started by launchd:
#   run.sh          morning brief (weekdays 7:45, delivered by 8:00)
#   run.sh weekly   weekly review (Monday 7:30)
#   run.sh open     post-open read (weekdays 9:45)               optional extra for a trading setup
#   run.sh journal  trade journal after the close (weekdays 16:20) optional extra for a trading setup
# The open and journal runs are optional: install their launchd jobs only if you trade.
# To test a run without using up that day's run:
#   touch ~/Claude/Agents/kit/.install/platform/mac/morning/test-run
#   launchctl kickstart gui/$(id -u)/com.$USER.kit.morning      (or .open, .weekly)
# Settings live in .install/shared/morning/config: OWNER_NAME, SKIP_DAYS, BLOCK_TOOLS, and the
# delivery keys DELIVERY (local | outlook-drafts | outlook-review | imessage), DELIVERY_EMAIL_TO,
# IMESSAGE_TO, IMESSAGE_TO_ALT. Delivery itself is shared/deliver.py; it never sends mail.
MODE="${1:-morning}"
KIT="$HOME/Claude/Agents/kit"
MACDIR="$KIT/.install/platform/mac/morning"   # mac runner assets (test-run marker)
SHAREDIR="$KIT/.install/shared/morning"        # shared prompts + config
LOGDIR="$KIT/.install/logs"                    # OS-neutral run logs
TODAY=$(date +%Y-%m-%d)
LOG="$LOGDIR/$TODAY.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$LOGDIR" "$KIT/briefs" "$KIT/journal"
[ -f "$SHAREDIR/config" ] && source "$SHAREDIR/config"

case "$MODE" in
  open)   PROMPT="$SHAREDIR/prompt-open.md";   TEXT="briefs/open-text.txt" ;;
  weekly) PROMPT="$SHAREDIR/prompt-weekly.md"; TEXT="briefs/weekly-text.txt" ;;
  journal) PROMPT="$SHAREDIR/prompt-journal.md"; TEXT="briefs/journal-text.txt" ;;
  *)      MODE=morning; PROMPT="$SHAREDIR/prompt.md"; TEXT="briefs/latest-text.txt" ;;
esac
DONE="$LOGDIR/$TODAY.$MODE.done"
[ "$MODE" = "morning" ] && DONE="$LOGDIR/$TODAY.done"
# The journal scores a finished session, so it never runs before the close, not even as a test.
if [ "$MODE" = "journal" ] && [ $(date +%k) -lt 16 ]; then
  echo "== $(date) journal run skipped: before the close" >> "$LOG"
  exit 0
fi

TEST=""
if [ -f "$MACDIR/test-run" ]; then
  TEST="[Test] "
  rm -f "$MACDIR/test-run"
else
  # Skip the days in SKIP_DAYS (date +%u: 1 = Monday ... 7 = Sunday); the weekly review keeps
  # its own schedule. One run of each kind a day, and no post-open read once it's stale.
  if [ "$MODE" != "weekly" ]; then
    for d in ${=SKIP_DAYS:-}; do [ "$(date +%u)" = "$d" ] && exit 0; done
  fi
  [ -f "$DONE" ] && exit 0
  if [ "$MODE" = "open" ] && [ $(date +%k) -ge 12 ]; then
    echo "== $(date) open run skipped: too late in the day" >> "$LOG"
    exit 0
  fi
fi

# Delivery is shared/deliver.py; the channels come from DELIVERY in the config (default local:
# a notification plus a dashboard rebuild). It never sends mail.
# Usage: deliver <text file> [nobrief]   (nobrief: send the text alone, as for a failure notice)
deliver() {
  local brief=""
  case "$MODE" in
    morning|open) brief="briefs/$TODAY.md" ;;
    weekly)       brief="briefs/weekly-$TODAY.md" ;;
  esac
  local dargs=(--mode "$MODE" --text "$1")
  [ "${2:-}" != "nobrief" ] && [ -n "$brief" ] && [ -f "$brief" ] && dargs+=(--brief "$brief")
  [ -n "$TEST" ] && dargs+=(--test)
  python3 "$KIT/.install/shared/deliver.py" "${dargs[@]}"
}

cd "$KIT" || exit 1
rm -f "$TEXT"
if [ "$MODE" = "morning" ] || [ "$MODE" = "weekly" ]; then
  python3 "$KIT/.install/shared/doctor.py" --brief > briefs/health.txt 2>&1
  [ "$MODE" = "weekly" ] && AUDIT=--weekly || AUDIT=--daily
  python3 "$KIT/.install/shared/bin/kit-audit" "$AUDIT" >/dev/null 2>&1
fi
PROMPT_TEXT=$(sed "s/{{OWNER}}/${OWNER_NAME:-the owner}/g" "$PROMPT")
# Tools the unattended run may use: the basics, plus extras from config (permission rules separated
# by semicolons, since rules can contain spaces), for example the mail and calendar commands the
# setup files name. ALLOW_TOOLS_WEEKLY adds more for the weekly review, such as the Agent tool for
# the auditor. One --allowedTools list.
ALLOWED=("Bash(date:*)" "Edit(~/Claude/Agents/kit/briefs/**)" "Edit(~/Claude/Agents/kit/journal/**)")
for r in "${(@s:;:)ALLOW_TOOLS:-}"; do r="${r## }"; r="${r%% }"; [ -n "$r" ] && ALLOWED+=("$r"); done
if [ "$MODE" = "weekly" ]; then
  for r in "${(@s:;:)ALLOW_TOOLS_WEEKLY:-}"; do r="${r## }"; r="${r%% }"; [ -n "$r" ] && ALLOWED+=("$r"); done
fi
args=(-p "$PROMPT_TEXT" --output-format text --allowedTools "${ALLOWED[@]}")
[ -n "${BLOCK_TOOLS:-}" ] && args+=(--disallowedTools ${=BLOCK_TOOLS})

echo "== $(date) start $MODE ${TEST}" >> "$LOG"
perl -e 'alarm shift; exec @ARGV' 1200 claude "${args[@]}" >> "$LOG" 2>&1
rc=$?
echo "== $(date) end $MODE rc=$rc" >> "$LOG"

QUIET=$(cat "$TEXT" 2>/dev/null)
if [ "$QUIET" = "MARKET CLOSED" ] || [ "$QUIET" = "NO TEXT" ]; then
  echo "== $QUIET: no delivery" >> "$LOG"
  [ -z "$TEST" ] && touch "$DONE"
elif [ -s "$TEXT" ]; then
  if deliver "$TEXT" >> "$LOG" 2>&1; then
    [ -z "$TEST" ] && touch "$DONE"
    rm -f "briefs/unsent-$MODE.txt"
    echo "== delivered" >> "$LOG"
  else
    cp "$TEXT" "briefs/unsent-$MODE.txt"
    echo "== delivery failed" >> "$LOG"
  fi
else
  echo "Kit's $MODE run didn't finish (rc=$rc). Log: ~/Claude/Agents/kit/.install/logs/$TODAY.log" > "$LOGDIR/failure-$MODE.txt"
  deliver "$LOGDIR/failure-$MODE.txt" nobrief >> "$LOG" 2>&1
  echo "== sent failure notice" >> "$LOG"
fi

# Save the day's changes to Kit's private local history (never pushed), then refresh the dashboard.
if [ -d "$KIT/.git" ]; then
  git -C "$KIT" add -A >/dev/null 2>&1
  git -C "$KIT" commit -qm "auto: $MODE run $TODAY" >/dev/null 2>&1
fi
[ -f "$KIT/.install/shared/dashboard.py" ] && python3 "$KIT/.install/shared/dashboard.py" >/dev/null 2>&1
exit 0
