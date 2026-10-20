#!/bin/bash
# Tests kit-meetprep (meeting prep packs) with a fixture calendar, Kit, and library.
#   bash tests/test_meetprep.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import json, os, pathlib, subprocess, sys, tempfile, shutil
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-meetprep"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"; lib = tmp / "lib"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "briefs").mkdir(); (kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
(kit / "memory/context/precedent.md").write_text("- **Sources:** these files and folders in the library root:\n  - `published/`\n")
(lib / "artifacts/payments-upgrade").mkdir(parents=True); (lib / "published").mkdir()
(lib / "artifacts/payments-upgrade/stakeholders.md").write_text("| Role | Group | Influence |\n|---|---|---|\n| Sponsor | Payments | high |\n| Security architect | Security | medium |\n")
(lib / "published/gds-index.md").write_text("| LIB-0050 | DS-152 | Payments upgrade design |\n")
(kit / "QUEUE.md").write_text("""# Queue

## Alex
- [ ] **Decide payments upgrade cutover window** [work] (added 10-Oct-2026)
- [ ] **Unrelated thing** (added 10-Oct-2026)

## Done
""")
(kit / "briefs/pending-actions.md").write_text("| A1 | Send payments upgrade runbook | architect | 21-Oct | proposed |\n| A2 | Old payments upgrade item | pm | | dropped |\n")
cal = [
 {"start": "2026-10-19T10:00:00", "end": "2026-10-19T11:00:00", "all_day": False, "subject": "Payments upgrade review",
  "location": "Room 4 / someone@example.com", "organizer": "Pat Doe", "has_attendees": True, "my_response": "accepted"},
 {"start": "2026-10-19T10:30:00", "end": "2026-10-19T11:00:00", "all_day": False, "subject": "Focus time",
  "location": "", "organizer": "", "has_attendees": False, "my_response": "organizer"},
 {"start": "2026-10-19T00:00:00", "end": "2026-10-20T00:00:00", "all_day": True, "subject": "Holiday",
  "location": "", "organizer": "", "has_attendees": True, "my_response": "accepted"},
 {"start": "2026-10-19T10:15:00", "end": "2026-10-19T10:45:00", "all_day": False, "subject": "Declined sync",
  "location": "", "organizer": "x", "has_attendees": True, "my_response": "declined"},
 {"start": "2026-10-19T15:00:00", "end": "2026-10-19T16:00:00", "all_day": False, "subject": "Later meeting",
  "location": "", "organizer": "y", "has_attendees": True, "my_response": "organizer"},
]
(tmp / "cal.json").write_text(json.dumps(cal))
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-19", KIT_NOW="2026-10-19T09:30:00")
run = lambda *a, **k: subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env, **k)
r = run("--json", str(tmp / "cal.json"))
packs = sorted((kit / "briefs/meetprep").glob("*.md"))
ok(r.returncode == 0 and len(packs) == 1, "one pack: within 120 min, has attendees, not all-day, not declined")
t = packs[0].read_text() if packs else ""
ok(packs and packs[0].name == "2026-10-19-1000-payments-upgrade-review.md", "file name: date, time, slug")
ok("Sponsor" in t and "Security architect" in t and "payments-upgrade" in t, "stakeholder roles from the matching project")
ok("Pat Doe" not in t and "@" not in t, "no organizer name, no address")
ok("Decide payments upgrade cutover window" in t and "Unrelated thing" not in t, "related queue item only")
ok("Send payments upgrade runbook" in t and "Old payments upgrade item" not in t, "pending action listed, dropped one not")
ok("DS-152" in t, "related library document via kit-precedent")
ok("## What to decide" in t and "cutover window" in t.split("## What to decide")[1], "what to decide from decision items")
r = run("--json", str(tmp / "cal.json"))
ok("0 new pack" in r.stdout, "existing pack not rewritten")
r = run("--json", str(tmp / "cal.json"), "--force")
ok("1 new pack" in r.stdout, "--force rewrites")
r = run("--json", "-", input=json.dumps(cal), env=None) if False else subprocess.run([sys.executable, str(tool), "--json", "-", "--minutes", "400", "--force"], input=json.dumps(cal), capture_output=True, text=True, env=env)
ok("2 meeting(s)" in r.stdout, "stdin input and a longer window")
r = run("--today")
ok("2 pack(s) for today" in r.stdout, "--today lists today's packs")
r = run()
ok(r.returncode != 0, "no source refused")
r = run("--from-config")
ok(r.returncode != 0 and "CALENDAR_JSON_CMD" in r.stderr, "--from-config without a command explains")
plist = repo / "platform/mac/morning/com.USER.kit.meetprep.plist.template"
pt = plist.read_text()
ok(pt.count("<dict><key>Weekday") == 115 and "kit-meetprep" in pt and "PAUSED" in pt, "launchd template: weekdays 07:00-18:00 every 30 min, honours pause")
shutil.rmtree(tmp)
print(f"kit-meetprep tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY
