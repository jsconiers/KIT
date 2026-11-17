#!/usr/bin/env python3
"""Tests for kit-precedent --closest: whole past IAs and GDSs ranked against a request (text, a markdown file, or a
Word file), --kind, superseded (by status, by a newer version of the same title) and old (past Current means)
marking, rows for one document in two indexes merged, placeholder numbers not merging documents, the --brief block
(and its plainly stated "none found"), --json, and the line search still working. Synthetic library.

  python3 tests/test_precedent_closest.py
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
TOOL = REPO / "shared/bin/kit-precedent"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-precedent-closest-"))
KIT, LIB = TMP / "kit", TMP / "library"
PUB = TMP / "published-ia"
(KIT / "memory/context").mkdir(parents=True)
(LIB / "published").mkdir(parents=True)
PUB.mkdir()
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
(KIT / "memory/context/precedent.md").write_text(
    "- **Sources:** test.\n  - `CATALOG.md`\n  - `published/`\n- **Current means:** 24 months.\n")
(LIB / "CATALOG.md").write_text(
    "| Accession | Number | Title | Type | Status | Version | Owner | Project | Updated | Location | Note |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| LIB-0001 | DOC-201 | Message bus capacity upgrade | Impact assessment | Published | 1.0 | Kit | bus | 02-Mar-2026 | artifacts/bus/ia.docx | Kafka brokers sized for trade events |\n"
    "| LIB-0002 | DOC-202 | Message bus capacity upgrade design | Design specification | Superseded | 1.0 | Kit | bus | 02-Apr-2026 | artifacts/bus/gds.docx | replaced by v2 |\n"
    "| LIB-0003 | | Payroll vendor review | Review | Final | 1 | Kit | pay | 01-Jan-2026 | artifacts/pay/r.md | not a design |\n"
    "| LIB-0004 | DOC-### | Storage tiering for archives | Impact assessment | Published | 1 | Kit | st | 01-Jan-2020 | artifacts/st/ia.docx | object storage glacier tier |\n"
    "| LIB-0005 | DOC-### | Firewall rule cleanup | Impact assessment | Published | 1 | Kit | fw | 01-Jan-2026 | artifacts/fw/ia.docx | segmentation |\n")
(LIB / "published/ia-index.md").write_text(
    f"# Published index\nLocal folder: `{PUB}`\n\n| Accession | Number | Title | Version | Modified | MB | File | Notes |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| LIB-0001 | DOC-201 | Message bus capacity upgrade | 1.0 | 02-Mar-2026 | 1 | `Message bus @ DOC-201.pdf` | |\n"
    "| LIB-0010 | DOC-210 | Event streaming platform | 1.0 | 10-Jan-2026 | 1 | `Event streaming @ DOC-210.pdf` | |\n"
    "| LIB-0011 | DOC-211 | Event streaming platform | 2.0 | 10-Jun-2026 | 1 | `Event streaming v2 @ DOC-211.pdf` | |\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1")


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


def js(*a):
    code, out, err = run(*a, "--json")
    try:
        return json.loads(out)
    except ValueError:
        return {"closest": [], "_err": out + err}


try:
    d = js("--closest", "Upgrade the Kafka message bus for more trade event capacity")
    top = d["closest"][0] if d["closest"] else {}
    ok(top.get("number") == "DOC-201", "closest IA ranks first", d)
    ok(len(d["closest"]) <= 3, "default N is 3", d)
    ok(len(top.get("sources", [])) == 2, "catalog and published rows merge into one document", top)
    ok({"kafka", "bus"} <= set(top.get("matched", [])), "why it matched lists the terms", top)
    ok(not any(c["title"] == "Payroll vendor review" for c in d["closest"]), "non-IA/GDS rows left out", d)
    gds = [c for c in d["closest"] if c["number"] == "DOC-202"]
    ok(gds and gds[0]["superseded"], "superseded by status", d)

    d = js("--closest", "5", "--kind", "gds", "message bus design")
    ok(d["closest"] and all(c["kind"] == "gds" for c in d["closest"]), "--kind gds", d)
    d = js("--closest", "5", "--kind", "ia", "message bus design")
    ok(d["closest"] and all(c["kind"] == "ia" for c in d["closest"]), "--kind ia", d)

    d = js("--closest", "event streaming platform")
    by = {c["number"]: c for c in d["closest"]}
    ok(by.get("DOC-210", {}).get("superseded") and not by.get("DOC-211", {}).get("superseded"),
       "older version of the same title is superseded", d)
    ok(str(PUB) in by.get("DOC-211", {}).get("path", ""), "published path joined to the index's local folder", by)

    d = js("--closest", "archive storage glacier tier")
    st = [c for c in d["closest"] if c["title"].startswith("Storage tiering")]
    ok(st and st[0]["old"], "older than Current means is old", d)
    d = js("--closest", "10", "firewall segmentation storage glacier")
    titles = {c["title"] for c in d["closest"]}
    ok({"Storage tiering for archives", "Firewall rule cleanup"} <= titles,
       "placeholder numbers don't merge two documents", titles)

    req = TMP / "request.md"
    req.write_text("# Request\nWe need more Kafka capacity on the message bus for trade events.\n")
    code, out, _ = run("--closest", "--brief", "--from", req)
    ok(code == 0 and out.startswith("## Closest precedents"), "--brief block", out)
    ok("**Message bus capacity upgrade**" in out and "Why it matched" in out and "Where:" in out,
       "--brief lists title, where, why", out)
    code, out, _ = run("--brief", "--from", req)
    ok("## Closest precedents" in out, "--brief alone implies --closest", out)

    docx = TMP / "demand.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Kafka message bus capacity"
                   "</w:t></w:r></w:p></w:body></w:document>")
    d = js("--closest", "--from", docx)
    ok(d["closest"] and d["closest"][0]["number"] == "DOC-201", "--from a Word file", d)

    code, out, _ = run("--closest", "--brief", "zzzunrelated qqqnothing")
    ok("None found" in out, "none found said plainly", out)
    code, out, err = run("--closest")
    ok(code == 2, "no request text is a usage error", out + err)

    code, out, _ = run("kafka")
    ok("CATALOG.md:3" in out and "hit(s) in" in out, "line search unchanged", out)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
