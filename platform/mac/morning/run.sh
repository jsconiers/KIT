#!/bin/zsh
# Kit's scheduled runs, started by launchd:
#   run.sh          morning brief (weekdays 7:45, delivered by 8:00)
#   run.sh weekly   weekly review (Monday 6:30)
#   run.sh worklist proposed work list for the owner to approve (Monday to Thursday 9:00)
#   run.sh eod      end-of-day wrap-up (weekdays 17:30; EOD="off" in the config skips it)
# Nothing runs while Kit is paused (kit-pause). Before the morning and weekly runs, kit-outlook
# checks that Outlook answers (set OUTLOOK_CHECK="off" in the config to skip it).
# Every run records its estimated cost in .install/logs/cost.jsonl (kit-cost). With
# COST_BUDGET_MONTHLY set, runs other than COST_ESSENTIAL_MODES skip once COST_STOP_PCT of the
# budget is used, and the brief says how much is used from COST_WARN_PCT on.
#   run.sh open     post-open read (weekdays 9:45)               optional extra for a trading setup
#   run.sh journal  trade journal after the close (weekdays 16:20) optional extra for a trading setup
# The open and journal runs are optional: install their launchd jobs only if you trade.
# To test a run without using up that day's run:
#   touch ~/Claude/Agents/kit/.install/platform/mac/morning/test-run
#   launchctl kickstart gui/$(id -u)/com.$USER.kit.morning      (or .open, .weekly)
# Settings live in .install/shared/morning/config: OWNER_NAME, SKIP_DAYS, BLOCK_TOOLS, and the
# delivery keys DELIVERY (local | outlook-drafts | outlook-review | imessage), or DELIVERY_PERSONAL
# and DELIVERY_WORK to split them, DELIVERY_EMAIL_TO, IMESSAGE_TO, IMESSAGE_TO_ALT. Change them
# with kit-settings. Delivery itself is shared/deliver.py; it never sends mail.
# Auto-retry (RETRY_ON, default on; RETRY_DELAY seconds, default 120): one retry after a failure that
# looks transient (overload, rate limit, network, an API 5xx or 529); never after a timeout or refusal.
# Degraded mode (DEGRADED_MODE, default on): at the budget's stop level, and whenever the morning
# model run fails or times out, kit-degraded writes the brief from Kit's files with no model call.
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

# Kill switch: while kit-pause is on, no scheduled run starts (the test-run marker is left alone).
if [ -f "$KIT/.install/PAUSED" ]; then
  echo "== $(date) $MODE run skipped: Kit is paused ($(head -1 "$KIT/.install/PAUSED")); kit-pause resume to restart" >> "$LOG"
  exit 0
fi

case "$MODE" in
  open)   PROMPT="$SHAREDIR/prompt-open.md";   TEXT="briefs/open-text.txt" ;;
  weekly) PROMPT="$SHAREDIR/prompt-weekly.md"; TEXT="briefs/weekly-text.txt" ;;
  journal) PROMPT="$SHAREDIR/prompt-journal.md"; TEXT="briefs/journal-text.txt" ;;
  worklist) PROMPT="$SHAREDIR/prompt-worklist.md"; TEXT="briefs/worklist-text.txt" ;;
  eod)    [ "${EOD:-on}" = "off" ] && exit 0; PROMPT="$SHAREDIR/prompt-eod.md"; TEXT="briefs/eod-text.txt" ;;
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
    worklist)     brief="briefs/worklist-$TODAY.md" ;;
  esac
  local dargs=(--mode "$MODE" --text "$1")
  [ "${2:-}" != "nobrief" ] && [ -n "$brief" ] && [ -f "$brief" ] && dargs+=(--brief "$brief")
  [ -n "$TEST" ] && dargs+=(--test)
  python3 "$KIT/.install/shared/deliver.py" "${dargs[@]}"
}

cd "$KIT" || exit 1
rm -f "$TEXT" "${TEXT%.txt}-work.txt" "${TEXT%.txt}-personal.txt"   # never resend an old text

