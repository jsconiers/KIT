#!/bin/bash
# Tests kit-exceptions and morning/monitor_exceptions.py with a fake Kit and library. Nothing real is
# read or written.   bash tests/test_exceptions.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }

export HOME="$S/home" KIT_DIR="$S/home/Claude/Agents/kit" KIT_TODAY=2026-10-23
K="$KIT_DIR"; C="$K/memory/context"; L="$S/library"
mkdir -p "$C" "$L"
printf -- '- **Library root:** `%s`\n' "$L" > "$C/library.md"
printf '# Compliance setup\n\n- **Exception register:** optional. Default below.\n' > "$C/compliance.md"
REG="$L/compliance/exception-register.md"
X() { python3 "$BIN/kit-exceptions" "$@"; }

r=$(X list 2>&1); echo "$r" | grep -q "no register yet" && ok "no register: says so" || bad "empty list: $r"
r=$(X add --policy "Information security policy, v3, section 4.2" --system "DOC-101 v1.0" --reason "legacy protocol" 2>&1)
echo "$r" | grep -q "read-only; --write adds EXC-0001 (candidate)" && [ ! -e "$REG" ] && ok "add is read-only by default" || bad "read-only: $r"
r=$(X add --policy "Information security policy, v3, section 4.2" --system "DOC-101 v1.0" --reason "legacy protocol" \
      --controls "network isolation" --owner "service owner" --write 2>&1)
echo "$r" | grep -q "added EXC-0001 (candidate)" && grep -q "| EXC-0001 | Information security policy" "$REG" \
  && ok "add --write starts the register from the template" || bad "write: $r"
grep -q "<EXC-0001>" "$REG" && bad "template example row left in" || ok "template example row replaced"
grep -q "Classification" "$REG" && ok "register keeps the template's header" || bad "header"
X add --policy P --system S --reason R --status granted --write >/dev/null 2>&1 && bad "granted without approver accepted" \
  || ok "granted needs approver, granted date, and expiry"
X add --policy "Data retention standard, v2, section 3" --system "DOC-102" --reason "vendor limit" --status granted \
  --approver "security officer" --granted 2026-01-10 --expiry 2026-11-05 --review quarterly --last-reviewed 01-Sep-2026 --write >/dev/null \
  && ok "granted exception added" || bad "granted add"
X add --policy "Logging standard, v1, section 2" --system "DOC-103" --reason "tool gap" --status granted \
  --approver "security officer" --granted 01-Jan-2026 --expiry 01-Oct-2026 --review annual --write >/dev/null
X add --policy "Patching standard, v4, section 5" --system "DOC-104" --reason "freeze" --status granted \
  --approver "security officer" --granted 01-Jan-2026 --expiry 31-Dec-2027 --review monthly --last-reviewed 01-Aug-2026 --write >/dev/null
X add --policy "Encryption standard" --system "DOC-105" --reason "closed one" --status closed --expiry 01-Jan-2026 --write >/dev/null
[ "$(grep -c '^| EXC-' "$REG")" = 5 ] && grep -q "| EXC-0005 |" "$REG" && ok "IDs numbered in order" || bad "ids"
X add --policy P --system S --reason "password: hunter-two-x" --write >/dev/null 2>&1 && bad "credential accepted" \
  || ok "credential-like text refused"
X add --policy P --system S --reason R --status approved >/dev/null 2>&1 && bad "unknown status accepted" || ok "unknown status refused"
X add --policy "a | b" --system S --reason R >/dev/null 2>&1; r=$(X add --policy "a | b" --system S --reason R)
echo "$r" | grep -q "| a / b |" && ok "pipes in text can't break the table" || bad "pipe: $r"

