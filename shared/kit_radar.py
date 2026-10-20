"""kit_radar: shared helpers for the future tech planner's tools (kit-lifecycle, kit-roadmap).

Finds the library root and the radar folder from Kit's setup files, and reads the markdown tables
the planner keeps (RADAR.md, tech-debt.md, poc/INDEX.md). Read-only; nothing here reaches outside
this computer.
"""
import datetime as dt
import os
import pathlib
import re

KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
CONTEXT = KIT / "memory/context"


def expand(p):
    return pathlib.Path(os.path.expanduser(p.strip().strip("`")))


def library_root():
    """The library root that memory/context/library.md names, or None."""
    f = CONTEXT / "library.md"
    if not f.exists():
        return None
    m = re.search(r"\*\*Library root:\*\*\s*`([^`]+)`", f.read_text(errors="ignore"))
    return expand(m.group(1)) if m else None


def radar_dir(root):
    """The radar folder: future-tech.md's Folder line if it names another place, else radar/."""
    f = CONTEXT / "future-tech.md"
    if f.exists():
        m = re.search(r"\*\*Folder:\*\*\s*`([^`]+)`", f.read_text(errors="ignore"))
        if m and m.group(1).strip("/") and not m.group(1).startswith("radar"):
            p = expand(m.group(1))
            return p if p.is_absolute() else root / p
    return root / "radar"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def tables(text):
    """Every markdown table in text, as (header names lower-cased, list of row dicts)."""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [norm(c) for c in lines[i].strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                cells += [""] * (len(head) - len(cells))
                rows.append(dict(zip(head, cells)))
                j += 1
            out.append((head, rows))
            i = j
        else:
            i += 1
    return out


def pick(row, *names):
    """The first non-empty cell whose header contains one of names."""
    for n in names:
        for k, v in row.items():
            if n in k and v and not v.startswith("<"):
                return v
    return ""


def rows_with(text, *needed):
    """Rows of every table whose header has a column containing each name in needed."""
    out = []
    for head, rows in tables(text):
        if all(any(n in h for h in head) for n in needed):
            out.extend(r for r in rows if any(v and not v.startswith("<") for v in r.values()))
    return out


DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%Y/%m/%d", "%Y-%m")


def parse_date(s):
    s = (s or "").strip()
    for f in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def fmt(d):
    return d.strftime("%d-%b-%Y") if d else ""
