#!/bin/bash
# Tests the morning connector check's outage tracking (shared/morning/connector_health.py): the
# history file, the fail streak (CONNECTOR_FAIL_STREAK), one owner queue item per outage through
# `todo work`, the dashboard's connector-outage banner, and recovery. Synthetic history and a fake
# kit-connect in a throwaway folder; no connector, no model, nothing real is touched.
#   bash tests/test_connector_health.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export HOME="$S/home"
KIT="$HOME/Claude/Agents/kit"; export KIT_DIR="$KIT"
B="$KIT/briefs"; Q="$KIT/QUEUE.md"; AL="$B/connectors-alerts.json"; HI="$B/connectors-history.jsonl"
mkdir -p "$B" "$KIT/.install/shared/morning"
printf 'OWNER_NAME="Alex"\n' > "$KIT/.install/shared/morning/config"
cat > "$Q" <<'EOF'
# Queue

## Alex

- [ ] **Existing item** (added 01-Oct-2026)

## Kit

## Waiting on others

## Done
EOF
KC="$S/kit-connect"
cat > "$KC" <<'PY'
import json, os, sys
state = os.environ.get("FAKE_WIKI", "fail")
print(json.dumps({"servers": [
    {"server": "tracker", "pass": True, "checks": [{"check": "health", "pass": True, "detail": "Connected"}]},
    {"server": "wiki", "pass": state == "pass",
     "checks": [{"check": "health", "pass": state == "pass", "detail": "Connected" if state == "pass" else "Failed to connect"}]}]}))
sys.exit(0 if state == "pass" else 1)
PY
check() {  # check <date> [extra args]  -> prints the brief line
  local d="$1"; shift
  python3 "$HERE/shared/morning/connector_health.py" --kit-connect "$KC" --out "$B/connectors.txt" \
    --date "$d" --kit "$KIT" "$@" 2>>"$S/err.txt"
}
items() { grep -c 'Fix connector wiki' "$Q"; }
banner() { python3 - "$HERE" <<'PY'
import sys, importlib.util
spec = importlib.util.spec_from_file_location("dash", sys.argv[1] + "/shared/dashboard.py")
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
print(d.connector_banner())
PY
}

# ---- one failure: nothing yet ----------------------------------------------------------------
out=$(check 2026-10-19)
[ "$out" = "Connectors: tracker PASS; wiki FAIL (health: Failed to connect)." ] && ok "first failure: brief line unchanged" || bad "first line: $out"
[ "$(wc -l < "$HI" | tr -d ' ')" = "2" ] && grep -q '"server": "wiki"' "$HI" && grep -q '"pass": false' "$HI" \
  && ok "history: one line per server, with pass/fail and reason" || bad "history after one run"
[ "$(items)" = "0" ] && ! grep -q wiki "$AL" 2>/dev/null && [ -z "$(banner)" ] && ok "one fail: no queue item, no alert" || bad "one fail raised something"
# a rerun the same morning replaces that day's line (so it doesn't count twice)
check 2026-10-19 >/dev/null
[ "$(grep -c '"server": "wiki"' "$HI")" = "1" ] && [ "$(items)" = "0" ] && ok "same-day rerun replaces the day's line, no streak" || bad "same-day rerun"

# ---- two mornings running: one queue item and an alert ---------------------------------------
out=$(check 2026-10-20)
[ "$(items)" = "1" ] && grep -q '^- \[ \] \*\*Fix connector wiki, failing since 19-Oct-2026 (kit-connect test)\*\* \[work\] (added ' "$Q" \
  && ok "two in a row: one [work] queue item in the owner's section" || bad "queue item: $(grep wiki "$Q")"
awk '/^## Alex/{s=1;next} /^## /{s=0} s' "$Q" | grep -q 'Fix connector wiki' && ok "queue item sits in the owner's section" || bad "wrong section"
grep -q '  Last check 20-Oct-2026: health: Failed to connect' "$Q" && ok "queue item has the last reason as a detail line" || bad "detail line"
python3 -c "import json,sys; a=json.load(open('$AL')); w=a['wiki']; sys.exit(0 if w['since']=='2026-10-19' and w['streak']==2 and w['queued'] else 1)" \
  && ok "alert recorded (since, streak, queued)" || bad "alert file: $(cat "$AL" 2>/dev/null)"
case "$out" in *"wiki FAIL (health: Failed to connect; 2 mornings running)"*) ok "brief line says 2 mornings running";; *) bad "line: $out";; esac
banner | grep -q 'Connector outage.*wiki (failing since 19-Oct, 2 mornings running' && ok "dashboard: red connector-outage banner" || bad "banner: $(banner)"
banner | grep -q 'class="banner" role="alert"' && ok "banner uses the audit banner's markup" || bad "banner markup"

