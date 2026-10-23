#!/bin/bash
# Tests for shared/bin/kit-viewpoints against a synthetic GDS (Markdown and a tiny .docx).
# Run: bash tests/test_viewpoints.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-viewpoints"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if [[ "$3" == *"$2"* ]]; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }
K="$T/kit"; L="$T/lib"; D="$T/docs"
mkdir -p "$K/memory/context" "$L/artifacts/order-routing/drafts" "$D"
printf -- '- **Library root:** `%s`.\n' "$L" > "$K/memory/context/library.md"
printf -- '- **Lint rules:** not set.\n' > "$K/memory/context/diagrams.md"
export KIT_DIR="$K"
unset KIT_DRAWIO_STYLES

cat > "$D/orders-gds.md" <<'EOF'
# Order Routing General Design Specification

| Field | Value |
|---|---|
| Project | order-routing |
| System name | Order Router |
| Version | 1.0 |
| Classification | Confidential |

## 1 Introduction

This design describes the Order Router.

## 2 Actors

| Actor | Description |
|---|---|
| Trader | Submits and amends orders |
| Operations analyst | Monitors routing and repairs breaks |

## 3 External systems

| System | Description |
|---|---|
| Market Gateway | Exchange connectivity |
| Reference Data Service | Instrument and counterparty data |

## 4 Operational flow

1. The trader submits an order through the Order Portal.
2. The Order Router validates it and sends it to the Market Gateway.

## 5 Components

| Component | Description | Technology |
|---|---|---|
| Order Portal | Web front end for traders | React |
| Routing Engine | Picks a venue and routes the order | Java |
| Order Store | Holds orders and fills | PostgreSQL |

## 6 Interfaces

| Source | Target | Protocol | Port | Data |
|---|---|---|---|---|
| Order Portal | Routing Engine | HTTPS | 443 | Orders |
| Routing Engine | Order Store | JDBC | 5432 | Orders, fills |
| Routing Engine | Market Gateway | FIX | | Orders |

## 7 Functions

| Function | Performed by | Description |
|---|---|---|
| Capture order | Order Portal | Takes the trader's input |
| Validate order | Routing Engine | Checks limits and fields |
| Route order | Routing Engine | Picks the venue |
| Persist order | Order Store | Saves the order and its fills |

## 8 Data flows

| From | To | Data |
|---|---|---|
| Capture order | Validate order | New order |
| Validate order | Route order | Validated order |

## 9 Logical data model

| Entity | Attributes | Classification |
|---|---|---|
| Order | order id, instrument, side, quantity | Confidential |
| Fill | fill id, order id, price | Restricted |
| Instrument | | |

### 9.1 Relationships

| From | To | Cardinality |
|---|---|---|
| Order | Fill | one to many |
| Instrument | Order | one to many |
EOF

cat > "$D/archive-gds.md" <<'EOF'
# Archive Service GDS

## 1 Overview

Analysts search old statements. The Archive API calls the Statement Store over HTTPS on port 8443.
The Archive API validates search requests.
Each Statement has many Pages.
EOF

# --- OV-1 ---
out="$(python3 "$TOOL" "$D/orders-gds.md" --view OV-1)"
has "OV-1 title" "# OV-1 High-level operational concept: Order Routing General Design Specification" "$out"
has "OV-1 system from labelled field" "- Order Router [§Order Routing General Design Specification]" "$out"
has "OV-1 actor cited" "| Trader | Submits and amends orders | [§2 Actors] |" "$out"
has "OV-1 external system cited" "| Market Gateway | Exchange connectivity | [§3 External systems] |" "$out"
has "OV-1 flow cited" "The trader submits an order through the Order Portal. [§4 Operational flow]" "$out"
has "OV-1 connection carries protocol" "Connection: Routing Engine to Market Gateway, FIX [§6 Interfaces]" "$out"
has "OV-1 classification row" "| Classification | Confidential" "$out"
hasnot "only OV-1 printed" "# SV-1" "$out"

# --- SV-1 ---
out="$(python3 "$TOOL" "$D/orders-gds.md" --view sv-1)"
has "SV-1 component cited" "| Routing Engine | Picks a venue and routes the order | Java | not stated | [§5 Components] |" "$out"
has "SV-1 interface with protocol and port" "| Order Portal | Routing Engine | HTTPS | 443 | Orders | not stated | [§6 Interfaces] |" "$out"
has "SV-1 missing port is not stated" "| Routing Engine | Market Gateway | FIX | not stated |" "$out"
has "SV-1 not-stated summary" "Protocol or port for 1 interface(s): not stated in the document." "$out"
hasnot "SV-1 ignores function data flows" "| Capture order |" "$out"

# --- SV-4 ---
out="$(python3 "$TOOL" "$D/orders-gds.md" --view SV-4)"
has "SV-4 function and performer" "| Validate order | Routing Engine | Checks limits and fields | [§7 Functions] |" "$out"
has "SV-4 data flow cited" "| Capture order | Validate order | New order | [§8 Data flows] |" "$out"

