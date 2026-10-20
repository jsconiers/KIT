#!/bin/bash
# Tests kit-audit-export with a fake Kit and HOME. Nothing real is read or written.
#   bash tests/test_audit_export.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }

export HOME="$S/home" KIT_DIR="$S/home/Claude/Agents/kit"
K="$KIT_DIR"; C="$K/memory/context"
mkdir -p "$C" "$K/briefs" "$K/.install/logs" "$K/memory/personal" "$K/outbox/kit-a/drafts/sent" \
         "$HOME/.claude/agents" "$S/audit/reports"
cat > "$C/connector-guard.json" <<EOF
{"audit_dir": "$S/audit", "allowed_servers": ["svc"], "allow_tools": [], "deny_tools": ["mcp__svc__create"]}
EOF
echo '{"allowed_transports": ["folder"], "allow_confidential": false}' > "$C/sharing-policy.json"
echo '{"enabled_phase": 2, "default_profile": "deep", "org_profile": {"non_claude_max_data_class": "public"}, "agents": {}}' > "$K/models.json"
cat > "$S/audit/connectors-2026-10.jsonl" <<'EOF'
{"time": "2026-10-14T12:26:00-04:00", "event": "pre", "decision": "deny", "tool": "mcp__svc__create"}
{"time": "2026-10-15T10:56:00-04:00", "event": "pre", "decision": "allow", "tool": "mcp__svc__get_page"}
{"time": "2026-09-30T09:00:00-04:00", "event": "pre", "decision": "allow", "tool": "mcp__svc__old"}
EOF
cp "$S/audit/connectors-2026-10.jsonl" "$S/audit/connectors-2026-09.jsonl"
echo "weekly audit report" > "$S/audit/reports/2026-10-19.md"
echo '{"open_issue": false}' > "$K/briefs/audit-status.json"; echo "No audit issues." > "$K/briefs/audit.txt"
echo "- 2026-10-15 accepted work list 1,3" > "$K/briefs/phone-approvals.md"
echo "Brief body with private content" > "$K/briefs/2026-10-19.md"
echo "family matter" > "$K/memory/personal/secret-note.md"
echo '{"ts": "2026-10-16T09:00:00", "event": "tool", "tool": "Read"}' > "$K/.install/logs/kit-run-2026-10.jsonl"
echo '{"published_at": "2026-10-16T10:00:00", "body": {"to": ["kit-b"], "subject": "handoff", "body": "full text"}}' \
  > "$K/outbox/kit-a/drafts/sent/m1.json"
cat > "$HOME/.claude/settings.json" <<'EOF'
{"permissions": {"allow": ["Bash(git status:*)"], "ask": ["mcp__broker__place_order"], "deny": ["Bash(rm -rf:*)"]},
 "env": {"SOME_SETTING": "value-that-must-not-appear"}}
EOF
printf -- '---\nname: gateway\ndescription: x\ndisallowedTools: Write, Edit\nmodel: opus\n---\nbody\n' > "$HOME/.claude/agents/gateway.md"
mkdir -p "$K/.install"; echo '{"version": "1.4.0", "commit": "abcdef1234", "installed": "2026-10-19 21:30"}' > "$K/.install/VERSION.json"
printf '# Changelog\n\n## [Unreleased]\n\n- new thing\n\n## [1.4.0] - 2026-10-17\n\n- older\n\n## [1.3.0]\n- oldest\n' > "$K/.install/CHANGELOG.md"

