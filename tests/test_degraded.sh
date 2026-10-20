#!/bin/bash
# Tests kit-degraded (the no-model morning brief) with a fixture Kit. Nothing real is touched.
#   bash tests/test_degraded.sh
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 - "$HERE" <<'PY'
import json, os, pathlib, subprocess, sys, tempfile, shutil
here = pathlib.Path(sys.argv[1])
tool = here / "shared/bin/kit-degraded"
tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / "memory/context").mkdir(parents=True)
(kit / "memory/personal").mkdir(parents=True)
(kit / "briefs").mkdir()
(kit / "memory/personal/INDEX.md").write_text("Secret family appointment details\n")
(kit / "QUEUE.md").write_text("""# Queue

## Sprint

Sprint S1: 19-Oct-2026 to 30-Oct-2026
- [ ] **Org profile** (M) [open]
- [x] **Harness** (M) [done]

## Alex

- [ ] **Overdue design review** [work]: due 15-Oct-2026 (added 01-Oct-2026)
- [ ] **Change board pack** [work]: due 21-Oct-2026 (added 01-Oct-2026)
- [ ] **Pick up prescription**: due 20-Oct-2026 (added 01-Oct-2026)
- [ ] **Call the bank about the mortgage**: due 21-Oct-2026 (added 01-Oct-2026)
- [ ] **Someday work thing** [work] (added 01-Oct-2026)
  - [ ] sub item: due 01-Oct-2026

## Kit
- [ ] **Kit item**: due 01-Oct-2026

## Waiting on others
- [ ] **Extra credits**: Prod Support, since 15-Oct-2026 (added 15-Oct-2026)

## Done
""")
(kit / "briefs/health.txt").write_text("OK: all good\nWARN: Outlook didn't answer\n")
(kit / "briefs/audit.txt").write_text("Audit 21-Oct-2026: 1 warning (denied write attempt)\nmore detail\n")
(kit / "briefs/pending-commitments.md").write_text("| C1 | Send the runbook | recipient | 23-Oct | proposed |\n| C2 | x | y | | dropped |\n")
cal = tmp / "cal.json"
cal.write_text(json.dumps([
    {"title": "Standup", "start": "2026-10-21T09:00:00", "end": "2026-10-21T09:15:00", "has_attendees": True},
    {"title": "Design review with someone@example.com", "start": "2026-10-21T14:00:00", "end": "2026-10-21T15:00:00"},
    {"title": "Declined thing", "start": "2026-10-21T11:00:00", "my_response": "declined"},
    {"title": "Tomorrow", "start": "2026-10-22T10:00:00"},
]))
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-21")
PASS = FAIL = 0
def ok(c, name, detail=""):
    global PASS, FAIL
    if c: PASS += 1; print("ok  ", name)
    else: FAIL += 1; print("FAIL", name, detail)
def run(*a):
    return subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)

r = run("--reason", "the model run failed (exit 1)", "--calendar-json", str(cal))
ok(r.returncode == 0, "runs", r.stderr)
brief = (kit / "briefs/2026-10-21.md").read_text()
ok("Degraded brief: written without a model because the model run failed (exit 1)" in brief, "banner with the reason")
ok("Overdue design review" in brief and "Change board pack" in brief, "work to-dos overdue and due today are named")
ok("prescription" not in brief and "mortgage" not in brief and "bank" not in brief, "personal to-dos are never named")
ok("1 overdue, 1 due today (counted, not named)" in brief, "personal to-dos are counted", brief)
ok("Someday" not in brief and "sub item" not in brief and "Kit item" not in brief, "only due items are listed; sub-items and Kit's items left out")
ok("09:00  Standup" in brief and "14:00  Design review" in brief, "today's calendar with times and titles")
ok("example.com" not in brief and "Declined thing" not in brief and "Tomorrow" not in brief,
   "addresses masked; declined and other days' events left out")
ok("WARN: Outlook didn't answer" in brief and "OK: all good" not in brief, "health problems listed, OK lines skipped")
ok("1 warning (denied write attempt)" in brief, "audit headline")
ok("Extra credits: Prod Support, since 15-Oct-2026" in brief, "waiting-on item with who and since")
ok("Sprint S1: 19-Oct-2026 to 30-Oct-2026 (1 done, 1 open)" in brief, "sprint status")
ok("Commitments: 1" in brief, "pending commitments counted")
ok("Secret family" not in brief, "nothing from memory/personal")
t = (kit / "briefs/latest-text.txt").read_text().splitlines()
ok(t[0] == "Kit · Wed 21-Oct" and t[-1] == "Full brief: briefs/2026-10-21.md", "short text first and last lines", str(t))
ok("Degraded brief (no model)" in t[1], "short text says it's degraded")
allt = "".join((kit / "briefs" / n).read_text() for n in ("latest-text.txt", "latest-text-work.txt", "latest-text-personal.txt"))
ok("prescription" not in allt and "Overdue design review" not in allt, "short texts carry counts, not names")
ok(all(len((kit / "briefs" / n).read_text()) < 600 for n in ("latest-text.txt", "latest-text-work.txt", "latest-text-personal.txt")),
   "short texts under 600 characters")
ok("Personal to-dos: 1 overdue, 1 due today" in (kit / "briefs/latest-text-personal.txt").read_text(), "personal text counts")
ok("To-dos: 1 overdue, 1 due today (work)" in (kit / "briefs/latest-text-work.txt").read_text()
   and "Meetings: 2, first 09:00" in (kit / "briefs/latest-text-work.txt").read_text(), "work text counts and meetings")
# no overwrite
(kit / "briefs/2026-10-21.md").write_text("model brief\n")
(kit / "briefs/latest-text.txt").write_text("model text\n")
r = run("--reason", "x", "--no-calendar")
ok((kit / "briefs/2026-10-21.md").read_text() == "model brief\n" and "left it alone" in r.stdout, "an existing brief isn't overwritten")
ok((kit / "briefs/latest-text.txt").read_text() == "model text\n", "an existing short text isn't overwritten")
# no calendar
(kit / "briefs/2026-10-21.md").unlink()
run("--reason", "budget", "--no-calendar")
ok("Calendar left out" in (kit / "briefs/2026-10-21.md").read_text(), "--no-calendar says the calendar was left out")
shutil.rmtree(tmp)
print(f"\ndegraded tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
PY
