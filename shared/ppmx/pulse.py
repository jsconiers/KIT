"""The portfolio pulse: what changed in PPM Express since last week.

A snapshot holds the projects a token can see (name, status, manager, dates, progress, portfolio, program)
and the key dates of the open ones. Comparing this week's snapshot with last week's gives the projects
that turned At Risk or Critical (and those that recovered), key dates that slipped, came due, or went
overdue, and what else changed: finish dates, managers, progress, projects added and closed. Read only:
nothing here changes PPM Express. Standard library only.
"""
import datetime
import time

from .client import PPMXError
from .tools import is_done, pick, role_day, text_of

RISK = {1: "At Risk", 2: "Critical"}
RISK_WORDS = ("at risk", "critical")
SOON_DAYS = 14


def _code(row, field_keys):
    codes = row.get("codes") if isinstance(row.get("codes"), dict) else {}
    for key in field_keys:
        if isinstance(codes.get(key), int):
            return codes[key]
        if isinstance(row.get(key), int) and not isinstance(row.get(key), bool):
            return row[key]
    return None


def _day(row, role):
    d = role_day(row, role)
    return d.isoformat() if d else ""


def _text(row, role):
    return text_of(pick(row, role)[1]).strip()


def project_facts(row):
    status = _text(row, "status")
    return {"name": _text(row, "name") or "(no name)", "status": status,
            "status_code": _code(row, ("OverallStatus", "Status", "State")),
            "manager": _text(row, "manager"), "start": _day(row, "start"), "finish": _day(row, "finish"),
            "progress": _text(row, "progress"), "portfolio": _text(row, "portfolio"), "program": _text(row, "program"),
            "done": is_done(row) is True}


def key_date_facts(row, pid):
    return {"project": pid, "name": _text(row, "name") or "(no name)", "date": _day(row, "date"),
            "status": _text(row, "status"), "type": _text(row, "type"), "done": is_done(row) is True}


def at_risk(p):
    if p.get("status_code") in RISK:
        return True
    return any(w in (p.get("status") or "").lower() for w in RISK_WORDS)


def in_scope(row, scope, me):
    """scope: "all", "mine" (the token's own projects, by manager), or a list of portfolio or program names."""
    if not scope or scope == "all":
        return True
    if scope == "mine":
        who = text_of(pick(row, "manager")[1]).lower()
        return any(m and m.lower() in who for m in me or [])
    names = [s.lower() for s in scope]
    places = (text_of(pick(row, "portfolio")[1]) + " " + text_of(pick(row, "program")[1])).lower()
    return any(n in places for n in names)


def _rows(ctx, name, deadline, sleep, **parts):
    """ctx.rows, waiting out this token's request limit (PPM Express allows about 100 a minute) until the deadline."""
    while True:
        try:
            return ctx.rows(name, **parts)
        except PPMXError as e:
            if e.status != 429 or time.monotonic() + 31 > deadline:
                raise
            sleep(31)


def snapshot(ctx, scope="all", me=None, max_projects=300, key_dates=True, deadline_seconds=270, sleep=time.sleep,
             now=None):
    """The projects in scope and their key dates, as plain facts keyed by ID. Errors on single projects are
    counted, not raised; an error listing the projects is raised."""
    deadline = time.monotonic() + deadline_seconds
    rows = [r for r in _rows(ctx, "projects", deadline, sleep) if r.get("id") and in_scope(r, scope, me)]
    snap = {"taken": (now or datetime.datetime.now()).isoformat(timespec="minutes"),
            "scope": scope if isinstance(scope, str) else list(scope), "projects": {}, "key_dates": {},
            "skipped": 0, "errors": 0}
    for row in rows[:max_projects]:
        snap["projects"][str(row["id"])] = project_facts(row)
    snap["skipped"] = max(0, len(rows) - max_projects)
    if key_dates:
        for pid, p in snap["projects"].items():
            if p["done"]:
                continue
            if time.monotonic() > deadline:
                snap["errors"] += 1
                continue
            try:
                for kd in _rows(ctx, "key_dates", deadline, sleep, id=pid):
                    if kd.get("id"):
                        snap["key_dates"][f"{pid}/{kd['id']}"] = key_date_facts(kd, pid)
            except PPMXError:
                snap["errors"] += 1
    return snap


