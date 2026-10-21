#!/bin/bash
# Tests for shared/bin/kit-csf and the NIST CSF 2.0 mapping template: coverage math, ID checks,
# blanks, --json, and --portfolio. Run: bash tests/test_csf.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-csf"
DATA="$HERE/shared/data/csf2.json"
TPL="$HERE/kit/templates/csf-mapping-template.md"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -qF -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
q() { python3 -c "import json,sys; d=json.load(sys.stdin); r=($1); print(r)"; }

# The data file: six Functions, 22 Categories, IDs prefixed by their Function.
got="$(q "len(d['functions']), sum(len(f['categories']) for f in d['functions'])" < "$DATA")"
[ "$got" = "(6, 22)" ] && ok "csf2.json has 6 Functions and 22 Categories" || bad "csf2.json counts ($got)"
got="$(q "all(c['id'].startswith(f['id']+'.') for f in d['functions'] for c in f['categories'])" < "$DATA")"
[ "$got" = "True" ] && ok "every Category ID starts with its Function ID" || bad "Category prefixes"

# The template lists exactly the Categories in csf2.json, in order, and kit-csf reads it as all blank.
python3 - "$DATA" "$TPL" <<'PY' && ok "template rows match csf2.json" || bad "template rows match csf2.json"
import json, re, sys
d = json.load(open(sys.argv[1])); text = open(sys.argv[2]).read()
want = [(c["id"], c["name"]) for f in d["functions"] for c in f["categories"]]
got = re.findall(r"^\| \w+ \| ([A-Z]{2}\.[A-Z]{2}) \| ([^|]+?) \|", text, re.M)
sys.exit(0 if got == want else 1)
PY
out="$(python3 "$TOOL" "$TPL" --json)"; rc=$?
[ $rc -eq 0 ] && ok "blank template: exit 0" || bad "blank template exit $rc"
[ "$(q "len(d['blank']), d['invalid_ids'], d['overall']['coverage_pct']" <<<"$out")" = "(22, [], None)" ] \
  && ok "blank template: 22 blanks, no invalid IDs, no coverage" || bad "blank template reading"
has "template cites the framework" "NIST CSF 2.0 (NIST CSWP 29, Feb 2024)" "$(cat "$TPL")"

# A filled mapping: GV 62.5, ID 83.3, PR 62.5, DE 100, RS 75, RC 50; overall 72.2.
cat > "$T/a.md" <<'MD'
# NIST CSF 2.0 mapping: Payments gateway

| Field | Value |
|---|---|
| Design | DES-0042 Payments gateway v1.2 |
| Classification | internal |

| Function | ID | Category | Addressed? | Design evidence (section) | Gap | Owner (role) | Tier or target note |
|---|---|---|---|---|---|---|---|
| Govern | GV.OC | Organizational Context | yes | 2.1 | | | |
| Govern | GV.RM | Risk Management Strategy | partial | 2.3 | Risk appetite not stated | Risk lead | |
| Govern | GV.RR | Roles, Responsibilities, and Authorities | no | | No RACI | Delivery lead | |
| Govern | GV.PO | Policy | Yes | 2.4 | | | |
| Govern | GV.OV | Oversight | n/a | | Covered at portfolio level | | |
| Govern | GV.SC | Cybersecurity Supply Chain Risk Management | <yes, partial, no, or not applicable> | | | | |
| Identify | ID.AM | Asset Management | yes | 3.1 | | | |
| Identify | ID.RA | Risk Assessment | yes | 3.2 | | | |
| Identify | ID.IM | Improvement | partial | 3.4 | | | |
| Protect | PR.AA | Identity Management, Authentication, and Access Control | yes | 4.1 | | | |
| Protect | PR.AT | Awareness and Training | not applicable | | | | |
| Protect | PR.DS | Data Security | partial | 4.3 | Key rotation not described | Security architect | Tier 3 |
| Protect | PR.PS | Platform Security | no | | No hardening baseline | Platform owner | |
| Protect | PR.IR | Technology Infrastructure Resilience | yes | 4.5 | | | |
| Detect | DE.CM | Continuous Monitoring | yes | 5.1 | | | |
| Detect | DE.AE | Adverse Event Analysis | yes | 5.2 | | | |
| Respond | RS.MA | Incident Management | yes | 6.1 | | | |
| Respond | RS.AN | Incident Analysis | no | | | | |
| Respond | RS.CO | Incident Response Reporting and Communication | yes | 6.3 | | | |
| Respond | RS.MI | Incident Mitigation | yes | 6.4 | | | |
| Recover | RC.RP | Incident Recovery Plan Execution | partial | 7.1 | DR test not planned | Service owner | |
| Protect | PR.XX | Made up | yes | | | | |
| Govern | XX.ZZ | Made up | yes | | | | |
MD
out="$(python3 "$TOOL" "$T/a.md" --json)"; rc=$?
[ $rc -eq 1 ] && ok "invalid IDs: exit 1" || bad "invalid IDs exit $rc"
for pair in "GV 62.5" "ID 83.3" "PR 62.5" "DE 100.0" "RS 75.0" "RC 50.0"; do
  set -- $pair
  got="$(q "d['functions']['$1']['coverage_pct']" <<<"$out")"
  [ "$got" = "$2" ] && ok "coverage $1 = $2" || bad "coverage $1 got $got, want $2"
