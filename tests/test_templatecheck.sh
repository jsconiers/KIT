#!/bin/bash
# Tests for shared/bin/kit-templatecheck with a synthetic template and drafts (Markdown, and a tiny
# .docx built here). Run: bash tests/test_templatecheck.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-templatecheck"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if [[ "$3" == *"$2"* ]]; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }
K="$T/kit"; L="$T/lib"; D="$T/docs"
mkdir -p "$K/memory/context" "$L/templates" "$D"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
export KIT_DIR="$K"

cat > "$L/templates/ia-template-v3.md" <<'EOF'
# Impact Assessment Template

| Field | Value |
|---|---|
| Template version | 3.1 |
| Document number | <document number> |

## 1 Business driver

Describe the business problem and why the change is needed now.

## 2 Scope

List what is in scope and what is out of scope for this change.

## 3 Requirements

## 4 Impact on existing systems

## 5 Risks

## 6 Glossary (optional)
EOF
cat > "$K/memory/context/writing.md" <<'EOF'
# Writing setup

- **Templates:** IA: `templates/ia-template-v3.md`; GDS: `templates/gds-template.md`.
- **Examples:** not set.
EOF

# A clean draft: every section, renumbered, current version.
cat > "$D/payments-ia-v1.md" <<'EOF'
# Payments Hub Impact Assessment

| Field | Value |
|---|---|
| Template version | 3.1 |
| Document number | DOC-0042 |

## 1. Business driver

Settlement misses its cut-off twice a month.

## 2. Scope

Settlement engine and ledger feed.

## 3. Requirements

## 4. Impact on existing systems

## 5. Risks
EOF

out="$(python3 "$TOOL" "$D/payments-ia-v1.md" 2>&1)"; rc=$?
[ $rc -eq 0 ] && ok "clean draft exits 0" || { bad "clean draft exits 0 (got $rc)"; echo "$out"; }
has "template found from writing.md" "ia-template-v3.md" "$out"
has "optional section reported as optional" "Glossary (optional)" "$out"
has "version current" "(current)" "$out"
has "no placeholders" "Placeholder text left in: none" "$out"

# A drifted draft: missing, renamed, reordered, added, old version, placeholders, guidance.
cat > "$D/ledger-ia-v2.md" <<'EOF'
# Ledger Feed Impact Assessment

Template: IA template v2

## 1 Business driver

Describe the business problem and why the change is needed now.

## 2 Risks

## 3 Scope of change

[Insert scope here]

## 4 Requirements

Owner: {{OWNER_ROLE}} by <target date>.

## 5 Vendor notes
EOF

out="$(python3 "$TOOL" "$D/ledger-ia-v2.md" 2>&1)"; rc=$?
[ $rc -eq 1 ] && ok "missing required section exits 1" || bad "missing required section exits 1 (got $rc)"
has "missing section named" "Impact on existing systems" "$out"
has "renamed section" "2 Scope  ->  3 Scope of change" "$out"
has "reordered section" "Risks (template position 5, draft 2)" "$out"
has "added section" "5 Vendor notes" "$out"
has "version behind" "draft claims 2, current is 3.1 (behind)" "$out"
has "bracket prompt" "[Insert scope here]" "$out"
has "field placeholder" "{{OWNER_ROLE}}" "$out"
has "angle placeholder" "<target date>" "$out"
has "guidance text left in" "[guidance]: Describe the business problem" "$out"
has "result line" "1 required section(s) missing" "$out"

js="$(python3 "$TOOL" "$D/ledger-ia-v2.md" --json 2>&1)"
check="$(printf '%s' "$js" | python3 -c '
import json, sys
r = json.load(sys.stdin)
assert r["ok"] is False and r["missing_required"] == 1, r
assert [m["heading"] for m in r["missing"] if m["required"]] == ["4 Impact on existing systems"], r["missing"]
assert r["renamed"] == [{"template": "2 Scope", "draft": "3 Scope of change"}], r["renamed"]
assert r["version"] == {"claimed": "2", "current": "3.1", "status": "behind"}, r["version"]
assert {p["kind"] for p in r["placeholders"]} >= {"prompt", "field", "angle", "guidance"}, r["placeholders"]
print("json-ok")' 2>&1)"
has "--json report" "json-ok" "$check"

# --template overrides writing.md; --type picks from writing.md; unknown type exits 2.
out="$(python3 "$TOOL" "$D/ledger-ia-v2.md" --template "$L/templates/ia-template-v3.md" 2>&1)"
has "--template used" "against $L/templates/ia-template-v3.md" "$out"
printf '# Notes\n\n## One\n' > "$D/notes.md"
out="$(python3 "$TOOL" "$D/notes.md" 2>&1)"; rc=$?
[ $rc -eq 2 ] && ok "unknown type exits 2" || bad "unknown type exits 2 (got $rc)"
has "unknown type explained" "--type IA|GDS" "$out"
out="$(python3 "$TOOL" "$D/notes.md" --type GDS 2>&1)"; rc=$?
[ $rc -eq 2 ] && ok "missing GDS template exits 2" || bad "missing GDS template exits 2 (got $rc)"
has "missing template named" "template not found" "$out"

# A tiny .docx draft built here: Title style, Heading styles, a field table.
python3 - "$D/payments-ia-v3.docx" <<'PY'
import sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
def row(*cells):
    return "<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in cells) + "</w:tr>"
body = (p("Payments Hub Impact Assessment", "Title") +
        "<w:tbl>" + row("Field", "Value") + row("Template version", "3.1") + "</w:tbl>" +
        p("1 Business driver", "Heading1") + p("Cut-off is missed.") +
        p("2 Scope", "Heading1") + p("[Describe scope]") +
        p("3 Requirements", "Heading1") +
        p("5 Risks", "Heading1") +
        p("4 Impact on existing systems", "Heading1"))
doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr("word/document.xml", doc)
PY
out="$(python3 "$TOOL" "$D/payments-ia-v3.docx" --type IA 2>&1)"; rc=$?
[ $rc -eq 0 ] && ok "docx with all required sections exits 0" || { bad "docx exits 0 (got $rc)"; echo "$out"; }
has "docx sections read" "5 draft sections, 6 in the template" "$out"
has "docx reorder found" "Impact on existing systems (template position 4, draft 5)" "$out"
has "docx version read" "draft claims 3.1, current is 3.1 (current)" "$out"
has "docx placeholder found" "[Describe scope]" "$out"
hasnot "docx title not a section" "Added: 1" "$out"

# A .docx template, compared with a Markdown draft.
python3 - "$L/templates/gds-template.docx" <<'PY'
import sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
body = (p("General Design Specification", "Title") + p("Version: 2.0") +
        p("Overview", "Heading1") + p("Design", "Heading1") + p("Security", "Heading2") + p("Operations", "Heading1"))
doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("word/document.xml", doc)
PY
printf '# Ledger GDS\n\nTemplate version: 2.0\n\n## Overview\n\n## Design\n\n### Security\n' > "$D/ledger-gds-v1.md"
out="$(python3 "$TOOL" "$D/ledger-gds-v1.md" --template "$L/templates/gds-template.docx" --json 2>&1)"; rc=$?
[ $rc -eq 1 ] && ok "docx template: missing Operations exits 1" || bad "docx template exits 1 (got $rc)"
has "docx template missing section" '"heading": "Operations"' "$out"
has "docx template version" '"current": "2.0"' "$out"

# Read-only: nothing new written next to the drafts.
n="$(find "$D" -type f | wc -l | tr -d ' ')"
[ "$n" = "5" ] && ok "read-only (no files written)" || bad "read-only (found $n files)"

echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
