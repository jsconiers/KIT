#!/bin/bash
# Tests kit-holds (draft calendar holds as .ics files) with a fixture Kit and calendar. Nothing real
# is touched and no calendar app is opened.
#   bash tests/test_holds.sh
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 - "$HERE" <<'PY'
import json, os, pathlib, re, subprocess, sys, tempfile, shutil
here = pathlib.Path(sys.argv[1])
tool = here / "shared/bin/kit-holds"
tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / "memory/context").mkdir(parents=True)
(kit / "briefs").mkdir()
(kit / "memory/context/calendar.md").write_text(
    "# Calendar setup\n\n- **Working hours and time zone:** 09:00-17:00 America/New_York\n")
(kit / "QUEUE.md").write_text("""# Queue

## Alex

- [ ] **Review the payments design** [work]: due 22-Oct-2026 (added 10-Oct-2026)
- [ ] **Dentist forms**: due 22-Oct-2026 (added 10-Oct-2026)
- [ ] **Far future item** [work]: due 30-Dec-2026 (added 10-Oct-2026)

## Kit

## Done
""")
cal = tmp / "cal.json"
cal.write_text(json.dumps([
    {"title": "Standup", "start": "2026-10-21T09:00:00", "end": "2026-10-21T09:30:00", "has_attendees": True},
    {"title": "Design review, payments; phase 2", "start": "2026-10-21T14:00:00",
     "end": "2026-10-21T15:00:00", "has_attendees": True},
    {"title": "Busy block", "start": "2026-10-22T09:00:00", "end": "2026-10-22T17:00:00", "has_attendees": False},
    {"title": "Holiday", "start": "2026-10-21", "all_day": True},
]))
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-21", KIT_NOW="2026-10-21T08:00:00",
           TZ="America/New_York", KIT_HOLDS_OPENER="true")
PASS = FAIL = 0
def ok(c, name, detail=""):
    global PASS, FAIL
    if c: PASS += 1; print("ok  ", name)
    else: FAIL += 1; print("FAIL", name, detail)
def run(*a):
    return subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)

day = kit / "briefs/holds/2026-10-21"
long_title = "Deep work on the market data platform resilience review, with notes; commas, and a backslash \\ é"
r = run("propose", "--calendar-json", str(cal), "--block", f"2026-10-21 10:00 90m {long_title}",
        "--block", "2026-10-21 14:30 60m Clashing block", "--block", "2026-10-21 18:00 30m Evening block",
        "--block", "2026-10-24 10:00 60m Saturday block", "--from-queue", "--meeting-prep", "30m", "--alarm", "10")
ok(r.returncode == 0, "propose runs", r.stderr)
files = sorted(day.glob("*.ics"))
ok(len(files) >= 3, "draft .ics files written", str([f.name for f in files]))
texts = {f.name: f.read_bytes() for f in files}
allb = b"".join(texts.values())
ok(all(b"\r\n" in t and not re.search(rb"[^\r]\n", t) for t in texts.values()), "every line ends CRLF")
ok(all(len(line) <= 75 for t in texts.values() for line in t.split(b"\r\n")), "no line longer than 75 octets")
ok(any(b"\r\n " in t for t in texts.values()), "a long line is folded with CRLF + space")
deep = next(t for n, t in texts.items() if "deep-work" in n)
unfolded = deep.replace(b"\r\n ", b"").decode()
ok("SUMMARY:Hold: Deep work on the market data platform resilience review\\, with notes\\; commas\\, and a backslash \\\\ é" in unfolded,
   "commas, semicolons and backslashes are escaped; UTF-8 survives folding", unfolded[:400])
ok("DTSTART;TZID=America/New_York:20261021T100000" in unfolded and "DTEND;TZID=America/New_York:20261021T113000" in unfolded,
   "DTSTART/DTEND carry the TZID")
ok("BEGIN:VTIMEZONE" in unfolded and "TZID:America/New_York" in unfolded and "BEGIN:DAYLIGHT" in unfolded
   and "BEGIN:STANDARD" in unfolded, "a VTIMEZONE with daylight and standard parts is included")
