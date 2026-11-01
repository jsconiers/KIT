#!/usr/bin/env python3
"""Tests for kit-wrap (the end-of-day wrap, no model call) and todo keeping a done work item's [work] tag.
Everything happens in a temp folder with a fake Kit; the calendar is a JSON file or a small command.

Run: python3 tests/test_wrap.py
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
bin_ = kit / ".install/shared/bin"
bin_.mkdir(parents=True)
morning = kit / ".install/shared/morning"
morning.mkdir(parents=True)
CONFIG = morning / "config"
CONFIG.write_text('OWNER_NAME="Alex"\n')
(kit / "memory/context").mkdir(parents=True)
briefs = kit / "briefs"
(briefs / "preread").mkdir(parents=True)
for f in ("kit-wrap", "kit-meetprep", "todo"):
    shutil.copy(SHARED / "bin" / f, bin_ / f)
shutil.copy(SHARED / "kit_daily.py", kit / ".install/shared/kit_daily.py")
shutil.copy(SHARED / "kit_queue.py", kit / ".install/shared/kit_queue.py")

QUEUE = """# Queue

## Alex

- [ ] **Payments design comments** [work]: due 05-Nov-2026 (added 01-Nov-2026)
- [ ] **Renew passport photo** : due 04-Nov-2026 (added 20-Oct-2026)
- [ ] **Vendor scorecard** [work]: due 06-Nov-2026 (added 05-Nov-2026)
- [ ] **Call the dentist**: due 06-Nov-2026 (added 02-Nov-2026)
- [ ] **Quarterly plan** [work]: due 20-Nov-2026 (added 01-Nov-2026)
- [ ] **No date at all** (added 01-Nov-2026)
- [ ] **Pick light or dark for the cover** (added 01-Nov-2026)

## Kit

- [ ] **Re-index the library** (added 05-Nov-2026)

## Waiting on others

- [ ] **Firewall change**: network team, since 28-Oct-2026

## Done