done
got="$(q "d['overall']['coverage_pct'], d['overall']['applies'], d['overall']['na'], d['overall']['blank']" <<<"$out")"
[ "$got" = "(72.2, 18, 2, 1)" ] && ok "overall 72.2 over 18 that apply, 2 n/a, 1 blank" || bad "overall ($got)"
[ "$(q "sorted(x['id'] for x in d['invalid_ids'])" <<<"$out")" = "['PR.XX', 'XX.ZZ']" ] && ok "invalid IDs flagged" || bad "invalid IDs"
[ "$(q "d['blank'], d['missing']" <<<"$out")" = "(['GV.SC'], ['RC.CO'])" ] && ok "blank and missing listed" || bad "blank/missing"
[ "$(q "[g['id'] for g in d['gaps']]" <<<"$out")" = "['GV.RR', 'PR.PS', 'RS.AN', 'GV.RM', 'ID.IM', 'PR.DS', 'RC.RP']" ] \
  && ok "gaps listed, no before partial" || bad "gaps order"
[ "$(q "d['design']" <<<"$out")" = "DES-0042 Payments gateway v1.2" ] && ok "design name from the field table" || bad "design name"
txt="$(python3 "$TOOL" "$T/a.md")"
has "text: function row" "| Govern (GV) | 2 | 1 | 1 | 1 | 1 | 62.5% |" "$txt"
has "text: gap with owner" "PR.DS Data Security: partial. Key rotation not described Owner: Security architect." "$txt"
has "text: undescribed gap noted" "RS.AN Incident Analysis: no. Gap not described. Owner: not set." "$txt"
has "text: blank listed" "Left blank (1): GV.SC" "$txt"
has "text: missing listed" "Missing from the mapping (1): RC.CO" "$txt"
has "text: invalid ID line" "Invalid ID: XX.ZZ" "$txt"
has "text: coverage rule stated" "partial as half" "$txt"

# A clean mapping exits 0; --strict exits 1 while anything is blank; bad status and duplicates exit 1.
grep -v "Made up" "$T/a.md" > "$T/clean.md"
python3 "$TOOL" "$T/clean.md" >/dev/null; rc=$?; [ $rc -eq 0 ] && ok "valid mapping: exit 0" || bad "valid exit $rc"
python3 "$TOOL" "$T/clean.md" --strict >/dev/null; rc=$?; [ $rc -eq 1 ] && ok "--strict: blanks exit 1" || bad "--strict exit $rc"
sed 's/| GV.OC | Organizational Context | yes |/| GV.OC | Organizational Context | maybe |/' "$T/clean.md" > "$T/badst.md"
out="$(python3 "$TOOL" "$T/badst.md" --json)"; rc=$?
[ $rc -eq 1 ] && [ "$(q "d['bad_status'][0]['id']" <<<"$out")" = "GV.OC" ] && ok "unrecognised status flagged" || bad "bad status ($rc)"
{ cat "$T/clean.md"; echo "| Govern | GV.OC | Organizational Context | no | | | | |"; } > "$T/dup.md"
python3 "$TOOL" "$T/dup.md" >/dev/null; rc=$?; [ $rc -eq 1 ] && ok "duplicate row: exit 1" || bad "dup exit $rc"
printf '# Notes\n\nNo table here.\n' > "$T/none.md"
python3 "$TOOL" "$T/none.md" >/dev/null 2>&1; rc=$?; [ $rc -eq 2 ] && ok "no mapping table: exit 2" || bad "no table exit $rc"
python3 "$TOOL" "$T/nope.md" >/dev/null 2>&1; rc=$?; [ $rc -eq 2 ] && ok "missing file: exit 2" || bad "missing file exit $rc"

