#!/bin/bash
# Tests run.sh's per-run time limits, the one-run-at-a-time lock, and the model hook (models.env).
# Everything runs in a throwaway folder with a fake Kit and a fake claude; nothing real is touched.
#   bash tests/test_runsh.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'kill $HOLDER 2>/dev/null; rm -rf "$S"' EXIT
HOLDER=""
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
KIT="$S/home/Claude/Agents/kit"
M="$KIT/.install/shared/morning"
mkdir -p "$M" "$KIT/.install/logs" "$KIT/briefs" "$S/home/.local/bin"
cp "$HERE/shared/morning/prompt.md" "$HERE/shared/morning/prompt-worklist.md" "$HERE/shared/morning/prompt-weekly.md" "$M/"
LOG="$KIT/.install/logs/$(date +%Y-%m-%d).log"
run() { HOME="$S/home" zsh "$HERE/platform/mac/morning/run.sh" "$1" >/dev/null 2>&1; }
fresh() { rm -f "$KIT/.install/logs/"*.done "$LOG" "$S/claude-args.txt" "$KIT/briefs/"*-text*.txt; }

# Fake claude: records its arguments, sleeps FAKE_SLEEP seconds, then writes the short text the
# prompt asks for (so delivery has something to send) and prints a JSON result.
cat > "$S/home/.local/bin/claude" <<EOF
#!/bin/bash
printf "%s\\n" "\$@" > "$S/claude-args.txt"
sleep \${FAKE_SLEEP:-0}
[ -n "\${FAKE_FAIL:-}" ] && exit 3
if [ -n "\${FAKE_FLAKY:-}" ]; then
  n=\$(cat "$S/flaky-count" 2>/dev/null || echo 0); n=\$((n+1)); echo \$n > "$S/flaky-count"
  if [ "\$n" -le "\$FAKE_FLAKY" ]; then echo "\${FAKE_ERRMSG:-API Error: 529 Overloaded}" >&2; exit 1; fi
fi
echo "Kit test" > "$KIT/briefs/latest-text.txt"
echo "Kit test" > "$KIT/briefs/worklist-text.txt"
echo '{"type":"result","result":"done","total_cost_usd":0.01,"usage":{}}'
EOF
chmod +x "$S/home/.local/bin/claude"

# ---- model hook ------------------------------------------------------------------------------
printf 'OUTLOOK_CHECK="off"\n' > "$M/config"
fresh; run morning
grep -qx -- "--model" "$S/claude-args.txt" && bad "no models.env: no --model flag" || ok "no models.env: no --model flag"
printf 'MODEL_MORNING=sonnet\nMODEL_WEEKLY=opus\n' > "$M/models.env"
fresh; run morning
grep -A1 -x -- "--model" "$S/claude-args.txt" | grep -qx sonnet && ok "models.env: morning run gets --model sonnet" || bad "models.env morning"
fresh; run worklist
grep -qx -- "--model" "$S/claude-args.txt" && bad "models.env: worklist without a line gets no --model" \
  || ok "models.env: a run with no line gets no --model"
rm -f "$M/models.env"

# ---- ~/ rules get a full-path twin ----------------------------------------------------------
printf 'OUTLOOK_CHECK="off"\nALLOW_TOOLS="Bash(python3 ~/Claude/Agents/kit/.install/shared/bin/kit-x:*)"\n' > "$M/config"
fresh; run morning
grep -qF "Bash(python3 $S/home/Claude/Agents/kit/.install/shared/bin/kit-x:*)" "$S/claude-args.txt" \
  && ok "a ~/ Bash rule also gets a full-path twin" || bad "full-path twin missing"
[ "$(grep -cF 'kit-queue hygiene:*' "$S/claude-args.txt")" = "2" ] && ok "rules that already have a twin aren't doubled" || bad "twin duplicated"

