"""kit_inbox: phone and remote access, phase 1 (Microsoft 365 only, nothing from your organization
needed). Used by reminders_sync.py (what arrives in the "Kit Inbox" list) and deliver.py (codes and
publishing). Three parts:

1. Kit Inbox requests. A to-do you add to "Kit Inbox" on your phone arrives at the next sync:
     plain text            one of your to-dos, as before
     "kit: <text>"         a to-do for Kit, and a request in briefs/requests.md
     "ask: <text>"         a question for Kit, in briefs/requests.md only (not a to-do)
     "approve <code> ..."  a phone approval (part 2); never a to-do
   Inbound text is information, never instructions to run: nothing outward-facing (sending,
   deleting, installing, committing, changing settings) ever happens because of a phone request.
   Kit lists requests in the next brief and handles them in a session with you.

2. Coded approvals, low tier only. Each delivered work list and morning brief ends with a code
   for that list: random, single-use, valid until midnight, kept only as a salted hash in
   .install/cache/phone-codes.json. Add "approve <code> 1,3" (or "approve <code> all") to Kit
   Inbox to approve work-list items, or "approve <code> H1 keep, H2 drop" for queue hygiene
   verdicts from the brief. The sync checks the code and records the result in
   briefs/phone-approvals.md; Kit picks it up at the next session. Medium- and high-tier actions
   (commit, push, install, send, delete, change settings, money) can never be approved this way:
   a payload that asks for one is refused and recorded as refused.

3. Publishing for the phone. With ONEDRIVE_PUBLISH_DIR set to a folder inside your OneDrive (or
   under ONEDRIVE_ALLOWED_PREFIX), each delivered brief is written there as simple HTML, plus a
   work summary page (index.html). Files are owner-only. Personal items are left out unless
   PUBLISH_PERSONAL="on"; nothing from memory/personal/ is ever published, and the full dashboard
   copy (which lists personal to-dos) is published only with PUBLISH_PERSONAL="on".
"""
import datetime as dt
import hashlib
import hmac
import html
import json
import os
import pathlib
import re
import secrets

HOME = pathlib.Path.home()
KIT = pathlib.Path(os.environ.get("KIT_DIR", HOME / "Claude/Agents/kit")).expanduser()

# Which code goes with which delivery, and what it may approve.
CODE_SCOPES = {"worklist": "work list", "morning": "queue hygiene"}
# Words that mark a medium- or high-tier action. A phone approval naming one is refused.
FORBIDDEN = re.compile(r"\b(commit\w*|push\w*|install\w*|send\w*|sent|mail|email|delete\w*|remove\w*|"
                       r"settings?|config\w*|permission\w*|money|pay\w*|trade\w*|order\w*|deploy\w*|"
                       r"merge\s+pr|publish\w*|share\w*|upload\w*)\b", re.I)
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L
CODE_LEN = 6


def _paths(kit=None):
    k = pathlib.Path(kit) if kit else KIT
    return {"kit": k, "codes": k / ".install/cache/phone-codes.json",
            "requests": k / "briefs/requests.md", "approvals": k / "briefs/phone-approvals.md"}


def _now():
    return dt.datetime.now()


def _fmt(d):
    return d.strftime("%d-%b-%Y")