# Budget guard (kit-cost): at the stop level only the essential runs go ahead; the others skip, with
# one notice a day. Without a budget, or without kit-cost, every run goes ahead.
COST_LEVEL="ok"; COST_PCT=""
if [ -f "$KIT/.install/shared/bin/kit-cost" ]; then
  COST_LINE=$(python3 "$KIT/.install/shared/bin/kit-cost" check --mode "$MODE" 2>/dev/null)
  COST_LEVEL=${COST_LINE%% *}
  COST_PCT=$(print -r -- "$COST_LINE" | cut -d' ' -f2 | tr -d ';')
  case "$COST_LEVEL" in ok|warn|stop) ;; *) COST_LEVEL="ok" ;; esac
  if [ "$COST_LEVEL" = "stop" ] && [[ " ${COST_ESSENTIAL_MODES:-morning} " != *" $MODE "* ]]; then
    echo "== $(date) $MODE run skipped: $COST_PCT of the monthly budget used (stop at ${COST_STOP_PCT:-95}%)" >> "$LOG"
    if [ ! -f "$LOGDIR/$TODAY.cost-notice" ]; then
      echo "Kit budget: $COST_PCT of this month's budget is used, so Kit skipped its $MODE run. The morning brief still runs. See: kit-cost" > "$LOGDIR/cost-notice.txt"
      deliver "$LOGDIR/cost-notice.txt" nobrief >> "$LOG" 2>&1 && touch "$LOGDIR/$TODAY.cost-notice"
    fi
    exit 0
  fi
fi
# Degraded mode: at the stop level the morning brief is written from Kit's files, with no model call.
DEGRADED_REASON=""
if [ "$MODE" = "morning" ] && [ "$COST_LEVEL" = "stop" ] && [ "${DEGRADED_MODE:-on}" != "off" ] \
   && [ -f "$KIT/.install/shared/bin/kit-degraded" ]; then
  DEGRADED_REASON="$COST_PCT of this month's budget is used (stop at ${COST_STOP_PCT:-95}%)"
fi
if [ "$MODE" = "morning" ] || [ "$MODE" = "weekly" ]; then
  # Outlook self-recovery: check Outlook answers, retrying if it's slow (never starts or quits it).
  # If it still doesn't answer, the brief marks calendar and mail stale instead of skipping them.
  OUTLOOK_STATUS=""
  if [ "${OUTLOOK_CHECK:-on}" != "off" ] && [ -f "$KIT/.install/shared/bin/kit-outlook" ]; then
    python3 "$KIT/.install/shared/bin/kit-outlook" check --retry --write briefs/outlook.txt >> "$LOG" 2>&1
    OUTLOOK_STATUS=$(cut -d' ' -f1 briefs/outlook.txt 2>/dev/null)
  fi
  python3 "$KIT/.install/shared/doctor.py" --brief > briefs/health.txt 2>&1
  [ "$MODE" = "weekly" ] && AUDIT=--weekly || AUDIT=--daily
  python3 "$KIT/.install/shared/bin/kit-audit" "$AUDIT" >/dev/null 2>&1
fi
PROMPT_TEXT=$(sed "s/{{OWNER}}/${OWNER_NAME:-the owner}/g" "$PROMPT")
if [ "$MODE" = "morning" ] || [ "$MODE" = "weekly" ]; then
  case "$OUTLOOK_STATUS" in
    not-responding|blocked|error)
      PROMPT_TEXT+=$'\n\n'"Outlook check before this run: $(cut -d' ' -f4- briefs/outlook.txt). Don't call the Outlook calendar or mail commands. In the brief, put this line under both the Calendar and the Mail headings: \"Stale: $(cut -d' ' -f4- briefs/outlook.txt)\" Add \"Outlook: restart it\" as the second line of every short text." ;;
  esac
  # Records retention: show active legal holds at the top of the brief.
  if [ -f "$KIT/.install/shared/bin/kit-retention" ]; then
    HOLDS=$(python3 "$KIT/.install/shared/bin/kit-retention" holds --brief 2>/dev/null)
    [ -n "$HOLDS" ] && PROMPT_TEXT+=$'\n\n'"Active legal holds (nothing in these projects may be deleted, moved, or rewritten; list them in a \"Legal holds\" section near the top of the brief, by project name only): $HOLDS"
  fi
fi
case "$COST_LEVEL" in
  warn|stop)
    PROMPT_TEXT+=$'\n\n'"Budget: $COST_PCT of this month's budget for Kit's scheduled runs is used. Add the line \"Budget: $COST_PCT used\" to the health section of what you write and as the last line before the closing line of every short text."
    if [ "$MODE" = "weekly" ]; then
      PROMPT_TEXT+=" Keep this run lean: skip the horizon scan's researcher call (list the due items only) and the optional parts of the monthly retrospective (keep only the three most important points)."
    fi ;;