def _days_between(a, b):
    try:
        return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
    except ValueError:
        return None


def compare(old, new, today, soon_days=SOON_DAYS):
    """What changed from the old snapshot (None for the first pulse) to the new one."""
    today_s = today.isoformat()
    soon_s = (today + datetime.timedelta(days=soon_days)).isoformat()
    np_, op = new["projects"], (old or {}).get("projects", {})
    nk, ok = new["key_dates"], (old or {}).get("key_dates", {})
    rep = {"first": old is None, "since": (old or {}).get("taken", "")[:10], "projects": len(np_),
           "key_dates": len(nk), "skipped": new.get("skipped", 0), "errors": new.get("errors", 0),
           "turned": [], "worse": [], "recovered": [], "still": [], "slipped": [], "pulled_in": [],
           "coming_due": [], "overdue": [], "finished_kd": [], "finish_moved": [], "manager": [], "progress": [],
           "added": [], "closed": [], "gone": []}
    for pid, p in np_.items():
        o = op.get(pid)
        if p["done"]:
            if o and not o["done"]:
                rep["closed"].append(p["name"])
            continue
        if at_risk(p):
            if old is None:
                rep["still"].append((p["name"], p["status"]))
            elif not o or not at_risk(o):
                rep["turned"].append((p["name"], p["status"], o["status"] if o else ""))
            elif p.get("status_code") == 2 and o.get("status_code") == 1:
                rep["worse"].append((p["name"], p["status"], o["status"]))
            else:
                rep["still"].append((p["name"], p["status"]))
        elif o and at_risk(o):
            rep["recovered"].append((p["name"], p["status"], o["status"]))
        if old is None:
            continue
        if not o:
            rep["added"].append(p["name"])
            continue
        if p["finish"] and o["finish"] and p["finish"] != o["finish"]:
            rep["finish_moved"].append((p["name"], o["finish"], p["finish"], _days_between(o["finish"], p["finish"])))
        if p["manager"] != o["manager"] and (p["manager"] or o["manager"]):
            rep["manager"].append((p["name"], o["manager"], p["manager"]))
        if p["progress"] != o["progress"] and p["progress"] and o["progress"]:
            rep["progress"].append((p["name"], o["progress"], p["progress"]))
    for pid, o in op.items():
        if pid not in np_ and not o["done"]:
            rep["gone"].append(o["name"])
    pname = {pid: p["name"] for pid, p in np_.items()}
    for key, k in nk.items():
        o = ok.get(key)
        where = pname.get(k["project"], "")
        if k["done"]:
            if o and not o["done"]:
                rep["finished_kd"].append((where, k["name"], k["date"]))
            continue
        if o and k["date"] and o["date"] and k["date"] != o["date"]:
            moved = _days_between(o["date"], k["date"])
            (rep["slipped"] if (moved or 0) > 0 else rep["pulled_in"]).append((where, k["name"], o["date"], k["date"], moved))
        if k["date"] and k["date"] < today_s:
            rep["overdue"].append((where, k["name"], k["date"]))
        elif k["date"] and today_s <= k["date"] <= soon_s:
            rep["coming_due"].append((where, k["name"], k["date"]))
    for lst in ("coming_due", "overdue"):
        rep[lst].sort(key=lambda r: r[2])
    rep["slipped"].sort(key=lambda r: -(r[4] or 0))
    return rep


