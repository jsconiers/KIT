"""kit_daily: shared helpers for Kit's daily-workflow tools (kit-wins, kit-oneonone, kit-meetprep,
kit-triage, kit-awaiting).

Paths come from KIT_DIR (default ~/Claude/Agents/kit). Everything here reads local files only;
nothing reaches outside this computer, sends, or moves mail.
"""
import datetime as dt
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
CONTEXT = KIT / "memory/context"
BRIEFS = KIT / "briefs"
CONFIG = KIT / ".install/shared/morning/config"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
STOP = set("""a an and are as at be by for from has have in is it of on or re fw fwd the to with
our your you we i me my this that will can not meeting call sync update weekly review""".split())


def today():
    return dt.date.fromisoformat(os.environ["KIT_TODAY"]) if os.environ.get("KIT_TODAY") else dt.date.today()


def now():
    if os.environ.get("KIT_NOW"):
        return dt.datetime.fromisoformat(os.environ["KIT_NOW"])
    return dt.datetime.now()


def fmt(d):
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}" if d else ""


def parse_date(s):
    """DD-Mmm-YYYY, YYYY-MM-DD, 'Mon 19-Oct-2026 09:00', or an ISO datetime. None if none found."""
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})-([A-Z][a-z]{2})-(\d{4})\b", s)
    if m and m[2] in MONTHS:
        try:
            return dt.date(int(m[3]), MONTHS.index(m[2]) + 1, int(m[1]))
        except ValueError:
            return None
    return None


def read(path):
    try:
        return pathlib.Path(path).read_text(errors="ignore")
    except OSError:
        return ""


def write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def setting(text, field):
    """The value of a '- **Field:** value' line in a setup file, or ''."""
    m = re.search(r"^- \*\*" + re.escape(field) + r":\*\*\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip() if m else ""


def owner():
    m = re.search(r'^OWNER_NAME="?([^"\n]+)"?', read(CONFIG), re.M)
    return m.group(1).strip() if m else "Owner"


def library_root():
    m = re.search(r"\*\*Library root:\*\*\s*`([^`]+)`", read(CONTEXT / "library.md"))
    return pathlib.Path(os.path.expanduser(m.group(1))) if m else None


def mask(s):
    """Replace email addresses so they never land in a brief."""
    return EMAIL.sub("[address]", s or "")


def clip(s, n):
    s = " ".join(mask(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def slug(s, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:n].rstrip("-") or "item")


def words(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2 and w not in STOP}


def norm_subject(s):
    s = (s or "").strip()
    while True:
        t = re.sub(r"^\s*(re|fw|fwd|aw|wg|tr)\s*(\[\d+\])?\s*:\s*", "", s, flags=re.I)
        t = re.sub(r"^\s*\[(external|ext)\]\s*", "", t, flags=re.I)
        if t == s:
            break
        s = t
    return " ".join(s.lower().split())


def is_reply(subject):
    return bool(re.match(r"^\s*(re|aw)\s*(\[\d+\])?\s*:", subject or "", re.I))


# kitmail inbox listing: "*  3  19-Oct 09:12  Sender name (28 wide)  Subject"
LISTING = re.compile(r"^(?P<flag>[ *])\s*(?P<n>\d+)\s{2}(?P<when>\d{2}-[A-Z][a-z]{2} \d{2}:\d{2}|\s{12})\s{2}"
                     r"(?P<sender>.{28})\s{2}(?P<subject>.*)$")


def parse_listing(text, base=None):
    """Messages from `kitmail inbox`-style lines: unread, n, when (datetime or None), sender, subject."""
    base = base or today()
    out = []
    for line in (text or "").splitlines():
        m = LISTING.match(line)
        if not m:
            continue
        when = None
        if m["when"].strip():
            d, t = m["when"].split()
            day, mon = d.split("-")
            if mon in MONTHS:
                year = base.year
                cand = dt.datetime(year, MONTHS.index(mon) + 1, int(day), *map(int, t.split(":")))
                if cand.date() > base + dt.timedelta(days=1):
                    cand = cand.replace(year=year - 1)
                when = cand
        out.append({"unread": m["flag"] == "*", "n": int(m["n"]), "when": when,
                    "sender": m["sender"].strip(), "subject": m["subject"].strip(), "body": "", "head": {}})
    return out


def parse_messages(text):
    """Messages from `kitmail read` / `sent-read` / `sent-dump` output (headers, dashed line, body),
    separated by '=== message' lines when there are several."""
    chunks = re.split(r"(?m)^=== message.*$", text or "")
    out = []
    for c in chunks:
        if not c.strip():
            continue
        m = re.search(r"(?m)^-{20,}\s*$", c)
        if not m:
            continue
        head = {}
        for line in c[: m.start()].splitlines():
            hm = re.match(r"^(From|To|Cc|Date|Subject|Role):\s*(.*)$", line.strip())
            if hm:
                head[hm.group(1).lower()] = hm.group(2).strip()
        when = None
        dm = re.search(r"(\d{1,2})-([A-Z][a-z]{2})-(\d{4})(?:\s+(\d{2}):(\d{2}))?", head.get("date", ""))
        if dm and dm[2] in MONTHS:
            when = dt.datetime(int(dm[3]), MONTHS.index(dm[2]) + 1, int(dm[1]),
                               int(dm[4] or 0), int(dm[5] or 0))
        sender = re.sub(r"\s*<[^>]*>", "", head.get("from", "")).strip()
        out.append({"unread": False, "n": len(out) + 1, "when": when, "sender": sender,
                    "subject": head.get("subject", ""), "body": c[m.end():], "head": head})
    return out


def parse_mail(text, base=None):
    """Either format: full messages if the text has header blocks, else listing lines."""
    msgs = parse_messages(text)
    return msgs if msgs else parse_listing(text, base)


def own_text(body):
    """The part of a message body the writer typed: stops at quoted replies and signatures."""
    out = []
    for line in (body or "").splitlines():
        if re.match(r"^(>|-{2,}\s*Original Message|_{5,}|From:\s|On .+ wrote:|Sent from my )", line.strip(), re.I):
            break
        out.append(line)
    return "\n".join(out)


def queue_lines():
    return read(KIT / "QUEUE.md").splitlines()


def section(lines, name):
    """Lines of '## name' up to the next '## '."""
    out, on = [], False
    for ln in lines:
        if ln.startswith("## "):
            on = ln[3:].strip() == name
            continue
        if on:
            out.append(ln)
    return out


def sections(lines):
    return [ln[3:].strip() for ln in lines if ln.startswith("## ")]


def owner_section(lines):
    skip = {"Sprint", "Kit", "Waiting on others", "Someday", "Done"}
    for name in sections(lines):
        if name not in skip:
            return name
    return None


ITEM = re.compile(r"^(?P<indent>\s*)- \[(?P<x>[ xX])\] (?:\*\*(?P<title>.+?)\*\*)?(?P<rest>.*)$")


def items(lines, name):
    """Open and checked items of a section: dicts with title, rest, done, sub (bool), parent."""
    out, parent = [], None
    for ln in section(lines, name):
        m = ITEM.match(ln)
        if not m:
            continue
        sub = len(m["indent"]) >= 2
        title = (m["title"] or m["rest"]).strip()
        it = {"title": title, "rest": m["rest"] if m["title"] else "", "done": m["x"].lower() == "x",
              "sub": sub, "parent": parent if sub else None, "line": ln}
        if not sub:
            parent = title
        out.append(it)
    return out


def due_of(text):
    m = re.search(r"due (\d{1,2}-[A-Z][a-z]{2}-\d{4})", text or "")
    return parse_date(m.group(1)) if m else None
