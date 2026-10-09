#!/usr/bin/env python3
# UNTESTED on Windows -- validate on a real Windows box with Outlook installed.
#
# kitcal (Windows): Kit's calendar tool, driving the installed desktop Outlook
# via COM (win32com.client / pywin32). This is the Windows counterpart to
# platform/mac/calendar/kitcal.swift (EventKit) and mirrors its CLI, output,
# and SAFETY GUARDS exactly.
#
# Safety, enforced here rather than left to the agent (same as the Mac tool):
# - Calendars and accounts listed under "exclude" in the config are never read
#   or written.
# - Events with attendees are never changed or deleted, so kitcal can't notify
#   anyone. (Outlook never sends on Save for an attendee-less appointment; we
#   additionally refuse to touch anything whose Recipients list is non-empty.)
# - Writes to read-only calendars are refused (PR_ACCESS / MAPI_ACCESS check).
#
#   kitcal calendars
#   kitcal events [--from DATE] [--to DATE] [--cal NAME ...]
#   kitcal free [--date DATE] [--from HH:MM] [--to HH:MM]
#   kitcal add --title T (--start "DATE HH:MM" --end "DATE HH:MM" | --all-day --date DATE)
#              [--cal NAME] [--location L] [--notes N] [--alert MINUTES]
#   kitcal move --id ID --start "DATE HH:MM" [--end "DATE HH:MM"] [--span this|future]
#   kitcal update --id ID [--title T] [--location L] [--notes N] [--cal NAME] [--span this|future]
#   kitcal delete --id ID [--span this|future]
#
# DATE is YYYY-MM-DD, "today", or "tomorrow". Output is JSON. Config:
# %USERPROFILE%\Claude\Agents\kit\.install\calendar\config.json
#     = {"default": "...", "exclude": ["..."]}
#
# Because pywin32 / Outlook do not exist on macOS, this file is written
# defensively and has NOT been executed. See README.md "Manual test".

