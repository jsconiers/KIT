#!/bin/bash
# Tests that kit-audit reads PPM Express's own audit log (ppmx-YYYY-MM.jsonl, written by kit-ppmx) next to
# the connector guard's: calls are counted, changes listed, refused changes and failures are warnings, and
# a ppmx log that shrinks is caught like any other. Run: bash tests/test_audit_ppmx.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUDIT="$HERE/shared/bin/kit-audit"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
mkdir -p "$S/kit/memory/context" "$S/kit/agents" "$S/audit" "$S/out"
printf '{"allowed_servers": ["tickets"], "audit_dir": "%s"}\n' "$S/audit" > "$S/kit/memory/context/connector-guard.json"
printf '**Working hours:** 08:00-18:00 Mon-Fri\n' > "$S/kit/memory/context/audit.md"
NOW="2026-10-21T12:00:00+00:00"
cat > "$S/audit/ppmx-2026-10.jsonl" <<'EOF2'
{"ts": "2026-10-21T09:00:00+00:00", "via": "stdio", "user": "u:abc", "method": "initialize"}
{"ts": "2026-10-21T09:01:00+00:00", "via": "stdio", "user": "u:abc", "method": "tools/call", "tool": "list_projects", "args": ["limit"], "outcome": "ok", "rows": 12, "ms": 300}
{"ts": "2026-10-21T09:05:00+00:00", "via": "stdio", "user": "u:abc", "method": "tools/call", "tool": "update_task", "args": ["id", "status"], "write": "update", "id": "T1", "fields": ["status"], "outcome": "ok", "ms": 410}
{"ts": "2026-10-21T02:05:00+00:00", "via": "stdio", "user": "u:abc", "method": "tools/call", "tool": "create_task", "args": ["name"], "write": "create", "id": "T2", "fields": ["name"], "outcome": "ok", "ms": 410}
{"ts": "2026-10-21T09:06:00+00:00", "via": "stdio", "user": "u:abc", "method": "tools/call", "tool": "create_idea", "args": ["name"], "write": "create", "outcome": "refused"}
{"ts": "2026-10-21T09:07:00+00:00", "via": "stdio", "user": "u:abc", "method": "tools/call", "tool": "get_project", "args": ["id"], "outcome": "error", "status": 503}
EOF2
run() { TZ=UTC python3 "$AUDIT" --daily --kit-dir "$S/kit" --out-dir "$S/out" --now "$NOW" > "$S/out.txt" 2>&1; }
check() { python3 - "$S/out/audit-status.json" "$S/out/audit.txt" "$1" <<'EOF2'
import json, sys
st = json.load(open(sys.argv[1])); txt = open(sys.argv[2]).read()
ff = {f["check"]: f for f in st["findings"]}
assert eval(sys.argv[3]), (st.get("ppmx"), [f for f in st["findings"]], txt)
EOF2
}
run
check 'st["ppmx"]["calls"] == 5 and st["ppmx"]["changes"] == 2 and st["ppmx"]["refused"] == 1 and st["ppmx"]["errors"] == 1' \
  && ok "PPM Express calls, changes, refusals, and failures counted" || bad "ppmx counts"
check '"PPM Express: 5 calls (2 changes, 1 refused, 1 failed)" in txt' && ok "summary line in audit.txt" || bad "summary line"
check 'ff["ppmx-refused"]["severity"] == "warning" and ff["ppmx-failure"]["severity"] == "warning"' \
  && ok "refused changes and failures are warnings" || bad "ppmx warnings"
check 'any(f["title"] == "PPM Express changes outside working hours" and f["count"] == 1 for f in st["findings"])' \
  && ok "a change at 02:05 is flagged as outside working hours" || bad "after-hours change"
check '"T1" not in json.dumps(st.get("ppmx")) and "status" not in json.dumps(st.get("ppmx"))' && ok "no record IDs or field values in the summary" || bad "summary leaks"
head -3 "$S/audit/ppmx-2026-10.jsonl" > "$S/x" && mv "$S/x" "$S/audit/ppmx-2026-10.jsonl"
run
check 'any(f["check"] == "log-integrity" and "ppmx-2026-10.jsonl" in f["detail"] for f in st["findings"])' \
  && ok "a ppmx log that got smaller is critical" || bad "ppmx integrity"
TZ=UTC python3 "$AUDIT" --weekly --kit-dir "$S/kit" --out-dir "$S/out" --now "$NOW" > /dev/null 2>&1
check '"by tool:" in txt' && ok "the weekly summary lists PPM Express calls by tool" || bad "weekly by tool"
echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
