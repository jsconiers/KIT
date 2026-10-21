#!/bin/bash
# Tests the Windows runner (platform/windows/morning/run.ps1) under PowerShell 7 (pwsh) on this
# machine: the model hook (models.env), per-run time limits, the one-run-at-a-time lock, the
# kit-pause kill switch, the kit-cost budget guard, cost recording from JSON output, and the weekly
# demand refresh. It uses a
# fake Kit and a fake claude in a throwaway folder. This exercises the script's logic, not Windows
# itself: Task Scheduler, NTFS, and the py launcher are still untested on a real Windows machine.
# Skips (passes) when pwsh or python isn't installed.
#   bash tests/test_runps1.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v pwsh >/dev/null 2>&1 || ! command -v python >/dev/null 2>&1; then
  echo "run.ps1 tests: skipped (needs pwsh and a 'python' command)"; exit 0
fi
S="$(mktemp -d)"; HOLDER=""; trap 'kill $HOLDER 2>/dev/null; rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
KIT="$S/home/Claude/Agents/kit"
M="$KIT/.install/shared/morning"
mkdir -p "$M" "$KIT/.install/shared/bin" "$KIT/.install/logs" "$KIT/briefs" "$S/bin"
cp "$HERE/shared/morning/prompt.md" "$HERE/shared/morning/prompt-worklist.md" "$HERE/shared/morning/prompt-weekly.md" "$M/"
cp "$HERE/shared/bin/kit-cost" "$KIT/.install/shared/bin/"
LOG="$KIT/.install/logs/$(date +%Y-%m-%d).log"
LEDGER="$KIT/.install/logs/cost.jsonl"
run() { USERPROFILE="$S/home" KIT_DIR="$KIT" PATH="$S/bin:$PATH" pwsh -NoProfile -File "$HERE/platform/windows/morning/run.ps1" "$1" >/dev/null 2>&1; }
fresh() { rm -f "$KIT/.install/logs/"*.done "$LOG" "$S/claude-args.txt" "$KIT/briefs/"*-text*.txt; }

# Fake claude: records its arguments, sleeps FAKE_SLEEP, writes the short texts, prints JSON.
cat > "$S/bin/claude" <<EOF
#!/bin/bash
printf "%s\\n" "\$@" > "$S/claude-args.txt"
sleep \${FAKE_SLEEP:-0} || exit 1   # a killed run stops here, as a real claude process would
[ -n "\${FAKE_FAIL:-}" ] && exit 3
if [ -n "\${FAKE_FLAKY:-}" ]; then
  n=\$(cat "$S/flaky-count" 2>/dev/null || echo 0); n=\$((n+1)); echo \$n > "$S/flaky-count"
  if [ "\$n" -le "\$FAKE_FLAKY" ]; then echo "\${FAKE_ERRMSG:-API Error: 529 Overloaded}" >&2; exit 1; fi
fi
echo "Kit test" > "$KIT/briefs/latest-text.txt"
echo "Kit test" > "$KIT/briefs/worklist-text.txt"
echo "a warning on stderr" >&2
echo '{"type":"result","result":"done","total_cost_usd":0.02,"usage":{},"modelUsage":{"claude-sonnet-5-5":{"costUSD":0.02,"inputTokens":5,"outputTokens":3}}}'
EOF
chmod +x "$S/bin/claude"

# ---- JSON output, cost recording, model hook --------------------------------------------------
printf 'DELIVERY="local"\n' > "$M/config"
fresh; run morning
grep -qx -- "json" "$S/claude-args.txt" && ok "asks claude for JSON output" || bad "json flag"
grep -qx -- "--model" "$S/claude-args.txt" && bad "no models.env: no --model" || ok "no models.env: no --model flag"
[ -f "$LEDGER" ] && grep -q '"model": "claude-sonnet-5-5"' "$LEDGER" && ok "cost reaches the ledger, with the model" || bad "ledger"
grep -q "^done$" "$LOG" && grep -q "a warning on stderr" "$LOG" && ok "result text and stderr both reach the log" || bad "log text"
printf 'MODEL_MORNING=sonnet\n' > "$M/models.env"
fresh; run morning
grep -A1 -x -- "--model" "$S/claude-args.txt" | grep -qx sonnet && ok "models.env: morning gets --model sonnet" || bad "models.env"
rm -f "$M/models.env"

