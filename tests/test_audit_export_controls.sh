#!/bin/bash
# Tests kit-audit-export --controls (a pack organised by control) with a fake Kit, HOME, and library.
# Nothing real is read or written.   bash tests/test_audit_export_controls.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }

export HOME="$S/home" KIT_DIR="$S/home/Claude/Agents/kit"
K="$KIT_DIR"; C="$K/memory/context"; L="$S/library"
mkdir -p "$C" "$K/briefs" "$K/.install/logs" "$K/memory/personal" "$HOME/.claude/agents" "$S/audit/reports" \
         "$L/artifacts/proj-a/change" "$L/artifacts/proj-a/reviews" "$L/artifacts/proj-a/approvals" "$L/decisions" "$L/compliance"
printf -- '- **Library root:** `%s`\n' "$L" > "$C/library.md"
echo "{\"audit_dir\": \"$S/audit\", \"allowed_servers\": [\"svc\"]}" > "$C/connector-guard.json"
cat > "$S/audit/connectors-2026-10.jsonl" <<'J'
{"time": "2026-10-14T12:26:00-04:00", "event": "pre", "decision": "deny", "tool": "mcp__svc__create"}
{"time": "2026-10-15T10:56:00-04:00", "event": "pre", "decision": "allow", "tool": "mcp__svc__get_page"}
J
echo "weekly audit report" > "$S/audit/reports/2026-10-19.md"
echo '{"ts": "2026-10-16T09:00:00", "event": "tool", "tool": "Read"}' > "$K/.install/logs/kit-run-2026-10.jsonl"
echo '{"permissions": {"allow": ["Bash(git status:*)"], "deny": ["Bash(rm -rf:*)"]}}' > "$HOME/.claude/settings.json"
printf -- '---\nname: gateway\ndisallowedTools: Write, Edit\nmodel: opus\n---\nbody\n' > "$HOME/.claude/agents/gateway.md"
echo "change pack for DOC-301" > "$L/artifacts/proj-a/change/change-pack-2026-10-12.md"
echo "old change pack" > "$L/artifacts/proj-a/change/change-pack-2026-08-01.md"
echo "design review of DOC-301" > "$L/artifacts/proj-a/reviews/review-2026-10-05.md"
printf '# ADR-0007\n\n- **Date:** 09-Oct-2026\n' > "$L/decisions/ADR-0007-use-queue.md"
printf '# ADR-0002\n\n- **Date:** 01-Mar-2026\n' > "$L/decisions/ADR-0002-old.md"
echo "family matter" > "$K/memory/personal/note-2026-10-10.md"
cat > "$L/compliance/exception-register.md" <<'R'
| ID | Policy and section | System or design | Granted | Expiry | Status |
|---|---|---|---|---|---|
| EXC-0001 | Logging standard, section 2 | DOC-301 | 01-Jan-2026 | 31-Dec-2026 | granted |
| EXC-0002 | Patching standard | DOC-302 | 01-Jan-2025 | 01-Jun-2025 | expired |
R
MAP="$S/control-map.json"
cat > "$MAP" <<'M'
{"controls": [
  {"id": "CHG-01", "name": "Change approval",
   "evidence": [{"library": "artifacts/*/change/*.md", "label": "change packs", "copy": true},
                {"library": "artifacts/*/reviews/*.md", "label": "design reviews"}, "adrs"]},
  {"id": "ACC-02", "name": "Access review", "evidence": ["agent-permissions", "config", "approvals"]},
  {"id": "LOG-01", "name": "Audit logging", "evidence": ["connector-audit", "kit-audit"]},
  {"id": "DES-01", "name": "Design approval", "evidence": [{"library": "artifacts/*/approvals/*.md", "label": "IA and GDS approvals"}]},
  {"id": "EXC-01", "name": "Exceptions approved", "evidence": ["exceptions"]},
  {"id": "SNEAK", "name": "Escape attempt", "evidence": [{"library": "../home/Claude/Agents/kit/memory/personal/*.md"}]}
]}
M
OUT="$S/pack"
r=$(python3 "$BIN/kit-audit-export" --controls "$MAP" --request "REQ 17" --from 2026-10-01 --to 2026-10-31 --out "$OUT" 2>&1)
echo "$r" | grep -q "scanned clean" && ok "controls pack built and scanned clean" || bad "build: $r"
for d in CHG-01 ACC-02 LOG-01 DES-01 EXC-01; do [ -f "$OUT/controls/$d/EVIDENCE.md" ] || bad "folder $d"; done
ok "one folder per control with EVIDENCE.md"
[ -f "$OUT/audit/connector-calls.jsonl" ] && [ -f "$OUT/agents.json" ] && ok "the standard pack is still there" || bad "base pack"
[ "$(wc -l < "$OUT/controls/LOG-01/connector-calls.jsonl" | tr -d ' ')" = 2 ] && [ -f "$OUT/controls/LOG-01/kit-audit/reports/2026-10-19.md" ] \
  && ok "LOG-01: audit lines and reports" || bad "LOG-01"
