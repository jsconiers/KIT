#!/bin/bash
# Tests kit-cost and the budget guard in run.sh. Everything runs in a throwaway folder with a fake
# Kit and a fake claude; nothing real is touched, and no launchd job is loaded or unloaded.
#   bash tests/test_cost.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit"
CONF="$KIT_DIR/.install/shared/morning/config"
LEDGER="$KIT_DIR/.install/logs/cost.jsonl"
mkdir -p "$KIT_DIR/.install/shared/morning" "$KIT_DIR/.install/shared/bin" "$KIT_DIR/.install/logs" "$KIT_DIR/briefs"
cp "$BIN/kit-cost" "$KIT_DIR/.install/shared/bin/"
cp "$HERE/shared/morning/prompt.md" "$HERE/shared/morning/prompt-worklist.md" "$HERE/shared/morning/prompt-weekly.md" "$KIT_DIR/.install/shared/morning/"
echo 'OUTLOOK_CHECK="off"' > "$CONF"
TODAY=$(date +%Y-%m-%d)
LOG="$KIT_DIR/.install/logs/$TODAY.log"

# ---- kit-cost record: JSON output -> text in the log, one line in the ledger --------------------
cat > "$S/run.json" <<'EOF'
{"type":"result","subtype":"success","is_error":false,"duration_ms":61000,"duration_api_ms":50000,
 "num_turns":7,"result":"done","session_id":"s1","total_cost_usd":1.25,
 "usage":{"input_tokens":1000,"output_tokens":500,"cache_read_input_tokens":20000,"cache_creation_input_tokens":3000},
 "modelUsage":{}}
EOF
python3 "$BIN/kit-cost" record --mode morning --rc 0 --json-file "$S/run.json" --log "$S/t.log"
grep -q "^done$" "$S/t.log" && ok "record: text result written to the log" || bad "record text"
python3 - "$LEDGER" <<'EOF' && ok "record: ledger line with cost, tokens, duration, turns" || bad "record ledger"
import json, sys
rec = json.loads(open(sys.argv[1]).read().splitlines()[-1])
assert rec["cost_usd"] == 1.25 and rec["mode"] == "morning" and rec["input_tokens"] == 1000
assert rec["output_tokens"] == 500 and rec["cache_read_tokens"] == 20000 and rec["cache_write_tokens"] == 3000
assert rec["duration_ms"] == 61000 and rec["turns"] == 7 and rec["rc"] == 0
EOF
[ "$(stat -f %Lp "$LEDGER" 2>/dev/null || stat -c %a "$LEDGER")" = "600" ] && ok "record: ledger is owner-only" || bad "ledger perms"
echo "not json at all" > "$S/garbage.json"
n0=$(wc -l < "$LEDGER")
python3 "$BIN/kit-cost" record --mode weekly --rc 1 --json-file "$S/garbage.json" --log "$S/t.log"; rc=$?
[ $rc -eq 0 ] && grep -q "not json at all" "$S/t.log" && grep -q "wasn't JSON" "$S/t.log" && [ "$(wc -l < "$LEDGER")" = "$n0" ] \
  && ok "record: garbage output logged as is, no ledger line, exit 0" || bad "record garbage (rc=$rc)"

# ---- kit-cost math: spend, budget %, projection, check exit codes -------------------------------
rm -f "$LEDGER"
for d in 01 05 10; do
  echo "{\"date\":\"2026-03-${d}T08:00:00\",\"mode\":\"morning\",\"cost_usd\":10}" >> "$LEDGER"
done
echo '{"date":"2026-02-20T08:00:00","mode":"weekly","cost_usd":15}' >> "$LEDGER"
export KIT_COST_TODAY=2026-03-10
out=$(COST_BUDGET_MONTHLY=100 python3 "$BIN/kit-cost" check --json)
python3 - "$out" <<'EOF' && ok "math: \$30 of \$100 = 30%, projected \$93 for a 31-day month" || bad "math: $out"
import json, sys
st = json.loads(sys.argv[1])
assert st["spend_usd"] == 30 and st["pct_used"] == 30.0 and st["projection_usd"] == 93.0 and st["level"] == "ok", st
EOF
COST_BUDGET_MONTHLY=100 python3 "$BIN/kit-cost" check >/dev/null; [ $? -eq 0 ] && ok "check: exit 0 under the warning level" || bad "check ok"
COST_BUDGET_MONTHLY=35 python3 "$BIN/kit-cost" check >/dev/null; [ $? -eq 1 ] && ok "check: exit 1 at warn (86%)" || bad "check warn"
COST_BUDGET_MONTHLY=30 python3 "$BIN/kit-cost" check >/dev/null; [ $? -eq 2 ] && ok "check: exit 2 at stop (100%)" || bad "check stop"
python3 "$BIN/kit-cost" check >/dev/null; [ $? -eq 0 ] && ok "check: no budget means exit 0" || bad "check no budget"
COST_BUDGET_MONTHLY=30 python3 "$BIN/kit-cost" check --mode worklist | grep -q "should skip" \
  && COST_BUDGET_MONTHLY=30 python3 "$BIN/kit-cost" check --mode morning | grep -q "may go ahead" \
  && ok "check --mode: worklist skips at stop, morning goes ahead" || bad "check mode"
