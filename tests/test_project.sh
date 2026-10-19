#!/bin/bash
# Tests kit-project and project-types.md. Runs in a throwaway folder; nothing real is touched.
#   bash tests/test_project.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit"; mkdir -p "$KIT_DIR/memory/context" "$S/lib"
printf -- '- **Library root:** `%s/`\n' "$S/lib" > "$KIT_DIR/memory/context/library.md"
P="python3 $HERE/shared/bin/kit-project"
$P types | grep -q "^poc " && ok "types lists poc" || bad "types"
$P new poc vendor-x-eval | grep -q "would create" && [ ! -e "$S/lib/artifacts/vendor-x-eval" ] && ok "dry run writes nothing" || bad "dry run"
$P new poc vendor-x-eval --yes >/dev/null && [ -d "$S/lib/artifacts/vendor-x-eval/poc" ] && [ -d "$S/lib/artifacts/vendor-x-eval/labs" ] \
  && ok "--yes creates the poc folders" || bad "create"
grep -q "1. charter" "$S/lib/artifacts/vendor-x-eval/README.md" && grep -q "Type: poc" "$S/lib/artifacts/vendor-x-eval/README.md" \
  && ok "README lists type and stages" || bad "readme"
echo keep > "$S/lib/artifacts/vendor-x-eval/poc/note.md"
$P new poc vendor-x-eval --yes >/dev/null 2>&1 && bad "refuses an existing project" || ok "refuses an existing project"
[ "$(cat "$S/lib/artifacts/vendor-x-eval/poc/note.md")" = keep ] && ok "existing files untouched" || bad "existing touched"
$P new poc "Bad Slug" --yes >/dev/null 2>&1 && bad "bad slug refused" || ok "bad slug refused"
$P new delivery payments-upgrade --root "$S/lib" --yes >/dev/null && [ -d "$S/lib/artifacts/payments-upgrade/changeboard" ] && ok "--root works; delivery has changeboard/" || bad "root/delivery"
rm "$KIT_DIR/memory/context/library.md"
$P new lab lab-one --yes >/dev/null 2>&1 && bad "no library root refused" || ok "no library root: refused"
for t in delivery poc lab training research; do grep -q "^## $t$" "$HERE/kit/memory/context/project-types.md" || { bad "project-types.md has $t"; continue; }; done
ok "project-types.md documents every type"
echo "kit-project tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
