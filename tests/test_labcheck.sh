#!/bin/bash
# Tests for shared/bin/kit-labcheck. Run: bash tests/test_labcheck.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-labcheck"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }
check() { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /'; fi; }
checknot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /'; else ok "$1"; fi; }

K="$T/kit"; mkdir -p "$K/memory/context"
export KIT_DIR="$K"

cat > "$T/clean.md" <<'EOF'
# Lab runbook: LAB-0001
| Data | <synthetic, masked, or public; production data needs the data owner's approval> |
Load the synthetic trade set from the generator. No production data is used.
Use the non-production network segment only; nonprod hosts are fine.
This lab has zero customer data.
EOF
out="$(python3 "$TOOL" "$T/clean.md")"; rc=$?
[ $rc -eq 0 ] && ok "clean runbook exits 0" || { bad "clean runbook exits 0 (rc=$rc)"; echo "$out"; }
check "clean runbook reports 0 findings" "0 finding" "$out"

cat > "$T/dirty.md" <<'EOF'
Step 3: copy the production database to the lab.
Step 4: load customer data from the nightly extract.
Step 5: connect to db01.prod.example.com for reference data.
Test card 4111 1111 1111 1111 in the payment flow.
Use SSN 123-45-6789 for the test user.
The sheet is marked Confidential.
EOF
out="$(python3 "$TOOL" "$T/dirty.md")"; rc=$?
[ $rc -eq 1 ] && ok "dirty runbook exits 1" || bad "dirty runbook exits 1 (rc=$rc)"
check "flags production database" "dirty.md:1: production database" "$out"
check "flags customer data" "dirty.md:2: customer data" "$out"
check "flags prod hostname" "dirty.md:3: production hostname" "$out"
check "flags Luhn-valid card number" "dirty.md:4: card number shape" "$out"
check "flags SSN shape" "dirty.md:5: social security number shape" "$out"
check "flags confidential" "dirty.md:6: confidential" "$out"
checknot "masks the card number" "4111 1111 1111 1111" "$out"
checknot "masks the SSN" "123-45-6789" "$out"

echo "Order id 1234567890123 is not a card." > "$T/notcard.md"
out="$(python3 "$TOOL" "$T/notcard.md")"
checknot "non-Luhn number not flagged as card" "card number shape" "$out"

out="$(python3 "$TOOL" --json "$T/dirty.md")"
check "json output has findings" '"term": "customer data"' "$out"

out="$(python3 "$TOOL" "$T/missing.md" 2>&1)"; rc=$?
[ $rc -eq 2 ] && ok "missing file exits 2" || bad "missing file exits 2 (rc=$rc)"

cat > "$K/memory/context/labs.md" <<'EOF'
# Lab setup
- **Data rule check terms:** trade blotter, /\bcorpdb\d+\b/
- **Template:** something
EOF
echo "Pull the trade blotter from corpdb7 nightly." > "$T/custom.md"
out="$(python3 "$TOOL" "$T/custom.md")"
check "custom word term from labs.md" "trade blotter" "$out"
check "custom regex term from labs.md" "corpdb" "$out"
out="$(python3 "$TOOL" --terms)"
check "--terms reports labs.md source" "plus 2 from" "$out"

printf -- '- **Data rule check terms:** not set. Extra terms.\n' > "$K/memory/context/labs.md"
out="$(python3 "$TOOL" --terms)"
check "not set falls back to built-in" "built-in only" "$out"

echo "kit-labcheck tests: $pass passed, $fail failed"
[ $fail -eq 0 ]