import json
import os
import sys
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Outlook / COM enum constants (so we don't depend on win32com.client.constants,
# which is only populated after a makepy type-library build).
# ---------------------------------------------------------------------------
OL_FOLDER_CALENDAR = 9          # olFolderCalendar (GetDefaultFolder)
OL_APPOINTMENT_ITEM = 1         # olAppointmentItem (Folder.DefaultItemType)

# OlRecurrenceState
OL_NOT_RECURRING = 0            # olApptNotRecurring
OL_MASTER = 1                   # olApptMaster
OL_OCCURRENCE = 2               # olApptOccurrence
OL_EXCEPTION = 3                # olApptException

# OlBusyStatus (0 == free). Anything non-zero counts as "busy", mirroring the
# Mac tool's `availability != .free`.
OL_FREE = 0

# PR_ACCESS (folder access rights) via PropertyAccessor + the MAPI access flags.
PR_ACCESS = "http://schemas.microsoft.com/mapi/proptag/0x0FF40003"
MAPI_ACCESS_MODIFY = 0x00000001
MAPI_ACCESS_CREATE_CONTENTS = 0x00000010

CONFIG_PATH = os.path.join(
    os.path.expanduser("~"),
    "Claude", "Agents", "kit", ".install", "calendar", "config.json",
)

USAGE = (
    "kitcal calendars | events | free | add | move | update | delete  "
    "(see the top of kitcal.py)"
)


# ---------------------------------------------------------------------------
# Small helpers mirroring the Swift tool's fail()/emit().
# ---------------------------------------------------------------------------
def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def emit(obj):
    # Match the Swift tool: pretty-printed with sorted keys, 2-space indent.
    print(json.dumps(obj, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Config.
# ---------------------------------------------------------------------------
def load_config():
    default_calendar = None
    exclude_names = set()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            d = data.get("default")
            if isinstance(d, str):
                default_calendar = d
            exc = data.get("exclude")
            if isinstance(exc, list):
                exclude_names = {str(x).lower() for x in exc}
    except Exception:
        # Missing or malformed config degrades to "no default, exclude nothing",
        # exactly like the Swift tool's optional-chaining read.
        pass
    return default_calendar, exclude_names


# ---------------------------------------------------------------------------
# Argument parsing (mirrors opt / opts / flag in the Swift tool).
# ---------------------------------------------------------------------------
class Args:
    def __init__(self, argv):
        self.argv = argv

    def opt(self, name):
        key = "--" + name
        for i, a in enumerate(self.argv):
            if a == key and i + 1 < len(self.argv):
                return self.argv[i + 1]
        return None

    def opts(self, name):
        key = "--" + name
        found = []
        i = 0
        while i < len(self.argv):
            if self.argv[i] == key and i + 1 < len(self.argv):
                found.append(self.argv[i + 1])
                i += 2
            else:
                i += 1
        return found

    def flag(self, name):
        return ("--" + name) in self.argv


# ---------------------------------------------------------------------------
# Date / time parsing and formatting (local time throughout, like the Mac tool
# which uses TimeZone.current).
# ---------------------------------------------------------------------------
def start_of_today():
    now = datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def day(s):
    v = (s or "").lower()
    if v in ("", "today"):
        return start_of_today()
    if v == "tomorrow":
        return start_of_today() + timedelta(days=1)
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        fail("Dates look like 2026-10-08, today, or tomorrow.")


def moment(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except Exception:
        fail('Times look like "2026-10-08 14:30".')


def show(d):
    return d.strftime("%Y-%m-%d %H:%M")


def show_day(d):
    return d.strftime("%Y-%m-%d")


def to_local_naive(dt):
    # Outlook returns pywintypes.datetime (a tz-aware datetime subclass) in
    # recent pywin32, or a naive datetime. Normalise to naive local time so all
    # of our comparisons line up.
    if dt is None:
        return None
    try:
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.astimezone()
            return dt.replace(tzinfo=None)
    except Exception:
        pass
    try:
        return datetime(dt.year, dt.month, dt.day,
                        getattr(dt, "hour", 0), getattr(dt, "minute", 0),
                        getattr(dt, "second", 0))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Outlook connection (graceful degradation if pywin32 / Outlook is missing).
# ---------------------------------------------------------------------------
def connect():
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        fail("kitcal needs pywin32. Install it with: pip install pywin32")
    try:
        import pythoncom
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass  # Already initialised on this thread; harmless.
    except Exception:
        pass
    import win32com.client as w32
    try:
        app = w32.Dispatch("Outlook.Application")
        ns = app.GetNamespace("MAPI")
    except Exception as exc:
        fail("Couldn't reach Outlook. Make sure desktop Outlook is installed "
             "and signed in. (" + str(exc) + ")")
    return app, ns


# ---------------------------------------------------------------------------
# Calendar discovery.
#
# There is no EventKit-style flat calendar list in Outlook, so we walk every
# store (account) and collect folders whose DefaultItemType is appointment.
# ---------------------------------------------------------------------------
def account_of(folder):
    try:
        name = folder.Store.DisplayName
        if name:
            return name
    except Exception:
        pass
    # Fallback: climb to the root folder's name.
    try:
        cur = folder
        for _ in range(32):  # defensive depth cap
            parent = cur.Parent
            pname = getattr(parent, "Name", None)
            if pname is None:
                break
            cur = parent
        return getattr(cur, "Name", "") or ""
    except Exception:
        return ""


def _walk(folder, out):
    try:
        if folder.DefaultItemType == OL_APPOINTMENT_ITEM:
            out.append(folder)
    except Exception:
        pass
    try:
        subs = folder.Folders
        count = subs.Count
    except Exception:
        return
    for i in range(1, count + 1):
        try:
            _walk(subs.Item(i), out)
        except Exception:
            continue


def all_calendar_folders(ns):
    out = []
    try:
        roots = ns.Folders
        count = roots.Count
    except Exception:
        count = 0
        roots = None
    if roots is not None:
        for i in range(1, count + 1):
            try:
                _walk(roots.Item(i), out)
            except Exception:
                continue
    # Always make sure the primary default calendar is represented, even if the
    # walk missed it for some odd profile layout.
    try:
        default_cal = ns.GetDefaultFolder(OL_FOLDER_CALENDAR)
        if not any(_same_folder(default_cal, f) for f in out):
            out.append(default_cal)
    except Exception:
        pass
    return out


def _same_folder(a, b):
    try:
        return a.EntryID == b.EntryID and a.StoreID == b.StoreID
    except Exception:
        return a is b


def folder_ref(folder):
    return folder.Name + "|" + account_of(folder)


def is_excluded(folder, exclude_names):
    try:
        title = folder.Name.lower()
    except Exception:
        title = ""
    account = account_of(folder).lower()
    return title in exclude_names or account in exclude_names


def allowed_calendars(ns, exclude_names):
    return [f for f in all_calendar_folders(ns) if not is_excluded(f, exclude_names)]


def folder_access(folder):
    try:
        return int(folder.PropertyAccessor.GetProperty(PR_ACCESS))
    except Exception:
        return None


def folder_writable(folder):
    # Best-effort read of the folder's MAPI access rights. If we can't read the
    # property (older Outlook, odd store), assume writable and let Outlook's own
    # Save enforce it -- the write path below still refuses when the property is
    # readable and says read-only.
    a = folder_access(folder)
    if a is None:
        return True
    return bool(a & (MAPI_ACCESS_CREATE_CONTENTS | MAPI_ACCESS_MODIFY))


def ensure_writable(folder, name):
    a = folder_access(folder)
    if a is not None and not (a & (MAPI_ACCESS_CREATE_CONTENTS | MAPI_ACCESS_MODIFY)):
        fail(name + " is read-only.")


def calendar_named(ns, name, default_calendar, exclude_names):
    # Accepts "Name" or "Name|Account". Refuses a bare name that matches more
    # than one calendar. Mirrors calendarNamed() in the Swift tool.
    raw = name if name is not None else (default_calendar or "")
    if not raw:
        fail("Name a calendar with --cal; no default is set.")
    parts = [p.strip() for p in raw.split("|")]
    title = parts[0].lower()
    account = parts[1].lower() if len(parts) > 1 else None
    if title in exclude_names or (account is not None and account in exclude_names):
        fail("That calendar is off-limits.")
    matches = []
    for f in allowed_calendars(ns, exclude_names):
        try:
            if f.Name.lower() == title and (account is None or account_of(f).lower() == account):
                matches.append(f)
        except Exception:
            continue
    if not matches:
        fail("No calendar named " + raw + ". Run: kitcal calendars")
    if len(matches) > 1:
        refs = ", ".join(folder_ref(f) for f in matches)
        fail("More than one calendar is named " + parts[0] + ": " + refs + ". Use one of those.")
    return matches[0]


# ---------------------------------------------------------------------------
# Event querying (recurrence-aware).
#
# We sort each folder's Items ascending by Start, turn on IncludeRecurrences
# (which expands recurring series into occurrences), then iterate and break as
# soon as Start passes the window end. This is the locale-independent idiom and
# avoids the Items.Restrict() date-format pitfalls -- but it REQUIRES the early
# break, because an open-ended recurring series would otherwise expand forever.
# ---------------------------------------------------------------------------
def query_folder(folder, win_start, win_end):
    out = []
    try:
        items = folder.Items
        items.IncludeRecurrences = True
        items.Sort("[Start]")
    except Exception:
        return out
    try:
        it = items.GetFirst()
    except Exception:
        return out
    guard = 0
    while it is not None:
        guard += 1
        if guard > 100000:  # defensive: never loop unbounded
            break
        try:
            s = to_local_naive(it.Start)
            e = to_local_naive(it.End)
        except Exception:
            try:
                it = items.GetNext()
                continue
            except Exception:
                break
        if s is None:
            try:
                it = items.GetNext()
                continue
            except Exception:
                break
        if s > win_end:
            break  # sorted ascending -> nothing further can overlap
        # Overlap test matches EventKit's predicate (start < end AND end > start).
        if e is not None and e > win_start and s < win_end:
            out.append(it)
        try:
            it = items.GetNext()
        except Exception:
            break
    return out


def query(folders, win_start, win_end):
    found = []
    for f in folders:
        found.extend(query_folder(f, win_start, win_end))
    return found


# ---------------------------------------------------------------------------
# Describing / identifying events.
# ---------------------------------------------------------------------------
def event_entry_id(e):
    # For a recurring occurrence, EntryID returns the MASTER's id -- same as
    # EventKit's shared eventIdentifier -- so the start time in the composite id
    # is what disambiguates a specific occurrence.
    try:
        return e.EntryID or ""
    except Exception:
        try:
            return e.GlobalAppointmentID or ""
        except Exception:
            return ""


def attendee_count(e):
    try:
        return int(e.Recipients.Count)
    except Exception:
        return 0


def is_all_day(e):
    try:
        return bool(e.AllDayEvent)
    except Exception:
        return False


def is_recurring(e):
    try:
        return bool(e.IsRecurring)
    except Exception:
        try:
            return e.RecurrenceState != OL_NOT_RECURRING
        except Exception:
            return False


def ident(e):
    return event_entry_id(e) + "|" + show(to_local_naive(e.Start))


def describe(e):
    start = to_local_naive(e.Start)
    end = to_local_naive(e.End)
    allday = is_all_day(e)
    cal_ref = ""
    try:
        parent = e.Parent
        cal_ref = parent.Name + "|" + account_of(parent)
    except Exception:
        cal_ref = ""
    d = {
        "id": ident(e),
        "title": _safe_str(getattr(e, "Subject", "")),
        "calendar": cal_ref,
        "start": show_day(start) if allday else show(start),
        "end": show_day(end) if allday else show(end),
        "all_day": allday,
        "recurring": is_recurring(e),
        "attendees": attendee_count(e),
    }
    loc = _safe_str(getattr(e, "Location", "") or "")
    if loc:
        d["location"] = loc
    return d


def _safe_str(v):
    try:
        return "" if v is None else str(v)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Locating an event by id, with the attendee + read-only safety guards.
# ---------------------------------------------------------------------------
def find_event(ns, id_str, exclude_names):
    parts = (id_str or "").split("|")
    if len(parts) != 2:
        fail("Use an id from kitcal events.")
    try:
        at = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
    except Exception:
        fail("Use an id from kitcal events.")
    entry = parts[0]
    folders = allowed_calendars(ns, exclude_names)
    # Search a window around the target start (mirrors the Mac -1d/+2d window).
    candidates = query(folders, at - timedelta(days=1), at + timedelta(days=2))
    hit = None
    for c in candidates:
        try:
            if event_entry_id(c) != entry:
                continue
            s = to_local_naive(c.Start)
            if s is not None and abs((s - at).total_seconds()) < 60:
                hit = c
                break
        except Exception:
            continue
    if hit is None:
        fail("Event not found. Run kitcal events again for a fresh id.")
    if attendee_count(hit) > 0:
        fail("That event has attendees, so changing it would notify them. "
             "Change it in Calendar yourself.")
    try:
        parent = hit.Parent
        if folder_access(parent) is not None and not folder_writable(parent):
            fail(parent.Name + " is read-only.")
    except SystemExit:
        raise
    except Exception:
        pass
    return hit


def recurrence_state(e):
    try:
        return int(e.RecurrenceState)
    except Exception:
        return OL_NOT_RECURRING


def guard_future_recurring(e, span):
    # EventKit supports editing "this and future" occurrences natively. Outlook
    # COM has no clean equivalent for arbitrary field/time edits of a recurring
    # series (you'd have to split the series into two, which is error-prone).
    # SAFE SUBSET: refuse move/update with --span future on a recurring event.
    # TODO: implement "this and future" by truncating the existing series and
    # creating a new master for the remainder, once this can be tested against a
    # real Outlook profile.
    if span == "future" and recurrence_state(e) in (OL_OCCURRENCE, OL_EXCEPTION, OL_MASTER):
        fail("Editing 'this and future' occurrences of a recurring event isn't "
             "supported through Outlook COM yet. Edit the series in Outlook, or "
             "re-run with --span this to change just this occurrence.")


# ---------------------------------------------------------------------------
# Command implementations.
# ---------------------------------------------------------------------------
def cmd_calendars(ns, args, default_calendar, exclude_names):
    def_lower = (default_calendar or "").lower()
    out = []
    for c in allowed_calendars(ns, exclude_names):
        try:
            ref = folder_ref(c)
            title = c.Name
        except Exception:
            continue
        is_default = def_lower == ref.lower() or def_lower == title.lower()
        out.append({
            "ref": ref,
            "writable": folder_writable(c),
            "default": is_default,
        })
    emit(out)


def cmd_events(ns, args, default_calendar, exclude_names):
    frm = day(args.opt("from"))
    to = day(args.opt("to") or args.opt("from")) + timedelta(days=1)
    names = args.opts("cal")
    if names:
        cals = [calendar_named(ns, n, default_calendar, exclude_names) for n in names]
    else:
        cals = allowed_calendars(ns, exclude_names)
    if not cals:
        emit([])
        return
    found = query(cals, frm, to)
    found_sorted = sorted(found, key=lambda e: to_local_naive(e.Start) or datetime.min)
    emit([describe(e) for e in found_sorted])


def cmd_free(ns, args, default_calendar, exclude_names):
    d = show_day(day(args.opt("date")))
    win_start = moment(d + " " + (args.opt("from") or "08:00"))
    win_end = moment(d + " " + (args.opt("to") or "21:00"))
    cals = allowed_calendars(ns, exclude_names)
    found = query(cals, win_start, win_end) if cals else []

    busy = []
    for e in found:
        if is_all_day(e):
            continue
        try:
            if int(e.BusyStatus) == OL_FREE:
                continue
        except Exception:
            pass  # unknown busy status -> treat as busy, like a non-free event
        s = to_local_naive(e.Start)
        en = to_local_naive(e.End)
        if s is None or en is None:
            continue
        busy.append((max(s, win_start), min(en, win_end)))
    busy.sort(key=lambda b: b[0])

    merged = []
    for b in busy:
        if merged and b[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b[1]))
        else:
            merged.append((b[0], b[1]))

    open_slots = []
    cursor = win_start
    for b in merged:
        if b[0] > cursor:
            open_slots.append({"from": show(cursor), "to": show(b[0])})
        cursor = max(cursor, b[1])
    if cursor < win_end:
        open_slots.append({"from": show(cursor), "to": show(win_end)})

    emit({
        "date": d,
        "busy": [{"from": show(b[0]), "to": show(b[1])} for b in merged],
        "free": open_slots,
    })


def cmd_add(ns, args, default_calendar, exclude_names):
    title = args.opt("title")
    if not title:
        fail("add needs --title.")
    target = calendar_named(ns, args.opt("cal"), default_calendar, exclude_names)
    ensure_writable(target, target.Name)
    try:
        appt = target.Items.Add()  # creates an appointment in THIS folder
    except Exception as exc:
        fail("Couldn't create the appointment: " + str(exc))
    appt.Subject = title

    if args.flag("all-day"):
        d = day(args.opt("date"))
        appt.AllDayEvent = True
        appt.Start = d
        appt.End = d + timedelta(days=1)
    else:
        start = moment(args.opt("start"))
        end = moment(args.opt("end"))
        if end <= start:
            fail("--end has to be after --start.")
        appt.Start = start
        appt.End = end

    loc = args.opt("location")
    if loc is not None:
        appt.Location = loc
    notes = args.opt("notes")
    if notes is not None:
        appt.Body = notes
    alert = args.opt("alert")
    if alert is not None:
        try:
            appt.ReminderSet = True
            appt.ReminderMinutesBeforeStart = int(float(alert))
        except Exception:
            pass

    try:
        appt.Save()
    except Exception as exc:
        fail("Couldn't save: " + str(exc))
    emit({"added": describe(appt)})


def cmd_move(ns, args, default_calendar, exclude_names):
    e = find_event(ns, args.opt("id"), exclude_names)
    span = args.opt("span") or "this"
    guard_future_recurring(e, span)
    start_old = to_local_naive(e.Start)
    end_old = to_local_naive(e.End)
    length = (end_old - start_old) if (start_old and end_old) else timedelta(0)
    start = moment(args.opt("start"))
    end_arg = args.opt("end")
    end = moment(end_arg) if end_arg is not None else (start + length)
    e.Start = start
    e.End = end
    try:
        e.Save()  # on a recurring occurrence this creates an exception (== .thisEvent)
    except Exception as exc:
        fail("Couldn't save: " + str(exc))
    emit({"moved": describe(e)})


def cmd_update(ns, args, default_calendar, exclude_names):
    e = find_event(ns, args.opt("id"), exclude_names)
    span = args.opt("span") or "this"
    guard_future_recurring(e, span)
    t = args.opt("title")
    if t is not None:
        e.Subject = t
    loc = args.opt("location")
    if loc is not None:
        e.Location = loc
    notes = args.opt("notes")
    if notes is not None:
        e.Body = notes
    cal = args.opt("cal")
    moved_item = e
    if cal is not None:
        target = calendar_named(ns, cal, default_calendar, exclude_names)
        ensure_writable(target, target.Name)
        try:
            e.Save()  # persist field edits before the move
            moved_item = e.Move(target)
        except Exception as exc:
            fail("Couldn't move to " + target.Name + ": " + str(exc))
    try:
        moved_item.Save()
    except Exception as exc:
        fail("Couldn't save: " + str(exc))
    emit({"updated": describe(moved_item)})


def cmd_delete(ns, args, default_calendar, exclude_names):
    e = find_event(ns, args.opt("id"), exclude_names)
    span = args.opt("span") or "this"
    gone = describe(e)
    state = recurrence_state(e)

    if span == "future" and state in (OL_OCCURRENCE, OL_EXCEPTION):
        # Delete this occurrence AND all later ones by truncating the series --
        # the closest Outlook-COM equivalent of EventKit's .futureEvents delete.
        # TODO: validate the PatternEndDate off-by-one against a real recurring
        # series (daily vs weekly vs monthly) on Windows.
        try:
            occ_start = to_local_naive(e.Start)
            store_id = e.Parent.StoreID
            master = ns.GetItemFromID(event_entry_id(e), store_id)
            pat = master.GetRecurrencePattern()
            pat_start = to_local_naive(pat.PatternStartDate)
            if pat_start is not None and occ_start.date() <= pat_start.date():
                master.Delete()  # this is the first occurrence -> drop the series
            else:
                pat.PatternEndDate = (occ_start - timedelta(days=1))
                master.Save()
        except Exception as exc:
            fail("Couldn't delete this-and-future occurrences: " + str(exc))
    else:
        try:
            e.Delete()
        except Exception as exc:
            fail("Couldn't delete: " + str(exc))

    emit({"deleted": gone})


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "help"
    rest = argv[1:]
    args = Args(rest)

    if cmd in ("help", "--help"):
        print(USAGE)
        sys.exit(0)

    if cmd not in ("calendars", "events", "free", "add", "move", "update", "delete"):
        print(USAGE)
        sys.exit(1)

    default_calendar, exclude_names = load_config()
    _app, ns = connect()

    handlers = {
        "calendars": cmd_calendars,
        "events": cmd_events,
        "free": cmd_free,
        "add": cmd_add,
        "move": cmd_move,
        "update": cmd_update,
        "delete": cmd_delete,
    }
    handlers[cmd](ns, args, default_calendar, exclude_names)


if __name__ == "__main__":
    main()
