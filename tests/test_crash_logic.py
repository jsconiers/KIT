#!/usr/bin/env python3
"""Tests the crash-path and logic fixes: numeric settings that aren't numbers fall back with a warning
(kit-ppmx's pulse limits, kit-preread's and kit-rehearse's time limits), kit-meetload survives a failed
kit-library or kit-holds call, reads a date-only UNTIL as the end of that day, and honors an event's
TZID; kit_queue finds the owner's section past a custom heading; kit-touch takes 02/29 in any year.

Run: python3 tests/test_crash_logic.py
"""
import datetime as dt
import importlib.machinery
import importlib.util
import io
import contextlib
import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
BIN = REPO / "shared/bin"
sys.path.insert(0, str(REPO / "shared"))
PASS = FAIL = 0
tmp = pathlib.Path(tempfile.mkdtemp())
os.environ["KIT_DIR"] = str(tmp / "kit")
(tmp / "kit/.install/shared/morning").mkdir(parents=True)


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(BIN / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---- numbers that aren't numbers
kp = load("kit-ppmx")
err = io.StringIO()
with contextlib.redirect_stderr(err):
    got = (kp.whole({"PPMX_PULSE_MAX": "lots"}, "PPMX_PULSE_MAX", 300), kp.whole({}, "PPMX_PULSE_SECONDS", 240),
           kp.whole({"PPMX_PULSE_SECONDS": "90"}, "PPMX_PULSE_SECONDS", 240))
ok(got == (300, 240, 90) and "isn't a whole number" in err.getvalue(), "kit-ppmx: a bad PPMX_PULSE_* falls back, with a warning",
   str(got))
pr = load("kit-preread")
os.environ["PREREAD_TIMEOUT"] = "15 minutes"
err = io.StringIO()
with contextlib.redirect_stderr(err):
    n = pr.number_setting("PREREAD_TIMEOUT", 900)
ok(n == 900 and "PREREAD_TIMEOUT" in err.getvalue(), "kit-preread: a bad PREREAD_TIMEOUT falls back to 900", str(n))
os.environ["REHEARSE_TIMEOUT"] = "600"
ok(pr.number_setting("REHEARSE_TIMEOUT", 900) == 600, "a good one is used")
ok("pr.number_setting(\"REHEARSE_TIMEOUT\", 900)" in (BIN / "kit-rehearse").read_text(),
   "kit-rehearse reads its time limit the same way")

# ---- kit-meetload
ml = load("kit-meetload")
ml.HERE = tmp / "nowhere"                      # neither kit-library nor kit-holds can run
(tmp / "nowhere").mkdir()
(tmp / "nowhere/kit-library").write_text("")
(tmp / "nowhere/kit-holds").write_text("")
real_run = ml.subprocess.run
ml.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no such program"))
ok(ml.deliver(tmp / "report.txt") is False, "kit-meetload: a kit-library that won't run means not delivered, no crash")
ml.today = lambda: dt.date(2026, 11, 2)
ml.KIT = tmp / "kit"
msg = ml.propose_holds([], [], "personal", (dt.time(9), dt.time(17)), 120)
ok("Couldn't propose the holds" in msg, "kit-meetload: a failed kit-holds is reported, no crash", str(msg))
ml.subprocess.run = real_run

ics = tmp / "cal.ics"
ics.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nSUMMARY:Standup\nDTSTART:20261102T100000\nDTEND:20261102T103000\n"
               "RRULE:FREQ=DAILY;UNTIL=20261104\nEND:VEVENT\n"
               "BEGIN:VEVENT\nUID:b\nSUMMARY:Zoned\nDTSTART;TZID=UTC:20261103T150000\nDTEND;TZID=UTC:20261103T160000\n"
               "END:VEVENT\nEND:VCALENDAR\n")
evs = ml.from_ics(ics, dt.datetime(2026, 11, 1), dt.datetime(2026, 11, 8))
stand = [e["start"] for e in evs if e["title"] == "Standup"]
ok(stand == ["2026-11-02 10:00", "2026-11-03 10:00", "2026-11-04 10:00"],
   "kit-meetload: UNTIL=YYYYMMDD keeps the meeting on that last day", str(stand))
zoned = [e["start"] for e in evs if e["title"] == "Zoned"]
want = dt.datetime(2026, 11, 3, 15, tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
ok(zoned == [want.isoformat(sep=" ", timespec="minutes")], "kit-meetload: a TZID time is turned into local time",
   f"{zoned} vs {want}")

# ---- kit_queue.owner_section
import kit_queue  # noqa: E402
q = ["# Queue", "## Sprint", "## Projects", "## Alex", "## Kit", "## Waiting on others", "## Someday", "## Done"]
ok(kit_queue.owner_section(q) == "Alex", "owner_section skips a custom heading above the owner's", kit_queue.owner_section(q))
ok(kit_queue.owner_section(q, "Alex Rivera") == "Alex", "owner_section matches OWNER_NAME's first name")
ok(kit_queue.owner_section(q, "Alex") == "Alex", "owner_section uses OWNER_NAME when it's there")
ok(kit_queue.owner_section(["## Sprint", "## Alex", "## Kit", "## Reading"]) == "Alex", "a custom heading after Kit's is ignored")
ok(kit_queue.owner_section(["## Sprint", "## Kit"]) is None, "no owner section: None")

# ---- kit-touch 02/29
kt = load("kit-touch")
for today_, want in ((dt.date(2026, 11, 2), dt.date(2026, 2, 28)), (dt.date(2028, 11, 2), dt.date(2028, 2, 29)),
                     (dt.date(2027, 1, 15), dt.date(2026, 2, 28))):
    kt.today = lambda t=today_: t
    got = kt.parse_day("02/29")
    ok(got == want, f"kit-touch: 02/29 on {today_} is {want}", str(got))
kt.today = lambda: dt.date(2026, 11, 2)
ok(kt.parse_day("10/25") == dt.date(2026, 10, 25) and kt.parse_day("12/25") == dt.date(2025, 12, 25),
   "kit-touch: other dates with no year are the latest on or before today")

print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
