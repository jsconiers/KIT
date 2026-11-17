"""kit_doctext: read the text of a document, block by block, with the section each block sits in. Python standard
library only (pdftotext is used for a PDF when it's installed).

Shared by kit-diagtext, kit-dedupe, and kit-facts.

  blocks(path)      -> [Block]   .docx (paragraphs, table cells, captions), .md / .txt, .pdf (needs pdftotext)
  sentences(text)   -> [str]
  words(text)       -> lowercase word tokens
  norm(text)        -> lowercase text with punctuation turned into single spaces (for phrase matching)
  has_phrase(hay, phrase) -> does the normalized phrase appear, on word boundaries, in the normalized text
  money(text)       -> [(amount as float, matched text, start)]   $347,840  $1.2M  $350k  USD 40,000
  counts(text)      -> [(number, noun, qualifier, matched text, start)]   "6 nodes", "three production sites"
  dates(text)       -> [(ISO-ish key, matched text, start)]
  project_dir(name) -> a project folder under <library root>/artifacts/, or a path to one
  project_of(path)  -> the project folder a file sits in, or None

A Block has .text, .kind ("heading", "para", "cell", "caption", "row"), .section (the nearest heading, with its
number when it has one, for example "3.2 Network design"), .where (section plus paragraph or table position, for
reports), and .cells for a table row.
"""
import datetime as dt
import os
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kit_daily as kd  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOC_SUFFIXES = {".docx", ".md", ".txt", ".pdf"}


class Block:
    __slots__ = ("text", "kind", "section", "where", "cells", "index")

    def __init__(self, text, kind, section, where, cells=None, index=0):
        self.text, self.kind, self.section, self.where = text, kind, section, where
        self.cells = cells or []
        self.index = index

    def __repr__(self):
        return f"Block({self.kind}, {self.where!r}, {self.text[:40]!r})"


# ---------------------------------------------------------------- reading
def _ptext(p):
    out = []
    for el in p.iter():
        if el.tag == W + "t" and el.text:
            out.append(el.text)
        elif el.tag == W + "tab":
            out.append(" ")
        elif el.tag in (W + "br", W + "cr"):
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _pstyle(p, styles):
    ps = p.find(f"{W}pPr/{W}pStyle")
    sid = ps.get(W + "val") if ps is not None else ""
    return styles.get(sid, sid) or ""


def _styles(z):
    out = {}
    if "word/styles.xml" in z.namelist():
        for s in ET.fromstring(z.read("word/styles.xml")).iter(W + "style"):
            n = s.find(W + "name")
            out[s.get(W + "styleId")] = n.get(W + "val") if n is not None else s.get(W + "styleId")
    return out


def _heading_level(style, text):
    s = (style or "").lower().replace(" ", "")
    m = re.match(r"heading(\d)", s)
    if m:
        return int(m.group(1))
    if s == "title":
        return 0
    return None


def _docx(path):
    z = zipfile.ZipFile(path)
    styles = _styles(z)
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    out, sec, n = [], "", 0
    for el in list(body) if body is not None else []:
        if el.tag == W + "p":
            text = _ptext(el)
            if not text:
                continue
            style = _pstyle(el, styles)
            lvl = _heading_level(style, text)
            n += 1
            if lvl is not None:
                sec = text
                out.append(Block(text, "heading", sec, sec))
                n = 0
            elif "caption" in style.lower() or re.match(r"(Figure|Fig\.|Table)\s+\d+", text):
                out.append(Block(text, "caption", sec, f"{sec or 'start'}, caption"))
            else:
                out.append(Block(text, "para", sec, f"{sec or 'start'}, paragraph {n}"))
        elif el.tag == W + "tbl":
            for r, tr in enumerate(el.iter(W + "tr"), 1):
                cells = [" ".join(_ptext(p) for p in tc.iter(W + "p")).strip() for tc in tr.findall(W + "tc")]
                if any(cells):
                    out.append(Block(" | ".join(cells), "row", sec, f"{sec or 'start'}, table row {r}", cells))
    return out


MD_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _text(text):
    out, sec, n, para = [], "", 0, []

    def flush():
        nonlocal n
        if para:
            t = " ".join(para).strip()
            n += 1
            kind = "caption" if re.match(r"\*{0,2}(Figure|Fig\.|Table)\s+\d+", t) else "para"
            out.append(Block(t, kind, sec, f"{sec or 'start'}, {'caption' if kind == 'caption' else f'paragraph {n}'}"))
            para.clear()
    row = 0
    for line in text.splitlines():
        s = line.strip()
        m = MD_HEAD.match(s)
        if m:
            flush()
            sec, n, row = m.group(2).strip(), 0, 0
            out.append(Block(sec, "heading", sec, sec))
        elif s.startswith("|") and s.endswith("|"):
            flush()
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            row += 1
            out.append(Block(" | ".join(cells), "row", sec, f"{sec or 'start'}, table row {row}", cells))
        elif not s:
            flush()
            row = 0
        elif re.match(r"^([-*+]|\d+[.)])\s+", s):
            flush()     # a list item is a block of its own
            para.append(re.sub(r"^([-*+]|\d+[.)])\s+", "", s))
        else:
            para.append(s)
    flush()
    return out


