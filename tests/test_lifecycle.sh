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

# ---- extended support, import, and data quality (fixtures in tests/fixtures/lifecycle) ----
FX="$HERE/tests/fixtures/lifecycle"
L2="$T/lib2"; R2="$L2/radar"; mkdir -p "$R2"
cp "$FX/eol-extended.json" "$R2/eol.json"

# import from a plain JSON list
out=$(python3 "$TOOL" --root "$L2" --today 2026-10-21 --import "$FX/export-list.json" --source "test export" 2>&1)
check "import prints a one-line summary" "imported 7 records from export-list.json" "$out"
check "import counts the skips" "1 skipped with no OS, 1 \"Unknown\", 1 marked duplicate" "$out"
[ -f "$R2/inventory.json" ] && ok "import writes inventory.json in the radar folder" || bad "no inventory.json: $out"
cp "$R2/inventory.json" "$T/inv-list.json"
i() { python3 -c "import json;d=json.load(open('$1'));print($2)"; }
[ "$(i "$T/inv-list.json" "sorted({r['product'] for r in d['records']})")" = "['Acme OS', 'Red Hat Linux', 'Windows Server']" ] \
  && ok "RHEL aliases become Red Hat Linux; other names kept as-is" || bad "aliases: $(i "$T/inv-list.json" "[r['product'] for r in d['records']]")"
[ "$(i "$T/inv-list.json" "[r['system'] for r in d['records'] if r['duplicate']]")" = "['host-a-03 - duplicate']" ] \
  && ok "duplicate records are kept and marked" || bad "dup: $(i "$T/inv-list.json" "d['records']")"
[ "$(i "$T/inv-list.json" "(d['skipped_no_os'], d['skipped_unknown_os'])")" = "(['host-a-06'], ['host-a-07'])" ] \
  && ok "blank and Unknown OS records are skipped and listed" || bad "skips"
[ "$(i "$T/inv-list.json" "(d['source'], d['imported'])")" = "('test export', '21-Oct-2026')" ] \
  && ok "import records the source and date" || bad "source/date: $(i "$T/inv-list.json" "(d['source'], d['imported'])")"
[ "$(i "$T/inv-list.json" "d['quality']['possible_mislabel']")" = "1" ] && ok "import carries a quality block" || bad "quality block"

# refuses to overwrite without --force; --out writes elsewhere
out=$(python3 "$TOOL" --root "$L2" --today 2026-10-21 --import "$FX/export-list.json" 2>&1); rc=$?
[ "$rc" = "1" ] && ok "import won't replace inventory.json without --force" || bad "overwrite rc=$rc"
check "and says how to replace it" "force" "$out"

# each other input shape gives the same records
for shape in export-records.json export-rows.json export.csv; do
  python3 "$TOOL" --root "$L2" --today 2026-10-21 --import "$FX/$shape" --out "$T/inv-$shape.out" >/dev/null 2>&1
  a=$(i "$T/inv-$shape.out" "[(r['system'],r['product'],r['version'],r['owner'],r['environment'],r['duplicate']) for r in d['records']], d['quality']" 2>&1)
  b=$(i "$T/inv-list.json" "[(r['system'],r['product'],r['version'],r['owner'],r['environment'],r['duplicate']) for r in d['records']], d['quality']")
  [ "$a" = "$b" ] && ok "import reads $shape the same as a JSON list" || { bad "import $shape"; echo "     $a"; }
done
check "default source names the file" "import of export.csv" "$(cat "$T/inv-export.csv.out")"

