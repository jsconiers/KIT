#!/bin/bash
# Tests shared/bin/kit-roadmap against a fixture library in a temp folder.
#   bash tests/test_roadmap.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-roadmap"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
check()    { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
checknot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -20; else ok "$1"; fi; }

K="$T/kit"; L="$T/library"; R="$L/radar"
mkdir -p "$K/memory/context" "$R/lifecycle" "$L/poc"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
export KIT_DIR="$K"

cat > "$R/RADAR.md" <<'EOF'
# Radar

| Technology | Ring | Quadrant | Vote date | Ballot |
|---|---|---|---|---|
| Event streaming | adopt | Platforms | 02-Oct-2026 | ballots/event-streaming-2026-10-02.md |
| Service mesh | trial | Platforms | 02-Oct-2026 | ballots/mesh.md |
| Legacy queue | hold | Platforms | 02-Oct-2026 | ballots/legacy-queue.md |
| Graph database | assess | Data | 02-Oct-2026 | ballots/graph.md |
EOF
cat > "$R/lifecycle/summary.json" <<'EOF'
{"items": [
 {"product": "Postgres", "version": "12.4", "flag": "past", "eol": "14-Nov-2024"},
 {"product": "Java", "version": "8", "flag": "warning", "eol": "30-Jun-2028"},
 {"product": "Kafka", "version": "3.6", "flag": "ok", "eol": "01-Sep-2029"}
]}
EOF
cat > "$R/tech-debt.md" <<'EOF'
# Tech debt register

## Open

| Id | Item | System | Type | Impact | Risk | Rough cost to fix | Lifecycle link and verdict | Owner | Target date | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| TD-001 | Hard-coded hostnames in batch jobs | batch | code | outages on moves | high | likely | | Platform team | | open |
| TD-002 | Manual certificate renewal | web | ops | expiry risk | low | low | | Platform team | 01-Jan-2029 | open |
| TD-003 | Old logging agent | all | tooling | gaps | medium | high | | Platform team | | closed |
EOF
cat > "$L/poc/INDEX.md" <<'EOF'
| Id | Title | Vendor | Status | Sponsor | Dates | Verdict |
|---|---|---|---|---|---|---|
| POC-0001 | Secrets vault | internal | closed | Platform lead | Sep-2026 | go |
| POC-0002 | Low-code portal | VendorX | closed | Apps lead | Aug-2026 | no-go |
EOF

out=$(python3 "$TOOL" --root "$L" --start 2026-11-01 --today 2026-10-19 --json)
echo "$out" > "$T/r.json"
c() { python3 -c "import json;d=json.load(open('$T/r.json'));print($1)"; }
titles=$(c "'\n'.join(i['title']+' | Y'+str(i['horizon']) for i in d['initiatives'])")
check "adopt -> roll out, year 1" "Roll out Event streaming | Y1" "$titles"
check "trial -> pilot and decide, year 1" "Pilot Service mesh and decide on adoption | Y1" "$titles"
check "hold -> stop new use, year 2" "Stop new use of Legacy queue; plan the exit | Y2" "$titles"
checknot "assess entries make no initiative" "Graph database" "$titles"
check "past end of support -> year 1" "Postgres 12.4 end of support.*| Y1" "$titles"
check "warning -> year 2" "Java 8 end of support.*| Y2" "$titles"
checknot "ok lifecycle items make no initiative" "Kafka" "$titles"
check "high-risk debt -> year 1" "Fix TD-001: Hard-coded hostnames in batch jobs | Y1" "$titles"
check "debt with a target date over two years out -> year 3" "Fix TD-002: Manual certificate renewal | Y3" "$titles"
checknot "closed debt is left out" "TD-003" "$titles"
check "POC go verdict -> deliver, year 1" "Deliver Secrets vault (POC-0001 go) | Y1" "$titles"
checknot "no-go POCs are left out" "Low-code portal" "$titles"
[ "$(c "d['draft']")" = "True" ] && ok "marked as a draft" || bad "draft flag"
check "ids are numbered" '"id": "R-01"' "$out"

md=$(python3 "$TOOL" --root "$L" --start 2026-11-01 --today 2026-10-19 --stdout)
check "markdown says it's a draft for the planner and approvers" "Draft for the future tech planner and the voters and approvers" "$md"
check "has a Mermaid gantt" '```mermaid' "$md"
check "gantt has a section per year" "section Year 2" "$md"
check "costs are left for the cost estimator" "ask the cost estimator" "$md"
check "sources are cited" "RADAR.md: Event streaming (adopt, vote 02-Oct-2026)" "$md"

out=$(python3 "$TOOL" --root "$L" --start 2026-11-01 --today 2026-10-19)
f="$R/roadmap/draft-2026-10-19.md"
[ -f "$f" ] && ok "writes roadmap/draft-<date>.md" || bad "no draft file: $out"
out=$(python3 "$TOOL" --root "$L" --start 2026-11-01 --today 2026-10-19 2>&1); rc=$?
[ "$rc" = "1" ] && check "won't overwrite today's draft without --force" "already exists" "$out" || bad "overwrite rc=$rc"
python3 "$TOOL" --root "$L" --start 2026-11-01 --today 2026-10-19 --force >/dev/null && ok "--force replaces it" || bad "--force"

E="$T/empty"; mkdir -p "$E"
md=$(python3 "$TOOL" --root "$E" --today 2026-10-19 --stdout)
check "an empty radar folder gives an empty draft with a note" "No initiatives yet" "$md"
check "default start is the first of next month" "starts 01-Nov-2026" "$md"

echo "roadmap tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
