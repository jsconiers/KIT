#!/usr/bin/env python3
"""Tests for the ticket routing watch in kit-tickets: unassigned too long (from the opened date, else from when the
watcher first saw it), misrouted by the owner's routing map (Markdown rules under "## Rules", whole words or /regex/,
or JSON), bounced between groups (counted day to day in the snapshot's history), TICKET_UNASSIGNED_DAYS and
TICKET_BOUNCE_MOVES, the Routing lines and their drafted next steps, numbers only in the short text, `kit-tickets
routing`, closed tickets left out, and the template's rules parsing. Synthetic tickets; no connector or model call.

  python3 tests/test_ticket_routing.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-tickets"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1200])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-routing-"))
KIT = TMP / "kit"
(KIT / "memory/context").mkdir(parents=True)
(KIT / "briefs").mkdir()
(KIT / ".install/shared/morning").mkdir(parents=True)
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
TODAY = KIT / "briefs/tickets-today.json"
SNAP = KIT / ".install/cache/tickets-snapshot.json"
BASE = dict(os.environ, KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1")
for k in ("TICKET_UNASSIGNED_DAYS", "TICKET_BOUNCE_MOVES", "TICKET_ROUTING_FILE"):
    BASE.pop(k, None)


def run(cmd, day, rows=None, **env):
    if rows is not None:
        TODAY.write_text(json.dumps(rows))
    e = dict(BASE, KIT_NOW=f"{day}T07:45:00", **env)
    r = subprocess.run([sys.executable, str(TOOL), *cmd], capture_output=True, text=True, env=e, timeout=60)
    return r.returncode, r.stdout + r.stderr


(KIT / "memory/context/ticket-routing.md").write_text("""# Routing

- this line isn't a rule -> Nowhere

## Rules

- SQL Server, MSSQL -> Database - SQL Server
- /postgres(ql)?/ -> Database - PostgreSQL

## Notes

