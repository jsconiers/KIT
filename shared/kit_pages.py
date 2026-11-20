"""kit_pages: page counts and page budgets for a project's documents. Python standard library only.

Shared by kit-pages and kit-review-loop (an over-budget document costs the "ready for ARB" score points).

  pages(path, render=False) -> (count or None, how)   how says where the number came from
  budgets(project)          -> [Budget]                from the project's facts.md (rows with the unit "pages")
  budget_for(path, budgets, default=None) -> Budget or None
  check(project, docs, max_pages=None, render=False) -> [dict], one per document
  over_budget(project)      -> [dict], the documents in drafts/ over their budget (for the score)

Page counts:
  .pdf   pdfinfo, else qpdf --show-npages, when either is installed; else the page tree's /Count read from the
         file itself (a PDF whose page tree is compressed may give no number: install poppler for those)
  .docx  docProps/app.xml <Pages>, the count Word stored when the file was last saved (so as of the last save
         in Word; a file written by a script may have none). With render=True and LibreOffice (soffice) already
         installed, the document is converted to a PDF in a temporary folder and that is counted instead.
         Nothing is installed, and Word is never driven.

Budgets live in the project's fact sheet (facts.md, the table kit-facts keeps), one row per budget, with the unit
"pages". The key names the document; the aliases, when there are any, are file-name patterns (* and ?), else the
key's words (without "pages") must all appear in the file name:

  | Pages executive | 4 | pages | *-executive* | the owner, 19-Nov | 19-Nov-2026 | Owner | |
  | Pages engineering | 6 | pages | *-engineering* | ... |
  | Pages main | 50 | pages | | ... |

The most specific match wins: the one with the most literal characters (pattern or words). `kit-facts set PROJECT "Pages
executive" 4 --unit pages --alias "*-executive*" --write` adds one.
"""
import fnmatch
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kit_doctext as dtx  # noqa: E402

PAGED = {".pdf", ".docx"}
FACTS = "facts.md"
FIELDS = ["key", "value", "unit", "aliases", "source", "agreed", "by", "superseded"]


class Budget:
    __slots__ = ("key", "max", "patterns", "words", "source")

    def __init__(self, key, max_pages, patterns, words, source="facts.md"):
        self.key, self.max, self.patterns, self.words, self.source = key, max_pages, patterns, words, source

    def matches(self, name):
        n = name.lower()
        if self.patterns:
            return any(fnmatch.fnmatch(n, p.lower()) for p in self.patterns)
        return bool(self.words) and all(w in n for w in self.words)

    def weight(self):
        """How specific the budget is: the literal characters in its longest pattern, or in its key's words."""
        if self.patterns:
            return max(len(p.replace("*", "").replace("?", "")) for p in self.patterns)
        return sum(map(len, self.words))


