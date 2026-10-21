#!/bin/bash
# Tests kit-audit's filter check: a search whose result total is far above its limit, or the same
# total for different queries, is a warning; a small total isn't; a log with no totals is "not
# checkable". Uses a synthetic audit log in a throwaway folder; touches nothing in ~/Claude/Agents/kit.
#   bash tests/test_audit_filter.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUDIT="$HERE/shared/bin/kit-audit"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); echo "ok   $1"; }
bad()  { fail=$((fail+1)); echo "FAIL $1"; }

mkdir -p "$S/kit/memory/context" "$S/kit/agents" "$S/audit" "$S/out"
printf '{"audit_dir": "%s", "allowed_servers": ["tickets"]}\n' "$S/audit" > "$S/kit/memory/context/connector-guard.json"
export KIT_CONNECTOR_GUARD_CONFIG="$S/kit/memory/context/connector-guard.json"
NOW="2026-10-20T15:00:00+00:00"
LOG="$S/audit/connectors-2026-10.jsonl"

# fixture <name>: writes the audit log for one case. Each call is a pre record (with its input) and
# a post record; T is the minute past 14:00.
fixture() {
  python3 - "$LOG" "$1" <<'EOF'
import json, sys
path, case = sys.argv[1], sys.argv[2]
calls = {
  "big":     [("search_records", {"query": "caller=Jane Example", "limit": 25}, {"result_total": 7663})],
  "small":   [("search_records", {"query": "number=REQ1", "limit": 25}, {"result_total": 3})],
  "nototal": [("search_records", {"query": "number=REQ1", "limit": 25}, {})],
  "same":    [("search_records", {"query": "group=alpha", "limit": 500}, {"result_total": 412}),
              ("search_records", {"query": "group=beta", "limit": 500}, {"result_total": 413})],
  "paged":   [("search_records", {"query": "group=alpha", "limit": 200, "offset": 0}, {"result_total": 412}),
              ("search_records", {"query": "group=alpha", "limit": 200, "offset": 200}, {"result_total": 412})],
  "getone":  [("get_record", {"id": "REQ1"}, {"result_total": 9000})],
}[case]
with open(path, "w") as f:
    for i, (tool, inp, post) in enumerate(calls):
        base = {"agent": "gateway", "session": "s1", "tool": f"mcp__tickets__{tool}", "tool_use_id": f"t{i}"}
        f.write(json.dumps(dict(base, time=f"2026-10-20T14:{i:02d}:00+00:00", event="pre", decision="allow",
                                reason="read-only", input=inp)) + "\n")
        f.write(json.dumps(dict(base, time=f"2026-10-20T14:{i:02d}:05+00:00", event="post", result_bytes=900,
                                is_error=False, **post)) + "\n")
    f.write(json.dumps({"time": "2026-10-20T14:30:00+00:00", "event": "stop", "agent": "gateway", "session": "s1"}) + "\n")
EOF
}
audit() { rm -f "$S/out/"*; python3 "$AUDIT" --daily --log-dir "$S/audit" --kit-dir "$S/kit" --out-dir "$S/out" --now "$NOW" > "$S/out.txt" 2>&1; }
check() {  # check <python assertion over st (status) and txt (audit.txt)>
  python3 - "$S/out/audit-status.json" "$S/out/audit.txt" "$1" <<'EOF'
import json, sys
st = json.load(open(sys.argv[1])); txt = open(sys.argv[2]).read()
ff = [f for f in st["findings"] if f["check"] == "filter-ignored"]
assert eval(sys.argv[3]), (ff, st["notes"])
EOF
}

fixture big; audit
check 'len(ff) == 1 and ff[0]["severity"] == "warning" and "total 7,663, limit 25" in ff[0]["detail"]' \
  && ok "7,663-total search with limit 25 is a warning, with the total and limit" || bad "big total"
check '"mcp__tickets__search_records at" in ff[0]["detail"] and "WARNING: Searches that may have ignored their filter" in txt' \
  && ok "warning names the tool and time, and reaches audit.txt" || bad "tool and time"
check '"Jane" not in json.dumps(st) and "caller=" not in txt' \
  && ok "the query values never appear in the output" || bad "query leaked"

fixture small; audit
check 'not ff' && ok "3-total search is no warning" || bad "small total"

fixture nototal; audit
check 'not ff and any("not checkable" in n for n in st["notes"]) and "not checkable" in txt' \
  && ok "no totals in the log: says 'not checkable'" || bad "not checkable"

fixture same; audit
check 'len(ff) == 1 and ff[0]["count"] == 2 and "same total as a different query" in ff[0]["detail"]' \
  && ok "near-identical totals for different queries are a warning" || bad "same totals"

fixture paged; audit
check 'not ff' && ok "pages of one query with the same total are no warning" || bad "paged flagged"

fixture getone; audit
check 'not ff' && ok "only search-type calls are checked" || bad "get flagged"

printf -- '- `filter_total_min: 10000`\n' > "$S/kit/memory/context/audit.md"
fixture big; audit
check 'not ff' && ok "threshold is configurable in audit.md" || bad "threshold"

echo "kit-audit filter tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
