#!/usr/bin/env python3
"""kit-author: books and the dated launch checklist, the series bible and its consistency check (spellings, facts,
ages, unknown names), royalties from a KDP-style .xlsx (shared strings, date serials, a sheet per format) and an
IngramSpark-style .csv, replacement on re-import, the dashboard page, your own launch checklist, the words that
are never names, and the brief. Synthetic data only.

Run: python3 tests/test_author.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent                                   # the repo, or the installed copy (.install)
fails = []


def check(cond, what, extra=""):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)
        if extra:
            print("     " + str(extra)[:1500].replace("\n", "\n     "))


tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
for d in (".install/shared/bin", ".install/shared/morning", ".install/logs"):
    (kit / d).mkdir(parents=True, exist_ok=True)
shutil.copy(ROOT / "shared/bin/kit-author", kit / ".install/shared/bin/kit-author")
shutil.copy(ROOT / "shared/kit_doctext.py", kit / ".install/shared/kit_doctext.py")
TOOL = kit / ".install/shared/bin/kit-author"
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-12-10", PYTHONUTF8="1")


def run(*args, **kw):
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=dict(env, **kw),
                       timeout=120, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------- books and the launch checklist
rc, o, e = run("book", "add", "The Lamp and the Road", "--series", "Lamp", "--launch", "2027-01-19")
check(rc == 0 and "Added The Lamp and the Road (Lamp), launching Tue 19-Jan-2027" in o, "book add", o + e)
run("book", "add", "The Lamp and the Road: A 40-Day Devotional", "--series", "Lamp", "--launch", "2027-01-19")
rc, o, e = run("launch", "The Lamp and the Road")
check(rc == 0 and o.startswith("Launch: The Lamp and the Road, Tue 19-Jan-2027"), "the exact title wins over another "
      "that starts the same", o + e)
rc, o, e = run("launch", "The Lamp")
check(rc == 1 and "fits more than one book" in e, "a start that fits two books asks which", e)
rc, o, e = run("launch", "The Lamp and the Road")
check("  1. [!] Final manuscript locked: every edit in (Wed 21-Oct-2026, -90 days)" in o
      and "Launch day: live in every format" in o and "(Tue 19-Jan-2027, +0 days)" in o, "the checklist, dated back", o + e)
rc, o, e = run("launch", "The Lamp and the Road", "done", "1", "2")
check(rc == 0 and "Done: Final manuscript locked" in o, "launch done N", o + e)
rc, o, e = run("launch", "The Lamp and the Road", "add", "Book signing at the church", "--offset", "10")
check(rc == 0 and "(+10 days)" in o, "launch add", o + e)
rc, o, e = run("brief")
check(o.startswith("Author (personal)\n") and 'Overdue for The Lamp and the Road: 4 items, the oldest "ISBNs assigned' in o
      and "Final manuscript locked" not in o, "brief: overdue items folded into a line, the done ones gone", o)
check("Cover final" not in o, "brief: items more than 30 days late drop off", o)
rc, o, e = run("brief", KIT_TODAY="2027-01-17")
check("Due Tue 19-Jan-2027 for The Lamp and the Road: Launch day: live in every format" in o
      and 'Overdue for The Lamp and the Road: 8 items, the oldest "Proof copy ordered"' in o, "brief: due in the next three days first; many "
      "overdue items in one line", o)
rc, o, e = run("brief", "weekly")
check("Launching Tue 19-Jan-2027: The Lamp and the Road (checklist 2 of 20)" in o, "weekly: launches in 60 days", o)
rc, o, e = run("books")
check("The Lamp and the Road [Lamp]: production, launch Tue 19-Jan-2027; launch checklist 2 of 20" in o, "books", o)

# ---------------------------------------------------------------- the series bible and the check
run("bible", "Lamp", "add", "Eliah", "--fact", "eyes=brown", "--fact", "father=Joram", "--age", "book1=17")
run("bible", "Lamp", "add", "Mirah", "--fact", "town=Bethel")
run("bible", "Lamp", "add", "Bethel", "--kind", "place")
rc, o, e = run("bible", "Lamp")
check("Characters:" in o and "Eliah: eyes: brown; father: Joram; age 17 in book1" in o and "Places:" in o, "bible show", o)
(tmp / "book1.md").write_text("""Eliah was seventeen years old when the lamp went out.

Eliah's green eyes searched the road. Eliah's father, Jorem, waited at the gate.

Elliah walked on. Elliah did not look back, and the Tabor road was long.