# --- DIV-2 ---
out="$(python3 "$TOOL" "$D/orders-gds.md" --view DIV-2)"
has "DIV-2 entity with attributes and class" "| Order | order id, instrument, side, quantity | Confidential |" "$out"
has "DIV-2 entity class from its own row" "| Fill | fill id, order id, price | Restricted |" "$out"
has "DIV-2 falls back to document class, marked" "| Instrument | not stated | Confidential (the document's classification)" "$out"
has "DIV-2 relationship cited" "| Order | Fill | one to many | [§9.1 Relationships] |" "$out"
has "DIV-2 missing attributes listed" "Attributes for 1 entity: not stated in the document." "$out"

# --- sparse document: inferred and not stated ---
out="$(python3 "$TOOL" "$D/archive-gds.md")"
has "inferred actor" "| Analyst | not stated | [§1 Overview] (inferred) |" "$out"
has "inferred interface with protocol and port" "| Archive API | Statement Store | HTTPS | 8443 | not stated | not stated | [§1 Overview] (inferred) |" "$out"
has "inferred function" "| Validate search requests | Archive API | not stated | [§1 Overview] (inferred) |" "$out"
has "inferred relationship" "| Statement | Pages | has many | [§1 Overview] (inferred) |" "$out"
has "external systems not stated" "- External systems: not stated in the document." "$out"
has "data flows not stated" "- Data flows between functions: not stated in the document." "$out"
has "classification not stated" "| Classification | not stated |" "$out"
hasnot "nothing invented for external systems" "| Market Gateway" "$out"

# --- --json ---
python3 "$TOOL" "$D/orders-gds.md" --json | python3 -c "
import json, sys
r = json.load(sys.stdin)
v = r['views']
assert set(v) == {'OV-1', 'SV-1', 'SV-4', 'DIV-2'}, v.keys()
assert [a['name'] for a in v['OV-1']['actors']] == ['Trader', 'Operations analyst']
assert all(x['section'] for view in v.values() for k, items in view.items() if isinstance(items, list) for x in items)
assert len(v['SV-1']['interfaces']) == 3 and v['SV-1']['interfaces'][2]['port'] == 'not stated'
assert v['SV-4']['functions'][0]['performer'] == 'Order Portal'
assert v['DIV-2']['entities'][1]['classification'] == 'Restricted'
assert r['meta']['classification']['value'] == 'Confidential'
" && ok "--json has every view, cited elements" || bad "--json"
python3 "$TOOL" "$D/archive-gds.md" --json | python3 -c "
import json, sys
r = json.load(sys.stdin)
assert r['views']['SV-1']['interfaces'][0]['inferred'] is True
assert r['views']['OV-1']['external_systems'] == []
" && ok "--json marks inferred and leaves gaps empty" || bad "--json inferred"

# --- --write: project folder auto-detected under the library, draw.io valid ---
cp "$D/orders-gds.md" "$L/artifacts/order-routing/drafts/orders-gds.md"
out="$(python3 "$TOOL" "$L/artifacts/order-routing/drafts/orders-gds.md" --write)"
VP="$L/artifacts/order-routing/viewpoints"
n=0; for v in ov-1 sv-1 sv-4 div-2; do for s in ".md" "-spec.json" ".drawio"; do [ -f "$VP/orders-gds-$v$s" ] && n=$((n+1)); done; done
[ "$n" = 12 ] && ok "--write saves 12 files in <project>/viewpoints/" || { bad "--write files ($n)"; echo "$out"; }
has "--write reports lint skipped" "skipped: diagrams.md names no lint rules" "$out"
python3 - "$VP" <<'PY' && ok "draw.io files are valid XML with shapes and bound edges" || bad "draw.io content"
import sys, pathlib, xml.etree.ElementTree as ET
vp = pathlib.Path(sys.argv[1])
for name, shapes, edges in (("ov-1", 6, 4), ("sv-1", 5, 3), ("sv-4", 7, 2), ("div-2", 4, 2)):
    root = ET.parse(vp / f"orders-gds-{name}.drawio").getroot()
    assert root.tag == "mxfile"
    cells = root.findall(".//mxCell")
    v = [c for c in cells if c.get("vertex") == "1"]
    e = [c for c in cells if c.get("edge") == "1"]
    assert len(v) >= shapes and len(e) >= edges, (name, len(v), len(e))
    assert all(c.get("source") and c.get("target") for c in e), name
sv1 = (vp / "orders-gds-sv-1.drawio").read_text()
assert "HTTPS port 443" in sv1 and "Market Gateway" in sv1
assert "Classification: Confidential" in (vp / "orders-gds-ov-1.drawio").read_text()
PY
has "--write spec links its diagram" "| Diagram | orders-gds-sv-1.drawio" "$(cat "$VP/orders-gds-sv-1.md")"
python3 "$TOOL" "$L/artifacts/order-routing/drafts/orders-gds.md" --write >/dev/null 2>&1 \
  && bad "overwrote without --force" || ok "refuses to overwrite without --force"
