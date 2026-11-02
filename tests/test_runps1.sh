#!/bin/bash
# Tests the Windows runner (platform/windows/morning/run.ps1) under PowerShell 7 (pwsh) on this
# machine: the model hook (models.env), per-run time limits, the one-run-at-a-time lock, the
# kit-pause kill switch, the kit-cost budget guard, cost recording from JSON output, the weekly
# demand refresh, the end-of-day wrap, runs of your own, the dates, renewals, brief.d hooks, PPM
# Express pulse, and architecture digest sections, and the connection check's address and proxy. It uses a
# fake Kit and a fake claude in a throwaway folder. This exercises the script's logic, not Windows
# itself: Task Scheduler, NTFS, and the py launcher are still untested on a real Windows machine.
# Skips (passes) when pwsh or python isn't installed.
#   bash tests/test_runps1.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v pwsh >/dev/null 2>&1 || ! command -v python >/dev/null 2>&1; then
  echo "run.ps1 tests: skipped (needs pwsh and a 'python' command)"; exit 0
fi
S="$(mktemp -d)"; HOLDER=""; SRV=""; trap 'kill $HOLDER $SRV 2>/dev/null; rm -rf "$S"' EXIT
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
# A local stand-in for the API, so the connection check before each run never reaches the internet: every
# run probes it (ANTHROPIC_BASE_URL), with no proxy, unless a test sets its own address or proxy.
cat > "$S/srv.py" <<'PY'
import http.server, sys
log = open(sys.argv[2], "a")
class H(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        log.write(self.path + "\n"); log.flush()
        self.send_response(204); self.end_headers()
    def log_message(self, *a): pass
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(s.server_port))
s.serve_forever()
PY
python3 "$S/srv.py" "$S/port" "$S/hits" & SRV=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$S/port" ] && break; sleep 0.5; done
PORT=$(cat "$S/port")
export ANTHROPIC_BASE_URL="http://127.0.0.1:$PORT"
unset HTTPS_PROXY https_proxy HTTP_PROXY http_proxy NO_PROXY no_proxy
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
[ -s "$S/hits" ] && ok "connection check: the runs probe the local stand-in, not the internet" || bad "stand-in not probed"
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

# ---- end-of-day wrap (eod): kit-wrap, no model call ------------------------------------------------
B="$KIT/.install/shared/bin"
cat > "$B/kit-wrap" <<'PY'
import os, pathlib, sys
if os.environ.get("FAKE_WRAP_FAIL"):
    sys.exit(2)
assert sys.argv[1:] == ["--write"], sys.argv
b = pathlib.Path(__file__).resolve().parents[3] / "briefs"
(b / "eod-text.txt").write_text("Kit wrap: 3 done\n", encoding="utf-8")
print("wrap written")
PY
cp "$HERE/shared/morning/prompt-eod.md" "$M/"
printf 'OUTLOOK_CHECK="off"\nCONNECTION_CHECK="off"\n' > "$M/config"
fresh; run eod
grep -q "start eod (kit-wrap, no model)" "$LOG" && [ ! -f "$S/claude-args.txt" ] && grep -q "wrap written" "$LOG" \
  && ok "eod: kit-wrap writes the wrap, no model call" || bad "eod kit-wrap"
grep -q "== delivered" "$LOG" && [ -f "$KIT/.install/logs/$(date +%Y-%m-%d).eod.done" ] && ! grep -q "start morning" "$LOG" \
  && ok "eod: delivered, marked done, and no morning brief" || bad "eod delivered"
fresh; FAKE_WRAP_FAIL=1 run eod
grep -q "end-of-day wrap didn't finish (rc=2)" "$KIT/.install/logs/failure-eod.txt" 2>/dev/null && grep -q "sent failure notice" "$LOG" \
  && ok "eod: a failed wrap sends a failure notice" || bad "eod failure"
printf 'OUTLOOK_CHECK="off"\nCONNECTION_CHECK="off"\nEOD="off"\n' > "$M/config"
fresh; run eod
[ ! -f "$LOG" ] && [ ! -f "$S/claude-args.txt" ] && ok "eod: EOD=off skips it" || bad "eod off"
printf 'OUTLOOK_CHECK="off"\nCONNECTION_CHECK="off"\nEOD_MODEL="on"\n' > "$M/config"
fresh; run eod
EODLINE=$(grep -m1 -v '^\s*$' "$HERE/shared/morning/prompt-eod.md" | cut -c1-40)
grep -qF -- "$EODLINE" "$S/claude-args.txt" 2>/dev/null && grep -q "start eod" "$LOG" \
  && ok "eod: EOD_MODEL=on runs prompt-eod.md with Claude" || bad "eod model"