# ---- third morning: no duplicate -------------------------------------------------------------
out=$(check 2026-10-21)
[ "$(items)" = "1" ] && ok "third fail: no duplicate queue item" || bad "duplicate items: $(items)"
grep -q '"streak": 3' "$AL" && case "$out" in *"3 mornings running"*) true;; *) false;; esac && ok "streak counts on (3)" || bad "streak 3"
# an alert file lost but the item still open: still no duplicate
rm -f "$AL"; check 2026-10-22 >/dev/null
[ "$(items)" = "1" ] && grep -q wiki "$AL" && ok "an open item with the same title is never added twice" || bad "dup after lost alert file"

# ---- recovery clears the alert ---------------------------------------------------------------
out=$(FAKE_WIKI=pass check 2026-10-23)
[ "$out" = "Connectors: tracker PASS; wiki PASS." ] && ok "recovery: line back to PASS" || bad "recovery line: $out"
! grep -q wiki "$AL" && [ -z "$(banner)" ] && ok "recovery: alert and banner cleared" || bad "alert not cleared: $(cat "$AL")"
grep -q '  Recovered 23-Oct-2026: the connector check passed again' "$Q" && grep -q '^- \[ \] \*\*Fix connector wiki.*updated 23-Oct-2026' "$Q" \
  && ok "recovery: queue item noted and stamped, left for the owner to check off" || bad "recovery note"
# a new outage later gets its own item
check 2026-10-26 >/dev/null; check 2026-10-27 >/dev/null
grep -q 'Fix connector wiki, failing since 26-Oct-2026' "$Q" && [ "$(items)" = "2" ] && ok "a later outage gets a new item" || bad "second outage"
FAKE_WIKI=pass check 2026-10-28 >/dev/null

# ---- streak setting, not-checked mornings, no-track, robustness -------------------------------
check 2026-11-02 --streak 3 >/dev/null; check 2026-11-03 --streak 3 >/dev/null
[ "$(items)" = "2" ] && ok "CONNECTOR_FAIL_STREAK=3: two fails aren't enough" || bad "streak 3 raised early"
check 2026-11-04 --streak 3 >/dev/null
[ "$(items)" = "3" ] && ok "CONNECTOR_FAIL_STREAK=3: the third fail raises it" || bad "streak 3 not raised"
FAKE_WIKI=pass check 2026-11-05 >/dev/null
n=$(wc -l < "$HI"); python3 "$HERE/shared/morning/connector_health.py" --kit-connect "$S/missing" --out "$B/connectors.txt" --kit "$KIT" >/dev/null
[ "$(wc -l < "$HI")" = "$n" ] && ok "a 'not checked' morning records nothing" || bad "not-checked recorded"
rm -f "$HI"; check 2026-11-06 --no-track >/dev/null
[ ! -f "$HI" ] && ok "--no-track keeps no history" || bad "no-track"
# synthetic history: a gap in dates still counts as consecutive mornings (weekends, skipped days)
printf '{"date":"2026-11-06","server":"wiki","pass":false,"reason":"x"}\n' > "$HI"
check 2026-11-09 >/dev/null
grep -q 'failing since 06-Nov-2026' "$Q" && ok "synthetic history: Friday + Monday fails count as two mornings running" || bad "weekend streak"
FAKE_WIKI=pass check 2026-11-10 >/dev/null
check 2026-11-11 >/dev/null
echo "not json" > "$AL"; chmod 000 "$Q"
out=$(check 2026-11-12); rc=$?
chmod 644 "$Q"
[ "$rc" = "0" ] && case "$out" in Connectors:*) true;; *) false;; esac && ok "an unreadable queue or alert file never fails the check" || bad "robustness rc=$rc out=$out"
grep -q 'connector_health' "$S/err.txt" && ok "problems are reported on stderr" || bad "no stderr note"

# ---- run.sh and run.ps1 pass CONNECTOR_FAIL_STREAK ---------------------------------------------
grep -q -- '--streak "${CONNECTOR_FAIL_STREAK:-2}"' "$HERE/platform/mac/morning/run.sh" && ok "run.sh passes CONNECTOR_FAIL_STREAK" || bad "run.sh streak"
grep -q 'CONNECTOR_FAIL_STREAK' "$HERE/platform/windows/morning/run.ps1" && ok "run.ps1 passes CONNECTOR_FAIL_STREAK" || bad "run.ps1 streak"
grep -q '^CONNECTOR_FAIL_STREAK="2"' "$HERE/shared/morning/config.example" && ok "config.example: CONNECTOR_FAIL_STREAK=2" || bad "config.example"

echo "connector health tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
