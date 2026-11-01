#!/usr/bin/env python3
"""Tests for kit-ppmx's work features against the fake PPM Express (tests/fake_ppmx.py): the portfolio pulse
(a weekly snapshot and what changed since last week) and meeting actions into PPM Express (proposals from
the scribe's Actions block, made one at a time), plus the permission rules Kit installs for them. Nothing
reaches the network, the Keychain, or a real PPM Express.

Run: python3 tests/test_ppmx_work.py
"""
import datetime
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SHARED = REPO / "shared"
sys.path[:0] = [str(SHARED), str(HERE)]
import fake_ppmx as F  # noqa: E402
from ppmx import actions as A  # noqa: E402
from ppmx import pulse as P  # noqa: E402
from ppmx.client import PPMXError  # noqa: E402

PASS = FAIL = 0
ALEX, BLAKE = "token-alex-0001", "token-blake-0002"


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


server, fake, BASE = F.start()
tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\n')
(kit / "memory/context").mkdir(parents=True)
(kit / "briefs").mkdir()
KP = [sys.executable, str(SHARED / "bin/kit-ppmx")]
ENV = {k: v for k, v in os.environ.items() if not k.startswith("PPMX_")}
ENV.update(KIT_DIR=str(kit), PPMX_TOKEN_KEYCHAIN="off", PPMX_TOKEN=ALEX, PPMX_CACHE_SECONDS="0", PYTHONUTF8="1")


def kp(*args, **extra):
    r = subprocess.run(KP + list(args), capture_output=True, text=True, encoding="utf-8", timeout=120,
                       env={**ENV, **extra})
    return r.returncode, r.stdout, r.stderr


WORK = kit / "briefs/ppmx"

# ---- the pulse: a first snapshot -------------------------------------------------------------------------
rc, o, e = kp("pulse", "--brief", "--save", PPMX_TODAY="2026-10-26")
ok(rc == 0 and o.startswith("PPM Express pulse\n"), "pulse --brief: a section for the brief", o + e)
lines = o.splitlines()[1:]
ok(lines and all(ln.startswith("[work] ") for ln in lines), "every line is tagged [work] (never in a personal text)")
ok("Text:" not in o, "no Text: line, so nothing reaches a short text")
ok("At Risk or Critical now: 1 (Data center exit, Critical)" in o, "the first pulse lists what's at risk now", o)
ok("Overdue key dates: Network refresh: Vendor contract (15-Oct)" in o, "an open key date in the past is overdue", o)
ok("Design approved" not in o, "a key date that's done isn't listed")
ok("3 projects, 3 key dates (the first pulse, so nothing to compare yet)" in o, "the totals and the basis", o)
snap1 = WORK / "pulse-2026-10-26.json"
ok(snap1.exists(), "--save keeps the snapshot")
if os.name != "nt":
    ok(stat.S_IMODE(snap1.stat().st_mode) == 0o600 and stat.S_IMODE(WORK.stat().st_mode) == 0o700,
       "the snapshot and its folder are owner-only")
saved = json.loads(snap1.read_text())
ok(set(saved["projects"]) == {F.A1, F.A2, F.A3} and saved["projects"][F.A2]["status_code"] == 2,
   "the snapshot keeps each project's status code", json.dumps(saved["projects"])[:300])
ok(ALEX not in snap1.read_text(), "no token in the snapshot")

# ---- a week later: what changed ---------------------------------------------------------------------------
proj = {r["id"]: r for r in fake.data["projects"]["alex"]}
proj[F.A1]["attributes"].update(OverallStatus=1, Manager="Sam Lee")
proj[F.A2]["attributes"].update(OverallStatus=0, FinishDate="2027-02-15T00:00:00")
fake.data["projects"]["alex"].append(F.item("cccccccc-0000-4000-8000-000000000004", Name="Branch Wi-Fi",
                                            OverallStatus=0, Manager="Alex Rivera", Portfolios=["Infrastructure"]))