rm -f "$B/kit-wrap"

# ---- runs of your own (prompt-NAME.md, ALLOW_TOOLS_<NAME>) -----------------------------------------
mkdir -p "$KIT/.install/prompts"
echo "STANDUP PROMPT for {{OWNER}}" > "$KIT/.install/prompts/prompt-stand-up.md"
printf 'OUTLOOK_CHECK="off"\nCONNECTION_CHECK="off"\nOWNER_NAME="Robin"\nALLOW_TOOLS_STAND_UP="Bash(standup-tool:*)"\nALLOW_TOOLS="Bash(~/bin/kit-x:*)"\n' > "$M/config"
fresh; run stand-up
grep -q "STANDUP PROMPT for Robin" "$S/claude-args.txt" && grep -qxF "Bash(standup-tool:*)" "$S/claude-args.txt" \
  && grep -q "start stand-up" "$LOG" && ok "custom run: its prompt and ALLOW_TOOLS_<NAME>" || bad "custom run"
grep -qxF "Bash($S/home/bin/kit-x:*)" "$S/claude-args.txt" && grep -qxF "Bash(~/bin/kit-x:*)" "$S/claude-args.txt" \
  && ok "allowed tools: a ~/ Bash rule gets a full-path twin" || bad "~/ twin"
fresh; run nosuch
grep -q "start morning" "$LOG" && ! grep -q "STANDUP" "$S/claude-args.txt" && ok "an unknown mode is the morning brief" || bad "unknown mode"
fresh; run morning
! grep -qxF "Bash(standup-tool:*)" "$S/claude-args.txt" && ok "ALLOW_TOOLS_<NAME> stays with its run" || bad "mode tools leak"
rm -rf "$KIT/.install/prompts"

# ---- dates, renewals, brief.d hooks, PPM Express pulse, architecture digest ---------------------------
for t in kit-dates kit-expiry kit-ppmx kit-digest; do
  printf 'import sys\nprint("%s " + " ".join(sys.argv[1:]))\nprint("caf\\u00e9 line")\n' "$t" > "$B/$t"
done
echo '{}' > "$KIT/dates.json"; echo '{}' > "$KIT/expiry.json"
mkdir -p "$KIT/.install/brief.d"
printf 'import sys\nprint("Hook section")\nprint("mode " + sys.argv[1])\n' > "$KIT/.install/brief.d/good.py"
printf 'import sys\nprint("half")\nsys.exit(1)\n' > "$KIT/.install/brief.d/broken.py"
printf 'import sys\n' > "$KIT/.install/brief.d/quiet.py"
printf 'param($m)\nWrite-Output "PS section"\nWrite-Output "mode $m"\n' > "$KIT/.install/brief.d/pshook.ps1"
echo "notes" > "$KIT/.install/brief.d/README.txt"
DOW=$(date +%u); OTHER=$(( DOW % 7 + 1 ))
printf "OUTLOOK_CHECK=\"off\"\nCONNECTION_CHECK=\"off\"\nPPMX_PULSE=\"on\"\nPPMX_PULSE_DAY=\"$DOW\"\nARCH_DIGEST=\"on\"\nARCH_DIGEST_WHEN=\"every-run\"\n" > "$M/config"
fresh; run morning
grep -qx "kit-dates brief --queue" "$KIT/briefs/dates.txt" 2>/dev/null && grep -qx "kit-expiry brief --queue" "$KIT/briefs/renewals.txt" 2>/dev/null \
  && ok "dates and renewals: written before the morning brief, with --queue" || bad "dates/renewals morning"
grep -qx "café line" "$KIT/briefs/dates.txt" 2>/dev/null && ok "dates: the tool's UTF-8 output stays UTF-8" || bad "dates utf-8"
[ ! -f "$KIT/briefs/renewals-missing.txt" ] && ok "renewals: no missing list in the morning" || bad "missing in morning"
grep -qx "mode morning" "$KIT/briefs/extra-good.py.txt" 2>/dev/null && grep -qx "mode morning" "$KIT/briefs/extra-pshook.ps1.txt" 2>/dev/null \
  && ok "brief.d: .py and .ps1 hooks write their sections" || bad "hooks"
