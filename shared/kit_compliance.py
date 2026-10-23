"""kit_compliance: shared helpers for Kit's compliance registers (kit-exceptions, kit-pbc,
kit-audit-export --controls, and morning/monitor_exceptions.py).

Every function takes Kit's folder explicitly, so the monitors can pass the one run_alerts.py uses.
Local files only: nothing here reaches outside this computer.
"""
import datetime as dt
import os
import pathlib
import re

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

try:  # the same credential patterns the records and the evidence pack use
    import kit_records
    _PATTERNS = [(p, w) for p, w in kit_records.SECRET_PATTERNS
                 if w not in ("account or card number", "Social Security number")]
except ImportError:  # pragma: no cover
    _PATTERNS = []


def kit_dir(kit=None):
    return pathlib.Path(os.path.expanduser(kit or os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))


def today():
    return dt.date.fromisoformat(os.environ["KIT_TODAY"]) if os.environ.get("KIT_TODAY") else dt.date.today()


def fmt(d):
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}" if d else ""


def parse_date(s):
    """DD-Mmm-YYYY or YYYY-MM-DD (anywhere in the text), else None."""
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


def cred_hits(text):
    return sorted({w for p, w in _PATTERNS if re.search(p, text or "")})


def read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def setting(text, field):
    """The value of a '- **Field:** value' line in a setup file, or ''."""
    m = re.search(r"^- \*\*" + re.escape(field) + r":\*\*\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip() if m else ""


def library_root(kit):
    m = re.search(r"\*\*Library root:\*\*\s*`([^`]+)`", read(kit_dir(kit) / "memory/context/library.md"))
    return pathlib.Path(os.path.expanduser(m.group(1))) if m else None


def setup_path(kit, field, default_rel, setup="compliance.md"):
    """A path from a setup field ('- **Field:** `path`'): absolute or ~ as is, otherwise relative to the
    library root. With the field not set, default_rel in the library root. None without a root."""
    val = setting(read(kit_dir(kit) / "memory/context" / setup), field)
    m = re.search(r"`([^`]+)`", val)
    rel = m.group(1) if m else default_rel
    p = pathlib.Path(os.path.expanduser(rel))
    if p.is_absolute():
        return p
    root = library_root(kit)
    return (root / p) if root else None


def template(kit, name):
    """A shipped template: Kit's installed templates/, else the repo's kit/templates/."""
    here = pathlib.Path(__file__).resolve().parent
    for c in (kit_dir(kit) / "templates" / name, here.parent / "kit/templates" / name,
              here.parents[1] / "templates" / name):
        if c.is_file():
            return read(c)
    return ""


# ---------- Markdown tables ----------

def cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s.strip().strip("|")
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def is_sep(cs):
    return cs is not None and any(cs) and all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in cs)


def norm(h):
    return re.sub(r"[^a-z0-9]+", " ", h.lower()).strip()


