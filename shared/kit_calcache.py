"""kit_calcache: the calendar cache behind the brief's fallback, for mornings when Outlook doesn't answer.

When the calendar works, the morning and weekly runs save what the calendar command printed (kitmail calendar
--json or CALENDAR_JSON_CMD's shape: a JSON list of events with start, end, all_day, title or subject, and
my_response) to .install/cache/calendar-YYYY-MM-DD.json, owner-only (0600), and keep CALENDAR_CACHE_KEEP days
(14). When Outlook is down, kit-degraded and the model run use the newest copy that covers today:

  1. a copy saved on or before today whose range covers today: today's events from it, labelled
     "from the calendar as of <when it was saved>; may be stale"
  2. else the copy from the same weekday one or two weeks back: its recurring events (all its events when the
     calendar doesn't say which repeat), labelled as likely only, from that day's calendar
  3. else nothing, and the brief says the calendar is unavailable

A copy covers the day it was saved through the later of its last event and CALENDAR_CACHE_DAYS - 1 days after
(1 by default: the command covers today only; set it to the look-ahead of CALENDAR_CACHE_CMD).
"""
import datetime as dt
import json
import os
import pathlib

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
WEEKDAYS = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()


def fmt(d):
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def cache_dir(kit):
    return pathlib.Path(kit) / ".install/cache"


def event_day(e):
    s = str(e.get("start") or "")[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def save(kit, events, days=1, now=None, keep=14):
    """Write today's copy (replacing an earlier one from today) and prune copies older than `keep` days.
    Returns the path written."""
    now = now or dt.datetime.now()
    if not isinstance(events, list):
        raise ValueError("the calendar output isn't a JSON list")
    d = cache_dir(kit)
    d.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(d, 0o700)
    today = now.date()
    last = max([x for x in (event_day(e) for e in events if isinstance(e, dict)) if x] or [today])
    covers_to = max(last, today + dt.timedelta(days=max(1, int(days)) - 1))
    doc = {"saved": now.isoformat(timespec="minutes"), "covers_from": today.isoformat(),
           "covers_to": covers_to.isoformat(), "events": events}
    path = d / f"calendar-{today.isoformat()}.json"
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    os.replace(tmp, path)
    if os.name != "nt":
        os.chmod(path, 0o600)
    prune(kit, today, keep)
    return path


def prune(kit, today, keep=14):
    for p in cache_dir(kit).glob("calendar-*.json"):
        try:
            day = dt.date.fromisoformat(p.stem[len("calendar-"):])
        except ValueError:
            continue
        if (today - day).days >= keep:
            try:
                p.unlink()
            except OSError:
                pass


def copies(kit):
    """[(saved_date, doc)], newest first, skipping unreadable files."""
    out = []
    for p in cache_dir(kit).glob("calendar-*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8-sig"))
            day = dt.date.fromisoformat(p.stem[len("calendar-"):])
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("events"), list):
            out.append((day, doc))
    return sorted(out, key=lambda r: (r[0], str(r[1].get("saved"))), reverse=True)


def _declined(e):
    return str(e.get("my_response") or "").lower() in ("declined", "decline")


def _recurring_flag(e):
    for k in ("recurring", "is_recurring", "isRecurring", "recurrence"):
        if k in e:
            return bool(e.get(k))
    return None


def _saved_label(doc):
    try:
        s = dt.datetime.fromisoformat(str(doc.get("saved")))
        return f"{fmt(s.date())} {s:%H:%M}"
    except ValueError:
        return str(doc.get("saved") or "an earlier run")


def lookup(kit, day=None):
    """(events, label, kind) for `day` (today by default). kind is "cache", "recurring", or None."""
    day = day or dt.date.today()
    all_copies = copies(kit)
    for saved, doc in all_copies:
        try:
            start = dt.date.fromisoformat(str(doc.get("covers_from") or saved.isoformat()))
            end = dt.date.fromisoformat(str(doc.get("covers_to") or saved.isoformat()))
        except ValueError:
            continue
        if saved <= day and start <= day <= end:
            evs = [e for e in doc["events"] if isinstance(e, dict) and event_day(e) == day and not _declined(e)]
            return evs, f"from the calendar as of {_saved_label(doc)}; may be stale", "cache"
    for weeks in (1, 2):
        back = day - dt.timedelta(days=7 * weeks)
        for saved, doc in all_copies:
            evs = [e for e in doc["events"] if isinstance(e, dict) and event_day(e) == back and not _declined(e)]
            if not evs:
                continue
            flags = [_recurring_flag(e) for e in evs]
            if any(f is not None for f in flags):
                evs = [e for e, f in zip(evs, flags) if f]
                which = "its recurring meetings"
            else:
                evs = [e for e in evs if not e.get("all_day")]
                which = "its meetings (the calendar doesn't say which repeat)"
            if not evs:
                continue
            shifted = []
            for e in evs:
                e = dict(e)
                e["start"] = day.isoformat() + str(e.get("start"))[10:]
                if e.get("end"):
                    e["end"] = day.isoformat() + str(e.get("end"))[10:]
                shifted.append(e)
            return (shifted, f"likely only: {which} from {WEEKDAYS[back.weekday()]} {fmt(back)}'s calendar, as of "
                    f"{_saved_label(doc)}; recurring meetings only if they still hold, and one-off meetings and "
                    "changes since then are missing", "recurring")
    return [], "", None


def rows(events):
    """[(when, title)] sorted, all-day first: the shape kit-degraded prints."""
    out = []
    for e in events:
        title = str(e.get("title") or e.get("subject") or "(no title)").strip()
        title = title if len(title) <= 70 else title[:69] + "…"
        when = "all day" if e.get("all_day") else str(e.get("start") or "")[11:16]
        out.append((when, title))
    out.sort(key=lambda r: (r[0] != "all day", r[0]))
    return out