[ ! -f "$KIT/briefs/extra-broken.py.txt" ] && [ ! -f "$KIT/briefs/extra-quiet.py.txt" ] && [ ! -f "$KIT/briefs/extra-README.txt.txt" ] \
  && ok "brief.d: failing, silent, and non-program hooks leave nothing" || bad "hook cleanup"
grep -qx "kit-ppmx pulse --brief --save" "$KIT/briefs/extra-ppmx-pulse.txt" 2>/dev/null && ok "ppmx pulse: on its day, in the morning brief" || bad "pulse"
[ ! -f "$KIT/briefs/extra-arch-digest.txt" ] && ok "digest: not in the morning brief" || bad "digest in morning"
touch "$KIT/.install/platform/windows/morning/test-run" 2>/dev/null || { mkdir -p "$KIT/.install/platform/windows/morning"; touch "$KIT/.install/platform/windows/morning/test-run"; }
fresh; run morning
grep -qx "kit-dates brief" "$KIT/briefs/dates.txt" 2>/dev/null && ok "dates: a test run adds no to-dos (no --queue)" || bad "test run --queue"
fresh; run weekly
grep -qx "kit-expiry missing" "$KIT/briefs/renewals-missing.txt" 2>/dev/null && grep -qx "kit-dates brief" "$KIT/briefs/dates.txt" 2>/dev/null \
  && ok "weekly: dates, renewals, and the missing renewals list" || bad "weekly dates"
grep -qx "kit-digest --write --month last --brief" "$KIT/briefs/extra-arch-digest.txt" 2>/dev/null && [ ! -f "$KIT/briefs/extra-ppmx-pulse.txt" ] \
  && ok "digest: in the weekly review (ARCH_DIGEST on); no pulse there" || bad "digest weekly"
printf "OUTLOOK_CHECK=\"off\"\nCONNECTION_CHECK=\"off\"\nPPMX_PULSE=\"on\"\nPPMX_PULSE_DAY=\"$OTHER\"\n" > "$M/config"
fresh; run morning
[ ! -f "$KIT/briefs/extra-ppmx-pulse.txt" ] && ok "ppmx pulse: not on other days" || bad "pulse other day"
fresh; run weekly
[ ! -f "$KIT/briefs/extra-arch-digest.txt" ] && ok "digest: off by default" || bad "digest default"
rm -rf "$KIT/.install/brief.d" "$KIT/dates.json" "$KIT/expiry.json"
for t in kit-dates kit-expiry kit-ppmx kit-digest; do rm -f "$B/$t"; done

# ---- connection check: ANTHROPIC_BASE_URL, proxies -----------------------------------------------------
printf 'OUTLOOK_CHECK="off"\nCONNECTION_WAIT="0"\n' > "$M/config"
fresh; : > "$S/hits"; ANTHROPIC_BASE_URL="http://127.0.0.1:$PORT/gw" run worklist
grep -q "/gw" "$S/hits" && grep -q "start worklist" "$LOG" && [ -f "$S/claude-args.txt" ] \
  && ok "connection: probes ANTHROPIC_BASE_URL and goes ahead" || bad "connection base url"
fresh; ANTHROPIC_BASE_URL="http://127.0.0.1:1" run worklist
grep -q "no internet connection after 0s (http://127.0.0.1:1)" "$LOG" && [ ! -f "$S/claude-args.txt" ] \
  && ok "connection: an unreachable ANTHROPIC_BASE_URL skips the model run" || bad "connection unreachable"
printf 'OUTLOOK_CHECK="off"\nCONNECTION_WAIT="0"\nCONNECTION_URL="http://kit-probe.invalid/ping"\n' > "$M/config"
fresh; : > "$S/hits"; HTTPS_PROXY="http://127.0.0.1:$PORT" run worklist
grep -q "kit-probe.invalid/ping" "$S/hits" && [ -f "$S/claude-args.txt" ] \
  && ok "connection: goes through HTTPS_PROXY (CONNECTION_URL wins over the default)" || bad "connection proxy"
