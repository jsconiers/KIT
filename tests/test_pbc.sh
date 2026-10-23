#!/bin/bash
# Tests kit-pbc (audit request tracker) with a fake Kit, HOME, and library. Nothing real is read,
# written, or sent.   bash tests/test_pbc.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }

export HOME="$S/home" KIT_DIR="$S/home/Claude/Agents/kit" KIT_TODAY=2026-10-23
K="$KIT_DIR"; C="$K/memory/context"; L="$S/library"
mkdir -p "$C" "$HOME/.claude/agents" "$S/audit" "$L/artifacts/proj-a/change"
printf -- '- **Library root:** `%s`\n' "$L" > "$C/library.md"
echo "{\"audit_dir\": \"$S/audit\"}" > "$C/connector-guard.json"
echo '{"time": "2026-10-15T10:56:00-04:00", "event": "pre", "decision": "allow", "tool": "mcp__svc__get"}' > "$S/audit/connectors-2026-10.jsonl"
echo "change pack" > "$L/artifacts/proj-a/change/change-pack-2026-10-12.md"
cat > "$S/map.json" <<'M'
{"controls": [
  {"id": "CHG-01", "name": "Change approval", "evidence": [{"library": "artifacts/*/change/*.md"}]},
  {"id": "LOG-01", "name": "Audit logging", "evidence": ["connector-audit"]},
  {"id": "ACC-02", "name": "Access review", "evidence": [{"library": "artifacts/*/access/*.md"}]}
]}
M
printf -- '- **Control map:** `%s`\n' "$S/map.json" > "$C/compliance.md"
T="$L/compliance/audit-requests/pbc-tracker.md"
P() { python3 "$BIN/kit-pbc" "$@"; }

r=$(P list 2>&1); echo "$r" | grep -q "no tracker yet" && ok "no tracker: says so" || bad "empty: $r"
r=$(P add --audit "Annual ITGC audit" --item "Change tickets sample for Q3" --controls "CHG-01, LOG-01" --due 2026-10-20 \
      --requester "external auditor" --owner "change manager" 2>&1)
echo "$r" | grep -q "read-only; --write adds PBC-0001" && [ ! -e "$T" ] && ok "add is read-only by default" || bad "ro: $r"
P add --audit "Annual ITGC audit" --item "Change tickets sample for Q3" --controls "CHG-01, LOG-01" --due 2026-10-20 \
      --requester "external auditor" --owner "change manager" --write >/dev/null && grep -q "| PBC-0001 | Annual ITGC audit |" "$T" \
  && ok "add --write starts the tracker from the template" || bad "write"
grep -q "<PBC-0001>" "$T" && bad "example row left in" || ok "example row replaced"
P add --audit "Annual ITGC audit" --item "Access review evidence" --controls ACC-02 --due 27-Oct-2026 --owner "IAM lead" --write >/dev/null
P add --audit "Annual ITGC audit" --item "Logging config" --controls LOG-01 --due 2026-12-01 --write >/dev/null
P add --id AUD-REQ-9 --audit "Vendor review" --item "Policy list" --controls CHG-01 --due 2026-10-01 --status provided --write >/dev/null
[ "$(grep -c '^| PBC-000[123] \|^| AUD-REQ-9 ' "$T")" = 4 ] && ok "IDs: PBC-0001.. and the auditor's own" || bad "ids: $(cat "$T")"
P add --id AUD-REQ-9 --audit A --item I --controls X --due 2026-11-01 >/dev/null 2>&1 && bad "duplicate id accepted" || ok "duplicate ID refused"
P add --audit A --item "secret: abcdefgh" --controls X --due 2026-11-01 >/dev/null 2>&1 && bad "credential accepted" || ok "credential refused"
P add --audit A --item I --controls X --due 2026-11-01 --status sent >/dev/null 2>&1 && bad "bad status accepted" || ok "unknown status refused"
P add --audit A --item I --controls X --due tomorrow >/dev/null 2>&1 && bad "bad date accepted" || ok "bad due date refused"

