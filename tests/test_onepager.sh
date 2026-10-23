#!/bin/bash
# Tests for shared/bin/kit-onepager against synthetic IA and GDS fixtures. Run: bash tests/test_onepager.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-onepager"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if [[ "$3" == *"$2"* ]]; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }
K="$T/kit"; L="$T/lib"; D="$T/docs"
mkdir -p "$K/memory/context" "$L/artifacts/payments-hub" "$D"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
export KIT_DIR="$K"

cat > "$D/payments-ia-v1.md" <<'EOF'
# Payments Hub Impact Assessment

| Field | Value |
|---|---|
| Project | payments-hub |
| Document number | DOC-0042 |
| Version | 1.2 |
| Demand | DEM-1001 |
| Classification | Confidential |
| Status | In review |

## 1 Business driver

The settlement batch misses its cut-off twice a month. Streaming settlement removes the batch window.

## 2 Scope

- In scope: settlement engine, ledger feed.
- Out of scope: front-office order entry.

## 3 Decision required

Approve option B (managed streaming platform) and fund the build phase.

## 4 Key design choices

- Managed streaming platform instead of self-hosted brokers.
- Active-active across two regions.
- Ledger feed moves to change-data-capture.
- Batch fallback kept for one quarter.
- Fifth choice that does not fit on one page.

## 5 Cost

ROM: USD 1.2m to 1.8m one-off, USD 300k a year to run.

## 6 Risks

| ID | Risk | Rating | Mitigation |
|---|---|---|---|
| R-1 | Vendor lock-in | Low | Exit plan |
| R-2 | Cut-over data loss | High | Parallel run |
| R-3 | Skills gap | Medium | Training |
| R-4 | Region outage | Critical | Active-active |

## 7 Milestones

- Architecture review board: 12-Nov-2026
- Go-live target: Q2 2027

## 8 Open questions

- Which role owns the ledger feed after cut-over?
- Does the regulator need notice?
EOF

cat > "$D/ledger-gds.md" <<'EOF'
# Ledger GDS

## 1 Introduction

This design specification describes the ledger service.

## 2 Solution overview

Two services behind a gateway.
EOF

# --- Markdown IA: sections found and cited ---
out="$(python3 "$TOOL" "$D/payments-ia-v1.md")"
has "title" "# Executive one-pager: Payments Hub Impact Assessment" "$out"
has "kind and version" "IA: payments-ia-v1.md, DOC-0042, version 1.2" "$out"
has "what and why cited" "- The settlement batch misses its cut-off twice a month. [§1 Business driver]" "$out"
has "scope cited" "Out of scope: front-office order entry. [§2 Scope]" "$out"
has "ask cited" "Approve option B (managed streaming platform) and fund the build phase. [§3 Decision required]" "$out"
has "design choices cited" "Active-active across two regions. [§4 Key design choices]" "$out"
hasnot "design choices capped at four" "Fifth choice" "$out"
has "cost cited" "ROM: USD 1.2m to 1.8m one-off" "$out"
has "top risk first by rating" "$(printf -- '## Top risks\n\n- Region outage; Rating: Critical')" "$out"
risks="$(sed -n '/## Top risks/,/## Dates/p' <<<"$out")"
has "second risk" "Cut-over data loss; Rating: High" "$risks"
hasnot "only top three risks" "Vendor lock-in" "$risks"
has "dates cited" "Architecture review board: 12-Nov-2026 [§7 Milestones]" "$out"
has "status from the field table" "| In review [§Payments Hub Impact Assessment]" "$(sed 's/^- /| /' <<<"$out")"
has "open question cited" "Does the regulator need notice? [§8 Open questions]" "$out"
has "classification row" "| Classification | Confidential [§Payments Hub Impact Assessment] |" "$out"
has "demand row" "| Demand | DEM-1001" "$out"

# --- thin GDS: not stated, never invented ---
out="$(python3 "$TOOL" "$D/ledger-gds.md")"
has "GDS recognised" "GDS: ledger-gds.md" "$out"
has "what and why from the introduction" "This design specification describes the ledger service. [§1 Introduction]" "$out"
has "design from the solution overview" "Two services behind a gateway. [§2 Solution overview]" "$out"
has "missing cost says not stated" "$(printf -- '## Cost (ROM)\n\n- Not stated in the document.')" "$out"
has "missing risks say not stated" "$(printf -- '## Top risks\n\n- Not stated in the document.')" "$out"
has "missing classification says not stated" "| Classification | not stated |" "$out"
n=$(grep -c "Not stated in the document" <<<"$out")
[ "$n" -eq 7 ] && ok "seven fields not stated" || bad "seven fields not stated (got $n)"

# --- --json ---
python3 "$TOOL" "$D/payments-ia-v1.md" --json | python3 -c "
import json,sys; d=json.load(sys.stdin); f=d['fields']
assert d['kind']=='IA', d['kind']
assert f['risks']['items'][0]['section']=='6 Risks'
assert len(f['risks']['items'])==3
assert f['ask']['stated'] and f['cost']['stated']
assert d['meta']['classification']['value']=='Confidential'
" && ok "json output" || bad "json output"
python3 "$TOOL" "$D/ledger-gds.md" --json | python3 -c "
import json,sys; d=json.load(sys.stdin); assert d['fields']['cost']=={'label':'Cost (ROM)','stated':False,'items':[]}
" && ok "json not stated" || bad "json not stated"

