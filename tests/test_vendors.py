#!/usr/bin/env python3
"""Tests for kit-vendors (the vendor evaluation desk): the question set and the questionnaire, answers
imported from CSV, XLSX, Markdown, and DOCX, scoring and ranking, must-haves, dodged answers, the one-page
report, and what's due. Everything happens in a temp folder with a fake Kit and library; nothing is sent.

Run: python3 tests/test_vendors.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
PASS = FAIL = 0
SECRET = "sk-" + "Q" * 30


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
bin_ = kit / ".install/shared/bin"
bin_.mkdir(parents=True)
(kit / "memory/context").mkdir(parents=True)
lib = tmp / "library"
lib.mkdir()
shutil.copy(SHARED / "bin/kit-vendors", bin_ / "kit-vendors")
for f in ("kit_compliance.py", "kit_records.py"):
    shutil.copy(SHARED / f, kit / ".install/shared" / f)
LIBMD = kit / "memory/context/library.md"
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-11-02", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")


def kv(*args, **extra):
    r = subprocess.run([sys.executable, str(bin_ / "kit-vendors"), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", env=dict(env, **extra))
    return r.returncode, r.stdout, r.stderr


def data(slug="obs"):
    return json.loads((lib / "vendor-evaluations" / slug / "eval.json").read_text(encoding="utf-8"))


def xlsx(path, rows, doctype=False):
    """A minimal workbook: a cover sheet, then the answers sheet (shared and inline strings, numbers)."""
    shared, idx, out = [], {}, []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, v in enumerate(row):
            ref = chr(65 + c) + str(r)
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            elif v.startswith("inline:"):
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(v[7:])}</t></is></c>')
            elif v:
                if v not in idx:
                    idx[v] = len(shared)
                    shared.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{idx[v]}</v></c>')
        out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
    ns = ('xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    dt = '<!DOCTYPE x [<!ENTITY a "aaaa">]>' if doctype else ""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook {ns}><sheets><sheet name="Cover" sheetId="1" '
                                      f'r:id="rId1"/><sheet name="Answers" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                   'relationships"><Relationship Id="rId1" Type="t" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Type="t" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0"?><worksheet {ns}><sheetData><row r="1">'
                                               '<c r="A1" t="inlineStr"><is><t>Cover</t></is></c></row></sheetData>'
                                               '</worksheet>')
        z.writestr("xl/worksheets/sheet2.xml", f'<?xml version="1.0"?>{dt}<worksheet {ns}><sheetData>' + "".join(out)
                   + "</sheetData></worksheet>")
        z.writestr("xl/sharedStrings.xml", f'<?xml version="1.0"?><sst {ns}>'
                   + "".join(f"<si><t>{escape(s)}</t></si>" for s in shared) + "</sst>")


def docx(path, rows, intro="Our answers"):
    """A minimal document with a paragraph, then one table; a string row is a section heading spanning three
    columns."""
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

    def cell(t, span=1):
        pr = f'<w:tcPr><w:gridSpan w:val="{span}"/></w:tcPr>' if span > 1 else ""
        return f"<w:tc>{pr}" + "".join(f"<w:p><w:r><w:t>{escape(x)}</w:t></w:r></w:p>" for x in t.split("\n")) + "</w:tc>"
    trs = ["<w:tr>" + (cell(r, 3) if isinstance(r, str) else "".join(cell(c) for c in r)) + "</w:tr>" for r in rows]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {w}><w:body><w:p><w:r><w:t>{escape(intro)}'
                                        "</w:t></w:r></w:p><w:tbl>" + "".join(trs) + "</w:tbl></w:body></w:document>")


# ---- no place for evaluations ---------------------------------------------------------------------------
rc, o, e = kv("new", "obs", "--title", "Observability platform")
ok(rc == 1 and "no place for evaluations" in e and "library root" in e, "no library root: stops and says where to set it", e)
rc, o, e = kv("list")
ok(rc == 1 and "no place for evaluations" in e, "list too, with no library root")
LIBMD.write_text(f"- **Library root:** `{lib}`.\n")

# ---- an empty desk ------------------------------------------------------------------------------------------
rc, o, e = kv()
ok(rc == 0 and "no evaluations yet" in o, "no command lists evaluations: none yet", o + e)
rc, o, e = kv("due")
ok(rc == 0 and "nothing due" in o, "due with nothing to do")

# ---- a new evaluation ------------------------------------------------------------------------------------------
rc, o, e = kv("new", "obs", "--title", "Observability platform", "--vendors", "Acme Corp, Globex; acme corp", "--due",
              "20-Nov-2026")
ok(rc == 0 and "28 questions, 6 must-haves, 2 vendor(s), answers due 20-Nov-2026" in o, "new: questions, must-haves, "
   "vendors (a repeat dropped), due date shown as DD-Mmm-YYYY", o + e)
d = data()
ok(d["due"] == "2026-11-20" and d["created"] == "2026-11-02", "dates are stored ISO")
ok({q["section"] for q in d["questions"]} == {"security", "resilience", "integration", "exit", "commercial"},
   "the default set covers security, resilience, integration, exit, and commercial; functional is yours")
ok(sum(d["weights"].values()) == 100 and d["weights"]["functional"] == 15, "default weights add up to 100", d["weights"])
if os.name != "nt":
    ok(oct((lib / "vendor-evaluations/obs/eval.json").stat().st_mode)[-3:] == "600", "eval.json is readable only by you")
rc, o, e = kv("new", "obs", "--title", "Again")
ok(rc == 1 and "already exists" in e, "an evaluation is never started twice")
rc, o, e = kv("new", "../x", "--title", "Bad")
ok(rc == 1 and "isn't a slug" in e, "a slug can't climb out of the folder", e)
rc, o, e = kv("new", "x1", "--title", "T", "--due", "31-Feb-2026")
ok(rc == 1 and "--due must be" in e, "a date that doesn't exist is refused", e)
rc, o, e = kv("new", "x2", "--title", "password: hunter2xx")
ok(rc == 1 and "credential" in e, "a title that looks like a credential is refused", e)
rc, o, e = kv("vendor", "obs", "Initech")
ok(rc == 0 and "3 vendor(s)" in o, "vendor adds one")
rc, o, e = kv("vendor", "obs", "GLOBEX")
ok(rc == 1 and "already in obs" in e, "the same vendor twice is refused, whatever the case")
rc, o, e = kv("vendor", "nope", "X")
ok(rc == 1 and "no evaluation 'nope'" in e, "a missing evaluation says so")

# ---- the question set -----------------------------------------------------------------------------------------
rc, o, e = kv("question", "obs", "add", "--section", "functional", "--must", "Describe how dashboards are shared "
              "across teams, with permissions per team and an audit of who saw what.")
ok(rc == 0 and "added FUN-01 to Functional as a must-have" in o, "question add: the next ID in the section", o + e)
rc, o, e = kv("question", "obs", "add", "--section", "func", "--id", "FUN-09", "Can it alert on SLO burn rate?")
ok(rc == 0 and "FUN-09" in o, "a section by prefix, and an ID of your own")
rc, o, e = kv("question", "obs", "add", "--section", "functional", "--id", "fun-9", "Duplicate ID question?")
ok(rc == 1 and "already a question" in e, "an ID already taken is refused, however it's written")
rc, o, e = kv("question", "obs", "add", "--section", "nowhere", "Some question here?")
ok(rc == 1 and "no section 'nowhere'" in e, "an unknown section is refused")
rc, o, e = kv("question", "obs", "must", "SEC-04")
ok(rc == 0 and "now a must-have" in o and [q for q in data()["questions"] if q["id"] == "SEC-04"][0]["must"],
   "question must marks a must-have")
kv("question", "obs", "must", "SEC-04", "off")
ok(not [q for q in data()["questions"] if q["id"] == "SEC-04"][0]["must"], "and off unmarks it")
rc, o, e = kv("question", "obs", "remove", "COM-05")
ok(rc == 0 and not any(q["id"] == "COM-05" for q in data()["questions"]), "question remove")
rc, o, e = kv("question", "obs", "remove", "XYZ-1")
ok(rc == 1 and "no question XYZ-1" in e, "removing a question that isn't there says so")
d = data()
order = [q["section"] for q in d["questions"]]
ok(order == sorted(order, key=["security", "resilience", "integration", "exit", "commercial", "functional"].index),
   "questions stay in section order")
ok(len(d["questions"]) == 29 and sum(1 for q in d["questions"] if q["must"]) == 7, "29 questions, 7 must-haves now")

# ---- weights ------------------------------------------------------------------------------------------------------------
rc, o, e = kv("weights", "obs")
ok(rc == 0 and "Security" in o and "(25%)" in o, "weights shows them with their shares")
rc, o, e = kv("weights", "obs", "security=30", "exit=5")
ok(rc == 0 and data()["weights"]["security"] == 30 and data()["weights"]["exit"] == 5, "weights SECTION=N sets them")
rc, o, e = kv("weights", "obs", "security:30")
ok(rc == 1 and "SECTION=N" in e, "a malformed weight is refused")
rc, o, e = kv("weights", "obs", *[f"{s}=0" for s in ("security", "resilience", "integration", "exit", "commercial",
                                                     "functional")])
ok(rc == 1 and "above 0" in e and data()["weights"]["security"] == 30, "all weights at 0 is refused, and nothing changes")

# ---- the questionnaire ---------------------------------------------------------------------------------------------------
rc, o, e = kv("questions", "obs")
ok(rc == 0 and "SEC-01  [must]" in o and "Functional (weight 15)" in o and "FUN-01" in o, "questions lists the set")
qcsv = tmp / "out/questions.csv"
rc, o, e = kv("questions", "obs", "--csv", qcsv)
lines = qcsv.read_text(encoding="utf-8-sig").splitlines()
ok(rc == 0 and lines[0] == "ID,Section,Question,Must have,Answer" and len(lines) == 30, "--csv: a header and a row per "
   "question", lines[:2])
ok("Kit never sends it" in o and "[work]" not in qcsv.read_text(encoding="utf-8-sig"),
   "the questionnaire is for you to send, with no [work] tag in it")
rc, o, e = kv("questions", "obs", "--csv", qcsv)
ok(rc == 1 and "kept" in e, "an existing questionnaire file is never overwritten")
rc, o, e = kv("questions", "obs", "--csv", qcsv, "--force")
ok(rc == 0, "--force replaces it")
qmd = tmp / "out/questions.md"
rc, o, e = kv("questions", "obs", "--md", qmd)
t = qmd.read_text(encoding="utf-8")
ok(rc == 0 and "| ID | Section | Question | Must have | Answer |" in t and "Please answer by 20-Nov-2026" in t,
   "--md: a table to send, with the due date")

# ---- answers: CSV, by ID and by text ---------------------------------------------------------------------------------------
acme = tmp / "acme.csv"
acme.write_text(
    "ID,Question,Response,Comments\n"
    "SEC-01,,AES-256 at rest with customer keys in an HSM; TLS 1.2 or later in transit.,\n"
    "SEC-02,,\"SAML and OIDC, MFA enforced, SCIM removes access within 1 hour.\",\n"
    "SEC-03,,Please see the attached SOC 2 report.,\n"
    "SEC-04,,TBD,\n"
    "SEC-05,,Yes,\n"
    "SEC-06,,N/A,\n"
    "SEC-07,,Available upon request.,\n"
    "RES-01,,RTO 4 hours and RPO 15 minutes; tested in March 2026 with a full region failover.,\n"
    "RES-05,,Uptime reporting is on our roadmap.,\n"
    "EXIT-01,,Contact your account manager.,\n"
    "EXIT-02,,,\n"
    f"COM-01,,Per seat pricing. Partner code {SECRET}.,\n"
    "COM-02,,Capped,\n"
    "XYZ-9,Do you have a mascot?,Yes a dog,\n"
    ",\"Which identity, monitoring, and ticketing products do you integrate with, out of the box?\","
    "\"Okta, ServiceNow, and Splunk, out of the box.\",\n", encoding="utf-8")
rc, o, e = kv("import", "obs", "ACME CORP", acme)
ok(rc == 0 and "read 14 question(s) for Acme Corp from acme.csv (13 by ID, 1 by question text; 1 left blank)" in o,
   "import: matched by ID, else by the question's text", o + e)
ok("1 row(s) matched no question and were left out: XYZ-9" in o, "a row that matches no question is listed, not guessed")
ok("1 piece(s) of text that looked like a credential were removed" in o, "a credential in an answer is removed")
ans = lib / "vendor-evaluations/obs/answers"
scrubbed = ans / "acme-corp-2026-11-02-scrubbed.csv"
ok(scrubbed.exists() and not (ans / "acme-corp-2026-11-02.csv").exists(),
   "a file with a credential in it isn't kept: the rows read are, with it removed", sorted(x.name for x in ans.iterdir()))
stext = scrubbed.read_text(encoding="utf-8") if scrubbed.exists() else ""
ok(SECRET not in stext and "[removed: looked like a credential]" in stext and "SEC-01" in stext,
   "the copy has no credential, and still has the answers")
if os.name != "nt" and scrubbed.exists():
    ok(oct(scrubbed.stat().st_mode)[-3:] == "600" and oct(ans.stat().st_mode)[-3:] == "700",
       "the copy and the answers folder are readable only by you")
ok(SECRET not in (lib / "vendor-evaluations/obs/eval.json").read_text(encoding="utf-8"), "and never stored")
ok(data()["vendors"][0].get("responded") == "2026-11-02", "the vendor is marked as having answered")

# boilerplate and a short answer to a long question, for Globex, in an XLSX with a cover sheet
boiler = "Our platform is enterprise grade and trusted by the world's leading companies."
gx = tmp / "globex.xlsx"
xlsx(gx, [["Globex RFP response"], [], ["Question ID", "Question", "Compliant (Y/N)", "Vendor comments"],
          ["SEC-01", "", "Y", "AES-256 everywhere, keys in a KMS, customer-managed keys optional."],
          ["SEC-02", "", "inline:Y", "SAML 2.0 and OIDC with MFA; SCIM deprovisioning."],
          ["SEC-08", "", "", boiler], ["RES-02", "", "", boiler], ["INT-01", "", "", boiler],
          ["RES-01", "", "", "1 hour"], ["EXIT-01", "", "Y", "Full CSV and Parquet export within 30 days at no cost."],
          ["EXIT-02", "", "Y", "Deleted within 30 days, with a signed certificate."],
          ["SEC-03", "", "", "SOC 2 Type II, scope all production, audited by an independent firm, May 2026."],
          ["FUN-01", "", "", "Dashboards are shared by team with role-based permissions and a full view audit log."]])
rc, o, e = kv("import", "obs", "Globex", gx)
ok(rc == 0 and "read 10 question(s) for Globex from globex.xlsx (10 by ID" in o, "XLSX: the answers sheet after a cover "
   "sheet, shared and inline strings", o + e)
ok(any("Y; AES-256" in a["text"] for a in data()["answers"]["Globex"].values()),
   "a compliance column and a comments column are read together")

# DOCX for Initech: a heading row spanning the table, and an answer in two paragraphs
ini = tmp / "initech.docx"
docx(ini, [["#", "Requirement", "Response"], "Security",
           ["SEC-1", "", "We encrypt everything.\nKeys rotate every year."],
           ["EXIT-01", "", "Full export in open formats within 30 days, at no cost."]])
rc, o, e = kv("import", "obs", "Initech", ini)
ok(rc == 0 and "read 2 question(s) for Initech" in o, "DOCX: a table with a heading row; SEC-1 matches SEC-01", o + e)
ok("We encrypt everything.\nKeys rotate every year." == data()["answers"]["Initech"]["SEC-01"]["text"],
   "a DOCX answer keeps its paragraphs")
md = tmp / "more.md"
md.write_text("# Extra\n\n| Ref | Answer |\n|---|---|\n| COM-03 | 24x7 \\| one hour for severity 1 |\n", encoding="utf-8")
rc, o, e = kv("import", "obs", "Initech", md)
ok(rc == 0 and data()["answers"]["Initech"]["COM-03"]["text"] == "24x7 | one hour for severity 1"
   and "SEC-01" in data()["answers"]["Initech"], "Markdown: an escaped pipe; a second file adds to the first", o + e)
ok((lib / "vendor-evaluations/obs/answers/initech-2026-11-02.md").exists(), "each file gets its own copy")

# files it can't use
bad = tmp / "x.pdf"
bad.write_text("x")
rc, o, e = kv("import", "obs", "Initech", bad)
ok(rc == 1 and "use CSV, XLSX" in e, "a format it can't read is named")
notzip = tmp / "x.xlsx"
notzip.write_text("not a zip")
rc, o, e = kv("import", "obs", "Initech", notzip)
ok(rc == 1 and "isn't a readable XLSX" in e, "a broken XLSX is refused with a clear line", e)
evil = tmp / "evil.xlsx"
xlsx(evil, [["ID", "Answer"], ["SEC-01", "x"]], doctype=True)
rc, o, e = kv("import", "obs", "Initech", evil)
ok(rc == 1 and "document type declaration" in e, "an XLSX with a DTD is refused (no entity expansion)", e)
nohead = tmp / "nohead.csv"
nohead.write_text("a,b\n1,2\n")
rc, o, e = kv("import", "obs", "Initech", nohead)
ok(rc == 1 and "no table with a question or ID column and an answer column" in e, "a table with no answer column")
nomatch = tmp / "nomatch.csv"
nomatch.write_text("ID,Answer\nQQ-1,Something\n")
rc, o, e = kv("import", "obs", "Initech", nomatch)
ok(rc == 1 and "nothing imported" in e, "no matching row: nothing imported")
rc, o, e = kv("import", "obs", "Nobody", acme)
ok(rc == 1 and "no vendor 'Nobody'" in e and "Acme Corp" in e, "an unknown vendor lists the ones there are")
rc, o, e = kv("import", "obs", "Initech", tmp / "missing.csv")
ok(rc == 1 and "no such file" in e, "a missing file says so")

# ---- dodged answers ----------------------------------------------------------------------------------------------------------
rc, o, e = kv("gaps", "obs", "acme corp")
g = {ln.split()[0]: ln for ln in o.splitlines() if ln.startswith("  ")}
ok("see attached" in g.get("SEC-03", ""), "see attached", o)
ok("TBD" in g.get("SEC-04", ""), "TBD")
ok("bare yes or no" in g.get("SEC-05", ""), "a bare yes to a question that asks how")
ok("N/A" in g.get("SEC-06", ""), "N/A")
ok("available on request" in g.get("SEC-07", ""), "available on request")
ok("roadmap" in g.get("RES-05", ""), "roadmap")
ok("contact sales" in g.get("EXIT-01", ""), "contact sales (your account manager)")
ok("no answer" in g.get("EXIT-02", ""), "a blank answer")
ok("SEC-01" not in g and "SEC-02" not in g and "RES-01" not in g and "INT-03" not in g, "real answers aren't flagged")
ok("COM-02" not in g or "word" not in g.get("COM-02", ""), "a short answer to a short question isn't flagged")
ok(SECRET not in o, "gaps never print a credential")
rc, o, e = kv("gaps", "obs", "Globex")
g = {ln.split()[0]: ln for ln in o.splitlines() if ln.startswith("  ")}
ok(all("same answer as 2 other questions" in g.get(q, "") for q in ("SEC-08", "RES-02", "INT-01")),
   "the same answer pasted on three questions", o)
ok("words for a long question" in g.get("RES-01", "") or "word for a long question" in g.get("RES-01", ""),
   "a very short answer to a long question", g.get("RES-01"))
rc, o, e = kv("gaps", "obs", "--json")
j = json.loads(o)
ok(set(j["gaps"]) == {"Acme Corp", "Globex", "Initech"} and j["gaps"]["Acme Corp"], "gaps --json for every vendor")

# ---- scoring -------------------------------------------------------------------------------------------------------------------
rc, o, e = kv("score", "obs", "Acme Corp", "SEC-01", "5", "--note", "customer-held keys")
ok(rc == 0 and "SEC-01 = 5 (customer-held keys)" in o, "score one question, with a note")
rc, o, e = kv("score", "obs", "Acme Corp", "sec-1", "6")
ok(rc == 1 and "0 (doesn't meet) to 5 (exceeds)" in e, "a score outside 0 to 5 is refused")
rc, o, e = kv("score", "obs", "Acme Corp", "SEC-01", "4.5")
ok(rc == 1, "a half point is refused")
rc, o, e = kv("score", "obs", "Acme Corp", "SEC-01", "3", "--note", "token = abcdefgh1234")
ok(rc == 1 and "credential" in e, "a note that looks like a credential is refused")
sc = tmp / "acme-scores.csv"
sc.write_text("ID,Score,Note\nSEC-02,4,\nSEC-03,3,report seen\nRES-01,4,\nEXIT-01,1,vague\nEXIT-02,0,no deletion\n"
              "COM-01,7,\nNOPE-1,3,\nSEC-04,,\n")
rc, o, e = kv("score", "obs", "Acme Corp", "--file", sc)
ok(rc == 0 and "5 score(s) saved" in o and "skipped COM-01: '7' isn't 0 to 5" in o and "skipped NOPE-1" in o,
   "--file: valid rows saved, the rest listed; a blank score is skipped quietly", o)
gl = tmp / "globex-scores.csv"
gl.write_text("ID,Score\n" + "".join(f"{q['id']},4\n" for q in data()["questions"]))
rc, o, e = kv("score", "obs", "Globex", "--file", gl)
ok(rc == 0 and "29 score(s) saved" in o, "a whole sheet of scores")
kv("score", "obs", "Globex", "INT-01", "1")
kv("score", "obs", "Globex", "SEC-03", "clear")
ok("SEC-03" not in data()["scores"]["Globex"], "clear removes a score")
bad = tmp / "noscore.csv"
bad.write_text("ID,Note\nSEC-01,x\n")
rc, o, e = kv("score", "obs", "Globex", "--file", bad)
ok(rc == 1 and "Score column" in e, "a scores file needs a Score column")

# ---- the side by side --------------------------------------------------------------------------------------------------------
rc, o, e = kv("show", "obs", "--json")
s = json.loads(o)
v = {x["name"]: x for x in s["vendors"]}
# Globex: everything 4 (80) except INT-01 at 1 and SEC-03 unscored. Integration: (1+4+4+4+4)/5*20 = 68.0.
ok(v["Globex"]["sections"]["integration"] == 68.0 and v["Globex"]["sections"]["security"] == 80.0,
   "a section's score is the mean of its scored questions times 20", v["Globex"]["sections"])
w = s["weights"]
want = round((30 * 80 + 20 * 80 + 15 * 68 + 5 * 80 + 15 * 80 + 15 * 80) / (30 + 20 + 15 + 5 + 15 + 15), 1)
ok(v["Globex"]["total"] == want and v["Globex"]["partial"], f"the total is the weighted mean ({want}), partial while "
   "a question is unscored", v["Globex"])
ok(v["Globex"]["rank"] == 1, "Globex ranks first")
ok(v["Acme Corp"]["rank"] == "out" and {"id": "EXIT-02", "why": "scored 0"} in v["Acme Corp"]["fails"],
   "a must-have scored 0 fails the vendor", v["Acme Corp"]["fails"])
ok(v["Initech"]["rank"] == "out" and any(f["why"] == "left unanswered" for f in v["Initech"]["fails"]),
   "a must-have left unanswered, once the vendor has answered, fails it too")
rc, o, e = kv("show", "obs")
ok(rc == 0 and "Weighted total" in o and "Must-haves failed" in o and "Unscored" in o and "[work]" in o,
   "show: the side by side, tagged [work]", o)
ok("Acme Corp: EXIT-02 scored 0" in o, "show names the failed must-haves", o)
rc, o, e = kv("show", "obs", "--answers", "--section", "security")
ok("\nSEC-03 [must]" in o and "[dodged: see attached]" in o and "\nRES-01 [must]" not in o, "--answers: each "
   "vendor's answer, dodges marked, one section", o[-600:])
ok(SECRET not in o, "show never prints a credential")

# ---- the report -------------------------------------------------------------------------------------------------------------------
rc, o, e = kv("report", "obs")
ok(rc == 0 and o.startswith("# Vendor evaluation: Observability platform"), "report: one page", o[:200])
ok("Drafted by Kit for your review" in o and "[work]" in o and "Nothing was sent to any vendor" in o,
   "drafted for your review, tagged [work], nothing sent")
ok(f"Provisional, as scoring isn't finished: **Globex**, with {want:.1f} of 100: the only vendor that meets every "
   "must-have." in o, "the recommendation: provisional while scoring is open", o[o.find("## Recommendation"):][:300])
ok("- Acme Corp fails EXIT-02" in o and "- Initech fails" in o, "must-haves failed")
ok("- Globex: INT-01 scored 1 of 5" in o, "risks: a low score for the recommended vendor", o[o.find("## Risks"):][:400])
ok("Acme Corp (" in o and "with no answer" in o, "dodged questions, blanks counted")
ok("Globex: 1 question(s) unscored (SEC-03)" in o, "open items: unscored questions")
ok(SECRET not in o, "the report never holds a credential")
kv("score", "obs", "Globex", "SEC-03", "4")
kv("score", "obs", "Acme Corp", "EXIT-02", "3")
for q in data()["questions"]:
    if q["id"] not in data()["scores"].get("Acme Corp", {}):
        kv("score", "obs", "Acme Corp", q["id"], "4")
rc, o, e = kv("report", "obs")
rec = o[o.find("## Recommendation"):].splitlines()[2]
top, second = sorted((x for x in json.loads(kv("show", "obs", "--json")[1])["vendors"] if x["rank"] in (1, 2)),
                     key=lambda x: x["rank"])
margin = top["total"] - second["total"]
ok(rec.startswith(f"**{top['name']}**, with {top['total']:.1f} of 100, ahead of {second['name']} "
                  f"({second['total']:.1f}) by {margin:.1f} points.") and "A close call" in rec and "Provisional" not in rec,
   "both scored: the leader, the margin, and a close call under 5 points", rec)
rc, o, e = kv("report", "obs", "--write")
ok(rc == 0 and (lib / "vendor-evaluations/obs/report-2026-11-02.md").exists(), "--write saves the report", o + e)
kv("report", "obs", "--write")
ok((lib / "vendor-evaluations/obs/report-2026-11-02-2.md").exists(), "a second report the same day never overwrites")

# ---- list and due --------------------------------------------------------------------------------------------------------------------
kv("new", "dbaas", "--title", "Database service", "--vendors", "Northwind", "--due", "2026-12-31")
rc, o, e = kv("list")
ok(rc == 0 and "2 evaluation(s)" in o and f"leading: {top['name']} ({top['total']:.1f})" in o
   and "0/1 answered, due 31-Dec-2026" in o, "list: answers in, due dates, who leads", o)
rc, o, e = kv("due", "--days", "30", KIT_TODAY="2026-11-18")
ok("obs" not in o and "nothing due" in o, "everyone answered: not due; the other is more than 30 days out", o)
rc, o, e = kv("due", KIT_TODAY="2027-01-02")
ok("dbaas: LATE by 2 days (31-Dec-2026); waiting on Northwind" in o, "late across the year end", o)
rc, o, e = kv("due", "--days", "3", KIT_TODAY="2026-12-29")
ok("dbaas: due in 2 days (31-Dec-2026)" in o, "due within the window")
rc, o, e = kv("due", "--json", KIT_TODAY="2026-12-31")
j = json.loads(o)
ok(j["due"][0]["days_left"] == 0 and not j["due"][0]["late"] and j["due"][0]["waiting"] == ["Northwind"],
   "due --json: due today")
rc, o, e = kv("report", "dbaas")
ok("No recommendation yet: nothing is scored." in o and "Northwind hasn't sent answers" in o,
   "a report with nothing scored says so", o)
kv("new", "empty", "--title", "No vendors yet")
rc, o, e = kv("report", "empty")
ok(rc == 0 and "No vendors yet" in o, "a report with no vendors")
rc, o, e = kv("show", "empty")
ok(rc == 0 and "No vendors yet" in o, "show with no vendors")
(lib / "vendor-evaluations/broken").mkdir()
(lib / "vendor-evaluations/broken/eval.json").write_text("{not json")
rc, o, e = kv("list")
ok(rc == 0 and "broken" in o and "can't be read" in o, "a broken eval.json is listed, not fatal", o)
rc, o, e = kv("show", "broken")
ok(rc == 1 and "can't read" in e, "and show says it can't read it")

# ---- a folder named in decisions.md ---------------------------------------------------------------------------------------------------
other = tmp / "elsewhere"
(kit / "memory/context/decisions.md").write_text(f"- **Vendor evaluations:** `{other}`\n")
rc, o, e = kv("new", "abc", "--title", "Somewhere else")
ok(rc == 0 and (other / "abc/eval.json").exists(), "decisions.md's Vendor evaluations names another folder", o + e)
LIBMD.unlink()
rc, o, e = kv("list")
ok(rc == 0 and "1 evaluation(s)" in o, "a full path works with no library root")

# ---- review fixes: copies, blanks, a Description column ------------------------------------------------------------
LIBMD.write_text(f"- **Library root:** `{lib}`.\n")
(kit / "memory/context/decisions.md").unlink()
kv("new", "fix", "--title", "Review fixes", "--vendors", "Acme, Beta, Gamma")
fix = lib / "vendor-evaluations/fix"
gx = tmp / "clean.xlsx"
xlsx(gx, [["ID", "Answer"], ["SEC-02", "SAML 2.0 and OIDC, MFA enforced through the identity provider."]])
rc, o, e = kv("import", "fix", "Gamma", gx)
copy = fix / "answers/gamma-2026-11-02.xlsx"
ok(rc == 0 and copy.exists() and "a copy is in answers/gamma-2026-11-02.xlsx" in o, "a clean file is copied as it is",
   o + e)
if os.name != "nt":
    ok(oct(copy.stat().st_mode)[-3:] == "600", "and the copy is readable only by you, like eval.json")
hidden = tmp / "hidden.csv"
hidden.write_text(f"ID,Answer,Sales contact\nSEC-01,AES-256 at rest and TLS 1.2 in transit.,demo key {SECRET}\n"
                  "SEC-02,SAML and OIDC with MFA.,\n", encoding="utf-8")
rc, o, e = kv("import", "fix", "Gamma", hidden)
names = sorted(x.name for x in (fix / "answers").iterdir())
ok(rc == 0 and names == ["gamma-2026-11-02-scrubbed.csv", "gamma-2026-11-02.xlsx"] and "1 piece(s) of text that "
   "looked like a credential were removed" in o, "a credential in a column that isn't read still keeps the vendor's "
   "file out", names)
prose = tmp / "prose.md"
prose.write_text(f"Our answers. The demo tenant's key is {SECRET}.\n\n| ID | Answer |\n|---|---|\n"
                 "| SEC-03 | SOC 2 Type II report, May 2026, covering all production. |\n", encoding="utf-8")
rc, o, e = kv("import", "fix", "Gamma", prose)
ok(rc == 0 and "the rows read are in answers/gamma-2026-11-02-scrubbed-2.csv, without the text that looked like a "
   "credential" in o and "outside the answers read; the vendor's file isn't kept" in o,
   "a credential in the prose around a Markdown table keeps the file out too", o + e)
dx = tmp / "intro.docx"
docx(dx, [["ID", "Answer"], ["SEC-04", "Scans on every build; critical fixes within 7 days, others within 30."]],
     intro=f"Demo key for the trial: {SECRET}")
rc, o, e = kv("import", "fix", "Gamma", dx)
ok(rc == 0 and "answers/gamma-2026-11-02-scrubbed-3.csv" in o and "the vendor's file isn't kept" in o,
   "and in a DOCX paragraph outside the table", o + e)
names = sorted(x.name for x in (fix / "answers").iterdir())
ok(not any(n.endswith((".md", ".docx")) for n in names) and all(
    SECRET.encode() not in (fix / "answers" / n).read_bytes() for n in names), "no copy holds it", names)
g = json.loads((fix / "eval.json").read_text(encoding="utf-8"))["answers"]["Gamma"]
ok(g["SEC-03"]["text"].startswith("SOC 2 Type II") and g["SEC-04"]["text"].startswith("Scans on every build"),
   "the answers themselves are read as usual", g)
p1, p2 = tmp / "p1.csv", tmp / "p2.csv"
p1.write_text("ID,Answer\nSEC-01,\"AES-256 at rest, TLS 1.2 in transit, keys in our HSM.\"\nRES-01,\n")
p2.write_text("ID,Answer\nSEC-01,\nRES-01,\"RTO 4 hours, RPO 15 minutes, tested each quarter.\"\n")
kv("import", "fix", "Acme", p1)
rc, o, e = kv("import", "fix", "Acme", p2)
ans_ = json.loads((fix / "eval.json").read_text(encoding="utf-8"))["answers"]["Acme"]
ok(ans_["SEC-01"]["text"].startswith("AES-256") and ans_["RES-01"]["text"].startswith("RTO 4 hours"),
   "a blank in a later file never erases an answer; a later answer fills a blank", ans_)
ok("1 blank answer(s) left the answer already there in place: SEC-01" in o, "and the import says so", o)
kv("score", "fix", "Acme", "SEC-02", "3")
v = {x["name"]: x for x in json.loads(kv("show", "fix", "--json")[1])["vendors"]}
ok(not any(f["id"] == "SEC-01" for f in v["Acme"]["fails"]), "so a must-have answered once isn't left unanswered",
   v["Acme"]["fails"])
desc = tmp / "desc.csv"
desc.write_text("Ref,Requirement,Compliance (Y/N),Description\n"
                "SEC-01,Encryption,Y,\"AES-256 at rest with customer-managed keys in a KMS; TLS 1.2 in transit.\"\n"
                "SEC-02,SSO,Y,\"SAML 2.0 and OIDC; MFA enforced; SCIM removes access within 5 minutes.\"\n")
rc, o, e = kv("import", "fix", "Beta", desc)
b = json.loads((fix / "eval.json").read_text(encoding="utf-8"))["answers"]["Beta"]
ok(b["SEC-01"]["text"] == "Y; AES-256 at rest with customer-managed keys in a KMS; TLS 1.2 in transit.",
   "a Description column next to a Y/N column is the vendor's answer", b.get("SEC-01"))
rc, o, e = kv("gaps", "fix", "Beta")
ok("bare yes or no" not in o, "so those answers aren't a bare yes", o)
both = tmp / "both.csv"
both.write_text("ID,Description,Response\nSEC-03,Assurance reports,\"SOC 2 Type II, May 2026, all production.\"\n")
kv("import", "fix", "Beta", both)
b = json.loads((fix / "eval.json").read_text(encoding="utf-8"))["answers"]["Beta"]
ok(b["SEC-03"]["text"] == "SOC 2 Type II, May 2026, all production.",
   "next to a Response column, a Description column describes the question and stays out of the answer", b["SEC-03"])

# ---- Kit's permission rules ------------------------------------------------------------------------------------------
sys.path.insert(0, str(SHARED))
import kit_setup  # noqa: E402
ok({"Bash(kit-vendors)", "Bash(kit-vendors list)", "Bash(kit-vendors show *)", "Bash(kit-vendors gaps *)",
    "Bash(kit-vendors due *)"} <= set(kit_setup.ALLOW)
   and not any(r == "Bash(kit-vendors *)" or r.startswith(("Bash(kit-vendors import", "Bash(kit-vendors score",
                                                            "Bash(kit-vendors report", "Bash(kit-vendors questions",
                                                            "Bash(kit-vendors new", "Bash(kit-vendors question "))
               for r in kit_setup.ALLOW),
   "the reading commands don't ask; the ones that change an evaluation or write a file you name do")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nkit-vendors tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
