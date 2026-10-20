#!/bin/bash
# Tests for shared/bin/kit-refarch against a fixture library. Run: bash tests/test_refarch.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-refarch"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
hasnot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -20; else ok "$1"; fi; }
K="$T/kit"; L="$T/lib"
mkdir -p "$K/memory/context" "$L/published" "$L/decisions" "$L/poc"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
cat > "$K/memory/context/standards.md" <<'EOF'
- **Reference architectures:** the published design specifications in `published/ds-index.md`; see `library.md`.
- **Security baselines:** not set.
EOF
cat > "$L/published/ds-index.md" <<'EOF'
# Published index

| Accession | Number | Title | Version | Modified | File | Notes |
|---|---|---|---|---|---|---|
| LIB-0001 | DS-101 | Kafka Event Streaming Platform | 2.0 | 08-Apr-2026 | `Kafka Event Streaming @ DS-101.pdf` | |
| LIB-0002 | DS-102 | RabbitMQ Messaging | 1.0 | 01-Jan-2018 | `RabbitMQ @ DS-102.pdf` | superseded by DS-101 |
| LIB-0003 | DS-103 | Payroll Reporting | 1.1 | 02-Feb-2026 | `Payroll @ DS-103.pdf` | |
EOF
echo "| ADR-0004 | Use Kafka for event streaming | accepted | 02-Mar-2026 |" > "$L/decisions/INDEX.md"
echo "| POC-0001 | Kafka tiered storage | go | 10-Jan-2026 |" > "$L/poc/INDEX.md"
export KIT_DIR="$K"
R="--today 2026-10-19"

out="$(python3 "$TOOL" $R "We need an event streaming platform on Kafka for trade events with DR failover and TLS.")"
has "best match ranked first" "| 1 | Kafka Event Streaming Platform | DS-101 |" "$out"
has "explains why (technology in title)" "technology 'kafka' in the title" "$out"
has "phrase match counted" "phrase 'event streaming'" "$out"
has "NFRs extracted" "resilience: dr, failover" "$out"
has "security NFR extracted" "security: tls" "$out"
has "cites the index line" "published/ds-index.md:5" "$out"
has "related precedent from decisions" "decisions/INDEX.md" "$out"
hasnot "unrelated document not suggested" "Payroll Reporting" "$out"
hasnot "setup file not treated as an index" "Missing reference-architecture sources" "$out"

out="$(python3 "$TOOL" $R "Replace RabbitMQ messaging")"
has "superseded document marked" "superseded or withdrawn" "$out"

out="$(python3 "$TOOL" $R "A garden watering schedule for the office plants")"
has "no good match said plainly" "No good match" "$out"

json="$(python3 "$TOOL" $R --json "Kafka event streaming")"
python3 - "$json" <<'PY' && ok "json output parses with matches and terms" || bad "json output"
import json,sys
d=json.loads(sys.argv[1]); assert d["good_match"] and d["matches"][0]["number"]=="DS-101" and "kafka" in d["terms"]["technologies"]
PY
out="$(echo "Kafka streaming platform" | python3 "$TOOL" $R)"
has "reads the demand from stdin" "DS-101" "$out"
printf 'Kafka event streaming\n' > "$T/demand.md"
out="$(python3 "$TOOL" $R --file "$T/demand.md")"
has "reads the demand from a file" "DS-101" "$out"

rm "$K/memory/context/standards.md"
mkdir -p "$L/published"; mv "$L/published/ds-index.md" "$L/published/gds-index.md"
out="$(python3 "$TOOL" $R "Kafka event streaming")"
has "falls back to the published GDS index" "published/gds-index.md" "$out"

echo "kit-refarch tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
