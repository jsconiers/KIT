#!/bin/bash
# Tests kit-metrics against a fake Kit folder. Nothing real is touched.
#   bash tests/test_metrics.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit"; K="$KIT_DIR"
mkdir -p "$K/.install/logs" "$K/.install/cache" "$K/briefs"
M=$(date +%Y-%m); D=$(date +%Y-%m-%d); DD=$(date +%d-%b-%Y)
cat > "$K/.install/logs/cost.jsonl" <<J
{"date":"${M}-01T07:45:00","mode":"morning","cost_usd":0.5,"model":"opus"}
{"date":"${M}-02T09:00:00","mode":"worklist","cost_usd":0.25}
not json
J
printf '== x start morning\n== x end morning rc=0\n== x start weekly\n== x end weekly rc=142\n== x worklist run skipped: paused\n== x end eod rc=1\n' > "$K/.install/logs/$D.log"
cat > "$K/QUEUE.md" <<Q
# Queue

## Alex
- [ ] **One** (added $DD)
  - [ ] Sub one

## Kit
- [ ] **Two** (added $DD)

## Done
- [x] **Three**: done $DD (added $DD)
Q
printf '# Work list\n\n1. **A**: S (approved)\n2. **B**: M (approved, done)\n3. **C**: S\n\n## Standby\n\n4. **D**: S\n' > "$K/briefs/worklist-$D.md"
echo '{"S1|2026-10-19":{"2026-10-19":10,"2026-10-20":7}}' > "$K/.install/cache/sprint-history.json"
printf 'WARN: Thing one: broken\nOK: fine\n' > "$K/briefs/health.txt"
echo '{"generated":"x","severity_counts":{"critical":0,"warning":1,"info":2}}' > "$K/briefs/audit-status.json"
J=$(python3 "$HERE/shared/bin/kit-metrics" --json)
py() { python3 -c "import json,sys;d=json.loads(sys.argv[1]);print($1)" "$J"; }
[ "$(py "round(d['cost']['by_month']['$M'],2)")" = "0.75" ] && ok "cost: month total, garbage line skipped" || bad "cost month"
[ "$(py "round(d['cost']['this_month_by_model']['opus'],2)")" = "0.5" ] && [ "$(py "round(d['cost']['this_month_by_model']['not recorded'],2)")" = "0.25" ] \
  && ok "cost: by model, unrecorded model labelled" || bad "cost model"
[ "$(py "(d['runs']['finished'],d['runs']['timed_out'],d['runs']['failed'],d['runs']['skipped'])")" = "(1, 1, 1, 1)" ] \
  && ok "runs: finished, timed out (142), failed, skipped" || bad "runs $(py "d['runs']")"
[ "$(py "(d['queue']['open_items'],d['queue']['open_sub_items'])")" = "(2, 1)" ] && ok "queue: open items and sub-items" || bad "queue"
[ "$(py "d['queue']['trend'][-1]['added']")" = "3" ] && [ "$(py "d['queue']['trend'][-1]['closed']")" = "1" ] && ok "queue: weekly trend" || bad "trend $(py "d['queue']['trend'][-1]")"
[ "$(py "(d['worklists']['proposed'],d['worklists']['approved'],d['worklists']['done'])")" = "(3, 2, 1)" ] \
  && ok "work lists: proposed (standby excluded), approved, done" || bad "worklists $(py "d['worklists']")"
[ "$(py "d['sprints'][0]['points_left_last']")" = "7" ] && ok "sprints: points left from history" || bad "sprints"
[ "$(py "d['health']['audit']['warning']")" = "1" ] && [ "$(py "len(d['health']['warnings'])")" = "1" ] && ok "health and audit read" || bad "health"
python3 "$HERE/shared/bin/kit-metrics" >/dev/null && [ -f "$K/metrics.html" ] && grep -q "Kit metrics" "$K/metrics.html" && ok "page written to the Kit folder" || bad "page"
[ "$(stat -f %Lp "$K/metrics.html" 2>/dev/null || stat -c %a "$K/metrics.html")" = "600" ] && ok "page is owner-only" || bad "perms"
rm -rf "$K/.install" "$K/briefs" "$K/QUEUE.md"
python3 "$HERE/shared/bin/kit-metrics" --out "$S/empty.html" >/dev/null && grep -q "No data yet" "$S/empty.html" && ok "empty Kit: page still renders" || bad "empty"
echo "kit-metrics tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