grep -q "change-pack-2026-10-12.md" "$OUT/controls/CHG-01/library-change-packs.md" && ! grep -q "2026-08-01" "$OUT/controls/CHG-01/library-change-packs.md" \
  && ok "library evidence limited to the period" || bad "library period"
[ -f "$OUT/controls/CHG-01/files/artifacts/proj-a/change/change-pack-2026-10-12.md" ] && ok "copy: true copies the file" || bad "copy"
[ ! -e "$OUT/controls/CHG-01/files/artifacts/proj-a/reviews" ] && grep -q "review-2026-10-05.md" "$OUT/controls/CHG-01/library-design-reviews.md" \
  && ok "without copy, files are listed only" || bad "list only"
python3 - "$OUT/controls/CHG-01/library-design-reviews.md" "$L/artifacts/proj-a/reviews/review-2026-10-05.md" <<'PY' && ok "listed files carry their SHA-256" || bad "sha"
import hashlib, sys
assert hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest() in open(sys.argv[1]).read()
PY
grep -q "ADR-0007" "$OUT/controls/CHG-01/adrs.md" && ! grep -q "ADR-0002" "$OUT/controls/CHG-01/adrs.md" && ok "ADRs by their date" || bad "adrs"
grep -q "EXC-0001" "$OUT/controls/EXC-01/exceptions.md" && ! grep -q "EXC-0002" "$OUT/controls/EXC-01/exceptions.md" \
  && ok "exceptions in force in the period" || bad "exceptions"
[ -f "$OUT/controls/ACC-02/agents.json" ] && [ -f "$OUT/controls/ACC-02/config/claude-permissions.json" ] && ok "ACC-02: permission snapshot" || bad "acc"
grep -q "^| DES-01 | Design approval | IA and GDS approvals: 0 | 2026-10-01 to 2026-10-31 | GAP: no evidence in the period |" "$OUT/CONTROLS.md" \
  && ok "index row: control, evidence, period, gap" || bad "index row: $(grep DES-01 "$OUT/CONTROLS.md")"
sed -n '/## Gaps/,$p' "$OUT/CONTROLS.md" | grep -q "DES-01 Design approval: no evidence in the period" && ok "gaps listed plainly" || bad "gaps"
grep -q "^| LOG-01 .* | none |$" "$OUT/CONTROLS.md" && ok "control with full evidence shows no gaps" || bad "log row"
grep -q "Audit request: REQ 17" "$OUT/CONTROLS.md" && ok "request id in the index" || bad "request"
grep -rq "family matter" "$OUT" && bad "personal note leaked" || ok "a glob can't reach outside the library"
grep -q "refused: the glob leaves the library root" "$OUT/controls/SNEAK/EVIDENCE.md" && ok "escape glob refused" || bad "sneak"
python3 - "$OUT" <<'PY' && ok "manifest covers the control folders" || bad "manifest"
import hashlib, json, pathlib, sys
pack = pathlib.Path(sys.argv[1]); m = json.loads((pack / "MANIFEST.json").read_text())["files"]
assert "CONTROLS.md" in m and "controls/CHG-01/EVIDENCE.md" in m
assert all(hashlib.sha256((pack / f).read_bytes()).hexdigest() == h for f, h in m.items())
PY
grep -q "CONTROLS.md and controls.json" "$OUT/README.md" && ok "README describes the control layout" || bad "readme"
python3 -c "import json,sys; d=json.load(open('$OUT/controls.json')); assert [c['id'] for c in d['controls'] if c['gap']]==['DES-01','SNEAK']" \
  && ok "controls.json gaps" || bad "controls.json"