# ---- worklist mode -----------------------------------------------------------------------------
fresh; run worklist
grep -q "start worklist" "$LOG" && ok "worklist mode runs" || bad "worklist mode"

# ---- time limit ----------------------------------------------------------------------------------
printf 'DELIVERY="local"\nRUN_TIMEOUT_WORKLIST="3"\n' > "$M/config"
fresh; FAKE_SLEEP=8 run worklist
grep -q "worklist run hit its time limit" "$LOG" && ok "timeout: stopped at RUN_TIMEOUT_WORKLIST, logged" || bad "timeout log"
grep -q "limit and stopped before writing anything" "$KIT/.install/logs/failure-worklist.txt" 2>/dev/null \
  && ok "timeout: failure notice says it hit the limit" || bad "timeout notice"
pgrep -f "kit-worklist-" >/dev/null && bad "timeout: claude process still running" || ok "timeout: the claude process was stopped (found by run id)"
sleep 7
[ ! -f "$KIT/briefs/worklist-text.txt" ] && ok "timeout: no late text from the stopped run" || bad "timeout: late text"
! grep -q "== delivered" "$LOG" && ok "timeout: nothing delivered as if it succeeded" || bad "timeout delivered"

# ---- kill switch ---------------------------------------------------------------------------------
printf 'DELIVERY="local"\n' > "$M/config"
echo "testing" > "$KIT/.install/PAUSED"
fresh; run morning
grep -q "run skipped: Kit is paused (testing)" "$LOG" && [ ! -f "$S/claude-args.txt" ] && ok "kit-pause: run skipped, claude not called" || bad "pause"
rm -f "$KIT/.install/PAUSED"

# ---- budget guard ----------------------------------------------------------------------------------
echo "{\"date\":\"$(date +%Y-%m)-01T08:00:00\",\"mode\":\"morning\",\"cost_usd\":96}" > "$LEDGER"
printf 'DELIVERY="local"\nCOST_BUDGET_MONTHLY="100"\n' > "$M/config"
fresh; run worklist
grep -q "worklist run skipped:" "$LOG" && [ ! -f "$S/claude-args.txt" ] && ok "budget: worklist skips at the stop level" || bad "budget skip"
fresh; run morning
grep -q "Budget:" "$S/claude-args.txt" && ok "budget: morning runs with the budget line" || bad "budget morning"
rm -f "$LEDGER"; printf 'DELIVERY="local"\nRUN_LOCK_WAIT="15"\n' > "$M/config"

# ---- lock ------------------------------------------------------------------------------------------
mkdir -p "$KIT/.install/logs/.run.lock"; sleep 60 & HOLDER=$!; echo $HOLDER > "$KIT/.install/logs/.run.lock/pid"
fresh; start=$(date +%s); run morning; took=$(( $(date +%s) - start ))
grep -q "waiting for another run to finish" "$LOG" && ok "lock: waits while another run holds it" || bad "lock wait"
grep -q "still holds the lock after" "$LOG" && [ "$took" -ge 15 ] && ok "lock: goes ahead after RUN_LOCK_WAIT ($took s)" || bad "lock give-up ($took s)"
[ "$(cat "$KIT/.install/logs/.run.lock/pid" 2>/dev/null)" = "$HOLDER" ] \
  && ok "lock: a run that went ahead leaves the other run's lock alone" || bad "lock taken over or removed"