# ---- time limit ------------------------------------------------------------------------------
printf 'OUTLOOK_CHECK="off"\nRUN_TIMEOUT_WORKLIST="2"\n' > "$M/config"
fresh; FAKE_SLEEP=6 run worklist
grep -q "worklist run hit its time limit" "$LOG" && ok "timeout: stopped at RUN_TIMEOUT_WORKLIST with a log line" || bad "timeout log line"
grep -q "rc=142" "$LOG" && ok "timeout: exit code 142 recorded" || bad "timeout rc"
grep -q "limit and stopped before writing anything" "$KIT/.install/logs/failure-worklist.txt" 2>/dev/null \
  && ok "timeout: failure notice says it hit the limit" || bad "timeout notice"
grep -q 'RUN_TIMEOUT_WEEKLY:-3000' "$HERE/platform/mac/morning/run.sh" && ok "weekly default limit is 50 minutes" || bad "weekly default"

# ---- lock ------------------------------------------------------------------------------------
printf 'OUTLOOK_CHECK="off"\nRUN_LOCK_WAIT="15"\n' > "$M/config"
mkdir -p "$KIT/.install/logs/.run.lock"; sleep 60 & HOLDER=$!; echo $HOLDER > "$KIT/.install/logs/.run.lock/pid"
fresh; start=$(date +%s); run morning; took=$(( $(date +%s) - start ))
grep -q "waiting for another run to finish" "$LOG" && ok "lock: waits while another run holds it" || bad "lock wait line"
grep -q "still holds the lock after" "$LOG" && [ "$took" -ge 15 ] && ok "lock: goes ahead after RUN_LOCK_WAIT ($took s)" || bad "lock give-up ($took s)"
[ -d "$KIT/.install/logs/.run.lock" ] && [ "$(cat "$KIT/.install/logs/.run.lock/pid" 2>/dev/null)" = "$HOLDER" ] \
  && ok "lock: a run that went ahead leaves the other run's lock alone" || bad "lock taken over or removed"
kill $HOLDER 2>/dev/null; wait $HOLDER 2>/dev/null; HOLDER=""
# stale lock (dead pid) is cleared
echo 999999 > "$KIT/.install/logs/.run.lock/pid"
fresh; start=$(date +%s); run morning; took=$(( $(date +%s) - start ))
[ "$took" -lt 10 ] && ! grep -q "waiting for another run" "$LOG" && ok "lock: a dead run's lock is cleared at once" || bad "stale lock ($took s)"
[ ! -d "$KIT/.install/logs/.run.lock" ] && ok "lock: released when the run ends" || bad "lock not released"
grep -q "start morning" "$LOG" && ok "lock: run proceeds after clearing" || bad "run after stale lock"

# ---- degraded mode ---------------------------------------------------------------------------
rm -rf "$KIT/.install/logs/.run.lock"
mkdir -p "$KIT/.install/shared/bin"
cp "$HERE/shared/bin/kit-degraded" "$KIT/.install/shared/bin/"; cp "$HERE/shared/kit_daily.py" "$KIT/.install/shared/"
BRIEF="$KIT/briefs/$(date +%Y-%m-%d).md"
printf 'OUTLOOK_CHECK="off"\n' > "$M/config"
fresh; rm -f "$BRIEF"; FAKE_FAIL=1 run morning
grep -q "Degraded brief: written without a model because the model run failed (exit 3)" "$BRIEF" 2>/dev/null \
  && grep -q "degraded brief written" "$LOG" && ok "degraded: a failed morning run still produces a brief" || bad "degraded after failure"
[ -s "$KIT/briefs/latest-text.txt" ] && grep -q "Degraded brief (no model)" "$KIT/briefs/latest-text.txt" \
  && ok "degraded: short text written for delivery" || bad "degraded short text"
! grep -q "sent failure notice" "$LOG" && ok "degraded: no failure-only notice when a brief exists" || bad "failure notice still sent"
printf 'OUTLOOK_CHECK="off"\nRUN_TIMEOUT="2"\n' > "$M/config"
fresh; rm -f "$BRIEF"; FAKE_SLEEP=6 run morning
grep -q "hit its 0-minute limit\|hit its .*-minute limit" "$BRIEF" 2>/dev/null && grep -q "Degraded brief (no model)" "$KIT/briefs/latest-text.txt" \
  && ok "degraded: a timed-out morning run still produces a brief" || bad "degraded after timeout"
