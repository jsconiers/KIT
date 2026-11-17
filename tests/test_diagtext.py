#!/usr/bin/env python3
"""Tests for kit-diagtext, the diagram-to-text consistency check: a figure caption naming another version of the
diagram, a connection whose protocol or port the text contradicts, a count the diagram doesn't draw (and "4 x node"
read as four), a component in the text's component table that's on no diagram, a diagram component the text never
names, a clean pair, project mode (the newest draft, diagrams/ with a -spec.json), a Visio file, --write, --json,
exit codes. Synthetic documents built in a temporary folder; nothing is sent.

  python3 tests/test_diagtext.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-diagtext"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1200])


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def docx(path, items):
    """items: ("h1", text) | ("p", text) | ("cap", text) | ("table", [[cells], ...])"""
    body = []
    for kind, val in items:
        if kind == "table":
            rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{esc(c)}</w:t></w:r></w:p></w:tc>" for c in r)
                           + "</w:tr>" for r in val)
            body.append(f"<w:tbl>{rows}</w:tbl>")
        else:
            style = {"h1": "Heading1", "h2": "Heading2", "cap": "Caption"}.get(kind)
            ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
            body.append(f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{esc(val)}</w:t></w:r></w:p>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>{"".join(body)}</w:body>'
                   '</w:document>')
        z.writestr("word/styles.xml", f'<?xml version="1.0"?><w:styles {W}>'
                   '<w:style w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
                   '<w:style w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>'
                   '<w:style w:styleId="Caption"><w:name w:val="caption"/></w:style></w:styles>')


def drawio(path, cells, page="Physical"):
    xml = []
    for c in cells:
        if c[0] == "v":
            _, cid, label = c
            xml.append(f'<mxCell id="{cid}" value="{esc(label)}" style="rounded=1;" vertex="1" parent="1">'
                       '<mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>')
        else:
            _, cid, src, tgt, label = c
            xml.append(f'<mxCell id="{cid}" value="{esc(label)}" edge="1" parent="1" source="{src}" target="{tgt}">'
                       '<mxGeometry relative="1" as="geometry"/></mxCell>')
    path.write_text(f'<mxfile><diagram name="{page}"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                    + "".join(xml) + "</root></mxGraphModel></diagram></mxfile>")


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-diagtext-"))
KIT = TMP / "kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/ledger-hub"
(KIT / "memory/context").mkdir(parents=True)
(PROJ / "drafts").mkdir(parents=True)
(PROJ / "diagrams").mkdir(parents=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-17", PYTHONDONTWRITEBYTECODE="1")


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


DIAG = PROJ / "diagrams/ledger-hub-physical-v3.drawio"
drawio(DIAG, [
    ("v", "2", "Ledger API<br>REST service"),
    ("v", "3", "Directory"),
    ("v", "4", "App node (4 x node)"),
    ("v", "5", "Audit vault"),
    ("v", "6", "Version: 3"),
    ("e", "7", "2", "3", "LDAPS 636"),
    ("e", "8", "2", "4", "HTTPS 443"),
])
DOC = PROJ / "drafts/Ledger hub DOC-101 v0.4.docx"
docx(DOC, [
    ("h1", "1 Summary"),
    ("p", "The Ledger API serves balances to the branch systems."),
    ("h1", "3 Design"),
    ("p", "The Ledger API binds to the Directory over LDAP on port 389 for group lookups."),
    ("p", "The cluster runs six app nodes behind the Ledger API, over HTTPS 443."),
    ("cap", "Figure 2: Ledger hub physical view (v2)"),
    ("table", [["Component", "Role"], ["Ledger API", "front door"], ["Directory", "identity"],
               ["Batch scheduler", "nightly jobs"]]),
])

rc, out, err = run(DOC, DIAG, "--json")
ok(rc == 1, "findings: exit 1", out + err)
d = json.loads(out)
kinds = {(f["level"], f["kind"]) for f in d["findings"]}
ok(("high", "version") in kinds, "a caption naming v2 when the file is v3 is high", d["findings"])
link = [f for f in d["findings"] if f["kind"] == "link"]
ok(link and "LDAPS" in link[0]["message"] and "389" in link[0]["message"] and link[0]["diagram"]["id"] == "7",
   "a sentence giving LDAP 389 for a line labelled LDAPS 636 is flagged, with the line's id", link)
ok(not any("HTTPS" in f["message"] for f in link), "a matching protocol and port (HTTPS 443) isn't flagged", link)
cnt = [f for f in d["findings"] if f["kind"] == "count"]
ok(cnt and cnt[0]["level"] == "high" and "6 nodes" in cnt[0]["message"] and "draws 4" in cnt[0]["message"],
   "six nodes in the text, 4 x node on the diagram, is a high count finding", cnt)
miss = [f for f in d["findings"] if f["kind"] == "missing"]
ok(len(miss) == 1 and "Batch scheduler" in miss[0]["message"] and "table row 4" in miss[0]["text"]["where"],
   "a component in the text's component table, on no diagram, with its table row", miss)
un = [f for f in d["findings"] if f["kind"] == "unnamed"]
ok(len(un) == 1 and "Audit vault" in un[0]["message"] and un[0]["diagram"]["id"] == "5",
   "a diagram component the text never mentions is low, with its id", un)
ok(not any("Version" in f["message"] for f in d["findings"]), "title-block shapes are left out")
order = [f["level"] for f in d["findings"]]
ok(order == sorted(order, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x]), "ranked most serious first", order)
ok("3 Design" in link[0]["text"]["where"], "the text location names the section", link[0]["text"])

rc, out, _ = run(DOC, DIAG)
ok("HIGH version" in out and "Ledger hub physical view (v2)" in out and "ledger-hub-physical-v3.drawio" in out,
   "the text report quotes the caption and names the diagram", out)
rc, out, _ = run(DOC, DIAG, "--min", "high", "--json")
ok(all(f["level"] == "high" for f in json.loads(out)["findings"]), "--min high leaves out the rest")

# A clean pair: exit 0.
CLEAN = TMP / "clean.md"
CLEAN.write_text("# 2 Design\n\nThe Ledger API binds to the Directory over LDAPS on port 636. Four app nodes run "
                 "behind the Ledger API over HTTPS 443. The Audit vault keeps the logs.\n\n**Figure 1: Ledger hub "
                 "physical view v3**\n")
rc, out, err = run(CLEAN, DIAG, "--json")
ok(rc == 0 and not json.loads(out)["findings"], "a document that agrees with its diagram: no findings, exit 0", out + err)

# Project mode: the newest draft, every diagram in diagrams/, and a -spec.json with no drawing of its name.
(PROJ / "diagrams/ledger-hub-logical-spec.json").write_text(json.dumps({
    "title": "Ledger hub logical", "nodes": [{"id": "a", "label": "Ledger API"}, {"id": "b", "label": "Rates feed"}],
    "edges": [{"from": "a", "to": "b", "label": "TCP 9092"}]}))
(PROJ / "diagrams/ledger-hub-physical-v3-spec.json").write_text(json.dumps({"nodes": [{"id": "x", "label": "Ghost"}]}))
rc, out, err = run("ledger-hub", "--json")
d = json.loads(out)
files = {pathlib.Path(x["file"]).name for x in d["diagrams"]}
ok(pathlib.Path(d["document"]).name == DOC.name and files == {DIAG.name, "ledger-hub-logical-spec.json"},
   "project mode: the newest draft, the drawings, and only the spec with no drawing of its name", files)
ok(any("Rates feed" in f["message"] for f in d["findings"]), "the spec's components are checked too", d["findings"])
rc, out, err = run("ledger-hub", "--write")
saved = list((PROJ / "reviews").glob("*-diagtext-2026-11-17.md"))
ok(saved and "Diagram and text check" in saved[0].read_text(), "--write saves the report in reviews/", out + err)

# A Visio file.
VS = TMP / "net-v1.vsdx"
VNSU = "http://schemas.microsoft.com/office/visio/2012/main"
with zipfile.ZipFile(VS, "w") as z:
    z.writestr("visio/pages/pages.xml", f'<Pages xmlns="{VNSU}"><Page ID="0" NameU="Network"/></Pages>')
    z.writestr("visio/pages/page1.xml", f'<PageContents xmlns="{VNSU}"><Shapes>'
               '<Shape ID="1"><Text>Edge firewall</Text></Shape><Shape ID="2"><Text>Core switch</Text></Shape>'
               '<Shape ID="3"><Text>Core switch</Text></Shape></Shapes></PageContents>')
VDOC = TMP / "net.md"
VDOC.write_text("# Network\n\nTraffic passes the Edge firewall to three core switches.\n")
rc, out, err = run(VDOC, VS, "--json")
d = json.loads(out)
ok(any(f["kind"] == "count" and "3 switches" in f["message"] and "draws 2" in f["message"] for f in d["findings"]),
   "Visio: three switches in the text, two drawn", out + err)

ok(run(DOC)[0] == 2, "a document with no diagrams is a usage problem (exit 2)")
ok(run(DOC, TMP / "nope.drawio")[0] == 2, "a diagram that isn't there: exit 2")
bad = TMP / "bad.drawio"
bad.write_text("<html/>")
ok(run(DOC, bad)[0] == 2, "a file that isn't a diagram: exit 2")
ok(not list(PROJ.glob("**/*.bak")) and DIAG.read_text().startswith("<mxfile>"), "the diagram is never changed")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-diagtext tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
