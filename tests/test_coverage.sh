#!/bin/bash
# Tests for shared/bin/kit-coverage against a synthetic library with a few projects and each artifact
# type. Run: bash tests/test_coverage.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-coverage"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if [[ "$3" == *"$2"* ]]; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }
K="$T/kit"; L="$T/lib"; A="$L/artifacts"
mkdir -p "$K/memory/context" "$K/briefs" "$A/payments-hub"/{standards,threat-model,red-team,reviews,compliance} \
         "$A/ledger"/{standards,reviews} "$A/empty-proj" "$L/waivers"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
export KIT_DIR="$K"

profile() {  # $1 CSF, $2 Zero Trust, $3 Secure by Design, $4 PCI DSS
cat > "$K/memory/context/compliance.md" <<EOF
# Compliance setup

## Framework profile

| Framework | Version | Applies? | Systems or data classes in scope | Owner (role) | Where the control list is |
|---|---|---|---|---|---|
| NIST Cybersecurity Framework (CSF) | 2.0 | $1 | all | Security architect | public |
| PCI DSS | v4.0.1 | $4 | cardholder data only | Compliance lead | team copy |
| CISA Zero Trust Maturity Model | 2.0 | $2 | all | Security architect | public |
| CISA Secure by Design | 2023/2024 | $3 | all | Architecture lead | public |
EOF
}
profile yes yes no yes

csfmap() {  # $1 file, $2 status for GV.OC, $3 status for PR.PS
cat > "$1" <<EOF
# NIST CSF 2.0 mapping: Payments hub

| Field | Value |
|---|---|
| Design | Payments hub GDS v1 |
| Classification | internal |

| Function | ID | Category | Addressed? | Design evidence (section) | Gap | Owner (role) | Tier or target note |
|---|---|---|---|---|---|---|---|
| Govern | GV.OC | Organizational Context | $2 | 2.1 | | | |
| Identify | ID.AM | Asset Management | yes | 3.1 | | | |
| Protect | PR.AA | Identity Management, Authentication, and Access Control | yes | 4.1 | | | |
| Protect | PR.PS | Platform Security | $3 | | No hardening baseline | Platform owner | |
| Detect | DE.CM | Continuous Monitoring | partial | 5.1 | Alert routing not stated | SOC lead | |
EOF
}
csfmap "$A/payments-hub/compliance/payments-hub-csf-mapping-v1.md" no no
csfmap "$A/payments-hub/compliance/payments-hub-csf-mapping-v2.md" yes no

cat > "$A/payments-hub/standards/payments-hub-zero-trust-rating-v1.md" <<'EOF'
# Zero Trust rating: Payments hub

| Field | Value |
|---|---|
| Target stage | Advanced |
| Classification | internal |

## Ratings

| Area | Stage | Evidence (design section or page) | Gaps to the next stage | Question or owner (role) |
|---|---|---|---|---|
| Identity | Advanced | 4.1 | | |
| Devices | Initial | 4.2 | No device posture | |
| Networks | Advanced | 4.3 | | |
| Applications and Workloads | Optimal | 4.4 | | |
| Data | can't rate | not stated | | Data owner |
| Visibility and Analytics (cross-cutting) | Traditional | 5.1 | | |
| Automation and Orchestration (cross-cutting) | Advanced | 5.2 | | |
| Governance (cross-cutting) | Advanced | 2.1 | | |
EOF

cat > "$A/payments-hub/standards/payments-hub-standards-check-v1.md" <<'EOF'
# Standards check: Payments hub

## Conformance

| Standard | Clause | Result | Evidence | Design section |
|---|---|---|---|---|
| Encryption standard v3 | 4.1 | Conforms | TLS 1.2+ | 4.3 |
| Logging standard v2 | 2.2 | Gap | No log retention | 5.1 |
| MFA standard v1 | 1.1 | Conforms | SSO with MFA | 4.1 |
| DR standard v2 | 3.4 | Can't tell | RPO not stated | 6 |
| Patching standard v1 | 2.0 | Not applicable | Managed service | 4.4 |

## Exceptions

| Standard and clause | What the design does instead | Reason | Compensating control | Grants it (role) |
|---|---|---|---|---|
| Logging standard v2, 2.2 | 30-day retention | Vendor limit | Export to SIEM | Security architect |
EOF

cat > "$A/payments-hub/threat-model/payments-hub-threat-model-v1.md" <<'EOF'
# Threat model: Payments hub

| Field | Value |
|---|---|
| Risk rating rule | default |

## Threats

