#!/usr/bin/env python3
"""Tests for kit-pages and kit_pages, the page-budget check: budgets read from facts.md (unit "pages", patterns from
the aliases, else the key's words; the most specific wins), PDF counts from the page tree (no poppler on PATH) and
from pdfinfo when it's there, .docx counts from docProps/app.xml (as of the last save), a .docx with no stored count,
over and within, the largest sections of a long .docx as places to cut, --max, budgets, count, --json, --write,
exit codes, and kit-review-loop score taking 5 points per draft over budget. Synthetic library; nothing installed.

  python3 tests/test_pages.py
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
TOOL = REPO / "shared/bin/kit-pages"
LOOP = REPO / "shared/bin/kit-review-loop"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1500])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-pages-"))
KIT = TMP / "kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/auth-upgrade"
(KIT / "memory/context").mkdir(parents=True)
(PROJ / "drafts").mkdir(parents=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
EMPTY = TMP / "nobin"
EMPTY.mkdir()
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-20", PYTHONDONTWRITEBYTECODE="1", PATH=str(EMPTY))


def pdf(path, n):
    """A small uncompressed PDF with n pages."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {n} >>"]
    objs += ["<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"] * n
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    path.write_bytes(out)


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx(path, pages, sections):
    def para(t, style=None):
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>"
    body = "".join(para(h, "Heading1") + para(" ".join(["word"] * n)) for h, n in sections)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
        z.writestr("word/styles.xml",
                   f'<w:styles {W}><w:style w:styleId="Heading1"><w:name w:val="heading 1"/></w:style></w:styles>')
        if pages is not None:
            z.writestr("docProps/app.xml", '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
                       f'extended-properties"><Pages>{pages}</Pages><Words>900</Words></Properties>')


def run(*a, tool=TOOL, env=ENV):
    r = subprocess.run([sys.executable, str(tool), *map(str, a)], capture_output=True, text=True, env=env, timeout=60)
    return r.returncode, r.stdout, r.stderr


D = PROJ / "drafts"
docx(D / "NTLM IA-executive.docx", 5, [("1 Decision", 300), ("2 Cost", 120), ("3 Risks", 600)])
docx(D / "NTLM IA-engineering.docx", 6, [("1 Waves", 200)])
pdf(D / "NTLM IA.pdf", 47)
docx(D / "NTLM IA-with-references.docx", None, [("1 All", 50)])
(D / "notes.md").write_text("# not paged\n")

# No budgets yet: counts only, exit 0.
rc, out, err = run("check", "auth-upgrade", "--json")
rows = {r["name"]: r for r in json.loads(out)}
ok(rc == 0 and "no page budgets" in err, "no budgets: counts only, says how to add one", err)
ok(set(rows) == {"NTLM IA-executive.docx", "NTLM IA-engineering.docx", "NTLM IA.pdf", "NTLM IA-with-references.docx"},
   "only .docx and .pdf drafts are checked", sorted(rows))
ok(rows["NTLM IA.pdf"]["pages"] == 47 and rows["NTLM IA.pdf"]["how"] == "the PDF's page tree",
   "a PDF's count from its page tree, with no poppler", rows["NTLM IA.pdf"])
ok(rows["NTLM IA-executive.docx"]["pages"] == 5 and "last save" in rows["NTLM IA-executive.docx"]["how"],
   "a .docx count from app.xml, as of the last save", rows["NTLM IA-executive.docx"])
ok(rows["NTLM IA-with-references.docx"]["pages"] is None and rows["NTLM IA-with-references.docx"]["status"] == "no budget"
   and "no page count" in rows["NTLM IA-with-references.docx"]["how"], "a .docx with no stored count says so",
   rows["NTLM IA-with-references.docx"])

(PROJ / "facts.md").write_text(
    "# Fact sheet\n\n| Key | Value | Unit | Aliases | Source | Agreed | By (role) | Superseded |\n|---|---|---|---|---|---|---|---|\n"
    "| Phase 1 likely cost | 347,840 | USD | | estimate | 12-Nov-2026 | Sponsor | |\n"
    "| Pages executive | 4 | pages | *-executive* | review | 19-Nov-2026 | Owner | |\n"
    "| Pages engineering | 6 | pages | | review | 19-Nov-2026 | Owner | |\n"
    "| Pages main | 50 | pages | ntlm ia.pdf; ntlm ia.docx | review | 19-Nov-2026 | Owner | |\n"
    "| Pages any IA | 70 | pages | *ia* | review | 19-Nov-2026 | Owner | |\n")