def find_table(text, must):
    """(header cells, index of the header line, index after the last row) of the first table whose
    normalised header holds every word group in must; None if there's none."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        cs = cells(ln)
        if cs is None or i + 1 >= len(lines) or not is_sep(cells(lines[i + 1])):
            continue
        head = " | ".join(norm(c) for c in cs)
        if all(re.search(w, head) for w in must):
            j = i + 2
            while j < len(lines) and cells(lines[j]) is not None:
                j += 1
            return cs, i, j
    return None


def placeholder(v):
    v = (v or "").strip()
    return not v or (v.startswith("<") and v.endswith(">"))


def rows(text, must, columns):
    """The table's rows as dicts keyed by the column keys in columns ([(key, header regex)]), skipping
    blank and <placeholder> example rows. Each row also carries "_line" (its index in the text)."""
    found = find_table(text, must)
    if not found:
        return None, []
    head, i, j = found
    keymap = {}
    for n, h in enumerate(head):
        nh = norm(h)
        for key, rx in columns:
            if key not in keymap.values() and re.search(rx, nh):
                keymap[n] = key
                break
    lines = text.splitlines()
    out = []
    for k in range(i + 2, j):
        cs = cells(lines[k])
        rec = {key: "" for key, _ in columns}
        for n, c in enumerate(cs):
            if n in keymap:
                rec[keymap[n]] = c.replace("\\|", "|")
        first = rec.get(columns[0][0], "")
        if placeholder(first) or all(placeholder(v) for v in rec.values()):
            continue
        rec["_line"] = k
        out.append(rec)
    return found, out


def clean_cell(v):
    return " ".join(str(v or "").replace("|", "/").split())


def append_row(text, found, columns, rec):
    """The text with rec added as the table's last row, in the table's own column order. A blank or
    placeholder-only example row is replaced."""
    head, i, j = found
    lines = text.splitlines()
    order = []
    for h in head:
        nh = norm(h)
        key = next((k for k, rx in columns if k not in order and re.search(rx, nh)), None)
        order.append(key)
    row = "| " + " | ".join(clean_cell(rec.get(k, "")) if k else "" for k in order) + " |"
    k = j
    while k > i + 2 and all(placeholder(c) for c in (cells(lines[k - 1]) or [""])):
        lines.pop(k - 1)
        k -= 1
    lines.insert(k, row)
    return "\n".join(lines) + "\n"


def next_id(recs, prefix, key="id"):
    top = 0
    for r in recs:
        m = re.match(re.escape(prefix) + r"-(\d+)$", r.get(key, "").strip())
        if m:
            top = max(top, int(m.group(1)))
    return f"{prefix}-{top + 1:04d}"


# ---------- the exception register ----------

EXC_COLUMNS = [
    ("id", r"^id$|exception id"),
    ("policy", r"policy"),
    ("system", r"system|design"),
    ("reason", r"reason|justification"),
    ("controls", r"compensating"),
    ("owner", r"owner"),
    ("approver", r"approv"),
    ("granted", r"granted"),
    ("expiry", r"expir"),
    ("review", r"review freq|frequency"),
    ("last_review", r"last review|reviewed"),
    ("status", r"status"),
    ("ticket", r"ticket"),
    ("evidence", r"evidence"),
]
EXC_MUST = [r"\bid\b", r"expir"]
EXC_STATUSES = ("candidate", "requested", "granted", "renewal requested", "expired", "revoked", "closed")
EXC_ACTIVE = ("granted", "renewal requested")


def exception_register(kit, override=None):
    if override:
        return pathlib.Path(os.path.expanduser(override))
    return setup_path(kit, "Exception register", "compliance/exception-register.md")


def frequency_days(text):
    """Review frequency to days: monthly, quarterly, semi-annual, annual, or 'N days/weeks/months'."""
    t = (text or "").lower().strip()
    named = {"weekly": 7, "monthly": 30, "quarterly": 91, "semi-annual": 182, "semiannual": 182,
             "half-yearly": 182, "six-monthly": 182, "annual": 365, "annually": 365, "yearly": 365}
    if t in named:
        return named[t]
    m = re.match(r"(?:every\s+)?(\d+)\s*(day|week|month|year)s?$", t)
    if m:
        return int(m[1]) * {"day": 1, "week": 7, "month": 30, "year": 365}[m[2]]
    return None


def load_exceptions(path):
    text = read(path) if path else ""
    found, recs = rows(text, EXC_MUST, EXC_COLUMNS)
    for r in recs:
        r["status_n"] = r["status"].strip().lower()
        r["granted_d"] = parse_date(r["granted"])
        r["expiry_d"] = parse_date(r["expiry"])
        r["last_review_d"] = parse_date(r["last_review"])
        r["review_days"] = frequency_days(r["review"])
    return text, found, recs


def exception_due(recs, on, days):
    """[(kind, rec, days, date)] for active exceptions: expired, expiring within days, review overdue."""
    out = []
    for r in recs:
        if r["status_n"] not in EXC_ACTIVE and r["status_n"] != "expired":
            continue
        e = r["expiry_d"]
        if e and e < on:
            out.append(("expired", r, (on - e).days, e))
        elif e and (e - on).days <= days and r["status_n"] in EXC_ACTIVE:
            out.append(("expiring", r, (e - on).days, e))
        if r["status_n"] in EXC_ACTIVE and r["review_days"]:
            base = r["last_review_d"] or r["granted_d"]
            if base:
                nxt = base + dt.timedelta(days=r["review_days"])
                if nxt < on and not (e and e < on):
                    out.append(("review", r, (on - nxt).days, nxt))
    return out


# ---------- the audit request (PBC) tracker ----------

PBC_COLUMNS = [
    ("id", r"request id|^id$"),
    ("audit", r"^audit$|audit name|engagement"),
    ("item", r"requested item|item|request$"),
    ("controls", r"control"),
    ("requester", r"requester|requested by"),
    ("due", r"^due|due date"),
    ("owner", r"owner"),
    ("status", r"status"),
    ("evidence", r"evidence"),
    ("notes", r"notes"),
]
PBC_MUST = [r"request id|\bid\b", r"due"]
PBC_STATUSES = ("open", "gathering", "drafted", "provided", "closed")
PBC_DONE = ("provided", "closed")


def pbc_tracker(kit, override=None):
    if override:
        return pathlib.Path(os.path.expanduser(override))
    return setup_path(kit, "PBC tracker", "compliance/audit-requests/pbc-tracker.md")


def load_pbc(path):
    text = read(path) if path else ""
    found, recs = rows(text, PBC_MUST, PBC_COLUMNS)
    for r in recs:
        r["status_n"] = r["status"].strip().lower()
        r["due_d"] = parse_date(r["due"])
        r["control_ids"] = [c for c in re.split(r"[,;\s]+", r["controls"]) if c and not placeholder(c)]
    return text, found, recs


def pbc_due(recs, on, days):
    """{"overdue": [...], "due_soon": [...]} for requests not provided or closed."""
    over, soon = [], []
    for r in recs:
        if r["status_n"] in PBC_DONE or not r["due_d"]:
            continue
        left = (r["due_d"] - on).days
        if left < 0:
            over.append((r, -left))
        elif left <= days:
            soon.append((r, left))
    return {"overdue": over, "due_soon": soon}


def slug(s, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:n].rstrip("-") or "item")