# lifecycle on the imported inventory: the extended flag
python3 "$TOOL" --root "$L2" --today 2026-10-21 --json > "$T/s2.json"
e() { python3 -c "import json;d=json.load(open('$T/s2.json'));print($1)"; }
it() { e "[(i['flag'], i['extended_urgency']) for i in d['items'] if i['version']=='$1'][0]"; }
[ "$(it 7.9)" = "('extended', 'ok')" ] && ok "7.9 past standard support with extended in 2029: extended" || bad "7.9: $(it 7.9)"
[ "$(it '2012 R2')" = "('past', None)" ] && ok "2012 R2 with extended passed: past" || bad "2012 R2: $(it '2012 R2')"
[ "$(it 7.5)" = "('past', None)" ] && ok "no extended date: past" || bad "7.5: $(it 7.5)"
[ "$(it 8.8)" = "('extended', 'urgent')" ] && ok "extended ending within 12 months is marked urgent" || bad "8.8: $(it 8.8)"
[ "$(it 8.6)" = "('extended', 'warning')" ] && ok "extended ending within 24 months is marked warning" || bad "8.6: $(it 8.6)"
[ "$(e "[i['extended_months_left'] for i in d['items'] if i['version']=='8.8'][0]")" = "7.3" ] \
  && ok "months left to the extended date" || bad "ext months"
[ "$(e "(d['counts']['past'], d['counts']['extended'], d['counts']['unknown'])")" = "(2, 3, 1)" ] \
  && ok "counts add an extended key" || bad "counts $(e "d['counts']")"
[ "$(e "[i['flag'] for i in d['items']][:2]")" = "['past', 'past']" ] && ok "past still sorts first, then extended" || bad "sort2"
[ "$(e "[i['version'] for i in d['items'] if i['flag']=='extended']")" = "['8.8', '8.6', '7.9']" ] \
  && ok "extended items sort by time left on extended support" || bad "ext sort"
check "notes extended support only applies with the subscription" "subscription is held" "$(e "d['extended_note']")"
[ "$(e "[i['duplicates'] for i in d['items'] if i['version']=='8.8'][0]")" = "1" ] && ok "items count their duplicate records" || bad "item dups"
for k in generated counts items researcher_lookups notes policy; do
  [ "$(e "'$k' in d")" = "True" ] || bad "summary.json lost key $k"
done
[ "$(e "all(k in d['items'][0] for k in ('product','version','instances','systems','environments','owners','eol','extended','months_left','source','checked','flag'))")" = "True" ] \
  && ok "existing summary and item keys are unchanged" || bad "item keys"

# data quality
[ "$(e "[d['quality'][k] for k in ('records','skipped_no_os','skipped_unknown_os','duplicates','blank_owner','blank_environment','possible_mislabel')]")" = "[7, 1, 1, 1, 1, 2, 1]" ] \
  && ok "data quality counts" || bad "quality $(e "d['quality']")"
python3 "$TOOL" --root "$L2" --today 2026-10-21 >/dev/null
md=$(cat "$R2/lifecycle/summary.md")
check "summary.md has an extended section" "## Past standard support, inside paid extended support" "$md"
check "summary.md marks the urgent extended end" "Urgent: ends in 12 months or less" "$md"
check "summary.md has a data quality section" "## Data quality" "$md"
check "mislabels are called inferred" "Possible mislabel.*inferred" "$md"

# data quality from a plain inventory (no import): duplicates, blanks, mislabels from the records
cat > "$T/inv-plain.csv" <<'EOF'
Product,Version,System,Owner,Environment
Postgres,16.2,host-b-01,Database team,Production
Postgres,16.2,host-b-02 - duplicate,,Production
Postgres,16.2,host-qa-03,Database team,Production
Postgres,16.2,host-b-04,Database team,
EOF
out=$(python3 "$TOOL" --root "$L2" --today 2026-10-21 --inventory "$T/inv-plain.csv" --eol "$T/none.json" --json)
q=$(python3 -c "import json,sys;d=json.load(sys.stdin)['quality'];print([d[k] for k in ('records','skipped_no_os','duplicates','blank_owner','blank_environment','possible_mislabel')])" <<<"$out")
[ "$q" = "[4, 0, 1, 1, 1, 1]" ] && ok "data quality works from a plain inventory" || bad "plain quality $q"

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
