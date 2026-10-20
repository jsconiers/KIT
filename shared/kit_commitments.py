"""kit_commitments: find commitments you made in your own words (sent mail, meeting minutes) and
propose them as to-dos. It never adds anything to the queue: proposals go to
briefs/pending-commitments.md, the morning brief counts them, and you confirm or drop each one with
Kit in a session, the same way as meeting actions (briefs/pending-actions.md).

What counts: first-person promises in your own new text ("I'll send", "I will", "I can have",
"let me get back to you", "I'm going to"), with a due date when one is stated ("by Friday",
"tomorrow", "next week", "by 23-Oct", "by 10/23", "EOD"). Quoted replies below your text are
skipped. Counterparts are recorded by role (from a "Role:" line or --role), never by name, and
email addresses are masked.
"""
import datetime as dt
import hashlib
import os
import pathlib
import re

HOME = pathlib.Path.home()
KIT = pathlib.Path(os.environ.get("KIT_DIR", HOME / "Claude/Agents/kit")).expanduser()

PROMISE = re.compile(
    r"\b(I'?ll|I will|I can have|I can get|I'm going to|I am going to|I'll make sure to|let me|I'll get back|"
    r"I will get back|I'll follow up|I will follow up)\b\s*(.*)", re.I)
QUOTE_START = re.compile(r"^(>|-{2,}\s*Original Message|_{5,}|From:\s|On .+ wrote:|Sent from my )", re.I)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                      "oct", "nov", "dec"], 1)}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
HEADER = ("# Pending commitments\n\n"
          "Promises found in your own sent mail or meeting minutes. Proposals only: confirm or drop each "
          "with Kit in a session. Confirmed ones become your to-dos; nothing is added on its own.\n\n"
          "| Id | Status | Action | Counterpart | Due | Source | Found |\n"
          "|---|---|---|---|---|---|---|\n")


def _fmt(d):
    return d.strftime("%d-%b-%Y")


def own_text(body):
    """The new text at the top of a message, without quoted replies or signatures below it."""
    out = []
    for line in body.splitlines():
        if QUOTE_START.match(line.strip()):
            break
        out.append(line)
    return "\n".join(out)


def parse_due(text, base):
    t = text.lower()
    if re.search(r"\b(eod|end of (the )?day|today|tonight)\b", t):
        return base
    if re.search(r"\btomorrow\b", t):
        return base + dt.timedelta(days=1)
    if re.search(r"\bnext week\b", t):
        return base + dt.timedelta(days=7 - base.weekday())
    if re.search(r"\b(end of (the )?week|eow|this week)\b", t):
        return base + dt.timedelta(days=(4 - base.weekday()) % 7)
    for i, wd in enumerate(WEEKDAYS):
        if re.search(rf"\b(by |on |this |next )?{wd}\b", t):
            ahead = (i - base.weekday()) % 7 or 7
            if re.search(rf"\bnext {wd}\b", t) and ahead < 7:
                ahead += 7
            return base + dt.timedelta(days=ahead)
    m = re.search(r"\b(\d{1,2})[- ]([a-z]{3})[a-z]*(?:[- ](\d{4}))?\b", t)
    if m and m.group(2) in MONTHS:
        y = int(m.group(3)) if m.group(3) else base.year
        try:
            d = dt.date(y, MONTHS[m.group(2)], int(m.group(1)))
            return d if m.group(3) or d >= base else d.replace(year=y + 1)
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        y = int(m.group(3)) if m.group(3) else base.year
        y = y + 2000 if y < 100 else y
        try:
            d = dt.date(y, int(m.group(1)), int(m.group(2)))
            return d if m.group(3) or d >= base else d.replace(year=y + 1)
        except ValueError:
            pass
    return None


def _clean_action(phrase, rest):
    s = (phrase + " " + rest).strip()
    s = re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0]
    s = EMAIL.sub("[address]", s).strip(" .;,")
    s = re.sub(r"(?i)^I can\s+", "", s)   # "I can have the draft ..." -> "have the draft ..."
    s = re.sub(r"(?i)^(I'?ll|I will|I'm going to|I am going to|let me)\s+", "", s)
    s = re.sub(r"(?i)^(make sure to|try to)\s+", "", s)
    return (s[:1].upper() + s[1:])[:160] if s else ""