kds = {r["id"]: r for r in fake.data["key_dates"][F.A1]}
kds[F.K2]["attributes"]["Date"] = "2026-12-14T00:00:00"
kds[F.K3]["attributes"]["Status"] = 10
fake.data["key_dates"][F.A1].append(F.item("90000000-0000-4000-8000-000000000004", Name="Pilot site",
                                           Date="2026-11-09T00:00:00", Type=0, Status=0))
rc, o, e = kp("pulse", "--brief", "--save", PPMX_TODAY="2026-11-02")
ok(rc == 0, "the second pulse runs", e)
ok("Turned At Risk or Critical since 26-Oct-2026: Network refresh (At Risk, was On Track)" in o,
   "a project that turned At Risk, with what it was", o)
ok("Back on track: Data center exit (On Track)" in o, "a project that recovered")
ok("Key dates that slipped: Network refresh: Go-live 30-Nov to 14-Dec (+14 days)" in o, "a key date that slipped", o)
ok("Coming due in 14 days: Network refresh: Pilot site 09-Nov" in o, "a key date coming due", o)
ok("Data center exit finish 15-Dec to 15-Feb" in o and "Network refresh manager now Sam Lee" in o,
   "finish dates and managers that changed", o)
ok("1 key date(s) met" in o and "1 new project(s): Branch Wi-Fi" in o, "key dates met and projects added", o)
ok("Overdue key dates" not in o, "the met key date is no longer overdue")
ok("compared with 26-Oct-2026" in o, "says what it compared with")
rc, o, e = kp("pulse", "--json", PPMX_TODAY="2026-11-02")
rep = json.loads(o) if rc == 0 else {}
ok(rep.get("projects") == 4 and rep.get("turned") and rep["turned"][0][0] == "Network refresh", "--json gives the comparison")
rc, o, e = kp("pulse", "--since", "2026-11-02", PPMX_TODAY="2026-11-02")
ok("Nothing turned At Risk or Critical" in o or "Turned" not in o, "--since compares with that day's snapshot", o)
rc, o, e = kp("pulse", "--scope", "mine", PPMX_TODAY="2026-11-02")
ok(rc == 0 and "2 projects" in o, "--scope mine: the projects you manage (Mobile app, Branch Wi-Fi)", o)
rc, o, e = kp("pulse", "--scope", "Digital", PPMX_TODAY="2026-11-02")
ok(rc == 0 and "1 projects" in o, "--scope NAME: one portfolio", o)
(kit / ".install/shared/morning/config").write_text(f'PPMX_BASE_URL="{BASE}"\nPPMX_PULSE_SCOPE="Digital"\n')
rc, o, e = kp("pulse", PPMX_TODAY="2026-11-02")
ok("(scope: Digital)" in o and "1 projects" in o, "PPMX_PULSE_SCOPE in Kit's config sets the default", o)
(kit / ".install/shared/morning/config").write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\n')
old = WORK / "pulse-2026-01-02.json"
old.write_text("{}")
kp("pulse", "--save", PPMX_TODAY="2026-11-02")
ok(not old.exists(), "snapshots older than 120 days are removed")
rc, o, e = kp("pulse", "--brief", PPMX_TOKEN="not a token")
ok(rc == 0 and "[work] Couldn't read PPM Express" in o, "--brief says what went wrong instead of going quiet", o + e)
rc, o, e = kp("pulse", PPMX_TOKEN="")
ok(rc == 2 and "No personal access token" in e, "without a token: exit 2 and what to do", e)
audit = "".join(f.read_text() for f in (kit / "audit").glob("ppmx-*.jsonl"))
ok('"via": "kit-ppmx pulse"' in audit and ALEX not in audit, "the pulse leaves an audit line, without the token")

# the pulse waits out the request limit, then carries on
class Ctx:
    def __init__(self):
        self.calls = 0

    def rows(self, name, **parts):
        self.calls += 1
        if name == "key_dates" and self.calls == 2:
            raise PPMXError(429, "too many requests")
        if name == "projects":
            return [{"id": "p1", "Name": "One", "OverallStatus": "On Track", "codes": {"OverallStatus": 0}}]
        return [{"id": "k1", "Name": "Launch", "Date": "2026-11-05", "Status": "On Track"}]