# Portfolio: mapping a plus an all-yes mapping b; non-mapping files skipped.
mkdir -p "$T/lib/p1/compliance" "$T/lib/p2/compliance"
cp "$T/a.md" "$T/lib/p1/compliance/p1-csf-mapping-v1.md"
sed -E 's/^(\| [A-Za-z]+ \| [A-Z]{2}\.[A-Z]{2} \| [^|]+\| )[^|]*\|/\1yes |/' "$TPL" > "$T/lib/p2/compliance/p2-csf-mapping-v1.md"
cp "$T/none.md" "$T/lib/p2/notes.md"
out="$(python3 "$TOOL" --portfolio "$T/lib" --json)"; rc=$?
[ $rc -eq 1 ] && ok "portfolio: exit 1 when a mapping has invalid IDs" || bad "portfolio exit $rc"
got="$(q "len(d['mappings']), d['skipped_files'], d['overall']['coverage_pct'], d['functions']['GV']['coverage_pct']" <<<"$out")"
[ "$got" = "(2, 1, 87.5, 85.0)" ] && ok "portfolio: 2 mappings, 1 skipped, overall 87.5, GV 85.0" || bad "portfolio ($got)"
[ "$(q "sorted(m['coverage_pct'] for m in d['mappings'])" <<<"$out")" = "[72.2, 100.0]" ] && ok "portfolio: per-mapping coverage" || bad "per-mapping"
[ "$(q "d['categories']['RC.CO']['blank'], d['categories']['RC.CO']['yes']" <<<"$out")" = "(1, 1)" ] && ok "portfolio: missing counts as blank per category" || bad "per-category"
[ "$(q "d['weakest'][:3]" <<<"$out")" = "['GV.RR', 'PR.PS', 'RS.AN']" ] && ok "portfolio: weakest categories first" || bad "weakest"
txt="$(python3 "$TOOL" --portfolio "$T/lib")"
has "portfolio text: header" "across 2 mapping(s)" "$txt"
has "portfolio text: mapping line" "DES-0042 Payments gateway v1.2: 72.2%, 7 gap(s)" "$txt"
rm "$T/lib/p1/compliance/p1-csf-mapping-v1.md"
python3 "$TOOL" --portfolio "$T/lib" >/dev/null; rc=$?; [ $rc -eq 0 ] && ok "portfolio: clean mappings exit 0" || bad "clean portfolio exit $rc"
python3 "$TOOL" --portfolio "$T/none-dir" >/dev/null 2>&1; rc=$?; [ $rc -eq 2 ] && ok "portfolio: missing folder exit 2" || bad "portfolio missing exit $rc"

# Read-only and local: writes nothing, no network modules.
before="$(find "$T" -type f | sort | xargs cksum)"
python3 "$TOOL" "$T/clean.md" >/dev/null; python3 "$TOOL" --portfolio "$T/lib" --json >/dev/null
[ "$before" = "$(find "$T" -type f | sort | xargs cksum)" ] && ok "writes nothing" || bad "files changed"
grep -qE "^import (urllib|http|socket|requests)|^from (urllib|http|socket)" "$TOOL" && bad "network module imported" || ok "no network modules"
python3 "$TOOL" --categories | grep -q "PR.AA  Identity Management" && ok "--categories lists categories" || bad "--categories"

echo "kit-csf tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