kill $HOLDER 2>/dev/null; wait $HOLDER 2>/dev/null; HOLDER=""
echo 999999 > "$KIT/.install/logs/.run.lock/pid"
fresh; start=$(date +%s); run morning; took=$(( $(date +%s) - start ))
[ "$took" -lt 12 ] && ! grep -q "waiting for another run" "$LOG" && ok "lock: a dead run's lock is cleared at once" || bad "stale lock ($took s)"
[ ! -d "$KIT/.install/logs/.run.lock" ] && ok "lock: released when the run ends" || bad "lock not released"

# ---- degraded mode ---------------------------------------------------------------------------
rm -rf "$KIT/.install/logs/.run.lock"
cp "$HERE/shared/bin/kit-degraded" "$KIT/.install/shared/bin/"; cp "$HERE/shared/kit_daily.py" "$KIT/.install/shared/"
BRIEF="$KIT/briefs/$(date +%Y-%m-%d).md"
printf 'OUTLOOK_CHECK="off"\n' > "$M/config"
fresh; rm -f "$BRIEF"; FAKE_FAIL=1 run morning
grep -q "Degraded brief: written without a model" "$BRIEF" 2>/dev/null && grep -q "degraded brief written" "$LOG" \
  && ok "degraded: a failed morning run still produces a brief" || bad "degraded after failure"
grep -q "Degraded brief (no model)" "$KIT/briefs/latest-text.txt" 2>/dev/null && ok "degraded: short text written" || bad "degraded text"
printf 'OUTLOOK_CHECK="off"\nDEGRADED_MODE="off"\n' > "$M/config"
fresh; rm -f "$BRIEF"; FAKE_FAIL=1 run morning
[ ! -f "$BRIEF" ] && grep -q "sent failure notice" "$LOG" && ok "degraded: DEGRADED_MODE=off keeps the failure notice" || bad "degraded off"
rm -f "$KIT/.install/shared/bin/kit-degraded"

# ---- auto-retry -------------------------------------------------------------------------------
calls() { cat "$S/flaky-count" 2>/dev/null || echo 0; }
printf 'OUTLOOK_CHECK="off"\nRETRY_DELAY="0"\n' > "$M/config"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 run worklist
grep -q "retrying worklist after transient failure (Overloaded)" "$LOG" && [ "$(calls)" = "2" ] \
  && ok "retry: an overload is retried once" || bad "retry after overload ($(calls) calls)"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=2 run worklist
[ "$(grep -c "retrying worklist" "$LOG")" = "1" ] && [ "$(calls)" = "2" ] && ok "retry: only one retry" || bad "one retry ($(calls))"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 FAKE_ERRMSG="Error: permission denied" run worklist
! grep -q "retrying" "$LOG" && ok "retry: a refusal is not retried" || bad "refusal retried"
printf 'OUTLOOK_CHECK="off"\nRETRY_DELAY="0"\nRETRY_ON="off"\n' > "$M/config"
fresh; rm -f "$S/flaky-count"; FAKE_FLAKY=1 run worklist
! grep -q "retrying" "$LOG" && [ "$(calls)" = "1" ] && ok "retry: RETRY_ON=off turns it off" || bad "RETRY_ON off"
rm -f "$S/flaky-count"

# ---- connector health line (morning only) -------------------------------------------------------
grep -q 'connector_health.py' "$HERE/platform/windows/morning/run.ps1" && grep -q 'CONNECTOR_CHECK' "$HERE/platform/windows/morning/run.ps1" \
  && ok "connectors: run.ps1 calls connector_health.py and honours CONNECTOR_CHECK" || bad "connector wiring"
cp "$HERE/shared/morning/connector_health.py" "$M/"
KC="$KIT/.install/shared/bin/kit-connect"
cat > "$KC" <<'KC'
import json, os, sys, time
time.sleep(float(os.environ.get("FAKE_KC_SLEEP", "0")))
assert sys.argv[1:] == ["test", "--json"], sys.argv
print(json.dumps({"read": False, "servers": [
    {"server": "tracker", "pass": True, "checks": []},
    {"server": "wiki", "pass": False, "checks": [{"check": "health", "pass": False, "detail": "Failed to connect"}]}]}))
