#!/bin/bash
# Tests for shared/bin/kit-diagram-diff with generated draw.io (plain and compressed) and Visio files.
# Run: bash tests/test_diagramdiff.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-diagram-diff"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -qF -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -30; fi; }
hasnot() { if grep -qF -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -30; else ok "$1"; fi; }

python3 - "$T" <<'PY'
import base64, sys, urllib.parse, zipfile, zlib, pathlib
T = pathlib.Path(sys.argv[1])
def model(cells):
    return '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>' + cells + '</root></mxGraphModel>'
def v(i, label, style="rounded=1;"):
    return f'<mxCell id="{i}" value="{label}" style="{style}" vertex="1" parent="1"><mxGeometry as="geometry"/></mxCell>'
def e(i, s, t, label=""):
    return f'<mxCell id="{i}" value="{label}" edge="1" parent="1" source="{s}" target="{t}"><mxGeometry as="geometry"/></mxCell>'
old = model(v("a", "Web tier") + v("b", "App tier") + v("c", "Database") + v("d", "Cache")
            + e("e1", "a", "b", "HTTPS") + e("e2", "b", "c") + e("e3", "b", "d"))
new_cells = (v("a", "Web tier") + v("b", "Application tier") + v("c", "Database", "shape=cylinder3;")
             + v("x9", "Cache") + v("f", "Message queue")
             + e("e1", "a", "b", "HTTPS") + e("e2", "b", "c") + e("e4", "b", "f", "events"))
new = model(new_cells)
(T / "old.drawio").write_text(f'<mxfile><diagram name="Main" id="p1">{old}</diagram><diagram name="Gone" id="p2">{model(v("z","Z"))}</diagram></mxfile>')
(T / "new.drawio").write_text(f'<mxfile><diagram name="Main" id="p1">{new}</diagram><diagram name="Extra" id="p3">{model(v("q","Q"))}</diagram></mxfile>')
comp = zlib.compressobj(9, zlib.DEFLATED, -15)
packed = base64.b64encode(comp.compress(urllib.parse.quote(new).encode()) + comp.flush()).decode()
(T / "new-compressed.drawio").write_text(f'<mxfile><diagram name="Main" id="p1">{packed}</diagram><diagram name="Extra" id="p3">{model(v("q","Q"))}</diagram></mxfile>')
(T / "html.drawio").write_text('<mxfile><diagram name="Main">' + model(v("a", "Web &lt;b&gt;tier&lt;/b&gt;")) + '</diagram></mxfile>')
NS = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
def vsdx(path, shapes, connects):
    pages = f'<Pages {NS}><Page ID="0" NameU="Network" Name="Network"><Rel r:id="rId1"/></Page></Pages>'
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/></Relationships>')
    sh = "".join(f'<Shape ID="{i}" NameU="{n}"><Text>{t}</Text></Shape>' for i, n, t in shapes)
    cn = "".join(f'<Connect FromSheet="{f}" FromCell="{c}" ToSheet="{to}"/>' for f, c, to in connects)
    page = f'<PageContents {NS}><Shapes>{sh}</Shapes><Connects>{cn}</Connects></PageContents>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("visio/pages/pages.xml", pages)
        z.writestr("visio/pages/_rels/pages.xml.rels", rels)
        z.writestr("visio/pages/page1.xml", page)
vsdx(T / "old.vsdx", [("1", "Rectangle", "Firewall"), ("2", "Rectangle", "Router"), ("3", "Dynamic connector", "")],
     [("3", "BeginX", "1"), ("3", "EndX", "2")])
vsdx(T / "new.vsdx", [("1", "Rectangle", "Edge firewall"), ("2", "Rectangle", "Router"), ("4", "Rectangle", "Switch"),
                      ("3", "Dynamic connector", ""), ("5", "Dynamic connector", "")],
     [("3", "BeginX", "1"), ("3", "EndX", "2"), ("5", "BeginX", "2"), ("5", "EndX", "4")])
PY

out="$(python3 "$TOOL" "$T/old.drawio" "$T/new.drawio")"
has "added component" "Added: Message queue" "$out"
hasnot "same label under new id isn't removed" "Removed: Cache" "$out"
has "same label under new id noted" "kept their label under a new id" "$out"
has "renamed component" "Renamed: App tier -> Application tier" "$out"
has "restyled component" "Restyled: Database (rectangle -> cylinder3)" "$out"
has "connection added with label" "Connection added: Application tier -> Message queue (events)" "$out"
has "connection removed" "Connection removed: App tier -> Cache" "$out"
hasnot "a rename does not look like a rewiring" "Web tier -> Application tier" "$out"
has "page added" "Pages added: Extra" "$out"
has "page removed" "Pages removed: Gone" "$out"

out2="$(python3 "$TOOL" "$T/old.drawio" "$T/new-compressed.drawio")"
a="$(sed 1d <<<"$out")"; b="$(sed 1d <<<"$out2")"
[ "$a" = "$b" ] && ok "compressed draw.io gives the same result" || { bad "compressed draw.io differs"; diff <(echo "$a") <(echo "$b") | head; }

out="$(python3 "$TOOL" "$T/html.drawio" "$T/html.drawio")"
has "identical files: no changes" "0 change(s)" "$out"

out="$(python3 "$TOOL" "$T/old.vsdx" "$T/new.vsdx")"
has "vsdx page name" "## Network" "$out"
has "vsdx added shape" "Added: Switch" "$out"
has "vsdx renamed shape" "Renamed: Firewall -> Edge firewall" "$out"
has "vsdx connection added" "Connection added: Router -> Switch" "$out"
hasnot "vsdx rename keeps its connection" "Connection removed" "$out"
hasnot "connectors aren't listed as components" "Dynamic connector" "$out"

python3 "$TOOL" --json "$T/old.drawio" "$T/new.drawio" | python3 -c "import json,sys; d=json.load(sys.stdin); p=d['pages']['Main']; assert p['added'][0]['label']=='Message queue' and p['renamed'][0]['to']=='Application tier'" \
  && ok "json output" || bad "json output"
python3 "$TOOL" "$T/old.drawio" "$T/missing.drawio" >/dev/null 2>&1 && bad "missing file accepted" || ok "missing file refused"
echo "not xml" > "$T/bad.drawio"
python3 "$TOOL" "$T/old.drawio" "$T/bad.drawio" >/dev/null 2>&1 && bad "bad file accepted" || ok "unreadable file refused cleanly"

echo "diagram diff tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
