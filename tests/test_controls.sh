#!/bin/bash
# Tests for shared/bin/kit-controls: 800-53 and ATT&CK lookups, search, map on a threat model, --json,
# exit codes, and a schema check of the shipped data files. Lookups run on small synthetic data
# (KIT_CONTROLS_DATA), so they don't depend on the downloaded catalogs. Run: bash tests/test_controls.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-controls"
SHIPPED="$HERE/shared/data"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -qF -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
hasnt() { if grep -qF -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -20; else ok "$1"; fi; }
q() { python3 -c "import json,sys; d=json.load(sys.stdin); r=($1); print(r)"; }
NOTICE="© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation."

# ---------------------------------------------------------------- shipped data: schema only
python3 - "$SHIPPED" <<'PY' && ok "shipped data files parse and have the expected shape" || bad "shipped data schema"
import json, pathlib, re, sys
d = pathlib.Path(sys.argv[1])
n = json.loads((d / "nist-800-53r5.json").read_text())
a = json.loads((d / "mitre-attack-enterprise.json").read_text())
m = json.loads((d / "attack-to-800-53.json").read_text())
for f in (n, a, m):
    assert f.get("source") and f.get("retrieved") and f.get("licence"), "source, retrieved, licence"
assert n["framework"] == "NIST SP 800-53 Rev 5" and n["source_urls"][0].endswith("NIST_SP-800-53_rev5_catalog.json")
assert len(n["families"]) == 20 and len(n["controls"]) > 300
ids = set()
for c in n["controls"]:
    assert re.fullmatch(r"[A-Z]{2}-\d+", c["id"]) and c["family"] == c["id"][:2] and c["title"]
    assert c.get("withdrawn") or c.get("summary"), c["id"]
    assert set(c.get("baselines", [])) <= {"low", "moderate", "high", "privacy"}
    assert all(len(x.get("summary", "")) <= 205 for x in [c])
    ids.add(c["id"])
    for e in c.get("enhancements", []):
        assert re.fullmatch(re.escape(c["id"]) + r"\(\d+\)", e["id"]) and e["title"]
        ids.add(e["id"])
for want in ("AC-2", "AC-2(1)", "SC-8", "IA-2"):
    assert want in ids, want
assert a["attribution"].startswith("© ") and "reproduced and distributed with the permission of The MITRE" in a["attribution"]
assert "non-exclusive, royalty-free license" in a["licence"]
tids = {t["id"] for t in a["techniques"]}
mids = {x["id"] for x in a["mitigations"]}
tacs = {x["shortname"] for x in a["tactics"]}
assert len(tids) > 500 and len(mids) > 20 and len(tacs) >= 14
for t in a["techniques"]:
    assert re.fullmatch(r"T\d{4}(\.\d{3})?", t["id"]) and t["name"] and t["tactics"] and t["platforms"]
    assert set(t["tactics"]) <= tacs and set(t.get("mitigations", [])) <= mids
    assert ("." in t["id"]) == ("parent" in t) and (t.get("parent") in tids if "parent" in t else True)
assert all(v in tids for v in a.get("revoked", {}).values())
assert all(re.fullmatch(r"M\d{4}", x) for x in mids)
assert m["licence"].startswith("Apache License 2.0") and m["map"]
for t, cs in m["map"].items():
    assert re.fullmatch(r"T\d{4}(\.\d{3})?", t) and (t in tids or t in a.get("revoked", {}) or t.split(".")[0] in tids), t
    assert cs and all(c in ids for c in cs), (t, [c for c in cs if c not in ids])
assert all(re.fullmatch(r"T\d{4}(\.\d{3})?", t) and t not in m["map"] for t in m.get("not_in_attack", []))
for big in ("nist-800-53r5.json", "mitre-attack-enterprise.json", "attack-to-800-53.json"):
    assert (d / big).stat().st_size < 400_000, big
PY
# Kit's keyword hints only name techniques that exist in the shipped ATT&CK data.
python3 - "$TOOL" "$SHIPPED" <<'PY' && ok "every keyword hint names a live ATT&CK technique" || bad "keyword hints"
import json, re, sys
src = open(sys.argv[1]).read().split("HINTS = [", 1)[1].split("\n]\n", 1)[0]
tids = {t["id"] for t in json.load(open(sys.argv[2] + "/mitre-attack-enterprise.json"))["techniques"]}
missing = sorted(set(re.findall(r'"(T\d{4}(?:\.\d{3})?)"', src)) - tids)
print(missing) if missing else None
sys.exit(1 if missing else 0)
PY