rc, out, _ = run("budgets", "auth-upgrade", "--json")
b = {x["key"]: x for x in json.loads(out)}
ok(set(b) == {"Pages executive", "Pages engineering", "Pages main", "Pages any IA"} and b["Pages engineering"]["words"]
   == ["engineering"] and b["Pages executive"]["patterns"] == ["*-executive*"], "budgets: only rows with the unit pages", b)

rc, out, _ = run("check", "auth-upgrade", "--json")
rows = {r["name"]: r for r in json.loads(out)}
ex = rows["NTLM IA-executive.docx"]
ok(rc == 1 and ex["status"] == "over" and ex["budget"] == 4 and ex["over_by"] == 1, "executive 5 > 4: over, exit 1", ex)
ok([s["section"] for s in ex["largest_sections"]][:2] == ["3 Risks", "1 Decision"],
   "over budget: the largest sections first, as places to cut", ex.get("largest_sections"))
eng = rows["NTLM IA-engineering.docx"]
ok(eng["status"] == "within" and eng["budget"] == 6 and eng["budget_from"] == "facts.md (Pages engineering)",
   "engineering 6 of 6: within, matched by the key's words", eng)
ok(rows["NTLM IA.pdf"]["budget"] == 50 and rows["NTLM IA.pdf"]["status"] == "within",
   "a longer pattern wins over a shorter one", rows["NTLM IA.pdf"])
ok(rows["NTLM IA-with-references.docx"]["budget"] == 70 and rows["NTLM IA-with-references.docx"]["status"] == "unknown",
   "a budget with no count: unknown, not over", rows["NTLM IA-with-references.docx"])

rc, out, _ = run("check", "auth-upgrade", "--write")
ok("| NTLM IA-executive.docx | 5 | 4 | OVER by 1 |" in out and "- 3 Risks: 600 words" in out
   and list((PROJ / "reviews").glob("auth-upgrade-pages-2026-11-20.md")), "report, saved with --write", out)
rc, out, _ = run("check", "auth-upgrade", "NTLM IA-engineering.docx", "--max", "5", "--json")
r = json.loads(out)[0]
ok(rc == 1 and r["budget"] == 5 and r["budget_from"] == "--max", "--max sets one budget instead", r)
rc, out, _ = run("count", D / "NTLM IA.pdf", "--max", "50")
ok(rc == 0 and "| NTLM IA.pdf | 47 | 50 | within |" in out, "count: any file, outside a project", out)
rc, _, err = run("count", TMP / "missing.pdf")
ok(rc == 2 and "no file" in err, "count: a missing file is exit 2", err)
rc, _, err = run("check", "auth-upgrade", "--max", "0")
ok(rc == 2, "--max 0 is a usage problem", err)

# pdfinfo, when it's on PATH, is used first.
FAKE = TMP / "fakebin"
FAKE.mkdir()
(FAKE / "pdfinfo").write_text("#!/bin/sh\necho 'Title: x'\necho 'Pages:          12'\n")
(FAKE / "pdfinfo").chmod(0o755)
rc, out, _ = run("count", D / "NTLM IA.pdf", "--json", env=dict(ENV, PATH=f"{FAKE}:/usr/bin:/bin"))
r = json.loads(out)[0]
ok(r["pages"] == 12 and r["how"] == "pdfinfo", "pdfinfo is used when installed", r)

# kit-review-loop score: 5 points off per draft over budget.
rc, out, err = run("score", "auth-upgrade", "--json", tool=LOOP)
s = json.loads(out)
ok(rc == 0 and s["pages_over"] == [{"name": "NTLM IA-executive.docx", "pages": 5, "budget": 4, "over_by": 1}]
   and s["score"] == 100 - 4 * 15 - 5, "score: -5 for the draft over its page budget", s)
ok("over the page budget: NTLM IA-executive.docx (5/4)" in s["headline"], "the headline says why", s["headline"])
rc, out, _ = run("score", "auth-upgrade", tool=LOOP)
ok("NTLM IA-executive.docx: 5 pages, budget 4 (-5" in out, "score's text names it", out)
(PROJ / "facts.md").write_text("| Key | Value | Unit |\n|---|---|---|\n")
rc, out, _ = run("score", "auth-upgrade", "--json", tool=LOOP)
s = json.loads(out)
ok(s["pages_over"] == [] and s["score"] == 40, "no budgets: no deduction", s)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