- also not a rule -> Nowhere
""")

T1 = {"number": "TKT0000001", "title": "Test database on SQL Server 2022", "state": "Open", "priority": "4 - Low",
      "assigned_to": "", "assignment_group": "Database - MySQL", "opened": "2026-11-10 09:00:00",
      "updated": "2026-11-10T09:00:00"}
T2 = {"number": "TKT0000002", "title": "Artifactory on object storage", "state": "New", "priority": "3 - Moderate",
      "assigned_to": "", "assignment_group": "Solutions Architecture", "updated": "2026-11-12T09:00:00"}
T3 = {"number": "INC00003", "title": "VPN drops", "state": "In Progress", "priority": "3 - Moderate",
      "assigned_to": "Sam Lee", "assignment_group": "Network Ops", "updated": "2026-11-12T09:00:00"}
T4 = {"number": "INC00004", "title": "Old postgres replica lag", "state": "Closed", "priority": "4 - Low",
      "assigned_to": "", "assignment_group": "Database - MySQL", "opened": "2026-10-01", "updated": "2026-11-01"}
T5 = {"number": "INC00005", "title": "PostgreSQL vacuum stuck", "state": "Open", "priority": "3 - Moderate",
      "assigned_to": "Pat Kim", "assignment_group": "Database - PostgreSQL Team", "updated": "2026-11-12"}

# Day 1: the first check. T1 is 8 days unassigned (from its opened date) and misrouted; T2 has no opened date, so
# its clock starts today.
rc, out = run(["diff"], "2026-11-18", [T1, T2, T3, T4, T5])
ok(rc == 0 and "Routing" in out.splitlines(), "a Routing subsection on the first check", out)
ok("TKT0000001 misrouted: with Database - MySQL, but 'SQL Server' tickets go to Database - SQL Server (your routing "
   "map); no one assigned for 8 days" in out, "misrouted by the routing map, unassigned age from the opened date", out)
ok("TKT0000001 unassigned" not in out, "one finding per ticket", out)
ok("Suggested next step (a draft; nothing is sent): Ask Database - MySQL to reassign TKT0000001 to Database - SQL "
   "Server" in out, "a drafted next step", out)
ok("TKT0000002" not in out.split("Routing", 1)[1], "no opened date: the clock starts when first seen", out)
ok("INC00004" not in out, "closed tickets are left out")
ok("INC00005" not in out.split("Routing", 1)[1], "a matching group (loosely) isn't misrouted", out)
ok("Nowhere" not in out, "only lines under '## Rules' are rules", out)
txt = [ln for ln in out.splitlines() if ln.startswith("Text:")]
ok(txt and txt[0].endswith("; routing: 1 (TKT0000001)") and "SQL" not in txt[0],
   "the short text adds counts and numbers only", txt)
ok(all(ln.startswith(("[work]", "Text:", "Your tickets", "Routing")) for ln in out.splitlines()),
   "every line is [work] (or a heading)", out)

# Day 5: T2 has been unassigned for 4 days by the watcher's clock; T3 moved twice since day 1.
run(["diff"], "2026-11-19", [T1, T2, dict(T3, assignment_group="Service Desk")])
rc, out = run(["diff"], "2026-11-22", [T1, T2, dict(T3, assignment_group="Network Security")])
ok("TKT0000002 unassigned: no one assigned for 4 days (Solutions Architecture)" in out,
   "unassigned counted from when first seen", out)
ok("INC00003 bounced: moved 2 times (Network Ops -> Service Desk -> Network Security)" in out,
   "bounced between groups, from day-to-day history", out)
hist = json.loads(SNAP.read_text())["history"]
ok(hist["INC00003"]["moves"] == 2 and "INC00004" not in hist, "the history is kept in the snapshot, open only",
   hist)

# Settings.
rc, out = run(["diff", "--no-save"], "2026-11-22", None, TICKET_UNASSIGNED_DAYS="20", TICKET_BOUNCE_MOVES="0")
ok("unassigned" not in out and "bounced" not in out and "misrouted" in out and "no one assigned for 12" not in out,
   "TICKET_UNASSIGNED_DAYS and TICKET_BOUNCE_MOVES=0", out)
js = TMP / "routing.json"
js.write_text(json.dumps({"rules": [{"match": ["object storage"], "group": "Storage Engineering"}]}))
rc, out = run(["diff", "--no-save"], "2026-11-22", None, TICKET_ROUTING_FILE=str(js), TICKET_UNASSIGNED_DAYS="30")
ok("TKT0000002 misrouted: with Solutions Architecture, but 'object storage' tickets go to Storage Engineering" in out
   and "TKT0000001 misrouted" not in out, "a JSON routing map from TICKET_ROUTING_FILE", out)
(KIT / "memory/context/ticket-routing.md").unlink()
rc, out = run(["diff", "--no-save", "--json"], "2026-11-22", None, TICKET_UNASSIGNED_DAYS="30", TICKET_BOUNCE_MOVES="5")
data = json.loads(out)
ok(data["routing"] == {"unassigned": 0, "misrouted": 0, "bounced": 0} and "Routing" not in data["lines"],
   "no map and nothing over the limits: no Routing lines", data)

# kit-tickets routing, from the last check.
rc, out = run(["routing"], "2026-11-22")
ok(rc == 0 and "INC00003 bounced" in out and "TKT0000002 unassigned" in out, "kit-tickets routing", out)

# The template parses: six rules, the regex included.
sys.path.insert(0, str(REPO / "shared"))
import importlib.machinery  # noqa: E402
import importlib.util  # noqa: E402
os.environ["KIT_DIR"] = str(KIT)
spec = importlib.util.spec_from_loader("kit_tickets", importlib.machinery.SourceFileLoader("kit_tickets", str(TOOL)))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)
rules = kt.load_rules(REPO / "kit/templates/ticket-routing.md")
ok(len(rules) == 12 and any(r[0] == "/postgres(ql)?/" for r in rules), "the template's rules parse",
   [(r[0], r[2]) for r in rules])
ok(any(r[1].search("Migrate to PostgreSQL 16") for r in rules if r[2] == "Database - PostgreSQL")
   and not any(r[1].search("mysqldump") for r in rules if r[0] == "MySQL"), "whole words, and the regex", rules)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nticket routing tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
