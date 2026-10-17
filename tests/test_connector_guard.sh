#!/bin/bash
# Tests connector-guard's failure logging, tool_use_id pairing in kit-audit, and the pause check.
# Runs in a throwaway folder; touches nothing in ~/Claude/Agents/kit.
#   bash tests/test_connector_guard.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$HERE/shared/bin/connector-guard"
AUDIT="$HERE/shared/bin/kit-audit"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); echo "ok   $1"; }
bad()  { fail=$((fail+1)); echo "FAIL $1"; }

mkdir -p "$S/kit/memory/context" "$S/kit/agents" "$S/kit/.install" "$S/audit" "$S/out"
printf '{"audit_dir": "%s", "allowed_servers": ["wiki"]}\n' "$S/audit" > "$S/kit/memory/context/connector-guard.json"
export KIT_CONNECTOR_GUARD_CONFIG="$S/kit/memory/context/connector-guard.json" KIT_DIR="$S/kit"
LOG="$S/audit/connectors-$(date +%Y-%m).jsonl"
g() { printf '%s' "$2" | python3 "$GUARD" "$1" gateway; }

# 1. A failed call gets a result record, with the error scrubbed of credentials.
g pre  '{"session_id":"s1","tool_name":"mcp__wiki__get_page","tool_use_id":"toolu_A","tool_input":{"id":1}}' >/dev/null
g fail '{"session_id":"s1","tool_name":"mcp__wiki__get_page","tool_use_id":"toolu_A","error":"401 Unauthorized: Bearer abcdefghijklmnop1234 token=zzzzzzzzzz","is_interrupt":false,"duration_ms":812}'
python3 - "$LOG" <<'EOF' && ok "failed call logged as post, is_error, scrubbed" || bad "failed call record"
import json,sys
r=[json.loads(l) for l in open(sys.argv[1])][-1]
assert r["event"]=="post" and r["hook"]=="failure" and r["is_error"] is True and r["tool_use_id"]=="toolu_A", r
assert "abcdefghijklmnop1234" not in r["error"] and "zzzzzzzzzz" not in r["error"] and "401" in r["error"], r["error"]
assert r["duration_ms"]==812
EOF

# 2. A successful call carries its tool_use_id.
g pre  '{"session_id":"s1","tool_name":"mcp__wiki__get_page","tool_use_id":"toolu_B"}' >/dev/null
g post '{"session_id":"s1","tool_name":"mcp__wiki__get_page","tool_use_id":"toolu_B","tool_response":{"ok":1}}'
grep -q '"tool_use_id": "toolu_B"' "$LOG" && ok "success record carries tool_use_id" || bad "tool_use_id on post"

# 3. A call with no result at all, plus an old-style record pair without ids.
g pre  '{"session_id":"s1","tool_name":"mcp__wiki__list_pages","tool_use_id":"toolu_C"}' >/dev/null
g pre  '{"session_id":"s2","tool_name":"mcp__wiki__search"}' >/dev/null
g post '{"session_id":"s2","tool_name":"mcp__wiki__search","tool_response":{}}'
g stop '{"session_id":"s1"}'; g stop '{"session_id":"s2"}'

# kit-audit, an hour later: only toolu_C is unpaired. An agent without the failure hook is flagged.
cat > "$S/kit/agents/gateway.md" <<'EOF'
---
name: gateway
hooks:
  PreToolUse:
    - command: 'python3 "x/connector-guard" pre gateway'
  Stop:
    - command: 'python3 "x/connector-guard" stop gateway'
---
body
EOF
NOW=$(python3 -c 'import datetime;print((datetime.datetime.now().astimezone()+datetime.timedelta(hours=3)).isoformat(timespec="seconds"))')
python3 "$AUDIT" --daily --json --log-dir "$S/audit" --kit-dir "$S/kit" --out-dir "$S/out" --now "$NOW" > "$S/a1.txt" 2>&1
python3 - "$S/out/audit-status.json" <<'EOF' && ok "kit-audit pairs by id: 1 unpaired call, failure-hook gap flagged" || bad "kit-audit pairing"
import json,sys
st=json.load(open(sys.argv[1]))
nr=[f for f in st["findings"] if f["check"]=="no-result"]
assert len(nr)==1 and nr[0].get("count")==1, nr
assert "PostToolUseFailure" in nr[0]["detail"], nr[0]["detail"]
assert any("PostToolUseFailure" in f["title"] for f in st["findings"]), [f["title"] for f in st["findings"]]
EOF

# With the hook added, the structural gap goes away.
sed -i.bak 's|  Stop:|  PostToolUseFailure:\n    - command: '"'"'python3 "x/connector-guard" fail gateway'"'"'\n  Stop:|' "$S/kit/agents/gateway.md"
python3 "$AUDIT" --daily --json --log-dir "$S/audit" --kit-dir "$S/kit" --out-dir "$S/out" --now "$NOW" > /dev/null 2>&1
python3 - "$S/out/audit-status.json" <<'EOF' && ok "failure-hook gap clears once the hook is present" || bad "gap clears"
import json,sys
st=json.load(open(sys.argv[1]))
assert not any("PostToolUseFailure" in f["title"] for f in st["findings"])
EOF

# 4. While paused, connector calls are denied; non-connector tools are untouched.
echo "testing the kill switch" > "$S/kit/.install/PAUSED"
out=$(g pre '{"session_id":"s3","tool_name":"mcp__wiki__get_page"}')
echo "$out" | grep -q '"deny"' && echo "$out" | grep -q "paused" && ok "paused: connector call denied" || bad "pause deny: $out"
out=$(g pre '{"session_id":"s3","tool_name":"Read"}')
[ -z "$out" ] && ok "paused: non-connector tool not blocked" || bad "pause non-connector: $out"
rm "$S/kit/.install/PAUSED"
out=$(g pre '{"session_id":"s3","tool_name":"mcp__wiki__get_page"}')
[ -z "$out" ] && ok "resumed: connector call allowed" || bad "resume: $out"

echo "connector-guard tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