# ---------------------------------------------------------------- counting
def _run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def pdf_pages(path):
    exe = shutil.which("pdfinfo")
    if exe:
        r = _run([exe, str(path)])
        m = re.search(r"^Pages:\s+(\d+)", r.stdout if r else "", re.M)
        if m:
            return int(m.group(1)), "pdfinfo"
    exe = shutil.which("qpdf")
    if exe:
        r = _run([exe, "--show-npages", str(path)])
        if r and r.returncode == 0 and r.stdout.strip().isdigit():
            return int(r.stdout.strip()), "qpdf"
    try:
        data = pathlib.Path(path).read_bytes()
    except OSError:
        return None, "unreadable"
    counts = [int(m.group(1)) for m in re.finditer(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data, re.S)]
    counts += [int(m.group(1)) for m in re.finditer(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", data, re.S)]
    if counts:
        return max(counts), "the PDF's page tree"
    n = len(re.findall(rb"/Type\s*/Page\b(?!s)", data))
    return (n, "page objects in the PDF") if n else (None, "no page count found (compressed; install poppler)")


def docx_saved_pages(path):
    try:
        with zipfile.ZipFile(path) as z:
            if "docProps/app.xml" not in z.namelist():
                return None
            m = re.search(rb"<(?:\w+:)?Pages>(\d+)</", z.read("docProps/app.xml"))
            return int(m.group(1)) if m else None
    except (OSError, zipfile.BadZipFile, KeyError):
        return None


def soffice():
    for name in ("soffice", "libreoffice"):
        exe = shutil.which(name)
        if exe:
            return exe
    mac = pathlib.Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return str(mac) if mac.exists() else None


def docx_rendered_pages(path):
    exe = soffice()
    if not exe:
        return None
    with tempfile.TemporaryDirectory(prefix="kit-pages-") as d:
        r = _run([exe, "--headless", "--convert-to", "pdf", "--outdir", d, str(path)], timeout=300)
        pdf = pathlib.Path(d) / (pathlib.Path(path).stem + ".pdf")
        if not r or not pdf.exists():
            return None
        n, _ = pdf_pages(pdf)
        return n


def pages(path, render=False):
    p = pathlib.Path(path)
    suf = p.suffix.lower()
    if suf == ".pdf":
        return pdf_pages(p)
    if suf == ".docx":
        if render:
            n = docx_rendered_pages(p)
            if n is not None:
                return n, "rendered with LibreOffice"
        n = docx_saved_pages(p)
        if n is not None:
            return n, "as of the last save in Word" + (" (LibreOffice isn't installed, so not rendered)"
                                                        if render and not soffice() else "")
        return None, "Word stored no page count (save it in Word, or use --render with LibreOffice)"
    return None, "not a paged format"


def sections(path, top=5):
    """The largest sections of a .docx or text document by word count: [(section, words)]."""
    try:
        blocks = dtx.blocks(path)
    except Exception:  # noqa: BLE001 - a section list is a nice-to-have
        return []
    sizes = {}
    for b in blocks:
        if b.kind == "heading":
            continue
        key = b.section or "(before the first heading)"
        sizes[key] = sizes.get(key, 0) + len(b.text.split())
    return sorted(sizes.items(), key=lambda kv: -kv[1])[:top]


# ---------------------------------------------------------------- budgets
def budgets(project):
    f = pathlib.Path(project) / FACTS
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        cells += [""] * (len(FIELDS) - len(cells))
        r = dict(zip(FIELDS, cells))
        if r["unit"].lower() not in ("pages", "page"):
            continue
        m = re.match(r"\d+", r["value"].replace(",", ""))
        if not m:
            continue
        pats = [a.strip() for a in r["aliases"].split(";") if a.strip()]
        words = [w for w in re.findall(r"[a-z0-9]+", r["key"].lower()) if w not in ("pages", "page", "max", "budget")]
        out.append(Budget(r["key"], int(m.group(0)), pats, words, f"facts.md ({r['key']})"))
    return out


def budget_for(path, blist, default=None):
    name = pathlib.Path(path).name
    hits = [b for b in blist if b.matches(name)]
    if hits:
        return max(hits, key=lambda b: b.weight())
    return default


def check(project, docs, max_pages=None, render=False):
    blist = budgets(project) if project else []
    default = Budget("--max", max_pages, [], [], "--max") if max_pages else None
    out = []
    for d in docs:
        d = pathlib.Path(d)
        n, how = pages(d, render)
        b = budget_for(d, blist, default) if not max_pages else default
        status = "no budget" if not b else ("unknown" if n is None else ("over" if n > b.max else "within"))
        row = {"file": str(d), "name": d.name, "pages": n, "how": how, "budget": b.max if b else None,
               "budget_from": b.source if b else None, "status": status,
               "over_by": (n - b.max) if (b and n is not None and n > b.max) else 0}
        if status == "over":
            row["largest_sections"] = [{"section": s, "words": w} for s, w in sections(d)]
        out.append(row)
    return out


def paged_drafts(project):
    return [p for p in dtx.drafts(pathlib.Path(project)) if p.suffix.lower() in PAGED]


def over_budget(project):
    """Documents in drafts/ over their facts.md budget. Never renders (the score must stay quick)."""
    if not budgets(project):
        return []
    return [r for r in check(project, paged_drafts(project)) if r["status"] == "over"]