# --- --write ---
ls "$D" | grep -q onepager && bad "wrote without --write" || ok "nothing written without --write"
python3 "$TOOL" "$D/payments-ia-v1.md" --write >/dev/null && [ -f "$D/payments-ia-v1-onepager.md" ] \
  && ok "--write saves next to the source" || bad "--write next to source"
python3 "$TOOL" "$D/payments-ia-v1.md" --write >/dev/null 2>&1 && bad "overwrote without --force" || ok "refuses to overwrite without --force"
python3 "$TOOL" "$D/payments-ia-v1.md" --write --force >/dev/null && ok "--force replaces" || bad "force"
python3 "$TOOL" "$D/payments-ia-v1.md" --write --project payments-hub >/dev/null \
  && [ -f "$L/artifacts/payments-hub/onepager/payments-ia-v1-onepager.md" ] \
  && ok "--project saves in the project's onepager/ folder" || bad "--project"
python3 "$TOOL" "$D/payments-ia-v1.md" --write --project "$T/elsewhere" >/dev/null 2>&1 && bad "accepted a missing project" || ok "missing project refused"

# --- .docx input, built here with zipfile ---
python3 - "$D/ledger-gds-v2.docx" <<'PY'
import sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def p(text, style=None):
    s = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{s}<w:r><w:t>{text}</w:t></w:r></w:p>'
def row(*cells):
    return "<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in cells) + "</w:tr>"
body = (p("Ledger Design Specification", "Title")
        + "<w:tbl>" + row("Field", "Value") + row("Classification", "Confidential") + row("Version", "2.0") + "</w:tbl>"
        + p("1 Purpose", "Heading1") + p("Replace the nightly ledger load with an event feed.")
        + p("2 Risks", "Heading1")
        + "<w:tbl>" + row("Risk", "Severity") + row("Feed lag", "Medium") + row("Schema drift", "High") + "</w:tbl>"
        + p("3 Open questions", "Heading1") + p("Retention period for replayed events?", "ListParagraph"))
doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml", doc)
PY
out="$(python3 "$TOOL" "$D/ledger-gds-v2.docx")"
has "docx title" "# Executive one-pager: Ledger Design Specification" "$out"
has "docx purpose cited" "Replace the nightly ledger load with an event feed. [§1 Purpose]" "$out"
has "docx risks ranked" "$(printf -- '## Top risks\n\n- Schema drift; Severity: High [§2 Risks]')" "$out"
has "docx open question" "Retention period for replayed events? [§3 Open questions]" "$out"
has "docx classification" "| Classification | Confidential" "$out"

# --- PDF input, when pdftotext is present ---
if command -v pdftotext >/dev/null 2>&1; then
  python3 - "$D/tiny-ia.pdf" <<'PY'
import sys
lines = ["Tiny Impact Assessment", "1 Purpose", "Retire the legacy file transfer host.", "2 Scope", "Transfer host only."]
ops = "BT /F1 11 Tf 72 720 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
out, offs = "%PDF-1.4\n", []
for i, o in enumerate(objs, 1):
    offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n"
x = len(out)
out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
open(sys.argv[1], "w").write(out)
PY
  out="$(python3 "$TOOL" "$D/tiny-ia.pdf")"
  has "pdf purpose cited" "Retire the legacy file transfer host. [§1 Purpose]" "$out"
  has "pdf scope cited" "Transfer host only. [§2 Scope]" "$out"
else
  echo "skip PDF input (pdftotext not installed)"
fi

# --- --docx output ---
python3 "$TOOL" "$D/payments-ia-v1.md" --docx >/dev/null && [ -f "$D/payments-ia-v1-onepager.docx" ] \
  && ok "--docx writes next to the source" || bad "--docx"
python3 - "$D/payments-ia-v1-onepager.docx" <<'PY' && ok "--docx is a valid zip with document.xml and a CONFIDENTIAL header" || bad "--docx content"
import sys, zipfile, xml.etree.ElementTree as ET
z = zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None
names = set(z.namelist())
for n in ("[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml", "word/header1.xml"):
    assert n in names, n
for n in names:
    ET.fromstring(z.read(n))
doc = z.read("word/document.xml").decode()
assert "Region outage" in doc and "[§6 Risks]" in doc
assert "CONFIDENTIAL" in z.read("word/header1.xml").decode()
PY
python3 "$TOOL" "$D/ledger-gds.md" --docx >/dev/null
python3 - "$D/ledger-gds-onepager.docx" <<'PY' && ok "no classification, no header" || bad "header without classification"
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1]); assert "word/header1.xml" not in z.namelist()
assert "Not stated in the document." in z.read("word/document.xml").decode()
PY
python3 "$TOOL" "$D/payments-ia-v1.md" --docx >/dev/null 2>&1 && bad "docx overwrote without --force" || ok "docx refuses to overwrite without --force"
python3 "$TOOL" "$T/nope.md" >/dev/null 2>&1 && bad "missing file accepted" || ok "missing file refused"

echo "kit-onepager tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
