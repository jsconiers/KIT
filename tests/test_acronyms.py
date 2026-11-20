#!/usr/bin/env python3
"""Tests for kit-acronyms: acronyms found (plurals folded, identifiers, units, Roman numerals, code, and headings in
capitals left out), the status of each (spelled out at first use, late, only in a table, missing, a question), the
"before" and "after" forms, proposals in source order (the draft, the project's other documents, the project
glossary, a template, Kit's glossary with its personal section skipped), the ignore file, the ranked report, --json,
--table, table, --write into reviews/, a .docx draft, exit codes, and the draft never changed. Synthetic library.

  python3 tests/test_acronyms.py
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-acronyms"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1500])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-acronyms-"))
KIT = TMP / "kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/trade-capture"
TPL = TMP / "templates"
(KIT / "memory/context").mkdir(parents=True)
(PROJ / "drafts").mkdir(parents=True)
TPL.mkdir()
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n- **Templates folder:** `{TPL}`\n")
(KIT / "memory/glossary.md").write_text("# Glossary\n\n| Term | Means | Notes |\n|---|---|---|\n"
                                        "- **GRC**: Governance, Risk, and Compliance (confirmed)\n"
                                        "- **SLA**: Service Level Agreement\n\n## Personal\n\n"
                                        "- **HOA**: Homeowners Association\n")
(TPL / "IA template.md").write_text("# Acronyms\n\n| Acronym | Meaning |\n|---|---|\n| SLA | Service Level Objective |\n"
                                    "| RTO | Recovery Time Objective |\n")
(PROJ / "glossary.md").write_text("# Project glossary\n\n- **CMDB**: Configuration Management Database\n")
(PROJ / "notes.md").write_text("The Object Request Broker (ORB) is retired next year.\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-20", PYTHONDONTWRITEBYTECODE="1")

DRAFT = PROJ / "drafts/Trade capture IA v0.2.md"
DRAFT.write_text("""# DRAFT CONFIDENTIAL WORKING COPY

# 1 Summary

The QZB and ORB teams will move the PCX database to AWS. Keys stay in KMS for IA-12 (INC00042, Q-012).
Phase II needs 40 GB and a 4 TB volume; the RTO is 4 hours. GRC and the CMDB owners must agree. See `API_KEY`.
HOA is not a work term. The APIs change. The SLA is agreed. DNS (Domain Name System) is unchanged.

# 2 Detail

Amazon Web Services (AWS) hosts the target. Key Management Service (KMS) holds the keys. We call an Application
Programming Interface (API).

