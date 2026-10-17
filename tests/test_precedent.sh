#!/bin/bash
# Tests for shared/bin/kit-precedent against a fixture library in a temp folder.
# Run: bash tests/test_precedent.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-precedent"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }
check() { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /'; fi; }
checknot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /'; else ok "$1"; fi; }

# Fixture Kit and library
K="$T/kit"; L="$T/library"
mkdir -p "$K/memory/context" "$L/knowledge" "$L/decisions" "$L/poc" "$L/published" "$L/radar"
cat > "$K/memory/context/library.md" <<EOF
- **Library root:** \`$L\`.
EOF
cat > "$K/memory/context/precedent.md" <<'EOF'
- **Sources:** test list.
  - `CATALOG.md`
  - `knowledge/`
  - `decisions/INDEX.md`
  - `poc/INDEX.md`
  - `published/`
  - `labs/REGISTER.md`
- **Current means:** 36 months.
EOF
echo "| LIB-0007 | Message bus upgrade design | current |" > "$L/CATALOG.md"
echo "- Kafka chosen over RabbitMQ for the trade event bus [LIB-0007 §3]" > "$L/knowledge/decisions.md"
echo "| ADR-0003 | Use Kafka for the event bus | accepted | 02-Mar-2026 |" > "$L/decisions/INDEX.md"
echo "| POC-0002 | Kafka tiered storage | no-go | 10-Jan-2026 |" > "$L/poc/INDEX.md"
echo "| Event Bus @ DS-101.pdf | event bus reference design |" > "$L/published/gds-index.md"
echo "not an index" > "$L/published/binary.pdf"
export KIT_DIR="$K"

out="$(python3 "$TOOL" kafka)"
check "finds term in several sources" "decisions/INDEX.md:1" "$out"
check "finds POC register" "poc/INDEX.md:1" "$out"
check "reports hit count" "hit(s) in" "$out"
checknot "skips non-text files" "binary.pdf" "$out"
first="$(python3 "$TOOL" kafka "event bus" | head -1)"
check "decision record with phrase ranks first" "decisions/INDEX.md" "$first"
out="$(python3 "$TOOL" "event bus")"
check "phrase search" "gds-index.md:1" "$out"
check "missing source reported" "missing sources, skipped: labs/REGISTER.md" "$out"
out="$(python3 "$TOOL" zzzunknown)"
check "no precedent stated plainly" "no precedent found" "$out"
out="$(python3 "$TOOL" --sources)"
check "sources list shows ok" "ok      knowledge/" "$out"
check "sources list shows missing" "missing labs/REGISTER.md" "$out"
out="$(python3 "$TOOL" --json kafka)"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["hits"] and "labs/REGISTER.md" in d["missing"]' <<<"$out" \
  && ok "json output" || bad "json output"
out="$(python3 "$TOOL" --limit 1 kafka | grep -c '^ *[0-9]* ')"
[ "$out" = "1" ] && ok "limit" || bad "limit (got $out)"
rm "$K/memory/context/library.md"
out="$(python3 "$TOOL" kafka 2>&1)"
check "no library root handled" "no library root set" "$out"
out="$(python3 "$TOOL" --root "$L" kafka)"
check "--root override" "decisions/INDEX.md:1" "$out"
rm "$K/memory/context/precedent.md"
out="$(python3 "$TOOL" --root "$L" kafka)"
check "default sources when setup missing" "decisions/INDEX.md:1" "$out"

echo "kit-precedent tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
