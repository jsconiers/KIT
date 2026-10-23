#!/bin/bash
# Tests for shared/bin/kit-sysprofile against a fixture library. Run: bash tests/test_sysprofile.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-sysprofile"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -30; fi; }
hasnot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -30; else ok "$1"; fi; }
K="$T/kit"; L="$T/lib"
mkdir -p "$K/memory/context" "$L/published" "$L/decisions" "$L/poc" "$L/labs" "$L/radar/lifecycle" "$L/demands"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
echo "| LIB-0001 | DS-101 | Ledger Core design | 2.0 |" > "$L/published/ds-index.md"
printf '| Accession | Title |\n|---|---|\n| LIB-0001 | Ledger Core design |\n' > "$L/CATALOG.md"
echo "| ADR-0002 | Ledger Core moves to managed database | accepted |" > "$L/decisions/INDEX.md"
echo "| POC-0003 | Ledger Core read replicas | go |" > "$L/poc/INDEX.md"
echo "| LAB-0001 | read replica test for ledger core | running |" > "$L/labs/REGISTER.md"
echo "| PostgreSQL | adopt | 01-Mar-2026 |" > "$L/radar/RADAR.md"
echo "- urgent: PostgreSQL 11 on Ledger Core, end of support 09-Nov-2026" > "$L/radar/lifecycle/summary.md"
echo "| TD-1 | Ledger Core | manual failover | high |" > "$L/radar/tech-debt.md"
echo "| DEM-12 | Ledger Core reporting extract | open |" > "$L/demands/REGISTER.md"
printf 'product,version,system,environment\nPostgreSQL,11,Ledger Core,prod\nRedis,7,Cache Tier,prod\n' > "$L/radar/inventory.csv"
echo "| Ledgerless Pay | unrelated |" >> "$L/published/ds-index.md"
export KIT_DIR="$K"

out="$(python3 "$TOOL" "Ledger Core")"
has "title" "# System profile: Ledger Core" "$out"
has "inventory row cited" "PostgreSQL.*radar/inventory.csv:2" "$out"
has "document cited" "published/ds-index.md:1" "$out"
has "decision cited" "decisions/INDEX.md:1" "$out"
has "POC cited" "poc/INDEX.md:1" "$out"
has "lab matched case-insensitively" "labs/REGISTER.md:1" "$out"
has "lifecycle warning cited" "radar/lifecycle/summary.md:1" "$out"
has "tech debt cited" "radar/tech-debt.md:1" "$out"
has "demand cited" "demands/REGISTER.md:1" "$out"
has "vendors listed as unknown" "Sections with nothing recorded: Vendors" "$out"
has "missing source listed" "radar/vendors.md" "$out"
hasnot "other system not included" "Cache Tier" "$out"
hasnot "partial word not matched" "Ledgerless" "$out"
hasnot "table separator not quoted" "^- [|: -]*---" "$out"

out="$(python3 "$TOOL" "LC" --alias "Ledger Core")"
has "alias matches" "decisions/INDEX.md:1" "$out"

python3 "$TOOL" "Ledger Core" --json | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['sections']['POCs'][0]['source']=='poc/INDEX.md:1'" && ok "json output" || bad "json output"

[ ! -e "$L/artifacts" ] && ok "nothing written without --write" || bad "wrote without --write"
python3 "$TOOL" "Ledger Core" --write --project payments >/dev/null && [ -f "$L/artifacts/payments/profile-ledger-core.md" ] && ok "--write saves under artifacts/<project>" || bad "write"
python3 "$TOOL" "Ledger Core" --write --project payments >/dev/null 2>&1 && bad "overwrote without --force" || ok "refuses to overwrite without --force"
python3 "$TOOL" "Ledger Core" --write --project payments --force >/dev/null && ok "--force replaces" || bad "force"

# FEAF reference models row
has "FEAF row blank when untagged" "| FEAF reference models | (optional) |" "$(python3 "$TOOL" "Ledger Core")"
printf '| LIB-0002 | Ledger Core data design | note [FEAF: Data, Application] |\n| LIB-0003 | Cache Tier | [FEAF: Infrastructure] |\n' >> "$L/CATALOG.md"
out="$(python3 "$TOOL" "Ledger Core")"
has "FEAF from catalog tag, cited" "| FEAF reference models | Data, Application \[CATALOG.md:4\] |" "$out"
hasnot "other system's FEAF tag ignored" "FEAF reference models | .*Infrastructure" "$out"
python3 "$TOOL" "Ledger Core" --json | python3 -c "import json,sys; d=json.load(sys.stdin)['feaf']; assert d['models']==['Data','Application'] and not d['inferred'], d" && ok "FEAF in json" || bad "FEAF in json"
mkdir -p "$L/knowledge/systems"
printf '# Cache Tier\n\n- **FEAF reference models:** Infrastructure, Security (inferred)\n' > "$L/knowledge/systems/cache-tier.md"
printf '| LIB-0003 | Cache Tier | no tag |\n' > "$L/CATALOG.md"
out="$(python3 "$TOOL" "Cache Tier")"
has "FEAF from curator page marked inferred" "| FEAF reference models | Infrastructure, Security (inferred) \[knowledge/systems/cache-tier.md:3\] |" "$out"
printf '# Cache Tier\n\n| FEAF reference models | Infrastructure |\n' > "$L/knowledge/systems/cache-tier.md"
out="$(python3 "$TOOL" "Cache Tier")"
has "FEAF from curator page, not inferred" "| FEAF reference models | Infrastructure \[knowledge/systems/cache-tier.md:3\] |" "$out"
hasnot "explicit curator line not marked inferred" "(inferred)" "$out"

echo "kit-sysprofile tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