| ID | Flow or element | STRIDE | Threat | Existing control (evidence) | Gap | L | I | Risk | Mitigation (owner if another team) | Test case ID |
|---|---|---|---|---|---|---|---|---|---|---|
| T-01 | F-01 | Spoofing | Forged client | mTLS (4.3) | none | 1 | 3 | medium | | TC-01 |
| T-02 | F-02 | Tampering | Message replay | none stated | No replay protection | 3 | 3 | high | Nonces | TC-02 |
| T-03 | D-01 | Information disclosure | Backup copies readable | none stated | Backup encryption not stated | 2 | 2 | medium | Encrypt backups | TC-03 |
| T-04 | P-01 | Denial of service | Burst traffic | rate limit | Limit not sized | 1 | 2 | low | | TC-04 |
EOF

cat > "$A/payments-hub/red-team/payments-hub-red-team-v1.md" <<'EOF'
# Red-team review: Payments hub

## Findings, most consequential first

| ID | Consequence | Likelihood | Area | Failure scenario | Evidence | Mitigation |
|---|---|---|---|---|---|---|
| RT-01 | critical | likely: one region | DR | Region loss stops payments | 6 | Second region |
| RT-02 | major | possible | Capacity | Peak exceeds queue depth | 5.2 | Size the queue |
| RT-03 | minor | unlikely | Ops | Cert expiry | not stated | Automate renewal |
EOF

cat > "$A/payments-hub/reviews/payments-hub-gds-review-v1.md" <<'EOF'
# Review: Payments hub GDS

## Findings

| ID | Severity | Category | Template | Section | Finding | Fix |
|---|---|---|---|---|---|---|
| F-01 | major | risk | GDS | 6 DR | RPO not stated. | State it. |

## Secure by Design

| # | Question (short) | Answer | Evidence |
|---|---|---|---|
| 1 | Secure by default | yes | 4.1 |
| 2 | No default passwords | yes | 4.1 |
| 3 | Phishing-resistant MFA | partial | not stated |
| 4 | Removes classes of flaw | no | |
| 5 | Security logs by default | yes | 5.1 |
EOF

cat > "$A/payments-hub/payments-hub-waivers.md" <<'EOF'
# Waivers: Payments hub

| Waiver | Standard | Status | Expires |
|---|---|---|---|
| W-01 | Logging standard v2, 2.2 | Granted | 31-Mar-2027 |
| W-00 | Old exception | Expired | 01-Jan-2026 |
EOF

cat > "$A/ledger/standards/ledger-standards-check-v2.md" <<'EOF'
# Standards check: Ledger

| Standard | Clause | Result | Evidence | Design section |
|---|---|---|---|---|
| Encryption standard v3 | 4.1 | Conforms | | 3 |
| Logging standard v2 | 2.2 | Conforms | | 4 |
EOF
cat > "$A/ledger/reviews/ledger-review-v1.md" <<'EOF'
# Review: Ledger

## Secure by Design

| # | Question (short) | Answer | Evidence |
|---|---|---|---|
| 1 | Secure by default | yes | 2 |
| 4 | Removes classes of flaw | no | |
EOF

cat > "$L/waivers/waiver-register.md" <<'EOF'
# Waiver register

| ID | Project | Standard | Status | Expiry |
|---|---|---|---|---|
| WR-7 | ledger | Patching standard v1 | Open | 30-Jun-2027 |
| WR-3 | ledger | DR standard v2 | Closed | 01-Feb-2026 |
EOF

snap() { find "$L" -type f -exec shasum {} \; | sort; }
before="$(snap)"

# --- Markdown report ---
out="$(python3 "$TOOL")"; rc=$?
[ $rc -eq 0 ] && ok "exit 0" || bad "exit $rc"
has "profile line names the required frameworks" "required: NIST CSF 2.0, Zero Trust" "$out"
has "other profiled framework noted" "with no Kit artifact to measure: PCI DSS" "$out"
hasnot "no 'profile not set' banner when set" "Framework profile not set" "$out"
has "CSF uses the latest version (v2) via kit-csf" "| payments-hub | 70.0%; 2 open (1 no)" "$out"
has "Zero Trust lowest pillar and below target" "lowest Traditional (Visibility and Analytics); 2 below Advanced; 1 can't rate" "$out"
has "standards counts and waiver candidates" "2 conform, 1 gap, 1 can't tell; 1 waiver candidate(s)" "$out"
has "threat model open high and medium" "1 high, 1 medium open" "$out"
has "red team critical and major" "1 critical, 1 major open" "$out"
has "Secure by Design greyed: not in profile" "(3 yes, 1 partial, 1 no; not in profile)" "$out"
has "project waiver open, expired one left out" "Waiver open: W-01; Logging standard v2, 2.2 (Granted, expires 31-Mar-2027)" "$out"
hasnot "expired waiver not shown" "W-00" "$out"
has "register waiver assigned to its project" "ledger: WR-7; Patching standard v1 (Open, expires 30-Jun-2027)" "$out"
hasnot "closed register waiver not shown" "WR-3" "$out"
has "required framework missing is flagged" "| ledger | **no assessment** (required) | **no assessment** (required)" "$out"
has "no assessment list per framework" "- NIST CSF 2.0: empty-proj, ledger" "$out"
has "design with nothing assessed" "Nothing assessed at all: empty-proj" "$out"
has "weakest CSF category" "NIST CSF 2.0 PR.PS Platform Security: no in 1, partial in 0" "$out"
has "weakest Zero Trust pillar" "Zero Trust Data: lowest n/a" "$out"
has "weakest Secure by Design question across designs" "Secure by Design 4 Removes classes of flaw: no in 2, partial in 0" "$out"
has "open gaps by design list a threat" "Threat T-02 high: No replay protection" "$out"