PDF_HEAD = re.compile(r"^(\d+(?:\.\d+){0,3})\.?\s+[A-Z][^.]{2,80}$")


def _pdf(path):
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("reading a PDF needs pdftotext (poppler), which isn't installed; give the .docx instead")
    r = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, text=True, timeout=120)
    lines = []
    for ln in r.stdout.splitlines():
        s = ln.strip()
        if PDF_HEAD.match(s):
            lines += ["", "# " + s, ""]
        else:
            lines.append(s)
    return _text("\n".join(lines))


def blocks(path):
    p = pathlib.Path(path)
    suf = p.suffix.lower()
    if suf == ".docx":
        out = _docx(p)
    elif suf == ".pdf":
        out = _pdf(p)
    else:
        out = _text(p.read_text(encoding="utf-8", errors="replace"))
    for i, b in enumerate(out):
        b.index = i
    return out


# ---------------------------------------------------------------- text helpers
ABBR = re.compile(r"\b(e\.g|i\.e|etc|vs|approx|Fig|No|Mr|Ms|Dr|Inc|Ltd)\.$", re.I)


def sentences(text):
    parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9\"'(\[])", text.strip())
    out = []
    for p in parts:
        if out and ABBR.search(out[-1]):
            out[-1] += " " + p
        elif p:
            out.append(p)
    return out


def words(text):
    return re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", (text or "").lower())


def norm(text):
    return " " + " ".join(re.findall(r"[a-z0-9]+", (text or "").lower())) + " "


def plural(w):
    if re.search(r"(s|x|ch|sh)$", w):
        return w + "es"
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    return w + "s"


def has_phrase(hay_norm, phrase):
    p = norm(phrase)
    return len(p.strip()) > 0 and p in hay_norm


STOP = set("""a an the and or of to in on for with by at from as is are was were be been being this that these those
it its into per via over under than then so not no any all each our we you they their there which who whom whose
will would shall should can could may might must also only more most less least new one""".split())

NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "a pair of": 2, "single": 1, "dual": 2}

MONEY = re.compile(r"(?:(?P<cur>\$|USD\s?|US\$\s?|£|€)\s?(?P<n>\d[\d,]*(?:\.\d+)?)\s?(?P<suf>[kKmM]\b|million\b|"
                   r"thousand\b|bn\b|billion\b)?|(?P<n2>\d[\d,]*(?:\.\d+)?)\s?(?P<suf2>[kKmM]\s|million\s|thousand\s)?"
                   r"\s?(?P<cur2>USD|dollars)\b)")
MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}


def money(text):
    out = []
    for m in MONEY.finditer(text or ""):
        n = m.group("n") or m.group("n2")
        suf = (m.group("suf") or m.group("suf2") or "").strip().lower()
        try:
            v = float(n.replace(",", "")) * MULT.get(suf, 1)
        except ValueError:
            continue
        out.append((v, m.group(0).strip(), m.start(), bool(suf)))
    return out


COUNT_NOUNS = {
    "node": "node", "nodes": "node", "server": "server", "servers": "server", "site": "site", "sites": "site",
    "region": "region", "regions": "region", "zone": "zone", "zones": "zone", "cluster": "cluster",
    "clusters": "cluster", "instance": "instance", "instances": "instance", "vm": "vm", "vms": "vm",
    "firewall": "firewall", "firewalls": "firewall", "appliance": "appliance", "appliances": "appliance",
    "database": "database", "databases": "database", "domain": "domain", "domains": "domain",
    "controller": "controller", "controllers": "controller", "broker": "broker", "brokers": "broker",
    "host": "host", "hosts": "host", "datacenter": "data center", "datacenters": "data center",
    "data-center": "data center", "data-centers": "data center", "switch": "switch", "switches": "switch",
    "router": "router", "routers": "router", "gateway": "gateway", "gateways": "gateway", "proxy": "proxy",
    "proxies": "proxy", "replica": "replica", "replicas": "replica", "shard": "shard", "shards": "shard",
    "subnet": "subnet", "subnets": "subnet", "environment": "environment", "environments": "environment",
    "tier": "tier", "tiers": "tier", "balancer": "load balancer", "balancers": "load balancer", "pod": "pod",
    "pods": "pod", "worker": "worker", "workers": "worker", "queue": "queue", "queues": "queue",
}
_NUM = r"(?P<num>\d{1,4}|" + "|".join(sorted((k for k in NUMWORDS), key=len, reverse=True)) + r")"
_NOUNS = "|".join(sorted((re.escape(k) for k in COUNT_NOUNS), key=len, reverse=True))
COUNT = re.compile(r"\b" + _NUM + r"(?:\s*[x×]\s*|\s+|-)(?P<q>(?:[A-Za-z][\w/-]*\s+){0,2}?)(?P<noun>data[ -]centers?|"
                   r"load[ -]balancers?|" + _NOUNS + r")\b", re.I)