r=$(X list --json)
python3 - "$r" <<'PY' && ok "list --json" || bad "list json"
import json, sys
d = json.loads(sys.argv[1]); ids = [e["id"] for e in d["exceptions"]]
assert ids == ["EXC-0001", "EXC-0002", "EXC-0003", "EXC-0004", "EXC-0005"], ids
assert d["exceptions"][1]["approver"] == "security officer" and d["exceptions"][1]["expiry"] == "05-Nov-2026"
PY
r=$(X list --status granted); echo "$r" | grep -q "3 exception" && ok "list --status filters" || bad "status filter: $r"

r=$(X due --json)
python3 - "$r" <<'PY' && ok "due: expiring, expired, review overdue; closed ignored" || bad "due json: $r"
import json, sys
d = json.loads(sys.argv[1]); got = sorted((x["kind"], x["id"], x["days"]) for x in d["due"])
assert got == [("expired", "EXC-0003", 22), ("expiring", "EXC-0002", 13), ("review", "EXC-0004", 53)], got
PY
r=$(X due --days 5 --json); python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert 'EXC-0002' not in [x['id'] for x in d['due']]" "$r" \
  && ok "due --days narrows the window" || bad "days"
r=$(X due); echo "$r" | grep -q "EXC-0003  expired 22 day(s) ago (01-Oct-2026)" && ok "due text" || bad "due text: $r"

# Columns found by name: a reordered register still reads.
cat > "$S/reordered.md" <<'EOF2'
| Status | Expiry | ID | Policy and section | System or design | Granted | Approver (role) |
|---|---|---|---|---|---|---|
| granted | 2026-10-30 | EXC-0042 | Access standard | DOC-200 | 2026-01-01 | risk lead |
EOF2
r=$(X due --register "$S/reordered.md" --json)
python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert [(x['id'],x['days']) for x in d['due']]==[('EXC-0042',7)]" "$r" \
  && ok "reordered columns read by name" || bad "reordered: $r"
r=$(X add --register "$S/reordered.md" --policy P2 --system DOC-201 --reason R)
echo "$r" | grep -q "^| candidate |  | EXC-0043 | P2 | DOC-201 |" && ok "add follows the register's column order" || bad "order: $r"

# Monitor: same interface as the other monitors.
r=$(python3 - "$HERE/shared/morning" "$K" <<'PY'
import datetime as dt, sys
sys.path.insert(0, sys.argv[1])
import monitor_exceptions as m
class Cfg:
    def __init__(self, v): self.v = v
    def get(self, k, d=""): return self.v.get(k, d)
    def number(self, k, d): return float(self.v.get(k, d))
p = m.problems(sys.argv[2], Cfg({}), dt.datetime(2026, 10, 23, 9, 0), None)
assert set(p) == {"exceptions:expired:EXC-0003", "exceptions:expiring:EXC-0002", "exceptions:review:EXC-0004"}, p
e = p["exceptions:expired:EXC-0003"]
assert e["title"].startswith("Renew or close policy exception EXC-0003") and "recovered" in e
assert "title" not in p["exceptions:expiring:EXC-0002"] and p["exceptions:expiring:EXC-0002"]["days"] == 13
assert all(x["reason"] for x in p.values())
p = m.problems(sys.argv[2], Cfg({"EXCEPTIONS_WARN_DAYS": "5"}), dt.datetime(2026, 10, 23), None)
assert "exceptions:expiring:EXC-0002" not in p
p = m.problems(sys.argv[2], None, dt.datetime(2026, 10, 23), None)
assert len(p) == 3
print("monitor ok")
PY
)
[ "$r" = "monitor ok" ] && ok "monitor problems(): keys, titles, warn days" || bad "monitor: $r"
r=$(python3 "$HERE/shared/morning/monitor_exceptions.py" --kit "$S/nowhere"); [ -z "$r" ] && ok "monitor: no register, nothing to report" || bad "monitor empty: $r"
before=$(shasum "$REG"); python3 "$HERE/shared/morning/monitor_exceptions.py" --kit "$K" >/dev/null
[ "$before" = "$(shasum "$REG")" ] && ok "monitor never edits the register" || bad "monitor wrote"

echo "exceptions tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