cat > "$KIT/.install/shared/bin/kit-cost" <<'KC'
import sys
if sys.argv[1:2] == ["check"]:
    print("stop 97%; budget 100")
    sys.exit(2)
KC
printf 'OUTLOOK_CHECK="off"\nCOST_STOP_PCT="95"\n' > "$M/config"
fresh; rm -f "$BRIEF"; run morning
[ ! -f "$S/claude-args.txt" ] && grep -q "because 97% of this month's budget is used" "$BRIEF" 2>/dev/null \
  && ok "degraded: at the budget stop level the morning brief is written without calling claude" || bad "stop-level degraded"
fresh; rm -f "$BRIEF"; run worklist
[ ! -f "$S/claude-args.txt" ] && grep -q "worklist run skipped" "$LOG" && [ ! -f "$BRIEF" ] \
  && ok "degraded: other runs still skip at the stop level" || bad "worklist at stop"
printf 'OUTLOOK_CHECK="off"\nDEGRADED_MODE="off"\n' > "$M/config"
fresh; rm -f "$BRIEF"; run morning
[ -f "$S/claude-args.txt" ] && [ ! -f "$BRIEF" ] && ok "degraded: DEGRADED_MODE=off keeps the old behaviour (claude runs)" || bad "degraded off"
rm -f "$KIT/.install/shared/bin/kit-cost"

# ---- auto-retry -------------------------------------------------------------------------------
calls() { cat "$S/flaky-count" 2>/dev/null || echo 0; }
printf 'OUTLOOK_CHECK="off"\nRETRY_DELAY="0"\n' > "$M/config"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 run worklist
grep -q "retrying worklist after transient failure (Overloaded)" "$LOG" && [ "$(calls)" = "2" ] && grep -q "end worklist rc=0" "$LOG" \
  && ok "retry: an overload is retried once and the second attempt succeeds" || bad "retry after overload ($(calls) calls)"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 FAKE_ERRMSG="HTTP 503 from upstream" run worklist
grep -q "retrying worklist after transient failure (503)" "$LOG" && ok "retry: an API 503 is retried" || bad "retry after 503"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 FAKE_ERRMSG="Error: rate limit exceeded" run worklist
grep -q "retrying worklist after transient failure (rate limit" "$LOG" && ok "retry: a rate limit is retried" || bad "retry after rate limit"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=2 run worklist
[ "$(grep -c "retrying worklist" "$LOG")" = "1" ] && [ "$(calls)" = "2" ] && grep -q "sent failure notice" "$LOG" \
  && ok "retry: only one retry; a second failure sends the failure notice" || bad "second failure ($(calls) calls)"
fresh; rm -f "$S/flaky-count" "$BRIEF"; FAKE_FLAKY=2 run morning
grep -q "retrying morning" "$LOG" && grep -q "degraded brief written" "$LOG" \
  && ok "retry: a morning run that fails twice falls back to the degraded brief" || bad "morning fails twice"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 FAKE_ERRMSG="Error: permission denied for tool" run worklist
! grep -q "retrying" "$LOG" && [ "$(calls)" = "1" ] && ok "retry: a permission refusal is not retried" || bad "refusal retried"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 FAKE_ERRMSG="something odd happened" run worklist
! grep -q "retrying" "$LOG" && ok "retry: an unrecognised failure is not retried" || bad "unknown failure retried"
printf 'OUTLOOK_CHECK="off"\nRETRY_DELAY="0"\nRUN_TIMEOUT_WORKLIST="2"\n' > "$M/config"
fresh; rm -f "$S/flaky-count"; FAKE_SLEEP=6 run worklist
! grep -q "retrying" "$LOG" && grep -q "hit its time limit" "$LOG" && ok "retry: a timeout is not retried" || bad "timeout retried"
printf 'OUTLOOK_CHECK="off"\nRETRY_DELAY="0"\nRETRY_ON="off"\n' > "$M/config"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 run worklist
! grep -q "retrying" "$LOG" && [ "$(calls)" = "1" ] && ok "retry: RETRY_ON=off turns it off" || bad "RETRY_ON off"
rm -f "$S/flaky-count"

echo "run.sh tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