slept = []
snap = P.snapshot(Ctx(), sleep=slept.append, deadline_seconds=100)
ok(slept == [31] and "p1/k1" in snap["key_dates"] and snap["errors"] == 0, "a 429 is waited out, once", str(slept))
snap = P.snapshot(Ctx(), sleep=slept.append, deadline_seconds=5)
ok(snap["errors"] == 1, "past the deadline, a project's key dates are counted as not read")

# ---- meeting actions: proposals -------------------------------------------------------------------------------
minutes = tmp / "2026-11-03-network-refresh-sync.md"
minutes.write_text("""# Network refresh sync

## Actions
- [action] Order the switches | owner: owner | due: 13-Nov-2026 | project: network-refresh | source: [PM]
- [action] Write the cutover plan | owner: owner | due: 12-Nov-2026 | project: network-refresh | source: [Architect]
- [action] Book the data hall walkthrough | owner: PM | due: no date | project: data-center-exit | source: [PM]
- [action] Draft the vendor RFP | owner: owner | due: 20-Nov-2026 | project: vendor-selection | source: [PM]
- [action] An idea we dropped | owner: owner | due: no date | project: network-refresh | source: [PM] dropped
""")
acts = A.parse(minutes.read_text())
ok(len(acts) == 5 and acts[0]["due"] == "2026-11-13" and acts[2]["due"] == "" and acts[4]["status"] == "dropped",
   "the Actions block is read: action, owner, due date, project, and status", str(acts[:1]))
ok(A.due_date("due 2026-11-05") == "2026-11-05" and A.due_date("no date") == "" and A.due_date("31-Feb-2026") == "",
   "due dates in either form; impossible dates are none")
rc, o, e = kp("actions", str(minutes), PPMX_TODAY="2026-11-03")
ok(rc == 0 and "5 action(s)" in o and "1 dropped and left out" in o and "Nothing has changed in PPM Express" in o,
   "proposing reads only, and says so", o + e)
ok('1. update the task "Order switches" in Network refresh: due 2026-11-13 (was 2026-10-20)' in o,
   "an action that matches an open task: update its due date", o)
ok('2. already in PPM Express as the task "Cutover plan"; nothing to change' in o, "an action PPM Express already has")
ok('3. create the task "Book the data hall walkthrough" in Data center exit: owner PM: assign it in PPM Express' in o,
   "a new action becomes a task; another owner's is left to assign", o)
ok("4. no PPM Express project clearly matches 'vendor-selection'" in o and "kit-ppmx actions map vendor-selection" in o,
   "an action with no clear project says how to map it", o)
ok("kit-ppmx actions apply 1" in o, "says how to make one")
ok(not fake.writes, "nothing was written to PPM Express")
props = WORK / "actions-2026-11-03-network-refresh-sync.json"
data = json.loads(props.read_text())
ok(data["proposals"][0]["args"] == {"project_id": F.A1, "task_id": F.T1, "fields": {"DueDate": "2026-11-13"}},
   "the update sends only the changed field, in the key the tasks use", str(data["proposals"][0].get("args")))

# ---- making them, one at a time ---------------------------------------------------------------------------------
rc, o, e = kp("actions", "apply", "1", PPMX_TODAY="2026-11-03")
ok(rc == 0 and "done: update the task" in o, "apply 1 makes that change", o + e)
ok(fake.writes and fake.writes[-1][1:] == ("PATCH", f"Projects/{F.A1}/Tasks/{F.T1}", {"updates": {"DueDate": "2026-11-13"}}),
   "PPM Express got exactly the proposed change", str(fake.writes[-1:]))