fresh; : > "$S/hits"; HTTPS_PROXY="http://127.0.0.1:$PORT" NO_PROXY="localhost,.invalid" run worklist
! grep -q "kit-probe" "$S/hits" && grep -q "no internet connection" "$LOG" \
  && ok "connection: NO_PROXY bypasses the proxy for its hosts" || bad "connection no_proxy"

# ---- Task Scheduler: the end-of-day task ------------------------------------------------------------------
RT="$HERE/platform/windows/morning/register-tasks.ps1"
grep -q '"Kit End of Day"' "$RT" && grep -q '"Kit End of Day"' "$HERE/platform/windows/morning/unregister-tasks.ps1" \
  && ok "tasks: the end-of-day task is registered and removed" || bad "eod task"
grep -A6 '"Kit End of Day"' "$RT" | grep -q '5:30pm' && grep -A6 '"Kit End of Day"' "$RT" | grep -q '3:30pm' \
  && grep -A6 '"Kit End of Day"' "$RT" | grep -q '"eod"' && ok "tasks: eod at 17:30 Mon-Thu and 15:30 Fri" || bad "eod task times"

# ---- Task Scheduler: register-tasks.ps1 run against stand-in ScheduledTasks cmdlets -------------------------
mkdir -p "$KIT/.install/platform/windows/morning"; touch "$KIT/.install/platform/windows/morning/run.ps1"
cat > "$S/fake-tasks.ps1" <<'PS'
$global:KitTasks = [System.Collections.Generic.List[object]]::new()
function New-ScheduledTaskPrincipal { [pscustomobject]@{} }
function New-ScheduledTaskSettingsSet { [pscustomobject]@{ ExecutionTimeLimit = "" } }
function New-ScheduledTaskAction { param($Execute, $Argument, $WorkingDirectory) [pscustomobject]@{ Argument = $Argument } }
function New-ScheduledTaskTrigger {
    param([switch]$Weekly, [switch]$Daily, [switch]$Once, [switch]$AtLogOn, $DaysOfWeek, $At, $RepetitionInterval, $RepetitionDuration)
    [pscustomobject]@{ Days = (@($DaysOfWeek) -join ","); At = "$At"
        Repetition = [pscustomobject]@{ Interval = "$RepetitionInterval"; Duration = "$RepetitionDuration" } }
}
function Unregister-ScheduledTask { }
function Register-ScheduledTask {
    param($TaskName, $TaskPath, $Action, $Trigger, $Principal, $Settings, $Description)
    $global:KitTasks.Add([pscustomobject]@{ Name = $TaskName; Argument = $Action.Argument
        Triggers = @($Trigger | ForEach-Object { "$($_.Days)@$($_.At) every $($_.Repetition.Interval) for $($_.Repetition.Duration)" }) })
}
& $env:RT | Out-Null
$global:KitTasks | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $env:OUT -Encoding UTF8
PS
USERPROFILE="$S/home" RT="$HERE/platform/windows/morning/register-tasks.ps1" OUT="$S/tasks.json" pwsh -NoProfile -File "$S/fake-tasks.ps1" >/dev/null 2>&1
python3 - "$S/tasks.json" "$S/meetprep-cmd.txt" > "$S/tasks-check.txt" <<'PY'
import json, sys
t = {x["Name"]: x for x in json.load(open(sys.argv[1], encoding="utf-8-sig"))}
mp, eod = t.get("Kit Meeting Prep", {}), t.get("Kit End of Day", {})
print("meetprep-trigger", mp.get("Triggers"))
print("eod-trigger", eod.get("Triggers"))
arg = mp.get("Argument", "")
open(sys.argv[2], "w").write(arg.split("-Command ", 1)[-1])
print("meetprep-arg", arg)
PY
grep -qF "meetprep-trigger ['Monday,Tuesday,Wednesday,Thursday,Friday@7:00am every 00:30:00 for 11:01:00']" "$S/tasks-check.txt" \
  && ok "tasks: meeting prep runs weekdays every 30 min from 07:00 to 18:00" || bad "meetprep trigger: $(grep meetprep-trigger "$S/tasks-check.txt")"
