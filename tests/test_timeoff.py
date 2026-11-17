#!/usr/bin/env python3
"""Tests for kit-timeoff, the time-off pack: queue items due while away, just after (grace days), and overdue;
[work] items into the delegate notes and the handoff brief, personal items listed for the owner only; PPM Express
key dates from the latest pulse snapshot; meetings from kitcal (a fake one here) split into ones to decline or
forward and own blocks; the calendar missing; the out-of-office drafts with the return date (next weekday) and
delegate; --delegate over the setup file; --brief, --json, --write; and --handoff with no handoff agent installed.
Synthetic Kit folder; no model call, nothing sent.

  python3 tests/test_timeoff.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-timeoff"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-timeoff-"))
KIT, HOME, BIN = TMP / "kit", TMP / "home", TMP / "bin"
for d in ("memory/context", "briefs/ppmx", ".install/shared/morning"):
    (KIT / d).mkdir(parents=True)
HOME.mkdir()
BIN.mkdir()
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(KIT / "memory/context/timeoff.md").write_text(
    "- **Delegate:** the deputy architect\n- **Grace days:** 5\n- **Urgent contact:** the team's support channel\n")
(KIT / "QUEUE.md").write_text(
    "# Queue\n\n## Alex\n\n"
    "- [ ] **[work] Send the IA to the review board** : due 08-Dec-2026, v0.2 drafted\n"
    "- [ ] **[work] Approve the change request** : due 14-Dec-2026\n"
    "- [ ] **[work] Close the vendor scorecard** : due 01-Dec-2026\n"
    "- [ ] **[work] Far-off planning** : due 20-Jan-2027\n"
    "- [ ] **Renew the passport** : due 09-Dec-2026\n"
    "- [x] **[work] Already done** : due 08-Dec-2026\n\n"
    "## Kit\n\n- [ ] **Kit's own check** : due 08-Dec-2026\n\n"
    "## Done\n\n- [x] **[work] Old** : due 08-Dec-2026\n")
(KIT / "briefs/ppmx/pulse-2026-11-02.json").write_text(json.dumps({"projects": {}, "key_dates": {}}))
(KIT / "briefs/ppmx/pulse-2026-11-16.json").write_text(json.dumps({
    "projects": {"p1": {"name": "Payments hub"}},
    "key_dates": {"p1/k1": {"project": "p1", "name": "Design sign-off", "date": "2026-12-09", "status": "On track",
                            "done": False},
                  "p1/k2": {"project": "p1", "name": "Kickoff", "date": "2026-12-08", "done": True},
                  "p1/k3": {"project": "p1", "name": "Go-live", "date": "2027-03-01", "done": False}}}))
events = [{"title": "Architecture review board", "start": "2026-12-08 10:00", "attendees": 8, "recurring": True},
          {"title": "Focus time", "start": "2026-12-09 13:00", "attendees": 0}]
(BIN / "kitcal").write_text("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(events) + "\nEOF\n")
os.chmod(BIN / "kitcal", 0o755)

ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-17", HOME=str(HOME),
           PATH=f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}")


def run(*args, env=ENV):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env)


r = run("2026-12-07", "09-Dec-2026")
out = r.stdout
ok(r.returncode == 0, "runs", r.stderr)
ok("Mon 07-Dec-2026 to Wed 09-Dec-2026" in out and "Back Thu 10-Dec-2026" in out, "dates and return day", out[:300])
slip = out.split("## What will slip")[1].split("## Meetings")[0]
away = slip.split("Due while you're away")[1].split("Due in the")[0]
ok("Send the IA to the review board" in away and "[work]" in away, "an item due while away, tagged [work]")
after = slip.split("Due in the 5 days after")[1].split("PPM Express")[0]
ok("Approve the change request" in after, "an item due within the grace days after return")
ok("Already overdue" in slip and "Close the vendor scorecard" in slip.split("Already overdue")[1].split("Due while")[0],
   "an overdue item is flagged")
ok("Far-off planning" not in out and "Already done" not in out, "far-off and finished items stay out")
ok("Design sign-off" in slip and "Payments hub" in slip and "Go-live" not in slip and "Kickoff" not in slip,
   "PPM Express key dates from the latest snapshot, in the window, not done")
ok("pulse-2026-11-16.json" in out, "the snapshot's date is shown")
ok("Renew the passport" in slip.split("Yours only")[1], "personal items listed for the owner only")
notes = out.split("## Notes for")[1].split("## Brief")[0]
brief = out.split("## Brief for the handoff agent")[1]
ok("passport" not in notes.lower() and "passport" not in brief.lower(), "personal items stay out of delegate notes and brief")
ok("Kit's own check" in slip.split("not tagged [work]")[1] and "Kit's own check" not in notes,
   "untagged items are listed but not handed over")
ok("Send the IA" in notes and "Design sign-off" in notes, "a delegate note per work item and key date")
meet = out.split("## Meetings while you're away")[1].split("## Out-of-office")[0]
ok("Architecture review board" in meet.split("Decline")[1].split("Your own blocks")[0] and "recurring" in meet,
   "meetings with attendees to decline or forward")
ok("Focus time" in meet.split("Your own blocks")[1], "own blocks to clear")
ooo = out.split("## Out-of-office drafts")[1].split("## Notes")[0]
ok("Thursday 10 December" in ooo and "the deputy architect" in ooo and "support channel" in ooo,
   "out-of-office drafts with return date, delegate, urgent contact", ooo)
ok("Kit doesn't" in ooo and "nothing is sent" in out, "says nothing is set or sent")

r = run("2026-12-07", "2026-12-09", "--delegate", "the platform lead", "--brief")
ok(r.returncode == 0 and "the platform lead" in r.stdout and "Send the IA" in r.stdout and "passport" not in r.stdout,
   "--brief prints the handoff brief, --delegate overrides the setup", r.stdout)

r = run("2026-12-07", "2026-12-09", "--json")
d = json.loads(r.stdout)
ok(d["away"] == 1 and d["after"] == 1 and d["overdue"] == 1 and d["key_dates"] == 1 and d["meetings"] == 1
   and d["back"] == "2026-12-10", "--json counts", d)

env2 = dict(ENV, PATH="/usr/bin:/bin")
r = run("2026-12-07", "2026-12-09", "--json", env=env2)
d = json.loads(r.stdout)
ok(d["meetings"] == 0 and "isn't installed" in d["calendar"], "no kitcal: noted, not an error", d)

r = run("2026-12-07", "2026-12-09", "--write")
f = KIT / "briefs/timeoff-2026-12-07.md"
ok(r.returncode == 0 and f.exists() and "(DRAFT)" in f.read_text(), "--write saves briefs/timeoff-START.md", r.stdout)

r = run("2026-12-07", "2026-12-09", "--handoff")
ok(r.returncode == 1 and "isn't installed" in r.stderr, "--handoff without the agent says so", r.stderr)

r = run("2026-12-09", "2026-12-07")
ok(r.returncode == 2, "END before START is a usage error")

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
