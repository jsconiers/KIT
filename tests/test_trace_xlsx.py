#!/usr/bin/env python3
"""Tests for `kit-trace --xlsx` and kit_xlsx: the traceability matrix as an Excel workbook for reviewers, from the
synthetic project in tests/fixtures/trace (the same one tests/test_trace.sh uses). It reads the workbook back as
XML: the sheets, the header row frozen with a filter, a row per requirement in the IA's order with its GDS section,
test cases, and change steps, gaps shaded, the reviewer columns empty, and the gaps, orphans, and summary sheets.
Also: the default file name, refusing to overwrite without --force, a file name that isn't .xlsx, and text XML
can't hold. No Excel or openpyxl needed (openpyxl, when present, also opens it).

  python3 tests/test_trace_xlsx.py
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-trace"
FIX = REPO / "tests/fixtures/trace/project-alpha"
sys.path.insert(0, str(REPO / "shared"))
import kit_xlsx  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


def read_book(path):
    """{sheet name: (rows as lists of text, {row number: style}, sheet xml root)}."""
    z = zipfile.ZipFile(path)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    out = {}
    for i, sh in enumerate(wb.find("m:sheets", NS), 1):
        root = ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
        rows, styles = [], {}
        for r in root.find("m:sheetData", NS):
            cells = []
            for c in r:
                t = c.find("m:is/m:t", NS)
                v = c.find("m:v", NS)
                cells.append(t.text if t is not None else (v.text if v is not None else ""))
                styles[int(r.get("r"))] = c.get("s")
            rows.append(cells)
        out[sh.get("name")] = (rows, styles, root)
    return out


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-trace-xlsx-"))
PROJ = TMP / "project-alpha"
shutil.copytree(FIX, PROJ)
(TMP / "kit/memory/context").mkdir(parents=True)
ENV = dict(os.environ, KIT_DIR=str(TMP / "kit"), PYTHONDONTWRITEBYTECODE="1")


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=120)
    return r.returncode, r.stdout, r.stderr


rc, out, err = run(PROJ, "--xlsx")
books = list((PROJ / "traceability").glob("trace-*.xlsx"))
ok(rc == 0 and len(books) == 1 and "8 requirements" in out, "--xlsx writes PROJECT/traceability/trace-<date>.xlsx",
   out + err)
book = read_book(books[0]) if books else {}
ok(list(book)[:3] == ["Matrix", "Gaps", "Orphan test cases"] and "Summary" in book and "IDs not in the IA" in book,
   "sheets: Matrix, Gaps, Orphan test cases, IDs not in the IA, Summary", list(book))
rows, styles, root = book["Matrix"]
ok(rows[0] == ["Requirement", "Statement", "IA location", "GDS section", "Test cases", "Change steps",
               "POC / verdict", "Gaps", "Reviewer status", "Reviewer notes"],
   "the Matrix reads left to right: IA requirement, GDS section, test cases, change steps", rows[0])
pane = root.find("m:sheetViews/m:sheetView/m:pane", NS)
ok(pane is not None and pane.get("state") == "frozen" and pane.get("ySplit") == "1"
   and root.find("m:autoFilter", NS) is not None, "the header row stays put and every column has a filter")
ok(styles[1] == "1", "the header row is bold and shaded")
byid = {r[0]: r for r in rows[1:]}
ok(len(rows) == 9 and [r[0] for r in rows[1:]][0] == "REQ-001", "a row per IA requirement, in the IA's order",
   [r[0] for r in rows])
ok(byid["REQ-001"][3] == "4.1 Authentication" and byid["REQ-001"][4] == "TC-01" and "POC-0007" in byid["REQ-001"][6],
   "a requirement's GDS section, test case, and POC", byid["REQ-001"])
ok("6.2 Backup (inferred)" in byid["NFR-2"][3], "inferred links are marked", byid["NFR-2"])
ok("5.2 Dashboards (cited IA 3.2)" in byid["NFR-1"][3], "cited links say how", byid["NFR-1"])
gap_rows = [i for i, r in enumerate(rows[1:], start=2) if r[7] != "none"]
ok(gap_rows and all(styles[i] == "3" for i in gap_rows) and all(styles[i] == "2" for i in range(2, len(rows) + 1)
                                                                  if i not in gap_rows),
   "rows with a gap are shaded, the rest aren't", (gap_rows, styles))
ok(all(len(r) == 10 and not r[8] and not r[9] for r in rows[1:]), "Reviewer status and notes are empty for reviewers")
grows = book["Gaps"][0]
ok(any(r[0] == "REQ-004" and r[1] == "not addressed in the GDS" for r in grows), "the Gaps sheet", grows)
ok(any(r[0] == "TC-04" for r in book["Orphan test cases"][0]), "the orphan test cases sheet")
summ = {r[0]: r[1] for r in book["Summary"][0][1:]}
ok(summ.get("Requirements in the IA") == "8" and summ.get("Impact assessment") == "ia-v2.md"
   and "internal" in summ.get("Classification", ""), "the Summary sheet", summ)

rc, out, err = run(PROJ, "--xlsx")
ok(rc != 0 and "--force" in err, "it won't replace the workbook without --force", err)
ok(run(PROJ, "--xlsx", "--force")[0] == 0, "--force replaces it")
rc, out, err = run(PROJ, "--xlsx", TMP / "out.xlsx")
ok(rc == 0 and (TMP / "out.xlsx").is_file(), "--xlsx FILE writes where it's told", err)
rc, out, err = run(PROJ, "--xlsx", TMP / "out.csv")
ok(rc != 0 and ".xlsx" in err, "a name that doesn't end in .xlsx is refused", err)

# kit_xlsx on its own: control characters dropped, numbers as numbers, long cells cut, unique sheet names.
p = kit_xlsx.write(TMP / "t.xlsx", [kit_xlsx.Sheet("A/B", ["x", "n"], [["bad\x01text & <tags>", 3], ["y" * 40000, 1.5]]),
                                    kit_xlsx.Sheet("a-b", ["x"], [])])
b = read_book(p)
ok(list(b) == ["A-B", "a-b 2"], "sheet names are cleaned and kept unique", list(b))
r = b["A-B"][0]
ok(r[1] == ["badtext & <tags>", "3"] and len(r[2][0]) == kit_xlsx.MAX_CELL and r[2][1] == "1.5",
   "text XML can't hold is dropped; numbers stay numbers; long cells are cut to fit", r[1])
try:
    import openpyxl  # noqa: F401
    wb = openpyxl.load_workbook(books[0])
    ok(wb.sheetnames[0] == "Matrix" and wb["Matrix"]["A2"].value == "REQ-001", "openpyxl opens the workbook")
except ImportError:
    print("skip openpyxl isn't installed")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-trace --xlsx tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