# ---------------------------------------------------------------- synthetic data
D="$T/data"; mkdir -p "$D"
cat > "$D/nist-800-53r5.json" <<'J'
{"framework": "NIST SP 800-53 Rev 5", "version": "test", "source": "SYNTHETIC 800-53", "retrieved": "01-Jan-2026",
 "licence": "test", "families": [{"id": "AC", "title": "Access Control"}, {"id": "AU", "title": "Audit and Accountability"}],
 "controls": [
  {"id": "AC-2", "family": "AC", "title": "Account Management", "summary": "Manage system accounts.",
   "baselines": ["low", "moderate", "high"],
   "enhancements": [{"id": "AC-2(1)", "title": "Automated System Account Management", "baselines": ["moderate", "high"]},
                    {"id": "AC-2(10)", "title": "Old Thing", "withdrawn": true}]},
  {"id": "AC-6", "family": "AC", "title": "Least Privilege", "summary": "Employ least privilege.", "baselines": ["moderate"]},
  {"id": "AU-9", "family": "AU", "title": "Protection of Audit Information", "summary": "Protect audit records."},
  {"id": "AU-99", "family": "AU", "title": "Withdrawn Example", "withdrawn": true}]}
J
cat > "$D/mitre-attack-enterprise.json" <<'J'
{"framework": "MITRE ATT&CK Enterprise", "version": "99.0", "source": "SYNTHETIC ATT&CK", "retrieved": "01-Jan-2026",
 "attribution": "© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.",
 "licence": "test",
 "tactics": [{"id": "TA0001", "shortname": "initial-access", "name": "Initial Access"},
             {"id": "TA0006", "shortname": "credential-access", "name": "Credential Access"},
             {"id": "TA0040", "shortname": "impact", "name": "Impact"}],
 "techniques": [
  {"id": "T1078", "name": "Valid Accounts", "tactics": ["initial-access"], "platforms": ["Windows", "SaaS"], "mitigations": ["M1032"]},
  {"id": "T1078.004", "name": "Cloud Accounts", "tactics": ["initial-access"], "platforms": ["IaaS"], "parent": "T1078"},
  {"id": "T1110", "name": "Brute Force", "tactics": ["credential-access"], "platforms": ["Windows"], "mitigations": ["M1032"]},
  {"id": "T1498", "name": "Network Denial of Service", "tactics": ["impact"], "platforms": ["Linux"]},
  {"id": "T1550", "name": "Use Alternate Authentication Material", "tactics": ["credential-access"], "platforms": ["Windows"]},
  {"id": "T1999", "name": "Renamed Technique", "tactics": ["impact"], "platforms": ["Linux"]}],
 "mitigations": [{"id": "M1032", "name": "Multi-factor Authentication"}],
 "revoked": {"T1900": "T1999"}}
J
cat > "$D/attack-to-800-53.json" <<'J'
{"mapping": "test", "source": "SYNTHETIC MAP", "retrieved": "01-Jan-2026", "licence": "Apache License 2.0 (test)",
 "map": {"T1078": ["AC-2", "AC-6"], "T1110": ["AC-2"], "T1550": ["AC-2", "AU-9"], "T1900": ["AU-9"]}}
J
run() { KIT_CONTROLS_DATA="$D" python3 "$TOOL" "$@"; }

# 800-53 lookups, with ID spellings normalised.
out="$(run 800-53 AC-2)"; rc=$?
[ $rc -eq 0 ] && ok "800-53 AC-2: exit 0" || bad "800-53 AC-2 exit $rc"
has "control title and family" "AC-2  Account Management" "$out"
has "summary" "Summary: Manage system accounts." "$out"
has "baselines" "Baselines: low, moderate, high" "$out"
has "live enhancement listed" "AC-2(1)  Automated System Account Management  [moderate, high]" "$out"
hasnt "withdrawn enhancement left out" "Old Thing" "$out"
has "reverse mapping to ATT&CK" "mitigates (3): T1078, T1110, T1550" "$out"
has "MITRE notice shown with ATT&CK content" "$NOTICE" "$out"
for spelling in ac-2 AC-02 "AC 2"; do
  got="$(run 800-53 "$spelling" --json 2>/dev/null | q "d['id']")"
  [ "$got" = "AC-2" ] && ok "800-53 '$spelling' reads as AC-2" || bad "800-53 '$spelling' got $got"
done
for spelling in "AC-2(1)" ac-2.1 "AC-02(01)"; do
  got="$(run 800-53 "$spelling" --json | q "d['id'], d['kind'], d['parent']['id']")"
  [ "$got" = "('AC-2(1)', 'enhancement', 'AC-2')" ] && ok "800-53 '$spelling' reads as enhancement AC-2(1)" || bad "enhancement '$spelling' ($got)"