- [x] **Close out audit item** [work]: Alex, done 05-Nov-2026 (added 30-Oct-2026)
- [x] **Pick up the dry cleaning**: Alex, done 05-Nov-2026 (added 04-Nov-2026)
- [x] **Rebuild the dashboard**: Kit, done 05-Nov-2026 (added 05-Nov-2026)
- [x] **Old thing** [work]: Alex, done 01-Nov-2026 (added 30-Oct-2026)
"""
(kit / "QUEUE.md").write_text(QUEUE)
(briefs / "pending-actions.md").write_text(
    "# Pending meeting actions\n\n"
    "- [action] Send the payments failover runbook | owner: owner | due: 10-Nov-2026 | project: payments | source: [PM]\n"
    "- [action] Book the room | owner: PM | due: no date | project: other | source: [PM] confirmed\n")
(briefs / "preread" / "2026-11-04-payments-gds.md").write_text(
    "# Pre-read: Payments GDS.docx\n\n- **For:** Architecture review Payments, 06-Nov-2026\n")
EVENTS = [
    {"title": "Architecture review: Payments", "start": "2026-11-06T09:00:00", "end": "2026-11-06T10:00:00",
     "location": "Building 3, room 210", "attendees": 7, "has_attendees": True, "calendar": "Work"},
    {"title": "Lunch with Sam", "start": "2026-11-06T12:00:00", "end": "2026-11-06T13:00:00",
     "location": "https://teams.example.com/l/xyz", "attendees": 1, "has_attendees": True, "calendar": "Work"},
    {"title": "Pick up Oreo", "start": "2026-11-06 16:30", "end": "2026-11-06 17:00", "calendar": "Home",
     "location": "12 Main St"},
    {"title": "Status sync", "start": "2026-11-06T15:00:00", "end": "2026-11-06T15:30:00", "calendar": "Work",
     "my_response": "declined"},
    {"title": "Veterans Day", "start": "2026-11-06", "end": "2026-11-06", "all_day": True,
     "calendar": "US Holidays|Subscribed"},
    {"title": "Team offsite planning", "start": "2026-11-06", "end": "2026-11-06", "all_day": True, "calendar": "Work"},
    {"title": "Today's standup", "start": "2026-11-05T09:00:00", "end": "2026-11-05T09:15:00", "calendar": "Work"},
]
cal = tmp / "cal.json"
cal.write_text(json.dumps(EVENTS))
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-11-05", KIT_NOW="2026-11-05T17:30:00", PYTHONUTF8="1")
for k in ("WRAP_CALENDAR_CMD", "WRAP_CALENDAR_SIDE", "WRAP_WORKDAYS", "CALENDAR_JSON_CMD"):
    env.pop(k, None)


def wrap(*args, **extra):
    e = dict(env, **extra)
    return subprocess.run([sys.executable, str(bin_ / "kit-wrap"), *args], capture_output=True, text=True,
                          env=e, encoding="utf-8")


def texts():
    return {n: (briefs / n).read_text(encoding="utf-8") for n in
            ("eod-text.txt", "eod-text-work.txt", "eod-text-personal.txt")}


# ---- a Thursday: the next working day is Friday -------------------------------------------------
r = wrap("--calendar-json", str(cal))
out = r.stdout
ok(r.returncode == 0, "prints the wrap", r.stderr)
ok(out.startswith("# End of day, Thu 05-Nov-2026"), "titled with today", out[:80])
ok("**Close out audit item** [work]" in out and "**Pick up the dry cleaning** (personal)" in out,
   "done today: work and personal items, in the wrap file")
ok("**Old thing**" not in out, "an item done on another day isn't counted")
ok("Kit finished 1 of its own item." in out, "Kit's own finished items are counted apart")
ok("New today: 1 item added" in out, "your items added today are counted (Kit's own aren't)", out)
ok("## Moves to tomorrow" in out and "**Payments design comments** [work]: due 05-Nov-2026" in out
   and "**Renew passport photo** (personal): due 04-Nov-2026, overdue" in out, "what moves to tomorrow, overdue marked")
ok("## Tomorrow, Fri 06-Nov" in out and "Due: **Vendor scorecard** [work]" in out
   and "Due: **Call the dentist** (personal)" in out, "due on the next working day")
ok("Quarterly plan" not in out and "No date at all" not in out, "later and undated items stay out")
ok("3 meetings; the first at 09:00: **Architecture review: Payments**" in out, "the first meeting, declined left out", out)
ok("- 16:30 Pick up Oreo (needs: travel)" in out, "a start written with a space; one short word in common isn't a related to-do", out)
ok("Open to-dos about it: **Payments design comments**" in out, "needs: the to-dos that share its words")
ok("not yet confirmed: 1" in out, "needs: the pending meeting action about it (a confirmed one isn't counted)")
ok("Pre-read ready: briefs/preread/2026-11-04-payments-gds.md" in out, "needs: the pre-read made for it")
ok("In person: Building 3, room 210; allow travel time" in out and "7 invited" in out, "needs: where it is, and who")
ok("- 12:00 Lunch with Sam" in out, "the other meetings, online ones without a travel note")
ok("Veterans Day" not in out and "Today's standup" not in out, "holidays and other days' events left out")
ok("All day: Team offsite planning" in out, "all-day events listed apart")
ok("On others: 1 item" in out and "1 meeting actions" in out, "waiting on others and decisions waiting")
ok(not (briefs / "eod-2026-11-05.md").exists(), "printing writes nothing")

# ---- writing the files and the texts --------------------------------------------------------------
r = wrap("--write", "--calendar-json", str(cal))
ok(r.returncode == 0 and (briefs / "eod-2026-11-05.md").exists(), "--write writes the wrap file", r.stderr)
t = texts()
ok(all(v.splitlines()[0] == "Kit · wrap Thu 05-Nov" for v in t.values()), "every text starts with the day")
ok(all(v.splitlines()[-1] == "Full wrap: briefs/eod-2026-11-05.md" for v in t.values()), "and ends with the file")
ok(all(len(v) < 600 for v in t.values()), "every text is under 600 characters")
personal_titles = ("dry cleaning", "passport", "dentist")
work_titles = ("Close out audit", "Payments design", "Vendor scorecard", "Architecture review")
ok(not any(p in v for v in t.values() for p in personal_titles), "personal items are never named in a text")
ok(not any(w in t["eod-text-personal.txt"] for w in work_titles), "the personal text has no work items")
ok("Done: Close out audit item" in t["eod-text-work.txt"] and "Moves to tomorrow: Payments design comments"
   in t["eod-text-work.txt"], "the work text names work items", t["eod-text-work.txt"])
ok("Tomorrow: 3 meetings, first 09:00 (needs: 1 to-do, 1 to confirm, travel)" in t["eod-text-work.txt"],
   "the first meeting and its needs go in the work text by default", t["eod-text-work.txt"])
ok("Done today: 1 personal item" in t["eod-text-personal.txt"] and "Moves to tomorrow: 1 personal"
   in t["eod-text-personal.txt"], "the personal text counts personal items", t["eod-text-personal.txt"])
ok("Done today: 2 (1 personal)" in t["eod-text.txt"] and "Moves to tomorrow: 2 (1 personal)" in t["eod-text.txt"],
   "the combined text counts both", t["eod-text.txt"])
if os.name != "nt":
    mode = stat.S_IMODE((briefs / "eod-2026-11-05.md").stat().st_mode)
    ok(mode == 0o600, "the wrap file is readable only by you", oct(mode))

r = wrap("--write", "--calendar-json", str(cal), WRAP_CALENDAR_SIDE="personal")
t = texts()
ok("Tomorrow: 3 meetings, first 09:00" in t["eod-text-personal.txt"] and "meetings" not in t["eod-text-work.txt"],
   "WRAP_CALENDAR_SIDE=personal moves the calendar line to the personal text")

# ---- hooks: a section, and a line for a text ---------------------------------------------------------
hooks = kit / ".install/wrap.d"
hooks.mkdir()
hook = hooks / "20-weekend"
hook.write_text(f"#!{sys.executable}\nimport sys\nprint('Weekend')\nprint('Preaching ' + sys.argv[1])\n"
                "print('Text: Sermon is final')\nprint('Text: [work] Badge renewal Monday')\n")
hook.chmod(0o755)
(hooks / "30-broken").write_text(f"#!{sys.executable}\nraise SystemExit(3)\n")
(hooks / "30-broken").chmod(0o755)
(hooks / "40-not-executable").write_text("print('no')\n")
if os.name != "nt":
    r = wrap("--write", "--calendar-json", str(cal))
    out = (briefs / "eod-2026-11-05.md").read_text(encoding="utf-8")
    t = texts()
    ok("## Weekend" in out and "- Preaching 2026-11-06" in out, "a hook adds a section, given the next working day", out)
    ok("Sermon is final" in t["eod-text-personal.txt"] and "Sermon is final" not in out,
       "a hook's Text: line goes in the personal text, not the file")
    ok("Badge renewal Monday" in t["eod-text-work.txt"] and "Badge renewal" not in t["eod-text-personal.txt"],
       "a [work] Text: line goes in the work text only")
    ok("no" not in out.split("## Weekend")[1].split("_Information")[0].split("\n")[0], "a hook that fails is skipped")
shutil.rmtree(hooks)

# ---- a Friday: the next working day is Monday ---------------------------------------------------------
fri = dict(KIT_TODAY="2026-11-06", KIT_NOW="2026-11-06T15:30:00")
r = wrap(**fri, CALENDAR_JSON_CMD=f"{sys.executable} -c print([])")
out = r.stdout
ok("## Moves to Monday" in out and "## Monday, Mon 09-Nov" in out, "after a Friday, the wrap looks to Monday", out)
ok("Monday's calendar isn't in reach (set WRAP_CALENDAR_CMD)" in out,
   "CALENDAR_JSON_CMD covers only tomorrow, so Monday's meetings need WRAP_CALENDAR_CMD")
day_cmd = tmp / "day.py"
day_cmd.write_text("import json, sys\nprint(json.dumps([{'title': 'Monday kickoff', 'start': sys.argv[1] + 'T08:30:00'}]))\n")
r = wrap(**fri, WRAP_CALENDAR_CMD=f'"{sys.executable}" "{day_cmd}" {{day}}')
ok("1 meeting; the first at 08:30: **Monday kickoff**" in r.stdout, "WRAP_CALENDAR_CMD gets the day in {day}", r.stdout)
r = wrap(**fri, WRAP_WORKDAYS="1 2 3 4 5 6", CALENDAR_JSON_CMD=f"{sys.executable} -c print([])")
ok("## Moves to tomorrow" in r.stdout, "WRAP_WORKDAYS changes the next working day")
CONFIG.write_text('OWNER_NAME="Alex"\nWRAP_WORKDAYS="1 2 3 4"\n')
r = wrap(KIT_TODAY="2026-11-05", CALENDAR_JSON_CMD="")
ok("## Moves to Monday" in r.stdout and "Calendar: no calendar command set" in r.stdout,
   "settings come from Kit's config too", r.stdout[:400])
CONFIG.write_text('OWNER_NAME="Alex"\n')
r = wrap(CALENDAR_JSON_CMD=f'"{tmp / "missing-command"}"')
ok(r.returncode == 0 and "Calendar: the calendar command didn't answer" in r.stdout, "a broken calendar command is noted")
r = wrap("--no-calendar")
ok("Calendar: left out" in r.stdout, "--no-calendar leaves it out")

# ---- an empty day -----------------------------------------------------------------------------------------
(kit / "QUEUE.md").write_text("# Queue\n\n## Alex\n\n## Done\n")
(briefs / "pending-actions.md").unlink()
r = wrap("--write", "--no-calendar", KIT_TODAY="2026-11-10")
t = texts()
ok("Nothing of yours checked off today." in r.stdout or (briefs / "eod-2026-11-10.md").read_text().count("Nothing of yours"),
   "an empty day says so")
ok(t["eod-text-personal.txt"].splitlines()[1] == "Nothing today." and t["eod-text-work.txt"].splitlines()[1] == "Nothing today.",
   "an empty side says Nothing today.")

# ---- todo keeps a done work item's [work] tag ----------------------------------------------------------------
(kit / "QUEUE.md").write_text("# Queue\n\n## Alex\n\n- [ ] **Ship it** [work]: due 05-Nov-2026 (added 01-Nov-2026)\n"
                              "- [ ] **Groceries** (added 01-Nov-2026)\n\n## Done\n")
for n in ("1", "1"):
    subprocess.run([sys.executable, str(bin_ / "todo"), "done", n], capture_output=True, text=True,
                   env=dict(env, HOME=str(tmp)))
q = (kit / "QUEUE.md").read_text()
ok("- [x] **Ship it** [work]: Alex, done " in q, "todo done keeps the [work] tag", q)
ok("- [x] **Groceries**: Alex, done " in q, "and a personal item stays untagged")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nkit-wrap tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