grep -qF "eod-trigger ['Monday,Tuesday,Wednesday,Thursday@5:30pm every  for ', 'Friday@3:30pm every  for ']" "$S/tasks-check.txt" \
  && ok "tasks: the end-of-day task's triggers, as registered" || bad "eod triggers: $(grep eod-trigger "$S/tasks-check.txt")"
grep -q "kit-meetprep' --from-config --minutes 45" "$S/tasks-check.txt" && grep -q "PAUSED" "$S/tasks-check.txt" \
  && ok "tasks: meeting prep runs kit-meetprep --from-config --minutes 45, unless paused" || bad "meetprep action"
# The task's command itself, run with a stand-in py: it runs kit-meetprep, and nothing while Kit is paused.
printf '#!/bin/bash\nprintf "%%s\\n" "$@" > "%s/py-args.txt"\n' "$S" > "$S/bin/py"; chmod +x "$S/bin/py"
rm -f "$S/py-args.txt"; PATH="$S/bin:$PATH" pwsh -NoProfile -Command "$(cat "$S/meetprep-cmd.txt")" >/dev/null 2>&1
grep -qx -- "--from-config" "$S/py-args.txt" 2>/dev/null && grep -qx -- "-3" "$S/py-args.txt" && ok "tasks: the meeting prep command runs (py -3)" || bad "meetprep command run"
echo testing > "$KIT/.install/PAUSED"; rm -f "$S/py-args.txt"
PATH="$S/bin:$PATH" pwsh -NoProfile -Command "$(cat "$S/meetprep-cmd.txt")" >/dev/null 2>&1
[ ! -f "$S/py-args.txt" ] && ok "tasks: the meeting prep command does nothing while Kit is paused" || bad "meetprep while paused"
rm -f "$KIT/.install/PAUSED" "$S/bin/py"
grep -q '"Kit Meeting Prep"' "$HERE/platform/windows/morning/unregister-tasks.ps1" && ok "tasks: unregister-tasks.ps1 removes meeting prep" || bad "meetprep unregister"

# ---- preflight.ps1: its paid login check asks for JSON and goes in the cost ledger -----------------------
mkdir -p "$S/pfbin"
cat > "$S/pfbin/claude" <<'SH'
#!/bin/bash
printf "%s\n" "$@" > "$PF_ARGS"
if [ -n "${PF_LOGGED_OUT:-}" ]; then echo "Not logged in · Please run /login" >&2; exit 1; fi
echo '{"type":"result","result":"OK","total_cost_usd":0.0004,"usage":{},"modelUsage":{"claude-haiku-4":{"costUSD":0.0004,"inputTokens":12,"outputTokens":2}}}'
SH
chmod +x "$S/pfbin/claude"
PFLOG="$KIT/.install/logs/preflight.log"
pf() { USERPROFILE="$S/home" KIT_DIR="$KIT" PF_ARGS="$S/pf-args.txt" PATH="$S/pfbin:$PATH" pwsh -NoProfile -File "$HERE/platform/windows/morning/preflight.ps1" >/dev/null 2>&1; }
rm -f "$LEDGER" "$PFLOG"; printf 'DELIVERY="local"\n' > "$M/config"
pf
grep -A1 -x -- "--output-format" "$S/pf-args.txt" | grep -qx json && ok "preflight: the login check asks for JSON output" || bad "preflight json"
grep -q '"mode": "preflight"' "$LEDGER" 2>/dev/null && ok "preflight: its paid check is in the cost ledger" || bad "preflight ledger"
grep -q "login ok" "$PFLOG" 2>/dev/null && ok "preflight: still reads the OK from the JSON" || bad "preflight ok: $(tail -1 "$PFLOG" 2>/dev/null)"
! grep -qi "kit-catalog" "$HERE/platform/windows/morning/preflight.ps1" && ok "preflight: no kit-catalog call" || bad "preflight kit-catalog"
PF_LOGGED_OUT=1 pf
grep -q "LOGGED OUT: Not logged in" "$PFLOG" 2>/dev/null && ok "preflight: a lapsed login is still caught" || bad "preflight logged out: $(tail -1 "$PFLOG" 2>/dev/null)"
ls "$KIT/.install/logs/".preflight-* >/dev/null 2>&1 && bad "preflight: temp files left" || ok "preflight: no temp files left"
rm -f "$LEDGER" "$KIT/.install/logs/login-lapsed"

echo "run.ps1 tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