# --- --json ---
python3 "$TOOL" --json | python3 -c "
import json, sys
r = json.load(sys.stdin)
d = {x['design']: x for x in r['designs']}
assert set(d) == {'payments-hub', 'ledger', 'empty-proj'}
f = d['payments-hub']['frameworks']
assert f['csf']['state'] == 'required' and f['csf']['file'].endswith('-v2.md')
assert f['sbd']['state'] == 'not in profile' and f['standards']['state'] == 'kit review'
assert f['threat']['detail']['high'] == 1 and f['redteam']['detail']['critical'] == 1
assert f['zt']['detail']['pillars']['Devices'] == 1
assert d['ledger']['frameworks']['waivers']['open'] == 1
assert r['profile']['set'] is True
assert r['portfolio']['nothing_assessed'] == ['empty-proj']
assert len(r['portfolio']['open_waivers']) == 2
" && ok "--json structure" || bad "--json structure"

# --- --project ---
out="$(python3 "$TOOL" --project ledger)"
has "--project shows one design" "# Framework coverage: 1 design(s)" "$out"
hasnot "--project leaves others out" "payments-hub |" "$out"
python3 "$TOOL" --project nope >/dev/null 2>&1 && bad "missing project accepted" || ok "missing project refused"

# --- --write: HTML and JSON in briefs/, self-contained ---
python3 "$TOOL" --write >/dev/null 2>&1
[ -f "$K/briefs/coverage.html" ] && [ -f "$K/briefs/coverage.json" ] && [ -f "$K/briefs/coverage.md" ] \
  && ok "--write saves briefs/coverage.html, .json, and .md" || bad "--write files"
python3 - "$K/briefs/coverage.html" "$K/briefs/coverage.json" <<'PY' && ok "HTML is self-contained, greyed column, JSON parses" || bad "HTML content"
import sys, json, re
h = open(sys.argv[1]).read()
assert h.startswith("<!doctype html>") and "</html>" in h
assert not re.search(r"""(src|href)\s*=\s*["']?(https?:|//)""", h), "external asset"
assert "<script" not in h and "@import" not in h
assert 'class="greyed"' in h and "Secure by Design (not in profile)" in h
assert "NIST CSF 2.0 (required)" in h and "payments-hub" in h
assert "missing required" in h
json.load(open(sys.argv[2]))
PY
python3 "$TOOL" --write --out "$T/out" >/dev/null 2>&1 && [ -f "$T/out/coverage.html" ] && ok "--out moves the files" || bad "--out"

# --- profile not set ---
profile "not set" "not set" "not set" "not set"
out="$(python3 "$TOOL")"
has "profile not set: said at the top" "**Framework profile not set**" "$(echo "$out" | sed -n 5p)"
hasnot "profile not set: nothing marked required" "(required)" "$out"
hasnot "profile not set: nothing greyed" "not in profile" "$out"
python3 "$TOOL" --write >/dev/null 2>&1
has "profile not set: HTML banner" 'class="banner"' "$(cat "$K/briefs/coverage.html")"
rm "$K/memory/context/compliance.md"
has "no compliance.md: profile not set" "Framework profile not set" "$(python3 "$TOOL")"

# --- read-only on the library ---
[ "$before" = "$(snap)" ] && ok "library unchanged" || bad "library was changed"

# --- no library ---
KIT_DIR="$T/none" python3 "$TOOL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "no library root: exit 2" || bad "no library exit"

echo "kit-coverage tests: $pass passed, $fail failed"
[ "$fail" = 0 ]