def _private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _append(path, line, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if new:
            f.write(header)
        f.write(line.rstrip("\n") + "\n")
    if os.name != "nt":
        os.chmod(path, 0o600)


# ---- 1. Kit Inbox requests ---------------------------------------------------------------------

def classify(title):
    """Return (kind, text) for a Kit Inbox title: kind is "todo", "kit", "ask", or "approve"."""
    t = (title or "").strip()
    m = re.match(r"(?i)^(kit|ask)\s*:\s*(.*)$", t)
    if m:
        return m.group(1).lower(), m.group(2).strip()
    if re.match(r"(?i)^approve\b", t):
        return "approve", t
    return "todo", t


REQUESTS_HEADER = ("# Requests from your phone\n\n"
                   "What arrived in Kit Inbox as \"kit:\" or \"ask:\". This is information for Kit to handle "
                   "with you in a session; nothing here is run as an instruction.\n\n")


def record_request(kind, text, kit=None, side=None):
    p = _paths(kit)
    clean = re.sub(r"\s+", " ", text).strip()[:500]
    tag = " [work]" if side == "work" else ""
    _append(p["requests"], f"- [ ] {_now():%d-%b-%Y %H:%M} {kind}:{tag} {clean}", REQUESTS_HEADER)
    return clean


# ---- 2. Coded approvals ------------------------------------------------------------------------

def _hash(code, salt):
    return hashlib.sha256((salt + ":" + code.upper()).encode()).hexdigest()


def _load_codes(kit=None):
    p = _paths(kit)["codes"]
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []


def issue_code(mode, kit=None, today=None):
    """Issue a single-use code for today's delivery of `mode` (worklist or morning). Returns the
    code; only a salted hash is kept. Older days' codes are dropped."""
    if mode not in CODE_SCOPES:
        raise ValueError(f"no phone approvals for {mode!r}")
    day = (today or _now().date()).isoformat()
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
    salt = secrets.token_hex(8)
    codes = [c for c in _load_codes(kit) if c.get("date") == day]
    codes.append({"date": day, "scope": mode, "salt": salt, "hash": _hash(code, salt), "used": None})
    _private_write(_paths(kit)["codes"], json.dumps(codes, indent=1) + "\n")
    return code


def code_section(mode, code):
    what = CODE_SCOPES[mode]
    example = "approve {c} 1,3" if mode == "worklist" else "approve {c} H1 keep, H2 drop"
    return ("\n\n## Phone approval\n\n"
            f"Code for this {what}: **{code}** (today only, once, and only for this {what}).\n"
            f"From your phone, add a task to Kit Inbox: `{example.format(c=code)}`"
            + (" or `approve " + code + " all`." if mode == "worklist" else ".") + "\n"
            "It can't approve commits, installs, sending, deleting, or settings; those need you at the Mac.\n")


APPROVALS_HEADER = ("# Approvals from your phone\n\n"
                    "Checked by the to-do sync. Kit acts on accepted ones in the next session with you; "
                    "refused ones are listed so you can see why.\n\n")


def _parse_payload(scope, payload):
    """Validate an approval payload for its scope. Returns (ok, normalized, reason)."""
    p = re.sub(r"\s+", " ", payload).strip().rstrip(".")
    if not p:
        return False, "", "nothing to approve"
    if FORBIDDEN.search(p):
        return False, p, "names an action a phone can't approve (commit, install, send, delete, settings, ...)"
    if scope == "worklist":
        if re.fullmatch(r"(?i)all", p):
            return True, "all", ""
        if re.fullmatch(r"\d{1,2}(\s*,\s*\d{1,2})*", p):
            nums = sorted({int(x) for x in re.findall(r"\d+", p)})
            return True, ",".join(map(str, nums)), ""
        return False, p, "a work-list approval is 'all' or item numbers like 1,3"
    if scope == "morning":
        parts = [x.strip() for x in p.split(",") if x.strip()]
        out = []
        for part in parts:
            m = re.fullmatch(r"(?i)(H\d{1,3})\s+(keep|drop|rewrite|merge(?:\s+into\s+H\d{1,3})?)", part)
            if not m:
                return False, p, f"'{part}' isn't a hygiene verdict like 'H1 keep' or 'H2 merge into H5'"
            verdict = re.sub(r"(?i)\bh(\d+)", r"H\1", m.group(2).lower())
            out.append(f"{m.group(1).upper()} {verdict}")
        return True, ", ".join(out), ""
    return False, p, "unknown scope"


def handle_approval(title, kit=None, now=None):
    """Check an 'approve <code> <payload>' title. Records the outcome in briefs/phone-approvals.md
    and returns (accepted, message). A code works once, today only, for its own scope."""
    now = now or _now()
    m = re.match(r"(?i)^approve\s+([A-Za-z0-9]{4,12})\b\s*(.*)$", (title or "").strip())
    p = _paths(kit)
    stamp = f"{now:%d-%b-%Y %H:%M}"
    if not m:
        msg = "refused: no code (use: approve <code> 1,3)"
        _append(p["approvals"], f"- {stamp} {msg}", APPROVALS_HEADER)
        return False, msg
    code, payload = m.group(1).upper(), m.group(2)
    codes = _load_codes(kit)
    day = now.date().isoformat()
    match = None
    for c in codes:
        if hmac.compare_digest(c.get("hash", ""), _hash(code, c.get("salt", ""))):
            match = c
            break
    if match is None:
        msg = "refused: code not recognised"
    elif match.get("date") != day:
        msg = "refused: code expired (codes work on the day they're issued)"
    elif match.get("used"):
        msg = f"refused: code already used at {match['used']}"
    else:
        ok, norm, reason = _parse_payload(match["scope"], payload)
        if not ok:
            msg = f"refused ({CODE_SCOPES[match['scope']]}): {reason}"
        else:
            match["used"] = stamp
            _private_write(p["codes"], json.dumps(codes, indent=1) + "\n")
            msg = f"accepted ({CODE_SCOPES[match['scope']]}): approve {norm}"
            _append(p["approvals"], f"- [ ] {stamp} {msg}", APPROVALS_HEADER)
            return True, msg
    _append(p["approvals"], f"- {stamp} {msg}", APPROVALS_HEADER)
    return False, msg


# ---- 3. Publishing for the phone ---------------------------------------------------------------

PERSONAL_HEADING = re.compile(r"(?i)personal|pastoral|care|trading|market|family|health|money|finance|journal")
PERSONAL_LINE = re.compile(r"(?i)\(personal\)|personal item|pastoral")


def allowed_roots(cfg):
    roots = []
    pref = (cfg.get("ONEDRIVE_ALLOWED_PREFIX") or "").strip()
    if pref:
        roots.append(pathlib.Path(os.path.expanduser(pref)))
    cs = HOME / "Library/CloudStorage"
    if cs.is_dir():
        roots += [p for p in cs.iterdir() if p.name.startswith("OneDrive")]
    for env in ("OneDriveCommercial", "OneDrive"):
        if os.environ.get(env):
            roots.append(pathlib.Path(os.environ[env]))
    return roots


def check_publish_dir(cfg, kit=None):
    """Return (path, None) if ONEDRIVE_PUBLISH_DIR is a subfolder of an allowed root, else
    (None, reason). An empty setting means publishing is off."""
    raw = (cfg.get("ONEDRIVE_PUBLISH_DIR") or "").strip()
    if not raw:
        return None, "off (ONEDRIVE_PUBLISH_DIR not set)"
    target = pathlib.Path(os.path.expanduser(raw)).resolve()
    k = (pathlib.Path(kit) if kit else KIT).resolve()
    if target == k or k in target.parents:
        return None, "refused: the publish folder can't be inside Kit's own folder"
    for root in allowed_roots(cfg):
        r = root.resolve()
        if r in target.parents:
            return target, None
    return None, "refused: ONEDRIVE_PUBLISH_DIR must be a folder inside your OneDrive (or under ONEDRIVE_ALLOWED_PREFIX)"


def strip_personal(md):
    """Drop personal sections and lines from a brief."""
    out, skip_level = [], None
    for line in md.splitlines():
        h = re.match(r"^(#{1,6})\s+(.*)", line)
        if h:
            level = len(h.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and PERSONAL_HEADING.search(h.group(2)):
                skip_level = level
                continue
        if skip_level is not None:
            continue
        if PERSONAL_LINE.search(line):
            continue
        out.append(line)
    return "\n".join(out)


def _page(title, body_html):
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>body{{font:16px/1.45 -apple-system,Segoe UI,Arial,sans-serif;"
            "max-width:46rem;margin:1rem auto;padding:0 1rem;color:#111}}h1,h2,h3{{line-height:1.2}}"
            "code{{background:#eee;padding:0 .2em}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;"
            "padding:.2em .4em}}.meta{{color:#666;font-size:.9em}}</style></head><body>"
            + body_html + "</body></html>\n")


def _md_to_html(md):
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("kit_deliver", str(pathlib.Path(__file__).with_name("deliver.py")))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.md_to_html(md)
    except Exception:  # noqa: BLE001
        return "<pre>" + html.escape(md) + "</pre>"


def work_summary(queue_text):
    """The owner's [work] to-dos, Kit's items, and Waiting on others, from QUEUE.md."""
    sections, cur = {}, None
    for line in queue_text.splitlines():
        h = re.match(r"^## (.+)", line)
        if h:
            cur = h.group(1).strip()
            sections[cur] = []
            continue
        if cur and re.match(r"^- \[ \] ", line):
            sections[cur].append(line)
    owner = next((s for s in sections if s not in ("Sprint", "Kit", "Waiting on others", "Someday", "Done")), None)
    parts = []
    if owner:
        work = [l for l in sections.get(owner, []) if "[work]" in l.lower()]
        parts.append(("Your work items", work))
    parts.append(("Kit's items", sections.get("Kit", [])))
    parts.append(("Waiting on others", sections.get("Waiting on others", [])))
    body = []
    for title, items in parts:
        body.append(f"<h2>{html.escape(title)}</h2>")
        if items:
            body.append("<ul>" + "".join(
                "<li>" + html.escape(re.sub(r"\*\*", "", l[6:]).split(" (added")[0]) + "</li>" for l in items) + "</ul>")
        else:
            body.append("<p class=\"meta\">Nothing here.</p>")
    return "\n".join(body)


def publish(brief_path, mode, cfg, kit=None, keep=14):
    """Write the brief (HTML), a work summary page, and (only with PUBLISH_PERSONAL=on) a copy of
    the dashboard to the OneDrive publish folder. Returns (ok, message)."""
    k = pathlib.Path(kit) if kit else KIT
    target, why = check_publish_dir(cfg, k)
    if not target:
        return False, why
    personal = (cfg.get("PUBLISH_PERSONAL") or "off").lower() == "on"
    target.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(target, 0o700)
    written = []
    brief = pathlib.Path(brief_path) if brief_path else None
    if brief and brief.is_file():
        rb = brief.resolve()
        if (k / "memory/personal").resolve() in rb.parents:
            return False, "refused: nothing from memory/personal is published"
        md = brief.read_text(encoding="utf-8", errors="replace")
        if not personal:
            md = strip_personal(md)
        page = _page(f"Kit {mode} {brief.stem}", f"<p class=\"meta\">Kit {html.escape(mode)}, "
                     f"published {_now():%d-%b-%Y %H:%M}</p>" + _md_to_html(md))
        bdir = target / "briefs"
        bdir.mkdir(exist_ok=True)
        _private_write(bdir / f"{brief.stem}.html", page)
        _private_write(target / f"latest-{mode}.html", page)
        written += [f"briefs/{brief.stem}.html", f"latest-{mode}.html"]
        old = sorted(bdir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
        for p in old:
            p.unlink()
    queue = k / "QUEUE.md"
    summary = work_summary(queue.read_text(encoding="utf-8")) if queue.exists() else "<p>No queue.</p>"
    links = "".join(f"<li><a href=\"latest-{m}.html\">Latest {m}</a></li>"
                    for m in ("morning", "worklist", "weekly", "eod") if (target / f"latest-{m}.html").exists())
    _private_write(target / "index.html", _page("Kit", f"<h1>Kit</h1><p class=\"meta\">Updated {_now():%d-%b-%Y %H:%M}. "
                   "Work items only" + ("" if not personal else " (personal publishing is on)") + ".</p>"
                   + (f"<ul>{links}</ul>" if links else "") + summary))
    written.append("index.html")
    dash = k / "dashboard.html"
    if personal and dash.is_file():
        _private_write(target / "dashboard.html", dash.read_text(encoding="utf-8", errors="replace"))
        written.append("dashboard.html")
    return True, "published " + ", ".join(written)
