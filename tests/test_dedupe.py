#!/usr/bin/env python3
"""Tests for kit-dedupe, the repetition and consistency checker: a statement repeated word for word and nearly in
other sections (keep in the first, cut the rest), a repeat in the summary left alone unless word for word, costs,
counts, and dates that disagree, a low-likely-high range not flagged, a Q-ID open in one place and closed in
another, a Q-ID defined twice with different text, two documents read as one, a clean document, --write, --json,
exit codes, and the false alarms seen on real IAs (thousands separators, product years, date ranges, reference
lists). Synthetic documents built in a temporary folder; nothing is sent.

  python3 tests/test_dedupe.py
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
TOOL = REPO / "shared/bin/kit-dedupe"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1500])


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def docx(path, items):
    body = []
    for kind, val in items:
        if kind == "table":
            rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{esc(c)}</w:t></w:r></w:p></w:tc>" for c in r)
                           + "</w:tr>" for r in val)
            body.append(f"<w:tbl>{rows}</w:tbl>")
        else:
            ppr = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if kind == "h1" else ""
            body.append(f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{esc(val)}</w:t></w:r></w:p>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>{"".join(body)}</w:body>'
                   '</w:document>')
        z.writestr("word/styles.xml", f'<?xml version="1.0"?><w:styles {W}><w:style w:styleId="Heading1">'
                   '<w:name w:val="heading 1"/></w:style></w:styles>')


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-dedupe-"))
KIT = TMP / "kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/auth-upgrade"
(KIT / "memory/context").mkdir(parents=True)
(PROJ / "drafts").mkdir(parents=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-17", PYTHONDONTWRITEBYTECODE="1")


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


REPEAT = "Each wave is sized so that a failed change can be rolled back within the agreed maintenance window."
DOC = PROJ / "drafts/Auth upgrade DOC-210 v0.5.docx"
docx(DOC, [
    ("h1", "1 Executive summary"),
    ("p", "Each wave is sized so a failed change can be rolled back within the agreed window, as section 4 explains."),
    ("p", "The phase 1 likely cost is $347,840 including support."),
    ("h1", "3 Approach"),
    ("p", REPEAT + " The pilot covers 12 production domains."),
    ("p", "The phase 1 estimate is low $300,000, likely $347,840, high $410,000."),
    ("p", "Target decision date is 15-Jan-2027."),
    ("h1", "4 Rollback"),
    ("p", REPEAT),
    ("p", "Overall, every wave is sized so that a failed change can be rolled back within the agreed maintenance "
          "window period."),
    ("h1", "6 Costs"),
    ("p", "The phase 1 likely cost is $345,000 including support."),
    ("p", "The migration then reaches 14 production domains in total."),
    ("p", "The target decision date moves to 12-Feb-2027 at the latest."),
    ("h1", "8 Open questions"),
    ("table", [["ID", "Question", "Status"], ["Q-047", "Which legacy domains are still in use?", "Open"],
               ["Q-048", "Which trusts does the partner forest need?", "Answered"]]),
    ("p", "Q-047 was closed at the November review."),
    ("p", "Q-048: Which trusts does the partner forest need today?"),
    ("h1", "9 Appendix"),
    ("table", [["ID", "Question"], ["Q-048", "Who owns the replacement certificate authority for all domains?"]]),
])

rc, out, err = run(DOC, "--json")
ok(rc == 1, "findings: exit 1", out + err)
d = json.loads(out)
reps = d["repeats"]
ok(len(reps) == 1, "one group of repeated statements", reps)
g = reps[0] if reps else {}
ok(g and g["keep"]["section"] == "§3 Approach" and {c["section"] for c in g["cut"]} == {"§4 Rollback"}
   and len(g["cut"]) == 2, "keep the first full statement (§3), cut the copy and the near copy in §4", g)
ok(g and [s["section"] for s in g.get("summary", [])] in ([], ["§1 Executive summary"]) and
   all("summary" not in c["section"].lower() for c in g["cut"]), "the summary's paraphrase is never proposed for a cut", g)
costs = [f for f in d["figures"] if f["kind"] == "cost"]
vals = sorted(v["value"] for f in costs for v in f["values"])
ok(len(costs) == 1 and vals == ["$345,000", "$347,840"], "the phase 1 likely cost given as two amounts is flagged once; "
   "the low-likely-high range isn't", costs)
cnt = [f for f in d["figures"] if f["kind"] == "count"]
ok(len(cnt) == 1 and sorted(v["value"] for v in cnt[0]["values"]) == ["12", "14"] and "production" in cnt[0]["subject"],
   "12 and 14 production domains disagree", cnt)
dts = [f for f in d["figures"] if f["kind"] == "date"]
ok(len(dts) == 1 and sorted(v["value"] for v in dts[0]["values"]) == ["2027-01-15", "2027-02-12"],
   "the target decision date on two dates", dts)
idf = {(f["id"], f["problem"].split(",")[0]) for f in d["ids"]}
ok(("Q-047", "open in one place") in idf, "Q-047 open in the table, closed in a paragraph", d["ids"])
q48 = [f for f in d["ids"] if f["id"] == "Q-048" and f["problem"].startswith("defined")]
ok(q48 and len(q48[0]["places"]) == 2 and any("certificate" in p["quote"] for p in q48[0]["places"]),
   "Q-048 defined twice with different text (a near copy of the question isn't a second definition)", q48)
ok(not any(f["id"] == "Q-048" and f["problem"].startswith("open") for f in d["ids"]), "Q-048 answered only: no status clash")

rc, out, _ = run(DOC)
ok("Keep in §3 Approach, cut in §4 Rollback" in out and "## Figures that disagree" in out and "$345,000" in out,
   "the markdown report proposes the cut and lists the figures", out)
rc, out, err = run(DOC, "--write")
saved = list((PROJ / "reviews").glob("*-dedupe-2026-11-17.md"))
ok(saved and "Repetition and consistency check" in saved[0].read_text() and "Saved:" in out,
   "--write saves the report in the project's reviews/ folder", out + err)

# Two documents read as one: the repeat crosses them.
A = TMP / "a.md"
B = TMP / "b.md"
A.write_text("# 2 Scope\n\n" + REPEAT + "\n")
B.write_text("# 5 Design\n\n" + REPEAT + "\n")
rc, out, err = run(A, B, "--json")
r = json.loads(out)["repeats"]
ok(r and r[0]["keep"]["section"] == "a.md: §2 Scope" and r[0]["cut"][0]["section"] == "b.md: §5 Design",
   "two documents: the sections carry the file name", out + err)
ok(run(A, B, "--write")[0] == 2, "--write with no project to save in: exit 2")

CLEAN = TMP / "clean.md"
CLEAN.write_text("# 1 Scope\n\nThe service moves to the new cluster in one weekend with a tested rollback plan.\n\n"
                 "# 2 Cost\n\nThe total cost is $120,000 for the first year of support.\n")
rc, out, _ = run(CLEAN, "--json")
d = json.loads(out)
ok(rc == 0 and not (d["repeats"] or d["figures"] or d["ids"]), "a clean document: nothing, exit 0", out)
ok(run(TMP / "nope.md")[0] == 2, "a file that isn't there: exit 2")
ok(run(CLEAN, "--threshold", "2")[0] == 2, "a threshold outside 0-1: exit 2")
rc, out, _ = run(DOC, "--threshold", "0.95", "--json")
ok(len(json.loads(out)["repeats"]) == 1 and len(json.loads(out)["repeats"][0]["cut"]) == 1,
   "a high threshold keeps only the word-for-word copy", out[:600])

# False alarms seen on real IAs (17-Nov-2026): thousands separators, product years, ranges, reference lists.
FA = TMP / "false-alarms.md"
FA.write_text(
    "# 2 Scope\n\nThe CMDB lists at least 51 operational Server 2016 servers in the estate today.\n\n"
    "# 3 Sizing\n\nThe CMDB holds 4,292 operational Windows servers across every production domain.\n\n"
    "# 4 Server\n\nAt least 51 operational Server 2016 servers still need an upgrade path before phase 3.\n\n"
    "# 5 Plan\n\nApproved end (30-Jun-2026) and due date (30-Aug-2026) have both passed for the demand.\n\n"
    "The target completion is 31-Jan-2027, set 26-May-2026 by the steering group.\n\n"
    "# 9 References\n\n[N1] Author's notes from the review, 08-Apr-2024 to 13-Oct-2026.\n\n"
    "[R2] Red-team review of the first draft, 03-Nov-2026.\n\n[D2] Decisions on the review, 12-Nov-2026.\n")
rc, out, err = run(FA, "--json")
d = json.loads(out)
ok(not d["figures"], "no false alarms: 4,292 isn't 292, Server 2016 isn't a count, a date range or a pair in one "
   "sentence isn't a disagreement, and a reference list's dates are left out", d["figures"])
FB = TMP / "real-count.md"
FB.write_text("# 2 Scope\n\nThe CMDB holds 4,292 operational Windows servers in every production domain.\n\n"
              "# 3 Sizing\n\nThe CMDB holds 4,290 operational Windows servers in every production domain.\n")
rc, out, err = run(FB, "--json")
fig = json.loads(out)["figures"]
ok(len(fig) == 1 and sorted(v["value"] for v in fig[0]["values"]) == ["4,290", "4,292"],
   "counts with a thousands separator still disagree when they really do", fig)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-dedupe tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