esac
# Tools the unattended run may use: the basics, plus extras from config (permission rules separated
# by semicolons, since rules can contain spaces), for example the mail and calendar commands the
# setup files name. ALLOW_TOOLS_WEEKLY adds more for the weekly review, such as the Agent tool for
# the auditor. One --allowedTools list.
ALLOWED=("Bash(date:*)" "Edit(~/Claude/Agents/kit/briefs/**)" "Edit(~/Claude/Agents/kit/journal/**)"
         "Bash(python3 ~/Claude/Agents/kit/.install/shared/bin/kit-queue hygiene:*)"
         "Bash(python3 $HOME/Claude/Agents/kit/.install/shared/bin/kit-queue hygiene:*)")
for r in "${(@s:;:)ALLOW_TOOLS:-}"; do r="${r## }"; r="${r%% }"; [ -n "$r" ] && ALLOWED+=("$r"); done
if [ "$MODE" = "weekly" ]; then
  for r in "${(@s:;:)ALLOW_TOOLS_WEEKLY:-}"; do r="${r## }"; r="${r%% }"; [ -n "$r" ] && ALLOWED+=("$r"); done
fi
# A rule written with ~/ doesn't match a command the run spells with the full home path, so each
# Bash rule with ~/ also gets a twin with $HOME spelled out.
for r in "${ALLOWED[@]}"; do
  if [[ "$r" == Bash\(*"~/"* ]]; then t="${r//\~\//$HOME/}"; (( ${ALLOWED[(Ie)$t]} )) || ALLOWED+=("$t"); fi
done
args=(-p "$PROMPT_TEXT" --output-format json --allowedTools "${ALLOWED[@]}")
[ -n "${BLOCK_TOOLS:-}" ] && args+=(--disallowedTools ${=BLOCK_TOOLS})
# Model for this run: kit-models apply writes MODEL_<MODE> lines to models.env (for example
# MODEL_WEEKLY=sonnet). Without it, the run uses Claude Code's default model.
[ -f "$SHAREDIR/models.env" ] && source "$SHAREDIR/models.env"
RUN_MODEL_VAR="MODEL_${(U)MODE}"
[ -n "${(P)RUN_MODEL_VAR:-}" ] && args+=(--model "${(P)RUN_MODEL_VAR}")

# Time limit for this run, in seconds. The weekly review does the most (auditor, horizon scan,
# sprint review, cost, retrospective), so it gets longer. Override with RUN_TIMEOUT_<MODE> or
# RUN_TIMEOUT in the config.
case "$MODE" in
  weekly)   TIMEOUT=${RUN_TIMEOUT_WEEKLY:-3000} ;;
  worklist) TIMEOUT=${RUN_TIMEOUT_WORKLIST:-900} ;;
  *)        TIMEOUT=${RUN_TIMEOUT:-1200} ;;
esac

# One scheduled run at a time: if another is still going (say, a long weekly review when the
# morning brief starts), wait for it, up to RUN_LOCK_WAIT seconds, then go ahead anyway. A lock
# left by a run that died is cleared.
LOCKDIR="$LOGDIR/.run.lock"
waited=0; OWN_LOCK=""
while true; do
  if mkdir "$LOCKDIR" 2>/dev/null; then OWN_LOCK=1; break; fi
  holder=$(cat "$LOCKDIR/pid" 2>/dev/null)
  if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
    rm -rf "$LOCKDIR"; continue
  fi
  if [ "$waited" -ge "${RUN_LOCK_WAIT:-1800}" ]; then
    echo "== $(date) $MODE: another run still holds the lock after ${waited}s; going ahead" >> "$LOG"
    break
  fi
  [ "$waited" -eq 0 ] && echo "== $(date) $MODE: waiting for another run to finish" >> "$LOG"
  sleep 15; waited=$((waited + 15))
done
if [ -n "$OWN_LOCK" ]; then
  echo $$ > "$LOCKDIR/pid"
  trap 'rm -rf "$LOCKDIR"' EXIT
fi

