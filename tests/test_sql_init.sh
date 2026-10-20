#!/bin/bash
# Offline test of kit-team db-init with a fake MySQL driver (no database needed). The real-server
# test is tests/live/test_sql_live.py.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
K="$S/kit"; mkdir -p "$K/memory/context" "$S/fake"
cat > "$S/fake/pymysql.py" <<'PY'
import json, os
LOG = os.environ["FAKE_SQL_LOG"]
class _Cur:
    def execute(self, sql, args=None):
        with open(LOG, "a") as f: f.write(" ".join(sql.split()) + "\n")
    def fetchall(self): return [("acks",), ("kits",), ("messages",), ("records",)]
    def close(self): pass
class _Conn:
    def __init__(self, **kw):
        with open(LOG, "a") as f: f.write("CONNECT " + json.dumps({k: v for k, v in kw.items() if k != "password"}, default=str) + "\n")
        if kw.get("password") != "plain-test-word": raise RuntimeError("bad password")
    def cursor(self): return _Cur()
    def commit(self): pass
    def close(self): pass
def connect(**kw): return _Conn(**kw)
PY
cat > "$K/memory/context/sharing-db.json" <<'J'
{"dialect": "mysql", "host": "127.0.0.1", "port": 3307, "database": "kit_sharing", "user": "kit_user",
 "credential_env": "KIT_TEST_DB_CRED", "keychain_entry": "", "tls": "off", "driver": "pymysql"}
J
echo '{"allowed_transports": ["folder"], "allowed_roots": [], "blocked_root_patterns": [], "max_classification": {"folder": "internal"}, "allow_confidential": false}' > "$K/memory/context/sharing-policy.json"
run() { KIT_DIR="$K" HOME="$S" PYTHONPATH="$S/fake" FAKE_SQL_LOG="$S/log" KIT_TEST_DB_CRED="plain-test-word" python3 "$HERE/shared/bin/kit-team" db-init 2>&1; }
out=$(run); [[ "$out" == *"doesn't allow the sql transport"* ]] && ok "db-init refused when the policy doesn't allow sql" || bad "policy refusal: $out"
sed -i '' 's/"allowed_transports": \["folder"\]/"allowed_transports": ["folder", "sql"]/' "$K/memory/context/sharing-policy.json"
rm -f "$S/log"; out=$(run)
[[ "$out" == *"is ready (tested on MySQL 8.0 with PyMySQL)"*"acks, kits, messages, records"* ]] && ok "db-init reports ready with the tables" || bad "ready line: $out"
grep -q "CREATE DATABASE IF NOT EXISTS \`kit_sharing\`" "$S/log" && ok "creates the database if missing" || bad "no CREATE DATABASE"
[ "$(grep -c '^CREATE TABLE IF NOT EXISTS' "$S/log")" = "4" ] && ok "creates the four tables" || bad "table count"
grep -q '"port": 3307' "$S/log" && ! grep -q "plain-test-word" "$S/log" && ok "uses the configured port; password never logged" || bad "port or password leak"
sed -i '' 's/"tls": "off"/"tls": "off", "host_note": ""/; s/"host": "127.0.0.1"/"host": "db.example.org"/' "$K/memory/context/sharing-db.json"
out=$(run); [[ "$out" == *"tls is off for a database that isn't on this computer"* ]] && ok "tls off refused for a remote host" || bad "tls refusal: $out"
sed -i '' 's/"host": "db.example.org"/"host": "127.0.0.1"/; s/"database": "kit_sharing"/"database": "kit-sharing; DROP"/' "$K/memory/context/sharing-db.json"
out=$(run); [[ "$out" == *"must be letters, digits, and underscores"* ]] && ok "unsafe database name refused" || bad "name check: $out"
echo "sql init tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