OUT="$S/pack"
r=$(python3 "$BIN/kit-audit-export" --from 2026-10-01 --to 2026-10-31 --out "$OUT" --zip 2>&1)
echo "$r" | grep -q "scanned clean" && ok "pack built and scanned clean" || bad "build: $r"
[ "$(wc -l < "$OUT/audit/connector-calls.jsonl" | tr -d ' ')" = 2 ] && ok "audit lines limited to the date range" || bad "range"
grep -q '"deny"' "$OUT/audit/connector-calls.jsonl" && ok "denied call included" || bad "deny missing"
[ -f "$OUT/kit-audit/audit.txt" ] && [ -f "$OUT/kit-audit/reports/2026-10-19.md" ] && ok "kit-audit outputs and reports" || bad "kit-audit"
[ -f "$OUT/approvals/phone-approvals.md" ] && grep -q '"Read"' "$OUT/approvals/kit-run-audit.jsonl" && ok "approvals and kit-run audit" || bad "approvals"
grep -q '"subject": "handoff"' "$OUT/approvals/kit-team-sent.json" && ! grep -q "full text" "$OUT/approvals/kit-team-sent.json" \
  && ok "sent messages: metadata only, no body" || bad "sent metadata"
grep -q '"enabled_phase": 2' "$OUT/config/models-policy.json" && ! grep -q '"agents"' "$OUT/config/models-policy.json" \
  && ok "models policy: phase and org profile only" || bad "models"
grep -q "place_order" "$OUT/config/claude-permissions.json" && ok "permission lists exported" || bad "perms"
grep -rq "value-that-must-not-appear" "$OUT" && bad "settings env leaked" || ok "settings env never exported"
grep -q '"model": "opus"' "$OUT/agents.json" && grep -q "Write, Edit" "$OUT/agents.json" && ok "agents with tools and model" || bad "agents"
grep -q "Kit 1.4.0 (abcdef1)" "$OUT/version.txt" && grep -q "Unreleased" "$OUT/version.txt" && ! grep -q "1.3.0" "$OUT/version.txt" \
  && ok "version and newest changelog entries" || bad "version"
grep -rq "family matter" "$OUT" && bad "personal note leaked" || ok "memory/personal never included"
grep -rq "Brief body with private content" "$OUT" && bad "brief leaked" || ok "briefs never included"
python3 - "$OUT" <<'PY' && ok "manifest checksums match" || bad "manifest"
import hashlib, json, pathlib, sys
pack = pathlib.Path(sys.argv[1]); m = json.loads((pack / "MANIFEST.json").read_text())
assert m["files"] and all(hashlib.sha256((pack / f).read_bytes()).hexdigest() == h for f, h in m["files"].items())
PY
[ -f "$S/pack.zip" ] && python3 -c "import zipfile,sys;sys.exit(0 if zipfile.ZipFile('$S/pack.zip').testzip() is None else 1)" \
  && ok "zip written and valid" || bad "zip"
[ "$(stat -f %Lp "$OUT/README.md")" = 600 ] && ok "pack files owner-only" || bad "perms on pack"
python3 "$BIN/kit-audit-export" --out "$OUT" >/dev/null 2>&1 && bad "overwrote an existing pack" || ok "refuses an existing folder"
python3 "$BIN/kit-audit-export" --out "$K/inside" >/dev/null 2>&1 && bad "pack inside Kit" || ok "refuses a pack inside Kit's folder"

# A credential slipping into an exported file: pack removed, nothing left.
echo "weekly report with password: hunter-two-test" > "$S/audit/reports/2026-10-20.md"
r=$(python3 "$BIN/kit-audit-export" --from 2026-10-01 --to 2026-10-31 --out "$S/pack2" 2>&1)
echo "$r" | grep -q "credential-like text turned up" && [ ! -e "$S/pack2" ] && ok "credential in a file: pack refused and removed" \
  || bad "cred scan: $r"
rm -f "$S/audit/reports/2026-10-20.md"
# A permission rule that looks like a credential is dropped, the rest kept.
python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["permissions"]["allow"].append("Bash(curl -H 'token: plainvaluewords':*)"); json.dump(d, open(p, "w"))
PY
r=$(python3 "$BIN/kit-audit-export" --from 2026-10-01 --to 2026-10-31 --out "$S/pack3" 2>&1)
echo "$r" | grep -q "left out because they looked like credentials" && ! grep -q "plainvaluewords" "$S/pack3/config/claude-permissions.json" \
  && grep -q "git status" "$S/pack3/config/claude-permissions.json" && ok "credential-like permission entry dropped, others kept" || bad "perm strip: $r"

echo "audit export tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