KC
printf 'OUTLOOK_CHECK="off"\n' > "$M/config"
fresh; run morning
grep -qF "Connectors: tracker PASS; wiki FAIL (health: Failed to connect)." "$S/claude-args.txt" \
  && ok "connectors: one PASS/FAIL line per server reaches the morning prompt" || bad "connector line"
printf 'OUTLOOK_CHECK="off"\nCONNECTOR_CHECK_TIMEOUT="2"\n' > "$M/config"
fresh; start=$(date +%s); FAKE_KC_SLEEP=20 run morning; took=$(( $(date +%s) - start ))
grep -qF "didn't finish in 2 s" "$S/claude-args.txt" && [ "$took" -lt 15 ] && grep -q "start morning" "$LOG" \
  && ok "connectors: a hung kit-connect is stopped at the limit ($took s) and the run goes on" || bad "connector timeout ($took s)"
printf 'OUTLOOK_CHECK="off"\nCONNECTOR_CHECK="off"\n' > "$M/config"
fresh; run morning
! grep -q "Connector check" "$S/claude-args.txt" && ok "connectors: CONNECTOR_CHECK=off skips it" || bad "connector off"
rm -f "$KC" "$M/connector_health.py"

# ---- weekly demand refresh (DEMAND_REFRESH) -----------------------------------------------------
P="$HERE/platform/windows/morning/run.ps1" pwsh -NoProfile -Command '$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile($env:P,[ref]$null,[ref]$e); exit $e.Count' \
  && ok "demands: run.ps1 parses" || bad "run.ps1 parse errors"
grep -q 'demand_refresh.py' "$HERE/platform/windows/morning/run.ps1" && grep -q '"DEMAND_REFRESH" "off"' "$HERE/platform/windows/morning/run.ps1" \
  && ok "demands: run.ps1 calls demand_refresh.py, off by default" || bad "demands wiring"
mkdir -p "$KIT/memory/context"
cp "$HERE/shared/morning/demand_refresh.py" "$HERE/shared/morning/prompt-demand-refresh.md" "$M/"
cp "$HERE/shared/bin/connector-guard" "$KIT/.install/shared/bin/"
printf '{"allowed_servers": ["tracker"], "allow_tools": ["mcp__tracker__get_demand", "mcp__tracker__create_demand"]}\n' \
  > "$KIT/memory/context/connector-guard.json"
ARGS="$S/claude-args.txt"
DCONF='OUTLOOK_CHECK="off"\nDEMAND_SERVER="tracker"\nDEMAND_REGISTER_DIR="~/library/demands"\n'
printf "$DCONF" > "$M/config"
fresh; run weekly
! grep -q "Demand refresh" "$ARGS" && ! grep -q "mcp__tracker" "$ARGS" && ok "demands: off by default" || bad "demands default off"
printf "${DCONF}DEMAND_REFRESH=\"on\"\n" > "$M/config"
fresh; run weekly
grep -q "Demand refresh (DEMAND_REFRESH is on)" "$ARGS" && grep -qxF "mcp__tracker__get_demand" "$ARGS" && grep -qxF "Agent" "$ARGS" \
  && grep -qxF "Edit(~/library/demands/**)" "$ARGS" && ! grep -q "create_demand" "$ARGS" \
  && ok "demands: on, the brief and only the read tools are added" || bad "demands on"
fresh; run morning
! grep -q "Demand refresh" "$ARGS" && ! grep -q "mcp__tracker" "$ARGS" && ok "demands: the morning run is unaffected" || bad "demands morning"
printf 'OUTLOOK_CHECK="off"\nDEMAND_REFRESH="on"\n' > "$M/config"
fresh; run weekly
grep -q "Refresh skipped: DEMAND_SERVER isn't set" "$ARGS" && ! grep -q "mcp__" "$ARGS" && ok "demands: incomplete setup is skipped with a line" || bad "demands skip"
rm -f "$M/demand_refresh.py" "$M/prompt-demand-refresh.md" "$KIT/memory/context/connector-guard.json"

echo "run.ps1 tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