def fmt_day(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "?"
    return d.strftime("%d-%b-%Y")


def _short(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d-%b")
    except (TypeError, ValueError):
        return iso or "?"


def _clip(s, n=60):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _list(items, show, n):
    shown = [show(x) for x in items[:n]]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def lines(rep, n=5, tag="[work] "):
    """The pulse as lines: what turned, slipped, comes due, and changed. Each starts with `tag`."""
    out = []
    since = f" since {fmt_day(rep['since'])}" if rep["since"] else ""

    def add(text):
        out.append(tag + text)
    if rep["turned"]:
        add(f"Turned At Risk or Critical{since}: " + _list(rep["turned"], lambda r: f"{_clip(r[0])} ({r[1]}"
                                                               + (f", was {r[2]})" if r[2] else ")"), n))
    if rep["worse"]:
        add("At Risk to Critical: " + _list(rep["worse"], lambda r: _clip(r[0]), n))
    if rep["recovered"]:
        add("Back on track: " + _list(rep["recovered"], lambda r: f"{_clip(r[0])} ({r[1]})", n))
    if rep["slipped"]:
        add("Key dates that slipped: " + _list(rep["slipped"], lambda r: f"{_clip(r[0], 40)}: {_clip(r[1], 40)} "
                                               f"{_short(r[2])} to {_short(r[3])} (+{r[4]} days)", n))
    if rep["overdue"]:
        add("Overdue key dates: " + _list(rep["overdue"], lambda r: f"{_clip(r[0], 40)}: {_clip(r[1], 40)} "
                                          f"({_short(r[2])})", n))
    if rep["coming_due"]:
        add(f"Coming due in {SOON_DAYS} days: " + _list(rep["coming_due"], lambda r: f"{_clip(r[0], 40)}: "
                                                         f"{_clip(r[1], 40)} {_short(r[2])}", n))
    other = []
    if rep["finish_moved"]:
        other.append(_list(rep["finish_moved"], lambda r: f"{_clip(r[0], 40)} finish {_short(r[1])} to "
                                                           f"{_short(r[2])}", 3))
    if rep["pulled_in"]:
        other.append(f"{len(rep['pulled_in'])} key date(s) pulled in")
    if rep["manager"]:
        other.append(_list(rep["manager"], lambda r: f"{_clip(r[0], 40)} manager now {_clip(r[2], 30) or 'none'}", 3))
    if rep["progress"]:
        other.append(_list(rep["progress"], lambda r: f"{_clip(r[0], 40)} {r[1]} to {r[2]}", 3))
    if rep["finished_kd"]:
        other.append(f"{len(rep['finished_kd'])} key date(s) met")
    if rep["added"]:
        other.append(f"{len(rep['added'])} new project(s): " + _list(rep["added"], _clip, 3))
    if rep["closed"]:
        other.append(f"{len(rep['closed'])} closed: " + _list(rep["closed"], _clip, 3))
    if rep["gone"]:
        other.append(f"{len(rep['gone'])} no longer visible: " + _list(rep["gone"], _clip, 3))
    if other:
        add("Also changed: " + "; ".join(other))
    if rep["still"]:
        label = "At Risk or Critical now" if rep["first"] else "Still At Risk or Critical"
        add(f"{label}: {len(rep['still'])} (" + _list(rep["still"], lambda r: f"{_clip(r[0], 40)}, {r[1]}", n) + ")")
    if not out:
        add("Nothing turned At Risk or Critical, no key date slipped, and none is due in the next "
            f"{SOON_DAYS} days.")
    basis = ("the first pulse, so nothing to compare yet" if rep["first"]
             else f"compared with {fmt_day(rep['since'])}")
    extra = []
    if rep["skipped"]:
        extra.append(f"{rep['skipped']} more projects left out")
    if rep["errors"]:
        extra.append(f"{rep['errors']} project(s) whose key dates couldn't be read")
    add(f"{rep['projects']} projects, {rep['key_dates']} key dates ({basis}"
        + (f"; {'; '.join(extra)}" if extra else "") + ").")
    return out
