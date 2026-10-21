#!/bin/bash
# Tests for shared/bin/kit-trace against synthetic fixtures. Run: bash tests/test_trace.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-trace"
FIX="$HERE/tests/fixtures/trace/project-alpha"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if grep -q -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }
mkdir -p "$T/kit/memory/context"
export KIT_DIR="$T/kit"     # no library.md: the tool must work from a folder alone

out="$(python3 "$TOOL" "$FIX")"
row() { grep -- "^| $1 |" <<<"$out"; }
has "title" "# Traceability matrix: project-alpha" "$out"
has "classification row" "| Classification |" "$out"
has "latest IA version picked" "| Impact assessment | ia-v2.md |" "$out"
hasnot "older IA ignored" "REQ-900" "$out"
hasnot "handoff file ignored" "REQ-777" "$out"
has "summary count of requirements" "Requirements in the IA: 8" "$out"
has "summary gap counts" "Gaps: 2 not addressed in the GDS, 1 addressed but untested, 1 tested but no change step, 1 orphan" "$out"
has "ID match to GDS section" "4.1 Authentication | TC-01 | step 1" "$(row REQ-001)"
has "POC verdict" "POC-0007: go" "$(row REQ-001)"
has "IA section cited in GDS" "5.2 Dashboards (cited IA 3.2)" "$(row NFR-1)"
has "GDS-section column in IA" "6.1 Monitoring (cited in the IA)" "$(row IA-1)"
has "numbered table row becomes IA-n" "Quarterly certificate rotation" "$(row IA-2)"
has "test cites GDS section" "TC-02 (cited GDS 5.1)" "$(row FR-3)"
has "change step via test case" "step 2 (via TC-02)" "$(row REQ-002)"
has "inferred GDS match marked" "6.2 Backup (inferred)" "$(row NFR-2)"
has "inferred test match marked" "TC-03 (inferred)" "$(row IA-1)"
has "heading-style test case found" "TC-05" "$(row NFR-2)"
has "gap: not addressed in GDS" "not addressed in the GDS" "$(row REQ-004)"
has "gap: addressed but untested" "addressed but untested" "$(row NFR-1)"
has "gap: tested but no change step" "tested but no change step" "$(row IA-1)"
has "orphan test case" "TC-04: Load printer drivers" "$out"
has "ID not in IA listed as written" "REQ-099 \[gds-v1.md" "$out"
hasnot "unrelated requirement not inferred" "certificate rotation runbook for the message broker cluster | [0-9]" "$out"

python3 "$TOOL" "$FIX" --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert set(d) >= {"project", "generated", "sources", "summary", "requirements", "orphan_tests", "ids_not_in_ia"}, d.keys()
assert d["summary"]["gaps"] == {"not_addressed_in_gds": 2, "addressed_but_untested": 1,
                                "tested_but_no_change_step": 1, "orphan_test_cases": 1}, d["summary"]
r = {x["id"]: x for x in d["requirements"]}
assert r["NFR-2"]["gds"][0]["how"] == "inferred"
assert r["REQ-001"]["gds"][0]["source"] == "gds-v1.md:7"
assert r["REQ-004"]["gaps"] == ["not addressed in the GDS"]
assert d["orphan_tests"][0]["id"] == "TC-04"
assert d["sources"]["test_plan"].endswith("implementation/test-plan-v1.md")
' && ok "--json shape" || bad "--json shape"

# Missing files: columns say "not checked" and don't raise gaps
out="$(python3 "$TOOL" --ia "$FIX/ia-v2.md" --gds "$FIX/gds-v1.md")"
has "explicit --ia/--gds" "4.1 Authentication | not checked | not checked" "$out"
has "no test plan: not checked" "Tested: not checked" "$out"
hasnot "no test plan: no untested gap" "addressed but untested |" "$out"

# A .docx IA, with a heading style and a table, built here with zipfile
python3 - "$T/ia.docx" <<'PY'
import sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
def tr(*cells):
    return "<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in cells) + "</w:tr>"
body = (p("Impact assessment", "Title") + p("2 Requirements", "Heading1") +
        "<w:tbl>" + tr("ID", "Requirement") + tr("REQ-010", "Settlement files are signed before transfer") +
        tr("REQ-011", "Partner onboarding questionnaire") + "</w:tbl>" +
        "<w:tbl>" + tr("No.", "Requirement") + tr("1", "Weekly capacity report for the archive tier") + "</w:tbl>")
doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr("word/document.xml", doc)
PY
printf '# GDS\n\n## 3 Transfer\n\nFiles are signed with the platform key (REQ-010).\n\n## 4 Reporting\n\nRequirement 1 is met by the archive report.\n' > "$T/gds.md"
out="$(python3 "$TOOL" --ia "$T/ia.docx" --gds "$T/gds.md")"
has "docx table row read" "| REQ-010 | Settlement files are signed before transfer | 3 Transfer |" "$out"
has "docx numbered row read" "| IA-1 | Weekly capacity report for the archive tier | 4 Reporting |" "$out"
has "docx gap flagged" "REQ-011.*not addressed in the GDS" "$out"

# --write saves under traceability/, only with --write, and won't overwrite without --force
cp -R "$FIX" "$T/proj"
python3 "$TOOL" "$T/proj" >/dev/null
[ ! -e "$T/proj/traceability" ] && ok "nothing written without --write" || bad "wrote without --write"
python3 "$TOOL" "$T/proj" --write >/dev/null
f="$T/proj/traceability/trace-$(date +%Y-%m-%d).md"
[ -f "$f" ] && ok "--write saves traceability/trace-<date>.md" || bad "--write path"
grep -q "Generated | $(date +%d-%b-%Y)" "$f" && ok "date written as DD-Mmm-YYYY" || bad "date format"
python3 "$TOOL" "$T/proj" --write >/dev/null 2>&1 && bad "overwrote without --force" || ok "refuses to overwrite without --force"
python3 "$TOOL" "$T/proj" --write --force >/dev/null && ok "--force replaces" || bad "--force"
out="$(python3 "$TOOL" "$T/proj")"
hasnot "own output not read back as a source" "trace-" "$out"

# A project name resolves under <library root>/artifacts/
mkdir -p "$T/lib/artifacts"; cp -R "$FIX" "$T/lib/artifacts/alpha"
printf -- '- **Library root:** `%s`.\n' "$T/lib" > "$KIT_DIR/memory/context/library.md"
out="$(python3 "$TOOL" alpha)"
has "project name under the library" "# Traceability matrix: alpha" "$out"
python3 "$TOOL" nosuch >/dev/null 2>&1 && bad "missing project accepted" || ok "missing project refused"

echo "kit-trace tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
