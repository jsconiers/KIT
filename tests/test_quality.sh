#!/bin/bash
# Tests shared/bin/kit-quality against fixture review notes in a temp folder. Nothing outside the
# temp folder is read or written.
#   bash tests/test_quality.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-quality"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
check()    { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
checknot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -20; else ok "$1"; fi; }

K="$T/kit"; L="$T/library"
mkdir -p "$K/memory/context" "$K/briefs" "$K/lessons" "$L/artifacts/alpha/reviews" "$L/artifacts/beta/reviews" "$L/artifacts/gamma/reviews"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
export KIT_DIR="$K"

note() {  # note <project> <file> <date> <rows...>
  local f="$L/artifacts/$1/reviews/$2"; shift 2
  { echo "# Review"; echo; echo "Date: $1"; shift; echo; echo "## Findings"; echo
    echo "| ID | Severity | Category | Template | Section | Finding | Fix |"
    echo "|---|---|---|---|---|---|---|"
    for r in "$@"; do echo "$r"; done; } > "$f"
}
note alpha ds-1-review-2026-08-01.md 01-Aug-2026 \
  "| F-01 | major | template | GDS | 4.2 Security | No encryption standard named. | Name the encryption standard and where it applies. |" \
  "| F-02 | minor | style | GDS | 2 Scope | Passive voice. | Use active voice. |"
note beta ds-2-review-2026-09-10.md 10-Sep-2026 \
  "| F-01 | critical | template | GDS | 4.2 Security controls | Section empty. | Name the encryption standard and where it applies. |" \
  "| F-02 | major | source | GDS | 3 Requirements | Requirement R4 not traced. | Trace every IA requirement. |"
note gamma ds-3-review-2026-10-05.md 05-Oct-2026 \
  "| F-01 | major | template | gds | §4.2 | Key management missing. | Name the encryption standard and where it applies. |" \
  "| F-02 | minor | style | GDS | 2 Scope | Passive voice again. | Use active voice. |"
echo "# Old review with no table" > "$L/artifacts/gamma/reviews/old-notes.md"

out=$(python3 "$TOOL" --today 2026-10-19 --json)
echo "$out" > "$T/q.json"
c() { python3 -c "import json;d=json.load(open('$T/q.json'));print($1)"; }
[ "$(c "d['findings']")" = "6" ] && ok "reads 6 findings from 3 notes" || bad "finding count $(c "d['findings']")"
[ "$(c "len(d['skipped_notes'])")" = "1" ] && ok "a note with no Findings table is skipped and counted" || bad "skipped"
[ "$(c "len(d['recurring'])")" = "1" ] && ok "one recurring finding (3 in 90 days across reviews)" || bad "recurring $(c "d['recurring']")"
[ "$(c "d['recurring'][0]['key']")" = "template|gds|4.2" ] && ok "section numbers group '4.2 Security', '4.2 Security controls', '§4.2'" || bad "key $(c "d['recurring'][0]['key']")"
[ "$(c "d['trend']['by_category']['template']")" = "3" ] && ok "trend by category" || bad "trend"
[ "$(c "d['trend']['by_month']['2026-10']['style']")" = "1" ] && ok "trend by month" || bad "by month"
[ ! -e "$K/briefs/pending-lessons.md" ] && ok "--json writes nothing" || bad "--json wrote"

out=$(python3 "$TOOL" --today 2026-10-19 --min 2 --no-write)
check "--min 2 also flags the style finding" "2 Scope \[style\]" "$out"
[ ! -e "$K/briefs/quality.json" ] && ok "--no-write writes nothing" || bad "--no-write wrote"

out=$(python3 "$TOOL" --today 2026-10-19)
check "writes the proposals" "1 new proposal" "$out"
LS=$(cat "$K/briefs/pending-lessons.md")
check "lesson has the rule (most common fix)" "Name the encryption standard and where it applies." "$LS"
check "lesson has Why with counts and dates" "found this 3 times in 3 reviews between 01-Aug-2026 and 05-Oct-2026" "$LS"
check "lesson has How to apply" "How to apply:" "$LS"
check "lesson carries its quality key" "quality-key: template|gds|4.2" "$LS"
TC=$(cat "$K/briefs/pending-template-changes.md")
check "template change names template and section" "GDS template, section 4.2 Security" "$TC"
check "template change lists an example finding" "Example finding:" "$TC"
[ -z "$(ls "$K/lessons")" ] && ok "never writes in lessons/" || bad "wrote lessons/"
[ -s "$K/briefs/quality.json" ] && ok "writes briefs/quality.json" || bad "quality.json"

out=$(python3 "$TOOL" --today 2026-10-19)
check "a second run proposes nothing new" "0 new proposal" "$out"
[ "$(grep -c 'quality-key: template|gds|4.2' "$K/briefs/pending-lessons.md")" = "1" ] && ok "no duplicate proposal" || bad "duplicate"

rm -f "$K/briefs/pending-lessons.md" "$K/briefs/pending-template-changes.md"
printf 'Rule.\n<!-- quality-key: template|gds|4.2 -->\n' > "$K/lessons/encryption.md"
out=$(python3 "$TOOL" --today 2026-10-19)
check "a finding already covered by a lesson isn't proposed" "0 new proposal" "$out"

out=$(python3 "$TOOL" --today 2027-06-01 --json)
[ "$(python3 -c "import json,sys;print(len(json.loads(sys.argv[1])['recurring']))" "$out")" = "0" ] && ok "findings older than the window don't recur" || bad "window"

printf -- '- **Quality loop:** min 2, days 400.\n' > "$K/memory/context/writing.md"
out=$(python3 "$TOOL" --today 2026-10-19 --json)
[ "$(python3 -c "import json,sys;d=json.loads(sys.argv[1]);print(d['min'],d['window_days'])" "$out")" = "2 400" ] && ok "writing.md's Quality loop line sets min and days" || bad "settings"

grep -q "| ID | Severity | Category | Template | Section | Finding | Fix |" "$HERE/kit/agents/reviewer.md" && ok "reviewer.md sets out the Findings table" || bad "reviewer format"

echo "quality tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
