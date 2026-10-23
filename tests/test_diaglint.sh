#!/bin/bash
# Tests for shared/bin/kit-diaglint with generated draw.io (plain and compressed) and Visio files.
# Run: bash tests/test_diaglint.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-diaglint"
EXAMPLE="$HERE/kit/templates/diagram-lint-rules.example.json"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export KIT_DIR="$T/kit"
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -qF -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if grep -qF -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }

python3 - "$T" <<'PY'
import base64, json, sys, urllib.parse, zipfile, zlib, pathlib
T = pathlib.Path(sys.argv[1])
rules = {
  "name": "Test standard",
  "ignore_pages": "^Scratch$",
  "palette": {"colors": {"#111111": "Ink", "#FFFFFF": "White", "#2255AA": "Blue", "#DD7700": "Amber"}},
  "fonts": {"allowed": ["Arial"]},
  "text": {"min_size_pt": 7},
  "title_block": {"fields": {"Title": {}, "Author": {}, "Date": {"pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                             "Version": {}, "Classification": {"aliases": ["Class"]}}},
  "legend": {"required": True},
  "connectors": {"require_label": True, "require_attached": True, "orthogonal": True,
                 "orthogonal_except_pages": "(?i)context"},
  "line_types": {"require_match": True, "types": [
      {"name": "Logical", "match": ["(?i)logical"], "pattern": "dashed", "stroke": "#111111", "width_pt": 1},
      {"name": "Physical", "match": ["(?i)physical"], "pattern": "solid", "stroke": "#111111", "width_pt": 1.5}]},
  "shapes": {"allowed": ["rectangle", "text", "Server.*"]},
  "page_names": {"pattern": "^[A-Z]"},
  "view_label": {"values": ["Physical", "Logical"]},
}
(T / "rules.json").write_text(json.dumps(rules))
(T / "warn-only.json").write_text(json.dumps({"connectors": {"require_label": True}}))
(T / "bad.json").write_text("{not json")

def model(cells):
    return '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>' + cells + '</root></mxGraphModel>'
def v(i, label, style="rounded=0;html=1;fillColor=#FFFFFF;strokeColor=#2255AA;fontFamily=Arial;fontSize=12;", x=0, y=0, w=80, h=40, parent="1"):
    return (f'<mxCell id="{i}" value="{label}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
def e(i, s, t, label="", style="edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;strokeWidth=2;"):
    st = f' source="{s}"' if s else ""
    tt = f' target="{t}"' if t else ""
    return f'<mxCell id="{i}" value="{label}" style="{style}" edge="1" parent="1"{st}{tt}><mxGeometry relative="1" as="geometry"/></mxCell>'
TB = (v("tb1", "Title: Payments physical view", "text;fontFamily=Arial;") + v("tb2", "Author: A. Person", "text;fontFamily=Arial;")
      + v("tb3", "Date: 2026-10-21", "text;fontFamily=Arial;") + v("tb4", "Version: v1.0", "text;fontFamily=Arial;")
      + v("tb5", "Classification: Internal", "text;fontFamily=Arial;") + v("lg", "Legend", "text;fontFamily=Arial;"))
clean_cells = (TB + v("a", "Web") + v("b", "App")
               + e("e1", "a", "b", "Physical link", "edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;strokeWidth=2;")
               + e("e2", "a", "b", "Logical path", "edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;strokeWidth=1.33;dashed=1;"))
bad_cells = (
    v("t1", "Title: Payments", "text;fontFamily=Arial;")
    + v("t2", "Date: 21-Oct-2026", "text;fontFamily=Arial;")
    + v("t3", "Author:", "text;fontFamily=Arial;")
    + v("c1", "Odd fill", "rounded=0;fillColor=#ABCDEF;strokeColor=#2255AA;fontFamily=Arial;")
    + v("c2", "Comic", "rounded=0;fillColor=#FFFFFF;fontFamily=Comic Sans MS;")
    + v("c3", "Tiny", "rounded=0;fillColor=#FFFFFF;fontFamily=Arial;fontSize=8;")
    + v("c4", "Cloud thing", "shape=mxgraph.aws4.lambda;fillColor=#FFFFFF;fontFamily=Arial;")
    + v("c5", "&lt;font color=&quot;#FF00FF&quot; face=&quot;Times New Roman&quot;&gt;Html text&lt;/font&gt;", "html=1;fontFamily=Arial;")
    + e("x1", "c1", "c2", "", "edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;strokeWidth=2;")
    + e("x2", "c1", None, "Floating physical", "edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;strokeWidth=2;")
    + e("x3", "c1", "c3", "Logical tunnel", "edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;strokeWidth=1.33;")
    + e("x4", "c2", "c3", "Physical uplink", "strokeColor=#111111;strokeWidth=2;")
    + e("x5", "c2", "c4", "Mystery", "edgeStyle=orthogonalEdgeStyle;strokeColor=#2255AA;strokeWidth=6;"))
(T / "clean.drawio").write_text(f'<mxfile><diagram name="Physical view" id="p1">{model(clean_cells)}</diagram></mxfile>')
(T / "bad.drawio").write_text(
    f'<mxfile><diagram name="overview" id="p1">{model(bad_cells)}</diagram>'
    f'<diagram name="Scratch" id="p2">{model(v("z", "anything", "fillColor=#123456;"))}</diagram></mxfile>')
comp = zlib.compressobj(9, zlib.DEFLATED, -15)
packed = base64.b64encode(comp.compress(urllib.parse.quote(model(bad_cells)).encode()) + comp.flush()).decode()
(T / "bad-compressed.drawio").write_text(f'<mxfile><diagram name="overview" id="p1">{packed}</diagram></mxfile>')
# title block as a table: field cell with its value in the cell to the right; layer gives the view label
table = (v("k1", "Title", "text;fontFamily=Arial;", 0, 0, 60, 20) + v("v1", "Ordering", "text;fontFamily=Arial;", 70, 0, 100, 20)
         + v("k2", "Author", "text;fontFamily=Arial;", 0, 30, 60, 20) + v("v2", "B. Person", "text;fontFamily=Arial;", 70, 30, 100, 20)
         + v("k3", "Date", "text;fontFamily=Arial;", 0, 60, 60, 20) + v("v3", "2026-01-02", "text;fontFamily=Arial;", 70, 60, 100, 20)
         + v("k4", "Version", "text;fontFamily=Arial;", 0, 90, 60, 20) + v("v4", "v2.1", "text;fontFamily=Arial;", 70, 90, 100, 20)
         + v("k5", "Class", "text;fontFamily=Arial;", 0, 120, 60, 20) + v("v5", "Internal", "text;fontFamily=Arial;", 70, 120, 100, 20)
         + v("lg", "Legend", "text;fontFamily=Arial;", 300, 0))
layered = ('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="L2" value="Logical" parent="0"/>'
           + table + '</root></mxGraphModel>')
(T / "table.drawio").write_text(f'<mxfile><diagram name="Ordering context" id="p1">{layered}</diagram></mxfile>')
(T / "notes.txt").write_text("not a diagram")
(T / "ws.drawio").write_text('<mxfile><diagram name="P">' + model(v("w1", "Title block", "text;") + v("w2", "Version v1.0", "text;")
                             + e("w3", "w1", None, "", "edgeStyle=orthogonalEdgeStyle;")) + '</diagram></mxfile>')
(T / "ws.json").write_text(json.dumps({"title_block": {"fields": {"Title": {}, "Version": {"pattern": "^v\\d"}}},
                                       "connectors": {"require_attached": True, "require_label": True, "attached_severity": "error"}}))

NS = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
pages = f'<Pages {NS}><Page ID="0" NameU="Physical network" Name="Physical network"><Rel r:id="rId1"/></Page></Pages>'
rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/></Relationships>')
masters = f'<Masters {NS}><Master ID="2" NameU="Server.Physical.Rack"/><Master ID="3" NameU="Freehand.Blob"/></Masters>'
def shape(i, text, cells="", char="", master=None, prop=""):
    m = f' Master="{master}"' if master else ""
    ch = f'<Section N="Character"><Row IX="0">{char}</Row></Section>' if char else ""
    return f'<Shape ID="{i}" NameU="Shape.{i}"{m}>{cells}{ch}{prop}<Text>{text}</Text></Shape>'
C = lambda n, val: f'<Cell N="{n}" V="{val}"/>'
sh = (shape("1", "Server A", C("FillForegnd", "#FFFFFF") + C("LineColor", "#2255AA"), C("Font", "Arial") + C("Size", "0.125"), "2")
      + shape("2", "Blob", C("FillForegnd", "#00FF00"), C("Font", "Calibri") + C("Size", "0.0694"), "3")
      + shape("3", "", C("BeginX", "1") + C("EndX", "2") + C("LineColor", "#111111") + C("LinePattern", "1") + C("LineWeight", "0.0139"))
      + shape("4", "Logical link", C("BeginX", "1") + C("EndX", "2") + C("LineColor", "#111111") + C("LinePattern", "1") + C("LineWeight", "0.0139"))
      + shape("5", "Legend") + shape("6", "Title block", "", "", None,
        '<Section N="Property"><Row N="Title"><Cell N="Value" V="Rack layout"/><Cell N="Label" V="Title"/></Row>'
        '<Row N="Author"><Cell N="Value" V="C. Person"/><Cell N="Label" V="Author"/></Row>'
        '<Row N="Date"><Cell N="Value" V="2026-10-21"/><Cell N="Label" V="Date"/></Row>'
        '<Row N="Version"><Cell N="Value" V=""/><Cell N="Label" V="Version"/></Row></Section>'))
cn = ('<Connect FromSheet="3" FromCell="BeginX" ToSheet="1"/><Connect FromSheet="3" FromCell="EndX" ToSheet="2"/>'
      '<Connect FromSheet="4" FromCell="BeginX" ToSheet="1"/>')
page = f'<PageContents {NS}><Shapes>{sh}</Shapes><Connects>{cn}</Connects></PageContents>'
with zipfile.ZipFile(T / "net.vsdx", "w") as z:
    z.writestr("visio/pages/pages.xml", pages)
    z.writestr("visio/pages/_rels/pages.xml.rels", rels)
    z.writestr("visio/pages/page1.xml", page)
    z.writestr("visio/masters/masters.xml", masters)
PY

R="$T/rules.json"
out="$(python3 "$TOOL" "$T/clean.drawio" --rules "$R")"; rc=$?
[ $rc -eq 0 ] && ok "clean diagram exits 0" || bad "clean diagram exits 0 (got $rc)"
has "clean diagram has no findings" "No findings." "$out"

out="$(python3 "$TOOL" "$T/bad.drawio" --rules "$R")"; rc=$?
[ $rc -eq 1 ] && ok "errors exit 1" || bad "errors exit 1 (got $rc)"
has "palette: off-palette fill with id and label" 'fill color #ABCDEF is not in the palette' "$out"
has "palette: names the element" 'c1 "Odd fill"' "$out"
has "palette: nearest allowed color" "(nearest: #" "$out"
has "palette: color inside an HTML label" "text color #FF00FF is not in the palette" "$out"
has "fonts: disallowed font" 'font "Comic Sans MS" is not allowed' "$out"
has "fonts: font inside an HTML label" 'font "Times New Roman" is not allowed' "$out"
has "text: below minimum size" "text is 6.0 pt, below the 7 pt minimum" "$out"
has "title block: missing fields" "title block is missing: Version, Classification" "$out"
has "title block: empty field" 'title block field "Author" has no value' "$out"
has "title block: pattern mismatch" 'title block field "Date" value "21-Oct-2026"' "$out"
has "legend: required" "no legend on this page" "$out"
has "connectors: unlabeled" "connector has no label" "$out"
has "connectors: floating end" "connector isn't attached at its end" "$out"
has "connectors: not orthogonal" "isn't routed orthogonally" "$out"
has "line types: logical should be dashed" "Logical connection: is solid, should be dashed" "$out"
has "line types: no standard type matches" "matches none of the standard line types" "$out"
has "shapes: outside allowed stencils" 'shape "mxgraph.aws4.lambda" is not an allowed stencil' "$out"
has "page names: pattern" 'page name "overview" doesn'"'"'t match' "$out"
has "view label: missing" "no view or layer label (Physical, Logical)" "$out"
has "severity shown" "WARNING connectors" "$out"
has "errors shown" "ERROR palette" "$out"
hasnot "ignored page skipped" "Scratch" "$out"
hasnot "physical link fits its line type" "Physical connection: is" "$(grep x2 <<<"$out")"

out2="$(python3 "$TOOL" "$T/bad-compressed.drawio" --rules "$R")"
a="$(sed 1,3d <<<"$out")"; b="$(sed 1,3d <<<"$out2")"
[ "$a" = "$b" ] && ok "compressed draw.io gives the same findings" || { bad "compressed draw.io differs"; diff <(echo "$a") <(echo "$b") | head; }

out="$(python3 "$TOOL" "$T/table.drawio" --rules "$R")"
hasnot "title block table: values found to the right" "title block" "$out"
hasnot "view label from a layer name" "no view or layer label" "$out"
hasnot "orthogonal exception by page name" "orthogonally" "$out"

out="$(python3 "$TOOL" "$T/net.vsdx" --rules "$R")"; rc=$?
[ $rc -eq 1 ] && ok "vsdx with errors exits 1" || bad "vsdx with errors exits 1 (got $rc)"
has "vsdx: page name" "### Page: Physical network" "$out"
has "vsdx: off-palette fill" 'fill color #00FF00 is not in the palette' "$out"
has "vsdx: font" 'font "Calibri" is not allowed' "$out"
has "vsdx: small text (inches to pt)" "text is 5.0 pt" "$out"
has "vsdx: master outside allowed stencils" 'shape "Freehand.Blob" is not an allowed stencil' "$out"
hasnot "vsdx: allowed master accepted" 'Server.Physical.Rack' "$out"
has "vsdx: unlabeled connector" "connector has no label" "$out"
has "vsdx: floating connector" "connector isn't attached at its end" "$out"
has "vsdx: line type from label" "Logical connection: is solid, should be dashed" "$out"
has "vsdx: shape data title block, empty field" 'title block field "Version" has no value' "$out"
has "vsdx: shape data title block, missing field" "title block is missing: Classification" "$out"
hasnot "vsdx: legend found" "no legend" "$out"
hasnot "vsdx: view label from page name" "no view or layer label" "$out"

out="$(python3 "$TOOL" "$T/bad.drawio" --rules "$R" --json)"; rc=$?
[ $rc -eq 1 ] && ok "--json keeps exit 1" || bad "--json keeps exit 1"
python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); f=d["files"][0]["pages"][0]["findings"]; assert d["errors"]>0 and d["warnings"]>0; assert any(x["rule"]=="palette" and x["id"]=="c1" and x["label"]=="Odd fill" for x in f); assert d["standard"]=="Test standard"' <<<"$out" \
  && ok "json output has findings with ids, labels, and totals" || bad "json output"

out="$(python3 "$TOOL" "$T/bad.drawio" --rules "$T/warn-only.json")"; rc=$?
[ $rc -eq 0 ] && ok "warnings only exit 0" || bad "warnings only exit 0 (got $rc)"
has "warning reported" "WARNING connectors: connector has no label" "$out"

out="$(python3 "$TOOL" "$T/ws.drawio" --rules "$T/ws.json")"; rc=$?
has "title block: 'Field value' without a separator needs the pattern" "title block is missing: Title" "$out"
hasnot "title block: 'Version v1.0' accepted by its pattern" "Version" "$out"
has "per-check severity override (attached is an error)" "ERROR connectors: connector isn't attached" "$out"
has "other connector checks keep the section severity" "WARNING connectors: connector has no label" "$out"
[ $rc -eq 1 ] && ok "per-check error severity fails the run" || bad "per-check error severity fails the run (got $rc)"

out="$(python3 "$TOOL" "$T" --rules "$R")"
has "folder: draw.io files found" "## clean.drawio" "$out"
has "folder: vsdx found" "## net.vsdx" "$out"
hasnot "folder: other files skipped" "notes.txt" "$out"

out="$(python3 "$TOOL" "$T/clean.drawio" --rules "$T/missing.json" 2>&1)"; rc=$?
[ $rc -eq 2 ] && ok "missing rules file exits 2" || bad "missing rules file exits 2 (got $rc)"
has "missing rules file message" "rules file $T/missing.json not found" "$out"
has "missing rules file points at the example" "diagram-lint-rules.example.json" "$out"

out="$(python3 "$TOOL" "$T/clean.drawio" 2>&1)"; rc=$?
[ $rc -eq 2 ] && ok "no rules and no setup exits 2" || bad "no rules and no setup exits 2 (got $rc)"
has "no setup message" "doesn't exist" "$out"

mkdir -p "$KIT_DIR/memory/context"
printf -- '- **Standard:** not set.\n- **Lint rules:** not set.\n' > "$KIT_DIR/memory/context/diagrams.md"
out="$(python3 "$TOOL" "$T/clean.drawio" 2>&1)"; rc=$?
[ $rc -eq 2 ] && has "setup field not set" '"Lint rules" field' "$out" || bad "setup field not set exits 2"
cp "$R" "$KIT_DIR/memory/context/my-rules.json"
printf -- '- **Lint rules:** `my-rules.json` (relative to this file)\n' > "$KIT_DIR/memory/context/diagrams.md"
out="$(python3 "$TOOL" "$T/clean.drawio" 2>&1)"; rc=$?
[ $rc -eq 0 ] && has "rules read from the setup field" "rules: $KIT_DIR/memory/context/my-rules.json" "$out" || { bad "rules from setup (rc $rc)"; echo "$out"; }

out="$(python3 "$TOOL" "$T/clean.drawio" --rules "$T/bad.json" 2>&1)"; rc=$?
[ $rc -eq 2 ] && has "bad JSON rules refused" "isn't valid JSON" "$out" || bad "bad JSON rules exit 2"
out="$(python3 "$TOOL" "$T/nope.drawio" --rules "$R" 2>&1)"; rc=$?
[ $rc -eq 2 ] && has "missing diagram refused" "not found" "$out" || bad "missing diagram exit 2"
echo "<broken" > "$T/broken.drawio"
out="$(python3 "$TOOL" "$T/broken.drawio" --rules "$R" 2>&1)"; rc=$?
[ $rc -eq 1 ] && has "unreadable diagram reported" "couldn't read the diagram" "$out" || bad "unreadable diagram exit 1"

out="$(python3 "$TOOL" "$T/clean.drawio" --rules "$EXAMPLE" 2>&1)"; rc=$?
[ $rc -le 1 ] && has "example rules file loads" "# Diagram lint" "$out" || { bad "example rules load (rc $rc)"; echo "$out"; }
python3 - "$EXAMPLE" <<'PY' && ok "example rules: valid JSON with every section" || bad "example rules sections"
import json, sys
d = json.load(open(sys.argv[1]))
need = {"palette", "fonts", "text", "title_block", "legend", "connectors", "line_types", "shapes", "page_names", "view_label"}
sys.exit(0 if need <= set(d) else 1)
PY

echo "diaglint tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