def find(text, base=None, source="", role=""):
    """Commitments in one message or minutes text. Returns a list of dicts."""
    base = base or dt.date.today()
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", own_text(text)):
        m = PROMISE.search(sentence)
        if not m:
            continue
        action = _clean_action(m.group(1), m.group(2))
        if len(action.split()) < 2 or re.match(r"(?i)^(know|be|see|think|try)\b", action):
            continue   # "let me know", "I'll be out", "I'll see": not commitments
        due = parse_due(sentence, base)
        found.append({"action": action, "due": _fmt(due) if due else "no date",
                      "role": role or "recipient", "source": source or "text", "found": _fmt(base)})
    return found


def split_messages(raw):
    """Split kitmail-style output ('From:/Date:/Subject:' headers, a dashed line, then the body)
    or '=== message' separated text into (headers, body) pairs."""
    chunks = re.split(r"(?m)^=== message.*$", raw)
    out = []
    for c in chunks:
        if not c.strip():
            continue
        head, body = {}, c
        m = re.search(r"(?m)^-{20,}\s*$", c)
        if m:
            for line in c[:m.start()].splitlines():
                hm = re.match(r"^(From|Date|Subject|To|Role):\s*(.*)$", line.strip())
                if hm:
                    head[hm.group(1).lower()] = hm.group(2).strip()
            body = c[m.end():]
        out.append((head, body))
    return out


def _msg_date(head):
    s = head.get("date", "")
    for fmtx in ("%a %d-%b-%Y %H:%M", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmtx).date()
        except ValueError:
            continue
    return None


def _norm(s):
    return set(w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2)


def _similar(a, b):
    x, y = _norm(a), _norm(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.7


def pending_path(kit=None):
    return (pathlib.Path(kit) if kit else KIT) / "briefs/pending-commitments.md"


def read_pending(kit=None):
    p = pending_path(kit)
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\| (C\d+) \| (\w+) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$", line)
            if m:
                rows.append(dict(zip(("id", "status", "action", "role", "due", "source", "found"), m.groups())))
    return rows


def write_pending(rows, kit=None):
    p = pending_path(kit)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"| {r['id']} | {r['status']} | {r['action']} | {r['role']} | {r['due']} | {r['source']} | {r['found']} |\n"
                   for r in rows)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(HEADER + body, encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def add_proposals(found, kit=None):
    """Add new commitments as proposals, skipping ones already in QUEUE.md or already proposed.
    Returns (added, skipped)."""
    k = pathlib.Path(kit) if kit else KIT
    queue = (k / "QUEUE.md").read_text(encoding="utf-8") if (k / "QUEUE.md").exists() else ""
    titles = re.findall(r"\*\*(.+?)\*\*", queue)
    rows = read_pending(k)
    n = max([int(r["id"][1:]) for r in rows] or [0])
    added = skipped = 0
    for f in found:
        clean = {key: str(v).replace("|", "/") for key, v in f.items()}
        if any(_similar(clean["action"], t) for t in titles) or any(_similar(clean["action"], r["action"]) for r in rows):
            skipped += 1
            continue
        n += 1
        rows.append({"id": f"C{n}", "status": "proposed", **clean})
        added += 1
    write_pending(rows, k)
    return added, skipped


def mark(cid, status, kit=None):
    if status not in ("confirmed", "dropped", "proposed"):
        raise ValueError("status is confirmed, dropped, or proposed")
    rows = read_pending(kit)
    for r in rows:
        if r["id"].upper() == cid.upper():
            r["status"] = status
            write_pending(rows, kit)
            return r
    raise KeyError(cid)


def source_label(kind, head):
    when = _msg_date(head)
    subj = EMAIL.sub("[address]", head.get("subject", ""))[:60]
    tag = hashlib.sha1((head.get("subject", "") + head.get("date", "")).encode()).hexdigest()[:6]
    return f"{kind} {(_fmt(when) if when else '')} \"{subj}\" #{tag}".replace("  ", " ").strip()
