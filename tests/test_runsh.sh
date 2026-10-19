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

echo "run.sh tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