NOT_COUNT_AFTER = re.compile(r"^\s*(per|each|in each|for each|a|an)\b", re.I)


def counts(text):
    out = []
    for m in COUNT.finditer(text or ""):
        noun = m.group("noun").lower().replace(" ", "-")
        noun = noun.replace("load-balancer", "balancer")
        key = COUNT_NOUNS.get(noun) or COUNT_NOUNS.get(noun.replace("data-", "data"))
        if not key:
            continue
        tail = text[m.end():m.end() + 14]
        if NOT_COUNT_AFTER.match(tail) or NOT_COUNT_AFTER.match(m.group("q") or ""):
            continue
        before = text[max(0, m.start() - 12):m.start()].lower()
        if re.search(r"(version|v|phase|wave|step|figure|table|section|§|q-|tier|level)\s*$", before):
            continue
        num = m.group("num").lower()
        n = NUMWORDS.get(num) if num in NUMWORDS else int(num)
        q = " ".join(w for w in words(m.group("q")) if w not in STOP)
        out.append((n, key, q, m.group(0), m.start()))
    return out


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                       "dec"], 1)}
DATE = re.compile(r"\b(?:(?P<iso>\d{4}-\d{2}-\d{2})|(?P<d>\d{1,2})[- ](?P<mon>[A-Z][a-z]{2,8})[- ,]+(?P<y>\d{4})|"
                  r"(?P<mon2>[A-Z][a-z]{2,8})\s+(?P<d2>\d{1,2}),?\s+(?P<y2>\d{4})|(?P<q>Q[1-4])\s+(?P<y3>\d{4})|"
                  r"(?P<mon3>[A-Z][a-z]{2,8})\s+(?P<y4>\d{4}))\b")


def dates(text):
    out = []
    for m in DATE.finditer(text or ""):
        g = m.groupdict()
        try:
            if g["iso"]:
                key = dt.date.fromisoformat(g["iso"]).isoformat()
            elif g["d"]:
                key = dt.date(int(g["y"]), MONTHS[g["mon"][:3].lower()], int(g["d"])).isoformat()
            elif g["d2"]:
                key = dt.date(int(g["y2"]), MONTHS[g["mon2"][:3].lower()], int(g["d2"])).isoformat()
            elif g["q"]:
                key = f"{g['y3']}-{g['q']}"
            else:
                key = f"{g['y4']}-{MONTHS[g['mon3'][:3].lower()]:02d}"
        except (KeyError, ValueError):
            continue
        out.append((key, m.group(0), m.start()))
    return out


# ---------------------------------------------------------------- projects
class Stop(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


def project_dir(name):
    p = pathlib.Path(os.path.expanduser(str(name)))
    if p.is_dir() and (p.is_absolute() or os.sep in str(name) or "/" in str(name)):
        return p.resolve()
    root = kd.library_root()
    if not root:
        raise Stop("no library root: set Library root in memory/context/library.md, or give the project's path")
    p = root / "artifacts" / str(name)
    if not p.is_dir():
        raise Stop(f"no project folder {p}")
    return p.resolve()


def project_of(path):
    p = pathlib.Path(path).resolve()
    root = kd.library_root()
    if root:
        art = (root / "artifacts").resolve() if (root / "artifacts").exists() else None
        if art:
            try:
                rel = p.relative_to(art)
                return art / rel.parts[0] if len(rel.parts) > 1 else None
            except ValueError:
                pass
    for parent in p.parents:
        if parent.name in ("drafts", "diagrams", "reviews"):
            return parent.parent
    return None


def find_doc(project, name):
    """A file in the project (its drafts/ folder is looked in too), or a path."""
    p = pathlib.Path(os.path.expanduser(str(name)))
    if p.is_file():
        return p.resolve()
    if project:
        for c in (project / name, project / "drafts" / name):
            if c.is_file():
                return c.resolve()
    raise Stop(f"no file {name}" + (f" in {project}" if project else ""))


def drafts(project):
    d = project / "drafts"
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in DOC_SUFFIXES
                  and not p.name.startswith(("~$", ".")))


def save_report(project, stem, kind, text):
    rev = project / "reviews"
    rev.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "document"
    out = rev / f"{safe}-{kind}-{kd.today().isoformat()}.md"
    out.write_text(text, encoding="utf-8")
    return out