done
got="$(run 800-53 AU-99 --json | q "d['withdrawn']")"
[ "$got" = "True" ] && ok "withdrawn control flagged" || bad "withdrawn ($got)"
out="$(run 800-53 'AC-2(1)')"
hasnt "no MITRE notice when no ATT&CK content is shown" "$NOTICE" "$out"
run 800-53 ZZ-9 >/dev/null 2>&1; rc=$?
[ $rc -eq 1 ] && ok "unknown control: exit 1" || bad "unknown control exit $rc"
run 800-53 >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "800-53 with no ID: exit 2" || bad "800-53 no ID exit $rc"

# ATT&CK lookups.
out="$(run attack T1078)"; rc=$?
[ $rc -eq 0 ] && ok "attack T1078: exit 0" || bad "attack T1078 exit $rc"
has "technique name" "T1078  Valid Accounts" "$out"
has "tactic names with IDs" "Tactics: Initial Access (TA0001)" "$out"
has "sub-techniques" "T1078.004  Cloud Accounts" "$out"
has "mitigations" "M1032  Multi-factor Authentication" "$out"
has "800-53 most specific first" "most specific first (2): AC-6, AC-2" "$out"
has "MITRE notice" "$NOTICE" "$out"
got="$(run attack t1078.4 --json | q "d['id'], d['nist_800_53'], d['nist_800_53_via']")"
[ "$got" = "('T1078.004', ['AC-6', 'AC-2'], 'T1078')" ] && ok "sub-technique falls back to its parent's mapping" || bad "parent fallback ($got)"
got="$(run attack T1999 --json | q "d['nist_800_53'], d['nist_800_53_via']")"
[ "$got" = "(['AU-9'], 'T1900')" ] && ok "technique uses the mapping of the ID it replaced" || bad "revoked mapping ($got)"
out="$(run attack T1900)"
has "revoked ID redirects" "T1900 was revoked in ATT&CK v99.0; it's now T1999." "$out"
got="$(run attack M1032 --json | q "d['kind'], [t['id'] for t in d['techniques']], d['attribution'][:6]")"
[ "$got" = "('mitigation', ['T1078', 'T1110'], '© 2026')" ] && ok "mitigation lists what it mitigates, with the notice in JSON" || bad "mitigation ($got)"
run attack T0001 >/dev/null 2>&1; rc=$?
[ $rc -eq 1 ] && ok "unknown technique: exit 1" || bad "unknown technique exit $rc"

# Search.
got="$(run search account --json | q "[x['id'] for x in d['results']['800-53']['results']], d['results']['attack']['total'], d['results']['mitigations']['total']")"
[ "$got" = "(['AC-2', 'AC-2(1)'], 2, 0)" ] && ok "search 'account': control, enhancement, and techniques" || bad "search account ($got)"
got="$(run search brute force --in attack --json | q "[x['id'] for x in d['results']['attack']['results']], d['results']['800-53']['total']")"
[ "$got" = "(['T1110'], 0)" ] && ok "search every word, limited to ATT&CK" || bad "search brute force ($got)"
got="$(run search priv --json | q "[x['id'] for x in d['results']['800-53']['results']]")"
[ "$got" = "['AC-6']" ] && ok "search matches the start of a word" || bad "search prefix ($got)"
got="$(run search vilege --json | q "d['results']['800-53']['total']")"
[ "$got" = "0" ] && ok "search doesn't match inside a word" || bad "search mid-word ($got)"
run search nothingmatches >/dev/null; rc=$?
[ $rc -eq 1 ] && ok "search with no hits: exit 1" || bad "search no hits exit $rc"

# Map: a threat model's threats table.
cat > "$T/tm.md" <<'MD'
# Threat model: Example service

| Field | Value |
|---|---|
| Design | Example design v1 |

## Threats