# --only, a past period (snapshots don't count), and the default folder name.
r=$(python3 "$BIN/kit-audit-export" --controls "$MAP" --request "REQ-18" --only ACC-02,NOPE-9 --from 2025-01-01 --to 2025-03-31 2>&1)
P2="$S/home/Claude/Agents/kit-audit-export-req-18-2025-01-01-to-2025-03-31"
[ -d "$P2/controls/ACC-02" ] && [ ! -d "$P2/controls/CHG-01" ] && ok "--only limits the controls; folder named for the request" || bad "only: $r"
grep -q "NOPE-9: not in the control map" "$P2/CONTROLS.md" && ok "unknown control named" || bad "nope"
grep -q "outside the period" "$P2/controls/ACC-02/EVIDENCE.md" && ok "old period: snapshots don't count as evidence" || bad "snapshot"

# Markdown control map and the setup field.
cat > "$S/map.md" <<'M'
| Control | Name | Evidence |
|---|---|---|
| LOG-01 | Audit logging | connector-audit, kit-audit |
| CHG-01 | Change approval | library:artifacts/*/change/*.md |
M
printf -- '- **Control map:** `%s`\n' "$S/map.md" > "$C/compliance.md"
r=$(python3 "$BIN/kit-audit-export" --controls --request R3 --from 2026-10-01 --to 2026-10-31 --out "$S/pack3" 2>&1)
grep -q "^| CHG-01 | Change approval | library artifacts/\*/change/\*.md: 1 |" "$S/pack3/CONTROLS.md" && [ -d "$S/pack3/controls/LOG-01" ] \
  && ok "Markdown control map from compliance.md" || bad "md map: $r $(cat "$S/pack3/CONTROLS.md" 2>/dev/null)"

# Credential scan still covers copied evidence.
echo "token: notarealvalue123" > "$L/artifacts/proj-a/change/change-pack-2026-10-20.md"
r=$(python3 "$BIN/kit-audit-export" --controls "$MAP" --request R4 --from 2026-10-01 --to 2026-10-31 --out "$S/pack4" 2>&1)
echo "$r" | grep -q "credential-like text turned up" && [ ! -e "$S/pack4" ] && ok "credential in copied evidence: pack removed" || bad "cred: $r"
rm -f "$L/artifacts/proj-a/change/change-pack-2026-10-20.md"

python3 "$BIN/kit-audit-export" --request R5 --out "$S/pack5" >/dev/null 2>&1 && bad "--request without --controls accepted" || ok "--request needs --controls"
python3 "$BIN/kit-audit-export" --controls "$S/missing.json" --out "$S/pack6" >/dev/null 2>&1 && bad "missing map accepted" || ok "missing map refused"
python3 "$BIN/kit-audit-export" --from 2026-10-01 --to 2026-10-31 --out "$S/pack7" >/dev/null 2>&1
[ ! -e "$S/pack7/CONTROLS.md" ] && [ ! -e "$S/pack7/controls" ] && ! grep -q "CONTROLS.md" "$S/pack7/README.md" \
  && ok "without --controls the pack is unchanged" || bad "plain pack"
python3 -c "import json; json.load(open('$HERE/kit/templates/control-map.example.json'))" && ok "example control map is valid JSON" || bad "example json"

echo "audit export controls tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
