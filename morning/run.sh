#!/bin/zsh
# Kit's scheduled runs, started by launchd:
#   run.sh          morning brief (weekdays 7:45, texted by 8:00)
#   run.sh open     post-open read (weekdays 9:45)
#   run.sh weekly   weekly review
#   run.sh journal  trade journal after the close (weekdays 16:20; no text unless it fails)
# To test a run without using up that day's run:
#   touch ~/Claude/Agents/kit/.install/morning/test-run
#   launchctl kickstart gui/$(id -u)/com.$USER.kit.morning      (or .open, .weekly)
# Settings live in ./config: OWNER_NAME, IMESSAGE_TO, IMESSAGE_TO_ALT, SKIP_DAYS, BLOCK_TOOLS.
MODE="${1:-morning}"
KIT="$HOME/Claude/Agents/kit"
DIR="$KIT/.install/morning"
LOGDIR="$DIR/logs"
TODAY=$(date +%Y-%m-%d)
LOG="$LOGDIR/$TODAY.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$LOGDIR" "$KIT/briefs" "$KIT/journal"
[ -f "$DIR/config" ] && source "$DIR/config"

case "$MODE" in
  open)   PROMPT="$DIR/prompt-open.md";   TEXT="briefs/open-text.txt" ;;
  weekly) PROMPT="$DIR/prompt-weekly.md"; TEXT="briefs/weekly-text.txt" ;;
  journal) PROMPT="$DIR/prompt-journal.md"; TEXT="briefs/journal-text.txt" ;;
  *)      MODE=morning; PROMPT="$DIR/prompt.md"; TEXT="briefs/latest-text.txt" ;;
esac
DONE="$LOGDIR/$TODAY.$MODE.done"
[ "$MODE" = "morning" ] && DONE="$LOGDIR/$TODAY.done"
# The journal scores a finished session, so it never runs before the close, not even as a test.
if [ "$MODE" = "journal" ] && [ $(date +%k) -lt 16 ]; then
  echo "== $(date) journal run skipped: before the close" >> "$LOG"
  exit 0
fi

TEST=""
if [ -f "$DIR/test-run" ]; then
  TEST="[Test] "
  rm -f "$DIR/test-run"
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

send_once() {
  local to
  for to in "${IMESSAGE_TO:-}" "${IMESSAGE_TO_ALT:-}"; do
    [ -z "$to" ] && continue
    /usr/bin/osascript - "$to" "$1" <<'APPLESCRIPT' && return 0
on run argv
  tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send (item 2 of argv) to participant (item 1 of argv) of svc
  end tell
end run
APPLESCRIPT
  done
  return 1
}

send_text() {  # keep trying for about 20 minutes, then leave a notification on the Mac
  local wait
  for wait in 0 120 240 360 480; do
    sleep $wait
    send_once "$1" && return 0
  done
  /usr/bin/osascript -e 'display notification "Kit could not text you. The brief is in ~/Claude/Agents/kit/briefs." with title "Kit"' 2>/dev/null
  return 1
}

cd "$KIT" || exit 1
rm -f "$TEXT"
if [ "$MODE" = "morning" ] || [ "$MODE" = "weekly" ]; then
  python3 "$KIT/.install/doctor.py" --brief > briefs/health.txt 2>&1
fi
PROMPT_TEXT=$(sed "s/{{OWNER}}/${OWNER_NAME:-the owner}/g" "$PROMPT")
args=(-p "$PROMPT_TEXT" --output-format text
      --allowedTools "Bash(date:*)" "Edit(~/Claude/Agents/kit/briefs/**)"
      "Edit(~/Claude/Agents/kit/journal/**)")
[ -n "${BLOCK_TOOLS:-}" ] && args+=(--disallowedTools ${=BLOCK_TOOLS})

echo "== $(date) start $MODE ${TEST}" >> "$LOG"
perl -e 'alarm shift; exec @ARGV' 1200 claude "${args[@]}" >> "$LOG" 2>&1
rc=$?
echo "== $(date) end $MODE rc=$rc" >> "$LOG"

QUIET=$(cat "$TEXT" 2>/dev/null)
if [ "$QUIET" = "MARKET CLOSED" ] || [ "$QUIET" = "NO TEXT" ]; then
  echo "== $QUIET: no text" >> "$LOG"
  [ -z "$TEST" ] && touch "$DONE"
elif [ -s "$TEXT" ]; then
  if send_text "${TEST}$(cat "$TEXT")" >> "$LOG" 2>&1; then
    [ -z "$TEST" ] && touch "$DONE"
    rm -f "briefs/unsent-$MODE.txt"
    echo "== texted" >> "$LOG"
  else
    cp "$TEXT" "briefs/unsent-$MODE.txt"
    echo "== text failed" >> "$LOG"
  fi
else
  send_text "${TEST}Kit's $MODE run didn't finish (rc=$rc). Log: ~/Claude/Agents/kit/.install/morning/logs/$TODAY.log" >> "$LOG" 2>&1
  echo "== sent failure notice" >> "$LOG"
fi

# Save the day's changes to Kit's private local history (never pushed), then refresh the dashboard.
if [ -d "$KIT/.git" ]; then
  git -C "$KIT" add -A >/dev/null 2>&1
  git -C "$KIT" commit -qm "auto: $MODE run $TODAY" >/dev/null 2>&1
fi
[ -f "$KIT/.install/dashboard.py" ] && python3 "$KIT/.install/dashboard.py" >/dev/null 2>&1
exit 0