rc, o, e = kp("actions", "apply", "1")
ok(rc == 2 and "made already" in e and len(fake.writes) == 1, "a proposal is never made twice")
rc, o, e = kp("actions", "apply", "2")
ok(rc == 2 and "nothing to make" in e, "a proposal with nothing to change can't be applied")
rc, o, e = kp("actions", "apply", "4")
ok(rc == 2 and "nothing to make" in e, "an action with no project can't be applied")
rc, o, e = kp("actions", "apply", "9")
ok(rc == 2 and "no proposal 9" in e, "an unknown number is refused")
rc, o, e = kp("actions", "apply", "3", PPMX_TOKEN=BLAKE)
ok(rc == 1 and "didn't make it" in e and json.loads(props.read_text())["proposals"][2]["status"] == "failed",
   "PPM Express refusing (a read-only token) marks the proposal failed", e)
rc, o, e = kp("actions", "apply", "3", PPMX_WRITES="off")
ok(rc == 1 and len(fake.writes) == 1, "PPMX_WRITES=off: nothing is sent", e)
rc, o, e = kp("actions", "apply", "3")
ok(rc == 0 and fake.writes[-1][1] == "POST" and fake.writes[-1][2] == f"Projects/{F.A2}/Tasks"
   and fake.writes[-1][3] == {"attributes": {"Name": "Book the data hall walkthrough"}},
   "apply 3 creates the task, with only its name", str(fake.writes[-1:]))
rc, o, e = kp("actions", "show")
ok("1. done: update" in o and "3. done: create" in o, "show lists the proposals and what's done", o)
audit = "".join(f.read_text() for f in (kit / "audit").glob("ppmx-*.jsonl"))
ok('"via": "kit-ppmx actions apply"' in audit and "2026-11-13" not in audit and ALEX not in audit,
   "each change leaves an audit line with field names, never values or the token")

# ---- mapping a project, and the default source ---------------------------------------------------------------------
rc, o, e = kp("actions", "map", "vendor-selection", "Mobile app")
ok(rc == 0 and json.loads((kit / "memory/context/ppmx-projects.json").read_text()) == {"vendor-selection": F.A3},
   "map remembers which PPM Express project a library project is", o + e)
(kit / "briefs/pending-actions.md").write_text(minutes.read_text().split("## Actions\n")[1])
rc, o, e = kp("actions", PPMX_TODAY="2026-11-03")
ok(rc == 0 and '4. create the task "Draft the vendor RFP" in Mobile app: due 2026-11-20, assigned to you' in o,
   "with the map, the action goes to its project, assigned to you (owner)", o)
d2 = json.loads((WORK / "actions-pending-actions.json").read_text())
ok(d2["proposals"][3]["args"]["fields"] == {"FinishDate": "2026-11-20", "AssignedTo": "alex@example.com"},
   "with no tasks to copy, the due date goes in FinishDate (PPMX_TASK_DUE_FIELD changes it)", str(d2["proposals"][3]))
rc, o, e = kp("actions", str(minutes), "--project", "Mobile app")
ok(o.count("in Mobile app") == 4, "--project puts every action in one project", o)
rc, o, e = kp("actions", "map", "x", "No such project")
ok(rc == 1 and "no project" in e, "mapping to a project that doesn't exist is refused")
(tmp / "empty.md").write_text("# Minutes\n\nNo actions.\n")
rc, o, e = kp("actions", str(tmp / "empty.md"))
ok(rc == 0 and "no actions" in o, "minutes with no actions say so")

# ---- Kit's permission rules for them ---------------------------------------------------------------------------------
sys.path.insert(0, str(SHARED))
import kit_setup  # noqa: E402
ok("Bash(kit-ppmx actions apply *)" in kit_setup.ASK, "Claude Code asks before every apply")
ok({"Bash(kit-ppmx pulse)", "Bash(kit-ppmx pulse *)", "Bash(kit-ppmx actions)", "Bash(kit-ppmx actions *)"}
   <= set(kit_setup.ALLOW), "the pulse and proposals (read only) don't ask")
ok("Bash(kit-wrap)" in kit_setup.ALLOW and "Bash(kit-rehearse *)" in kit_setup.ASK,
   "kit-wrap is allowed; kit-rehearse (a paid Claude run) asks")

server.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\nkit-ppmx work tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