python3 "$TOOL" "$L/artifacts/order-routing/drafts/orders-gds.md" --write --force >/dev/null \
  && ok "--force replaces" || bad "--force"
python3 "$TOOL" "$D/orders-gds.md" --write --project order-routing --view SV-1 --force >/dev/null \
  && [ -f "$VP/orders-gds-sv-1.drawio" ] && ok "--project by name" || bad "--project by name"
python3 "$TOOL" "$D/orders-gds.md" --write --project "$T/nowhere" >/dev/null 2>&1 \
  && bad "accepted a missing project" || ok "missing project refused"
python3 "$TOOL" "$D/archive-gds.md" --write >/dev/null && [ -f "$D/viewpoints/archive-gds-div-2.drawio" ] \
  && ok "outside the library: viewpoints/ next to the document" || bad "fallback folder"

# --- --styles reach kit-drawio, and KIT_DRAWIO_STYLES too ---
printf '{"font": "Verdana", "nodes": {"system": {"stroke": "#123456"}}}\n' > "$T/styles.json"
python3 "$TOOL" "$D/orders-gds.md" --write --view SV-1 --force --styles "$T/styles.json" >/dev/null
grep -q "fontFamily=Verdana" "$D/viewpoints/orders-gds-sv-1.drawio" && grep -q "#123456" "$D/viewpoints/orders-gds-sv-1.drawio" \
  && ok "--styles applies the team font and palette" || bad "--styles"
KIT_DRAWIO_STYLES="$T/styles.json" python3 "$TOOL" "$D/orders-gds.md" --write --view SV-4 --force >/dev/null
grep -q "fontFamily=Verdana" "$D/viewpoints/orders-gds-sv-4.drawio" && ok "KIT_DRAWIO_STYLES honored" || bad "KIT_DRAWIO_STYLES"

# --- lint runs when diagrams.md names rules ---
cp "$HERE/kit/templates/diagram-lint-rules.example.json" "$K/memory/context/lint.json"
printf -- '- **Lint rules:** `lint.json`\n' > "$K/memory/context/diagrams.md"
out="$(python3 "$TOOL" "$D/orders-gds.md" --write --force --view OV-1)"
has "lint summary printed" "kit-diaglint against Example diagramming standard:" "$out"
has "lint summary in the spec" "## Diagram lint" "$(cat "$D/viewpoints/orders-gds-ov-1.md")"
python3 "$TOOL" "$D/orders-gds.md" --write --force --view OV-1 --json | python3 -c "
import json, sys; r = json.load(sys.stdin); assert 'errors' in r['lint'] and r['files']['OV-1']['drawio'].endswith('.drawio')
" && ok "--write --json carries files and lint counts" || bad "--write --json"

# --- .docx input, built here with zipfile ---
python3 - "$D/ledger-gds.docx" <<'PY'
import sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def p(text, style=None):
    s = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{s}<w:r><w:t>{text}</w:t></w:r></w:p>'
def tbl(*rows):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>" for r in rows) + "</w:tbl>"
body = (p("Ledger Design Specification", "Title")
        + tbl(("Field", "Value"), ("Classification", "Internal"), ("Version", "2.0"))
        + p("1 Users", "Heading1") + tbl(("Role", "Description"), ("Accountant", "Posts journals"))
        + p("2 Interfaces", "Heading1")
        + tbl(("From", "To", "Protocol", "Port"), ("Ledger API", "Ledger DB", "TLS", "1521"))
        + p("3 Functions", "Heading1") + tbl(("Function", "Component"), ("Post journal", "Ledger API"))
        + p("4 Data model", "Heading1") + tbl(("Entity", "Attributes", "Classification"), ("Journal", "id, amount", "Internal")))
doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml", doc)
PY
out="$(python3 "$TOOL" "$D/ledger-gds.docx")"
has "docx actor" "| Accountant | Posts journals | [§1 Users] |" "$out"
has "docx interface" "| Ledger API | Ledger DB | TLS | 1521 |" "$out"
has "docx function" "| Post journal | Ledger API |" "$out"
has "docx entity" "| Journal | id, amount | Internal |" "$out"
has "docx classification" "| Classification | Internal" "$out"

python3 "$TOOL" "$T/nope.md" >/dev/null 2>&1 && bad "missing file accepted" || ok "missing file refused"
python3 "$TOOL" "$D/orders-gds.md" --view XV-9 >/dev/null 2>&1 && bad "unknown view accepted" || ok "unknown view refused"

echo "kit-viewpoints tests: $pass passed, $fail failed"
[ "$fail" = 0 ]
