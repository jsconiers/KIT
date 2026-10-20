#!/bin/bash
# Tests shared/bin/kit-lifecycle against a fixture library in a temp folder. Nothing outside the
# temp folder is read or written, and nothing reaches the network.
#   bash tests/test_lifecycle.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-lifecycle"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
check()    { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
checknot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -20; else ok "$1"; fi; }

K="$T/kit"; L="$T/library"; R="$L/radar"
mkdir -p "$K/memory/context" "$R"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
export KIT_DIR="$K"

cat > "$R/inventory.csv" <<'EOF'
Product,Version,System,Owner,Environment
Postgres,12.4,orders-db-01,Database engineering,prod
Postgres,12.9,orders-db-02,Database engineering,prod
Postgres,16.2,ledger-db-01,Database engineering,prod
Java,8u391,batch-app-03,Platform team,uat
Kafka,3.6.1,events-01,Messaging team,prod
Widget Server,2.0,legacy-07,Platform team,prod
EOF
cat > "$R/eol.json" <<'EOF'
[
 {"product": "Postgres", "cycle": "12", "eol": "2024-11-14", "source": "https://example.org/pg", "checked": "2026-10-01"},
 {"product": "Postgres", "cycle": "16", "eol": "2028-11-09", "source": "https://example.org/pg", "checked": "2026-10-01"},
 {"product": "Java", "cycle": "8", "eol": "2027-06-30", "extended": "2030-12-31", "source": "https://example.org/java", "checked": "2026-09-15"},
 {"product": "Kafka", "cycle": "3.6", "eol": "2027-09-01", "source": "", "checked": "2026-10-01"}
]
EOF

out=$(python3 "$TOOL" --today 2026-10-19 --json)
echo "$out" > "$T/s.json"
c() { python3 -c "import json;d=json.load(open('$T/s.json'));print($1)"; }
[ "$(c "d['counts']['past']")" = "2" ] && ok "Postgres 12.4 and 12.9 are both past end of support" || bad "past count: $(c "d['counts']")"
[ "$(c "[i['instances'] for i in d['items'] if i['version']=='12.4' or i['version']=='12.9']")" = "[1, 1]" ] \
  && ok "each version is its own row" || bad "rows: $(c "[(i['product'],i['version']) for i in d['items']]")"
[ "$(c "[i['flag'] for i in d['items'] if i['product']=='Java'][0]")" = "urgent" ] && ok "Java 8u391 matches cycle 8: urgent (8 months)" \
  || bad "java flag $(c "[i for i in d['items'] if i['product']=='Java']")"
[ "$(c "[i['flag'] for i in d['items'] if i['version']=='16.2'][0]")" = "ok" ] && ok "Postgres 16 is ok (25 months)" || bad "pg16"
[ "$(c "[i['flag'] for i in d['items'] if i['product']=='Kafka'][0]")" = "unknown" ] && ok "an EOL date without a source counts as unknown" || bad "kafka unsourced"
[ "$(c "d['items'][0]['flag']")" = "past" ] && ok "past items sort first" || bad "sort"
check "unknown products go on the researcher list" "Widget Server 2.0" "$(c "d['researcher_lookups']")"
checknot "the researcher list never includes system names" "legacy-07" "$(c "d['researcher_lookups']")"
check "unsourced dates are noted" "no source" "$(c "d['notes']")"
check "it says no outside service was called" "No outside EOL service" "$(c "d['policy']")"

# warning band and stale checks
cat > "$T/eol2.json" <<'EOF'
{"entries": [{"product": "Kafka", "cycle": "3.6", "eol": "2028-03-01", "source": "https://example.org/k", "checked": "2025-01-01"}]}
EOF
out=$(python3 "$TOOL" --today 2026-10-19 --eol "$T/eol2.json" --json)
check "17 months left is a warning" '"flag": "warning"' "$out"
check "a date checked over 180 days ago is listed for a recheck" "recheck" "$out"

# JSON inventory with other column names
cat > "$T/inv.json" <<'EOF'
{"records": [{"software": "Java", "release": "8.0.2", "configuration item": "app-9", "support group": "Platform team", "env": "dev"}]}
EOF
out=$(python3 "$TOOL" --today 2026-10-19 --inventory "$T/inv.json" --json)
check "JSON inventory with other column names is read" '"product": "Java"' "$out"

# writes the summary files
out=$(python3 "$TOOL" --today 2026-10-19)
[ -f "$R/lifecycle/summary.md" ] && [ -f "$R/lifecycle/summary.json" ] && ok "writes lifecycle/summary.md and summary.json" || bad "files: $out"
md=$(cat "$R/lifecycle/summary.md")
check "summary has a past section" "## Past end of support" "$md"
check "summary says it flags only" "Flags only" "$md"
checknot "summary contains no verdict words as decisions" "Verdict:" "$md"

# no network: the tool has no URL-opening code
checknot "the tool never opens a URL" "urlopen\|urllib.request\|http.client\|socket" "$(cat "$TOOL" "$HERE/shared/kit_radar.py")"

# missing inputs
rm "$R/inventory.csv"
out=$(python3 "$TOOL" --today 2026-10-19 2>&1); rc=$?
[ "$rc" = "2" ] && ok "no inventory: exit 2" || bad "no inventory rc=$rc"
check "no inventory: says how to get one" "gateway" "$out"
printf 'Product,Version\nJava,8\n' > "$R/inventory.csv"; rm "$R/eol.json"
out=$(python3 "$TOOL" --today 2026-10-19 --json)
check "no eol.json: everything unknown, with a note" "no eol.json yet" "$out"

echo "lifecycle tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