echo "== $(date) start $MODE ${TEST}" >> "$LOG"
# JSON output carries the text result plus the run's estimated cost and token counts. kit-cost
# writes the text to the log and the cost to the ledger; if the output isn't JSON it logs it as is.
RUNOUT="$LOGDIR/.run-$MODE-$$.json"
RUNERR="$LOGDIR/.run-$MODE-$$.err"
rc=0; TIMED_OUT=""
# One claude attempt: output to RUNOUT, stderr to RUNERR (and the log); then record its cost.
run_claude() {
  : > "$RUNERR"
  perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" claude "${args[@]}" > "$RUNOUT" 2> "$RUNERR"
  rc=$?
  cat "$RUNERR" >> "$LOG"
  [ "$rc" -eq 142 ] && TIMED_OUT=1 && echo "== $(date) $MODE run hit its time limit ($((TIMEOUT / 60)) min) and was stopped" >> "$LOG"
  if [ -f "$KIT/.install/shared/bin/kit-cost" ]; then
    python3 "$KIT/.install/shared/bin/kit-cost" record --mode "$MODE" --rc "$rc" --json-file "$RUNOUT" --log "$LOG" 2>> "$LOG" \
      || cat "$RUNOUT" >> "$LOG"
  else
    cat "$RUNOUT" >> "$LOG"
  fi
}
# Auto-retry (RETRY_ON, default on): retry once, after RETRY_DELAY seconds (default 120), when the
# run failed in a way that looks transient (overload, rate limit, network, a 5xx or 529 from the
# API) and wrote no text. Never after a timeout, or a refusal over permissions or policy.
transient_reason() {
  local blob p hit; blob="$(cat "$RUNERR" "$RUNOUT" 2>/dev/null)"
  print -r -- "$blob" | grep -qiE 'permission|not allowed|denied|refus|policy' && return 1
  # Most specific first, so the log names the actual cause.
  for p in 'overload(ed)?' 'rate.?limit(ed)?' 'too many requests' '(^|[^0-9])(429|500|502|503|504|529)([^0-9]|$)' \
           'service unavailable' 'temporarily unavailable' 'ECONNRESET|ECONNREFUSED|ETIMEDOUT|ENOTFOUND' \
           'network (error|is unreachable)' 'connection (reset|refused|error)' 'api error'; do
    hit=$(print -r -- "$blob" | grep -oiE "$p" | head -1 | sed -E 's/^[^A-Za-z0-9]+//; s/[^A-Za-z0-9]+$//')
    [ -n "$hit" ] && { print -r -- "$hit"; return 0; }
  done
  return 1
}
if [ -n "$DEGRADED_REASON" ]; then
  echo "== $(date) $MODE: no model run ($DEGRADED_REASON); writing a degraded brief" >> "$LOG"
  : > "$RUNOUT"
else
  run_claude
  if [ "$rc" -ne 0 ] && [ -z "$TIMED_OUT" ] && [ ! -s "$TEXT" ] && [ "${RETRY_ON:-on}" != "off" ]; then
    WHY=$(transient_reason)
    if [ -n "$WHY" ]; then
      echo "== $(date) retrying $MODE after transient failure ($WHY)" >> "$LOG"
      sleep "${RETRY_DELAY:-120}"
      run_claude
    fi
  fi
fi
rm -f "$RUNOUT" "$RUNERR"
echo "== $(date) end $MODE rc=$rc" >> "$LOG"

# Degraded fallback: if the morning run wrote no short text (it failed, timed out, or the budget
# stopped it), kit-degraded writes the brief and texts from Kit's files so a brief still arrives.
if [ "$MODE" = "morning" ] && [ "${DEGRADED_MODE:-on}" != "off" ] && [ -f "$KIT/.install/shared/bin/kit-degraded" ]; then
  DR="$DEGRADED_REASON"
  if [ -z "$DR" ] && { [ -n "$TIMED_OUT" ] || [ ! -s "$TEXT" ]; }; then
    if [ -n "$TIMED_OUT" ]; then DR="the model run hit its $((TIMEOUT / 60))-minute limit"
    elif [ "$rc" -ne 0 ]; then DR="the model run failed (exit $rc)"
    else DR="the model run finished without writing the brief"; fi
    rm -f "$TEXT" "${TEXT%.txt}-work.txt" "${TEXT%.txt}-personal.txt"   # never deliver a stopped run's text
  fi
  if [ -n "$DR" ]; then
    DARGS=(--reason "$DR")
    case "$OUTLOOK_STATUS" in not-responding|blocked|error) DARGS+=(--no-calendar) ;; esac
    python3 "$KIT/.install/shared/bin/kit-degraded" "${DARGS[@]}" >> "$LOG" 2>&1 \
      && echo "== degraded brief written ($DR)" >> "$LOG"
  fi
fi

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
  if [ -n "$TIMED_OUT" ]; then
    echo "Kit's $MODE run hit its $((TIMEOUT / 60))-minute limit and stopped before writing anything. Raise RUN_TIMEOUT_${(U)MODE} in the config if it keeps happening. Log: ~/Claude/Agents/kit/.install/logs/$TODAY.log" > "$LOGDIR/failure-$MODE.txt"
  else
    echo "Kit's $MODE run didn't finish (rc=$rc). Log: ~/Claude/Agents/kit/.install/logs/$TODAY.log" > "$LOGDIR/failure-$MODE.txt"
  fi
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