r=$(P list --json)
python3 - "$r" <<'PY' && ok "list --json" || bad "list json: $r"
import json, sys
d = json.loads(sys.argv[1]); rq = d["requests"]
assert [x["id"] for x in rq] == ["PBC-0001", "PBC-0002", "PBC-0003", "AUD-REQ-9"]
assert rq[0]["control_ids"] == ["CHG-01", "LOG-01"] and rq[0]["due"] == "20-Oct-2026" and rq[0]["status"] == "open"
PY
r=$(P list --status provided); echo "$r" | grep -q "1 request" && ok "list --status" || bad "status: $r"

r=$(P due --json)
python3 - "$r" <<'PY' && ok "due --json: overdue and due soon; provided ignored" || bad "due: $r"
import json, sys
d = json.loads(sys.argv[1])
assert [(x["id"], x["days_overdue"]) for x in d["overdue"]] == [("PBC-0001", 3)]
assert [(x["id"], x["days_left"]) for x in d["due_soon"]] == [("PBC-0002", 4)]
PY
r=$(P due --days 60 --json); python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert len(d['due_soon'])==2" "$r" && ok "due --days" || bad "days"
r=$(P due); echo "$r" | grep -q "OVERDUE 3 day(s)  PBC-0001" && ok "due text" || bad "due text: $r"

r=$(P gather PBC-0001 --from 2026-10-01 --to 2026-10-31 --dry-run)
echo "$r" | grep -q -- "--only CHG-01,LOG-01" && echo "$r" | grep -q -- "--request PBC-0001" && ok "gather --dry-run shows the export" || bad "dry: $r"
P gather PBC-0001 >/dev/null 2>&1 && bad "gather without a period" || ok "gather needs --from and --to"
before=$(shasum "$T")
r=$(P gather PBC-0001 --from 2026-10-01 --to 2026-10-31 2>&1)
G="$L/compliance/audit-requests/PBC-0001/evidence-2026-10-01-to-2026-10-31"
[ -f "$G/CONTROLS.md" ] && [ -d "$G/controls/CHG-01" ] && [ -d "$G/controls/LOG-01" ] && [ ! -d "$G/controls/ACC-02" ] \
  && ok "gather writes a controls pack for the request's controls into its folder" || bad "gather: $r"
[ "$before" = "$(shasum "$T")" ] && ok "gather leaves the tracker alone" || bad "tracker changed"
P gather PBC-0001 --from 2026-10-01 --to 2026-10-31 >/dev/null 2>&1 && bad "gather overwrote" || ok "gather refuses an existing pack"
P gather PBC-0002 --from 2026-10-01 --to 2026-10-31 >/dev/null 2>&1
P gather NOPE --from 2026-10-01 --to 2026-10-31 >/dev/null 2>&1 && bad "unknown id" || ok "unknown request refused"

r=$(P draft PBC-0001 2>&1)
D="$L/compliance/audit-requests/PBC-0001/response-draft-2026-10-23.md"
[ -f "$D" ] && grep -q "Kit never sends this" "$D" && grep -q "evidence-2026-10-01-to-2026-10-31" "$D" \
  && grep -q "| CHG-01 Change approval | library artifacts/\*/change/\*.md: 1 | none |" "$D" && ok "draft from the newest pack" || bad "draft: $r"
r=$(P draft PBC-0002 2>&1); D2="$L/compliance/audit-requests/PBC-0002/response-draft-2026-10-23.md"
grep -q "ACC-02 Access review: no evidence in the period" "$D2" && echo "$r" | grep -q "gap: ACC-02" && ok "draft names the gaps" || bad "gaps: $r"
P draft PBC-0001 >/dev/null; [ -f "$L/compliance/audit-requests/PBC-0001/response-draft-2026-10-23-2.md" ] && ok "draft never overwrites" || bad "overwrite"
r=$(P draft PBC-0003 --json); python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert d['pack'] is None" "$r" \
  && grep -q "No evidence gathered yet" "$L/compliance/audit-requests/PBC-0003/response-draft-2026-10-23.md" && ok "draft without a pack says so" || bad "nopack: $r"
[ "$before" = "$(shasum "$T")" ] && ok "draft leaves the tracker alone" || bad "tracker changed by draft"

echo "pbc tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