| ID | Flow or element | STRIDE | Threat | ATT&CK | Existing control (evidence) | Gap | 800-53 | L | I | Risk | Mitigation (owner if another team) | Test case ID |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T-01 | F-02 | Spoofing | A caller replays a captured token to the API. | | Mutual TLS (6.2) | Tokens don't expire. | | 2 | 3 | high | Short-lived tokens | TC-01 |
| T-02 | F-01 | Denial of service | A flood of requests exhausts the gateway. | | none stated | No rate limit | | 2 | 2 | medium | Rate limit | TC-02 |
| T-03 | E-01 | Spoofing | Password guessing against the login page. | T1110, T9999 | none | No lockout | AC-7, AC-2 | 2 | 3 | high | Lockout and MFA | TC-03 |
| T-04 | P-01 | Information disclosure | Brute Force of a PIN. | | | | | 1 | 1 | low | | |
| T-05 | D-01 | Tampering | The design doesn't say how backups are kept. | | | | | 1 | 1 | low | | |
| <T-nn> | <F-nn> | <category> | <threat> | | | | | | | | | |
MD
out="$(run map "$T/tm.md")"; rc=$?
[ $rc -eq 1 ] && ok "map with unknown IDs: exit 1" || bad "map unknown IDs exit $rc"
has "keyword suggestion marked" "ATT&CK (suggested): T1550 Use Alternate Authentication Material [replays]" "$out"
has "800-53 through the mapping, marked" "800-53 (suggested, via mapping): AU-9, AC-2" "$out"
has "flood suggests network DoS" "T1498 Network Denial of Service [flood]" "$out"
has "technique with no mapping" "800-53 (suggested, via mapping): none mapped" "$out"
has "given ATT&CK kept as given" "ATT&CK (given): T1110 Brute Force" "$out"
has "given 800-53 echoed" "800-53 already in the table: AC-7, AC-2" "$out"
has "unknown ATT&CK ID flagged" "Unknown ATT&CK ID: T9999 in T-03" "$out"
has "unknown 800-53 ID flagged" "Unknown 800-53 ID: AC-7 in T-03" "$out"
has "technique name matched" "T1110 Brute Force [brute force]" "$out"
has "no match said plainly" "ATT&CK: no keyword match" "$out"
hasnt "template placeholder row skipped" "<T-nn>" "$out"
has "MITRE notice" "$NOTICE" "$out"
got="$(run map "$T/tm.md" --json | q "d['threats'], [r['id'] for r in d['rows']], [t['suggested'] for t in d['rows'][0]['attack']], d['rows'][2]['attack'][0]['suggested']")"
[ "$got" = "(5, ['T-01', 'T-02', 'T-03', 'T-04', 'T-05'], [True], False)" ] && ok "map --json: rows and suggested flags" || bad "map json ($got)"
grep -v "T-03" "$T/tm.md" > "$T/clean.md"
run map "$T/clean.md" >/dev/null; rc=$?
[ $rc -eq 0 ] && ok "map with known IDs only: exit 0" || bad "map clean exit $rc"

# Without the mapping file: ATT&CK only, and it says so.
mkdir -p "$T/nomap"; cp "$D/nist-800-53r5.json" "$D/mitre-attack-enterprise.json" "$T/nomap/"
out="$(KIT_CONTROLS_DATA="$T/nomap" python3 "$TOOL" map "$T/clean.md")"
has "no mapping: says so" "No ATT&CK-to-800-53 mapping file, so no 800-53 suggestions." "$out"
hasnt "no mapping: no 800-53 lines" "800-53 (suggested" "$out"

# Errors.
printf '# Nothing here\n' > "$T/empty.md"
run map "$T/empty.md" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "map with no threats table: exit 2" || bad "map empty exit $rc"
run map "$T/missing.md" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "map with a missing file: exit 2" || bad "map missing exit $rc"
KIT_CONTROLS_DATA="$T/none" python3 "$TOOL" 800-53 AC-2 >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "missing data: exit 2" || bad "missing data exit $rc"
run frobnicate >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "unknown command: exit 2" || bad "unknown command exit $rc"

# The tool never writes: the data folder is unchanged.
before="$(ls -l "$D" | md5sum 2>/dev/null || ls -l "$D" | md5)"
run map "$T/tm.md" >/dev/null 2>&1; run search account >/dev/null
after="$(ls -l "$D" | md5sum 2>/dev/null || ls -l "$D" | md5)"
[ "$before" = "$after" ] && ok "writes nothing" || bad "data folder changed"

# Templates and agents carry the new columns and instructions.
TM="$HERE/kit/templates/threat-model-template.md"; RT="$HERE/kit/templates/red-team-review-template.md"
has "threat model template has ATT&CK and 800-53 columns" "| ID | Flow or element | STRIDE | Threat | ATT&CK | Existing control (evidence) | Gap | 800-53 |" "$(cat "$TM")"
has "threat model template carries the MITRE notice" "$NOTICE" "$(tr '\n' ' ' < "$TM")"
has "red-team template carries the MITRE notice" "$NOTICE" "$(tr '\n' ' ' < "$RT")"
has "red-team template has optional ATT&CK and 800-53 columns" "| ATT&CK (optional) | 800-53 (optional) |" "$(cat "$RT")"
has "threat modeler uses kit-controls" "kit-controls map" "$(cat "$HERE/kit/agents/threat-modeler.md")"
has "red team uses kit-controls" "kit-controls" "$(cat "$HERE/kit/agents/red-team.md")"
has "CRI Profile in the framework profile" "CRI Profile v2.x (Cyber Risk Institute, financial-sector profile of NIST CSF 2.0)" "$(cat "$HERE/kit/memory/context/compliance.md")"
has "CSF template notes CRI" "CRI Profile" "$(cat "$HERE/kit/templates/csf-mapping-template.md")"

echo; echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