python3 "$BIN/kit-cost" report --month 2026-03 --json | python3 -c '
import json,sys; d=json.load(sys.stdin)
assert d["previous_spend_usd"]==15 and d["change_pct"]==100.0 and d["by_mode"]["morning"]["runs"]==3 and len(d["by_day"])==3, d' \
  && ok "report: by kind, by day, and +100% against the month before" || bad "report"
python3 "$BIN/kit-cost" | grep -q "Interactive sessions aren't counted" && ok "summary: says interactive sessions aren't counted" || bad "summary"
unset KIT_COST_TODAY

# ---- run.sh: budget guard and cost recording (fake claude prints JSON, records its prompt) -------
mkdir -p "$S/home/Claude/Agents" "$S/home/.local/bin"; ln -s "$KIT_DIR" "$S/home/Claude/Agents/kit"
cat > "$S/home/.local/bin/claude" <<EOF
#!/bin/bash
printf "%s\\n" "\$@" > "$S/claude-args.txt"
cat "$S/claude-out.json"
EOF
chmod +x "$S/home/.local/bin/claude"
cp "$S/run.json" "$S/claude-out.json"
MONTH=$(date +%Y-%m)
rm -f "$LEDGER"
echo "{\"date\":\"${MONTH}-01T08:00:00\",\"mode\":\"morning\",\"cost_usd\":96}" >> "$LEDGER"
printf 'OUTLOOK_CHECK="off"\nCOST_BUDGET_MONTHLY="100"\n' > "$CONF"

rm -f "$S/claude-args.txt" "$KIT_DIR/.install/logs/"*.done
HOME="$S/home" zsh "$HERE/platform/mac/morning/run.sh" worklist >/dev/null 2>&1
[ ! -f "$S/claude-args.txt" ] && grep -q "worklist run skipped: 96.0% of the monthly budget used" "$LOG" \
  && ok "run.sh: worklist skips at the stop level, with a log line" || bad "run.sh stop skip"

HOME="$S/home" zsh "$HERE/platform/mac/morning/run.sh" morning >/dev/null 2>&1
[ -f "$S/claude-args.txt" ] && grep -q "Budget: 96.0% used" "$S/claude-args.txt" \
  && ok "run.sh: morning still runs at the stop level, with the budget line" || bad "run.sh morning at stop"
grep -q -- "--output-format" "$S/claude-args.txt" && grep -qx "json" "$S/claude-args.txt" \
  && ok "run.sh: asks claude for JSON output" || bad "run.sh json flag"
[ "$(grep -cE '"mode": ?"morning"' "$LEDGER")" = 2 ] && grep -q "^done$" "$LOG" \
  && ok "run.sh: the run's cost reaches the ledger and its text the log" || bad "run.sh ledger"

printf 'OUTLOOK_CHECK="off"\nCOST_BUDGET_MONTHLY="120"\n' > "$CONF"   # ~81%: warn
rm -f "$S/claude-args.txt" "$KIT_DIR/.install/logs/"*.done
HOME="$S/home" zsh "$HERE/platform/mac/morning/run.sh" weekly >/dev/null 2>&1
grep -q "Budget: 8[0-9.]*% used" "$S/claude-args.txt" 2>/dev/null && grep -q "skip the horizon scan's researcher call" "$S/claude-args.txt" \
  && ok "run.sh: weekly at warn gets the budget line and the lean-run flag" || bad "run.sh weekly warn"

printf 'OUTLOOK_CHECK="off"\n' > "$CONF"   # no budget
echo "garbage, not json" > "$S/claude-out.json"
rm -f "$S/claude-args.txt" "$KIT_DIR/.install/logs/"*.done
n0=$(wc -l < "$LEDGER")
HOME="$S/home" zsh "$HERE/platform/mac/morning/run.sh" worklist >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ -f "$S/claude-args.txt" ] && ! grep -q "Budget:" "$S/claude-args.txt" && grep -q "garbage, not json" "$LOG" \
  && [ "$(wc -l < "$LEDGER")" = "$n0" ] && ok "run.sh: no budget -> runs, no budget line; garbage output logged, run not broken" \
  || bad "run.sh no budget / garbage (rc=$rc)"

# ---- doctor reports cost ------------------------------------------------------------------------
python3 - "$HERE/shared" "$KIT_DIR" <<'EOF' && ok "doctor: Cost check reports spend and budget" || bad "doctor cost"
import sys, pathlib, importlib.util, os
os.environ["COST_BUDGET_MONTHLY"] = "100"
spec = importlib.util.spec_from_file_location("doctor", f"{sys.argv[1]}/doctor.py"); doc = importlib.util.module_from_spec(spec); spec.loader.exec_module(doc)
doc.KIT = pathlib.Path(sys.argv[2]); doc.results.clear(); doc.check_cost()
assert doc.results and doc.results[0][1] == "Cost" and "% of $100 budget" in doc.results[0][2], doc.results
EOF

echo "kit-cost tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