Mirah came out of Bethel. Tabor stood above them. On the road to Tabor they rested.

At the well Eliah, now nineteen, drank deeply.
""")
(tmp / "book2.md").write_text("""The sixteen-year-old Eliah lit the lamp again.

Mirah's town, Bethel, was quiet under Tabor.
""")
rc, o, e = run("bible", "Lamp", "check", str(tmp / "book1.md"), str(tmp / "book2.md"), "--write")
check(rc == 0 and '"Elliah" (2 times, first in book1.md, paragraph 3) looks like Eliah' in o, "check: a close spelling", o + e)
check("Eliah's eyes: the bible says brown; book1.md, paragraph 2 says green" in o, "check: a fact the text contradicts", o)
check("Eliah's father: the bible says Joram; book1.md, paragraph 2 says Jorem" in o, "check: a relation that differs", o)
check("Eliah in book1.md: the text gives 17, 19" in o, "check: two ages in one book", o)
check("Eliah: younger in a later manuscript (17 then 16" in o, "check: younger in a later book", o)
check("- Tabor (3 times)" in o, "check: names the bible doesn't have", o)
check("Mirah's town" not in o.split("## Facts")[1].split("##")[0] or "says Bethel" not in o, "a fact that agrees isn't flagged", o)
check((kit / f"author/bible/lamp/check-2026-12-10.md").exists(), "--write saves the report")
(kit / ".install/shared/morning/config").write_text('AUTHOR_COMMON_WORDS="Tabor, Gate"\n')
rc, o, e = run("bible", "Lamp", "check", str(tmp / "book1.md"), str(tmp / "book2.md"))
check(rc == 0 and "Tabor (" not in o and "Elliah" in o, "AUTHOR_COMMON_WORDS: a word your books use isn't a name", o + e)
(kit / ".install/shared/morning/config").write_text("")
rc, o, e = run("bible", "Lamp", "check")
check(rc == 0 and "Consistency check: Lamp" in o, "check again: the files are remembered", o + e)

# ---------------------------------------------------------------- royalties
def xlsx(path, sheets):
    """A workbook like KDP's: shared strings, numbers, and a date serial."""
    strings, sheet_xml = [], []

    def sidx(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)
    for name, rows in sheets:
        out = []
        for r, row in enumerate(rows, 1):
            cells = []
            for c, v in enumerate(row):
                ref = f"{chr(65 + c)}{r}"
                if isinstance(v, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{v}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="s"><v>{sidx(v)}</v></c>')
            out.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append((name, f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                                f'2006/main"><sheetData>{"".join(out)}</sheetData></worksheet>'))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
                   'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets>' + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in
                                        enumerate(sheet_xml, 1)) + '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships">' + "".join(
                       f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheet_xml) + 1))
                   + '</Relationships>')
        for i, (_, x) in enumerate(sheet_xml, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", x)
        z.writestr("xl/sharedStrings.xml", '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
                   'spreadsheetml/2006/main">' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")


HEAD = ["Royalty Date", "Title", "Author Name", "ASIN/ISBN", "Marketplace", "Royalty Type", "Transaction Type",
        "Units Sold", "Units Refunded", "Net Units Sold", "Avg. List Price", "Royalty", "Currency"]
xlsx(tmp / "kdp.xlsx", [
    ("eBook Royalty", [["Sales Period: October 2026"], HEAD,
                       [46296, "The Lamp and the Road", "Author", "B0X", "Amazon.com", "70%", "Standard", 12, 1, 11, 4.99, 38.42, "USD"],
                       [46297, "The Lamp and the Road", "Author", "B0X", "Amazon.co.uk", "70%", "Standard", 3, 0, 3, 3.99, 7.12, "GBP"]]),
    ("Paperback Royalty", [HEAD,
                           [46300, "The Lamp and the Road", "Author", "979", "Amazon.com", "60%", "Standard", 20, 0, 20, 14.99, 61.30, "USD"]]),
    # The same sales again in a combined tab and an orders tab: never counted twice.
    ("Combined Sales", [HEAD,
                        [46296, "The Lamp and the Road", "Author", "B0X", "Amazon.com", "70%", "Standard", 12, 1, 11, 4.99, 38.42, "USD"],
                        [46300, "The Lamp and the Road", "Author", "979", "Amazon.com", "60%", "Standard", 20, 0, 20, 14.99, 61.30, "USD"]]),
    ("eBook Orders", [["Order Date", "Title", "ASIN", "Marketplace", "Net Units Sold"],
                      [46296, "The Lamp and the Road", "B0X", "Amazon.com", 11]])])
rc, o, e = run("royalties", "import", str(tmp / "kdp.xlsx"))
led = json.loads((kit / "author/royalties/ledger.json").read_text()) if (kit / "author/royalties/ledger.json").exists() else {}
check(rc == 0 and "Imported kdp.xlsx (kdp): 3 total(s) for 2026-10; $99.72 in USD." in o, "import a KDP workbook", o + e)
check((oct((kit / "author/royalties/ledger.json").stat().st_mode & 0o777) == "0o600"
       and oct((kit / "author/royalties").stat().st_mode & 0o777) == "0o700") if os.name == "posix" else True,
      "the ledger is owner-only")
check({(r["format"], r["currency"]) for r in led.get("rows", [])} == {("ebook", "USD"), ("ebook", "GBP"), ("paperback", "USD")}
      and next(r for r in led["rows"] if r["format"] == "ebook" and r["currency"] == "USD")["units"] == 11,
      "formats from the sheet names; net units", led)
check("Author Name" not in json.dumps(led) and "B0X" not in json.dumps(led), "totals only: no other columns kept")
rc, o, e = run("royalties", "import", str(tmp / "kdp.xlsx"))
check(rc == 1 and "imported already" in e, "the same file twice is refused", e)
(tmp / "ingram.csv").write_text("Period,Title,ISBN,Format,Market,Net Qty,Publisher Compensation,Currency\n"
                                "2026-11,The Lamp and the Road,979,Paperback,US,5,22.50,USD\n"
                                "2026-11,The Lamp and the Road,979,Hardcover,US,2,(4.10),USD\n")
rc, o, e = run("royalties", "import", str(tmp / "ingram.csv"))
check(rc == 0 and "(ingramspark)" in o and "$18.40 in USD" in o, "import an IngramSpark CSV (a return in brackets)", o + e)
xlsx(tmp / "kdp2.xlsx", [("eBook Royalty", [HEAD, [46296, "The Lamp and the Road", "A", "B0X", "Amazon.com", "70%",
                                                    "Standard", 14, 0, 14, 4.99, 48.90, "USD"]])])
rc, o, e = run("royalties", "import", str(tmp / "kdp2.xlsx"))
check(rc == 0 and "replaced 3 earlier total(s) for those months" in o, "a later KDP report for October replaces it", o + e)
rc, o, e = run("royalties", "--html")
check(rc == 0 and "Royalties, 2026: $67.30 on 21 units (in USD; no other currencies)" in o
      and "By month: Oct $48.90 (14); Nov $18.40 (7)" in o, "the dashboard's totals", o + e)
page = kit / "author/royalties/dashboard-2026.html"
check(page.exists() and "<svg" in page.read_text() and "$67.30" in page.read_text(), "--html: a page with a chart")
rc, o, e = run("royalties", "--year", "2025")
check("No royalties for 2025" in o, "a year with nothing", o)
rc, o, e = run("brief", "weekly")
check("Royalties, November: $18.40 (kit-author royalties)" in o, "weekly: last month's royalties", o)
rc, o, e = run()
check("Royalties, November: $18.40 on 7 units" in o and "Launch Tue 19-Jan-2027: The Lamp and the Road" in o, "overview", o)
check((kit / "author/royalties/.gitignore").read_text() == "*\n", "the royalties folder keeps itself out of history")
# Your own launch checklist replaces the usual one; a book's own items stay on top.
(kit / "author/launch-checklist.json").write_text(json.dumps([[-10, "Order the banners"],
                                                              {"offset": 0, "item": "Launch party"}, ["bad"], [5, ""]]))
rc, o, e = run("launch", "The Lamp and the Road")
check(rc == 0 and "Order the banners" in o and "Launch party" in o and "Book signing at the church" in o
      and "Proof copy ordered" not in o, "author/launch-checklist.json: your checklist, the book's items on top", o + e)
(kit / "author/launch-checklist.json").write_text("not json")
rc, o, e = run("launch", "The Lamp and the Road")
check(rc == 0 and "Proof copy ordered" in o, "an unreadable checklist file: the usual checklist", o + e)
(tmp / "junk.csv").write_text("a,b\n1,2\n")
rc, o, e = run("royalties", "import", str(tmp / "junk.csv"))
check(rc == 1 and "no royalty rows" in e, "a file that isn't a report is refused", e)

shutil.rmtree(tmp)
print(f"\n{'FAILED' if fails else 'passed'}: kit-author, {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
