#!/bin/bash
# Tests kit-connect with a fake claude (no real servers, no real calls) in a throwaway Kit.
#   bash tests/test_connect.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit"; mkdir -p "$KIT_DIR/memory/context" "$S/bin"
KC="$HERE/shared/bin/kit-connect"
cat > "$KIT_DIR/memory/context/connector-guard.json" <<'EOF'
{"audit_dir": "/tmp/x", "allowed_servers": ["alpha", "beta", "gamma"], "allow_tools": [], "deny_tools": [],
 "credential_env": {"alpha": ["KC_TEST_ALPHA_VAR"]},
 "probe_tools": {"alpha": "mcp__alpha__get_item", "beta": "mcp__other__get_item"}}
EOF
# fake claude: 'mcp list' prints health lines with a header-looking argument; '-p' records its args
cat > "$S/bin/claude" <<EOF
#!/bin/bash
if [ "\$1" = "mcp" ] && [ "\$2" = "list" ]; then
  echo "Checking MCP server health…"; echo
  echo "alpha: npx remote https://example.test/mcp --header Authorization:\\\${HIDDEN} - ✔ Connected"
  echo "beta: node server.js - ✘ Failed to connect — -32000: Connection closed"
  echo "plugin:tools:thing: npx thing - ✔ Connected"
  echo; echo " ├ [Warning] [beta] mcpServers.beta: Missing environment variables: KC_TEST_BETA_VAR"
  exit 0
fi
printf "%s\n" "\$@" > "$S/probe-args.txt"
echo '{"result":"OK one item returned","total_cost_usd":0.004}'
EOF
chmod +x "$S/bin/claude"; export PATH="$S/bin:$PATH"
unset KC_TEST_ALPHA_VAR KC_TEST_BETA_VAR

out=$(python3 "$KC" test 2>&1); rc=$?
[ $rc -eq 1 ] && ok "missing credential and failed server -> exit 1" || bad "exit code ($rc)"
echo "$out" | grep -q "missing: KC_TEST_ALPHA_VAR" && ok "credential reported missing by name" || bad "alpha creds"
echo "$out" | grep -q "missing: KC_TEST_BETA_VAR" && ok "Claude Code's missing-variable diagnostic picked up" || bad "beta diag"
echo "$out" | grep -q "Failed to connect" && ok "failed health shown" || bad "beta health"
echo "$out" | grep -q "not configured in Claude Code" && ok "unconfigured server flagged" || bad "gamma"
echo "$out" | grep -qi "header\|example.test\|Authorization" && bad "command/url leaked into output" || ok "command and URL never printed"
export KC_TEST_ALPHA_VAR="present-for-test"
out=$(python3 "$KC" test alpha 2>&1); rc=$?
[ $rc -eq 0 ] && ok "alpha passes once the variable is set" || bad "alpha pass ($rc): $out"
echo "$out" | grep -q "present-for-test" && bad "variable value printed" || ok "variable value never printed"
echo "$out" | grep -q "KC_TEST_ALPHA_VAR (set)" && ok "reports the variable as set, by name" || bad "set by name"
out=$(python3 "$KC" test delta 2>&1)
echo "$out" | grep -q "not in allowed_servers" && ok "server outside the guard flagged" || bad "guard check"
rm -f "$S/probe-args.txt"
out=$(python3 "$KC" test alpha --read 2>&1); rc=$?
[ $rc -eq 0 ] && grep -qx -- "--agent" "$S/probe-args.txt" && grep -A1 -x -- "--agent" "$S/probe-args.txt" | grep -qx gateway \
  && ok "--read runs as the gateway agent" || bad "--read agent ($rc)"
grep -A1 -x -- "--allowedTools" "$S/probe-args.txt" | grep -qx "mcp__alpha__get_item" && ok "--read allows only the probe tool" || bad "probe tool"
echo "$out" | grep -q "about \$0.004" && ok "--read shows the run's cost" || bad "probe cost"
echo "$out" | grep -q "one short Claude Code run per server" && ok "--read warns about cost first" || bad "cost warning"
out=$(python3 "$KC" test beta --read 2>&1)
echo "$out" | grep -q "skipped: fix the checks above first" && ok "--read skipped when checks fail" || bad "read skip"
python3 "$KC" test alpha --json 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);assert d['servers'][0]['pass']" \
  && ok "--json output" || bad "json"
echo '{"allowed_servers": []}' > "$KIT_DIR/memory/context/connector-guard.json"
python3 "$KC" test >/dev/null 2>&1; [ $? -eq 2 ] && ok "no servers -> exit 2" || bad "no servers exit"
python3 "$KC" list | grep -q "none: allowed_servers is empty" && ok "list with nothing allowed" || bad "list"
grep -q -- "-w" "$KC" && grep -n -- '"-w"' "$KC" >/dev/null && bad "keychain value requested" || ok "never asks Keychain for a value"
cat > "$KIT_DIR/memory/context/connector-guard.json" <<'EOF2'
{"audit_dir": "/tmp/x", "allowed_servers": ["alpha", "beta"], "probe_tools": {"alpha": null}}
EOF2
out=$(python3 "$KC" list 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "alpha .*no probe tool" <<<"$out" && ok "list handles a probe tool set to null" || bad "null probe: $out"
echo "kit-connect tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