ok(b"ATTENDEE" not in allb and b"ORGANIZER" not in allb, "no ATTENDEE or ORGANIZER lines")
ok(b"METHOD:PUBLISH" in allb and b"TRANSP:OPAQUE" in allb, "METHOD:PUBLISH and TRANSP:OPAQUE")
ok(b"BEGIN:VALARM" in deep and b"TRIGGER:-PT10M" in deep, "the optional alarm is included")
ok(not any("clashing" in n for n in texts), "a requested block that clashes is skipped")
ok("Clashing block" in r.stdout and "clashes" in r.stdout, "the clash is reported")
ok(not any("evening" in n for n in texts) and "outside working hours" in r.stdout, "a block outside working hours is skipped")
ok(not any("saturday" in n for n in texts), "a weekend block is skipped")
prep = [t.replace(b"\r\n ", b"").decode() for n, t in texts.items() if "prep-review" in n]
ok(len(prep) == 1 and "20261021T" in prep[0], "queue prep lands on a free slot the day before (the due day is fully busy)",
   str(prep)[:200])
ok(any("prep-personal-item" in n for n in texts) and not any("dentist" in n for n in texts),
   "a personal to-do's hold is named 'personal item'")
ok(not any("far-future" in n for n in texts), "to-dos beyond --days are ignored")
mprep = [t.replace(b"\r\n ", b"").decode() for n, t in texts.items() if "prep-design-review" in n]
ok(len(mprep) == 1 and re.search(r"DTEND;TZID=America/New_York:20261021T1400", mprep[0]),
   "meeting prep ends by the meeting's start", str(mprep)[:300])
# overlap between holds and busy times
def spans(t):
    t = t.replace(b"\r\n ", b"").decode()
    s = re.search(r"DTSTART;TZID=[^:]+:(\d{8}T\d{6})", t).group(1); e = re.search(r"DTEND;TZID=[^:]+:(\d{8}T\d{6})", t).group(1)
    return s, e
sp = sorted(spans(t) for t in texts.values())
ok(all(sp[i][1] <= sp[i + 1][0] for i in range(len(sp) - 1)), "holds don't overlap each other")
busy = [("20261021T090000", "20261021T093000"), ("20261021T140000", "20261021T150000")]
ok(all(not (s < be and bs < e) for s, e in sp for bs, be in busy), "holds don't overlap busy calendar events")
ok((day / "README.md").exists() and "| 1 |" in (day / "README.md").read_text(), "README index lists the holds")
# stable UIDs
uids1 = sorted(re.findall(rb"UID:(\S+)", allb))
r2 = run("propose", "--calendar-json", str(cal), "--block", f"2026-10-21 10:00 90m {long_title}",
         "--from-queue", "--meeting-prep", "30m", "--alarm", "10")
files2 = sorted(day.glob("*.ics"))
uids2 = sorted(re.findall(rb"UID:(\S+)", b"".join(f.read_bytes() for f in files2)))
ok(len(files2) == len(files) and uids1 == uids2, "re-proposing keeps the same UIDs and files", f"{len(files)} vs {len(files2)}")
# working hours default
(kit / "memory/context/calendar.md").write_text("# Calendar setup\n\n- **Working hours and time zone:** not set.\n")
r3 = run("propose", "--block", "2026-10-23 08:30 30m Too early")
ok("09:00-17:00 is assumed" in r3.stdout and "outside working hours" in r3.stdout, "unset hours assume 09:00-17:00 and say so")
# list / open / clear
ok("Draft calendar holds" in run("list").stdout, "list shows the index")
ro = run("open", "1")
ok(ro.returncode == 0 and "opened" in ro.stdout, "open hands a draft to the calendar app (stubbed)")
ok(run("open", "99").returncode != 0, "open refuses a draft that doesn't exist")
old = kit / "briefs/holds/2026-10-01"; old.mkdir(parents=True); (old / "01-x.ics").write_text("x")
rc = run("clear", "--older-than", "7")
ok(not old.exists() and day.exists() and "removed 1" in rc.stdout, "clear removes only sets older than N days")
shutil.rmtree(tmp)
print(f"\nholds tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
PY