| Acronym | Meaning |
|---|---|
| PCX | Payment Capture Exchange |
""")
(PROJ / "acronyms-ignore.txt").write_text("# words to leave out\nWORKING\n")
before = hashlib.sha256(DRAFT.read_bytes()).hexdigest()


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


rc, out, err = run("check", "trade-capture", DRAFT.name, "--json")
ok(rc == 1, "something to fix: exit 1", out + err)
res = {r["acronym"]: r for r in json.loads(out)["acronyms"]}
for gone in ("IA", "INC", "GB", "TB", "II", "DRAFT", "CONFIDENTIAL", "API_KEY", "KEY", "WORKING"):
    ok(gone not in res, f"{gone} left out (identifier, unit, numeral, heading in capitals, code)", sorted(res))
ok(res["API"]["uses"] == 2, "APIs counted as API", res.get("API"))
ok(res["DNS"]["status"] == "ok" and res["DNS"]["meaning"] == "Domain Name System",
   "the 'DNS (Domain Name System)' form at first use is fine", res.get("DNS"))
for a, m in (("AWS", "Amazon Web Services"), ("KMS", "Key Management Service"),
             ("API", "Application Programming Interface")):
    ok(res[a]["status"] == "late" and res[a]["meaning"] == m and res[a]["spelled_out"].startswith("2 Detail"),
       f"{a} spelled out late, with where", res[a])
ok(res["PCX"]["status"] == "table only" and res["PCX"]["meaning"] == "Payment Capture Exchange", "PCX only in the table",
   res["PCX"])
ok(res["ORB"]["status"] == "missing" and res["ORB"]["source"] == "project document notes.md"
   and res["ORB"]["meaning"] == "Object Request Broker", "ORB proposed from another project document", res["ORB"])
ok(res["CMDB"]["meaning"] == "Configuration Management Database" and res["CMDB"]["source"] == "project glossary.md",
   "CMDB from the project glossary", res["CMDB"])
ok(res["RTO"]["source"].startswith("template ") and res["RTO"]["meaning"] == "Recovery Time Objective",
   "RTO from the template's acronyms table", res["RTO"])
ok(res["SLA"]["meaning"] == "Service Level Objective" and res["SLA"]["source"].startswith("template"),
   "a template comes before Kit's glossary", res["SLA"])
ok(res["GRC"]["source"] == "Kit's glossary" and res["GRC"]["meaning"] == "Governance, Risk, and Compliance",
   "GRC from Kit's glossary, the note in brackets dropped", res["GRC"])
ok(res["HOA"]["status"] == "question" and res["QZB"]["status"] == "question",
   "the glossary's personal section is skipped; unknowns are questions", (res["HOA"], res["QZB"]))

order = [r["status"] for r in json.loads(out)["acronyms"]]
rank = {"question": 0, "missing": 1, "late": 2, "table only": 3, "ok": 4}
ok(order == sorted(order, key=rank.get), "ranked: questions, missing, late, table only, ok", order)

rc, out, _ = run("check", "trade-capture", DRAFT.name, "--table")
ok("## Questions for the owner" in out and "**QZB** (1 use; first at 1 Summary" in out, "report: questions first", out)
ok("| ORB | 1 | 1 Summary, paragraph 1 | Object Request Broker (ORB) | project document notes.md |" in out,
   "report: a missing row with its proposal and source", out)
ok("## Acronyms table, ready to paste" in out and "| QZB | (to confirm) |" in out and "| AWS | Amazon Web Services |"
   in out and "DNS" in out.split("ready to paste")[1], "--table adds the paste-ready table", out)
ok("Nothing in the draft was changed" in out, "the report says the draft is untouched", out)
rc, out, _ = run("table", "trade-capture")
ok(rc == 0 and out.startswith("| Acronym | Meaning |") and "| KMS | Key Management Service |" in out,
   "table: only the table, from the latest draft", out)
rc, out, _ = run("check", "trade-capture", DRAFT.name, "--write")
saved = list((PROJ / "reviews").glob("*-acronyms-2026-11-20.md"))
ok(len(saved) == 1 and "Saved:" in out, "--write saves the report in reviews/", out)
ok(hashlib.sha256(DRAFT.read_bytes()).hexdigest() == before, "the draft is never changed")

# A clean draft: exit 0.
CLEAN = PROJ / "drafts/clean.md"
CLEAN.write_text("# 1 Scope\n\nThe Domain Name System (DNS) records move. DNS stays internal.\n")
rc, out, _ = run("check", "trade-capture", CLEAN.name)
ok(rc == 0 and "Every acronym is spelled out at its first use." in out, "a clean draft: exit 0", out)

# A .docx draft, read through kit_doctext.
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def para(t, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>"


body = para("1 Summary", "Heading1") + para("Tokens come from the ORB and the HSM.") + \
    para("2 Design", "Heading1") + para("A Hardware Security Module (HSM) signs them.")
DOCX = PROJ / "drafts/design.docx"
with zipfile.ZipFile(DOCX, "w") as z:
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
    z.writestr("word/styles.xml", f'<w:styles {W}><w:style w:styleId="Heading1"><w:name w:val="heading 1"/></w:style></w:styles>')
rc, out, err = run("check", "trade-capture", DOCX.name, "--json")
res = {r["acronym"]: r for r in json.loads(out)["acronyms"]}
ok(res["HSM"]["status"] == "late" and res["HSM"]["meaning"] == "Hardware Security Module"
   and res["HSM"]["first_use"].startswith("1 Summary"), "a .docx draft: HSM late", res)
ok(res["ORB"]["status"] == "missing", "a .docx draft: ORB missing, proposed from the project", res)

# A file outside a project, and usage problems.
LOOSE = TMP / "loose.md"
LOOSE.write_text("The SLA applies.\n")
rc, out, _ = run("check", LOOSE, "--json")
ok(rc == 1 and json.loads(out)["acronyms"][0]["source"].startswith("template"), "a loose file still gets proposals", out)
rc, _, err = run("check", LOOSE, "--write")
ok(rc == 2 and "needs the document to be in a project" in err, "--write outside a project: exit 2", err)
rc, _, err = run("check", "no-such-project")
ok(rc == 2 and "no project folder" in err, "an unknown project: exit 2", err)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
