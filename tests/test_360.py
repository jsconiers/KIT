#!/usr/bin/env python3
"""Tests for kit-360, the 360 feedback draft: evidence from kit-feedback notes (aliases count), the accomplishments
log, library documents and status reports, and meeting actions in minutes, each dated and cited; strengths from
praise notes, areas to grow only from coaching or concern notes (otherwise prompts); the thin-evidence warning;
the period; nothing personal read; --json; and --write into Kit's private feedback/ folder. Synthetic Kit folder
and library; no model call, no catalog (the file scan stands in for kit-library search).

  python3 tests/test_360.py
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-360"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-360-"))
KIT, LIB = TMP / "kit", TMP / "library"
for d in ("memory/context", "memory/personal", "feedback", ".install/shared/morning"):
    (KIT / d).mkdir(parents=True)
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
(KIT / "memory/personal/notes.md").write_text("Sam Rivera birthday party\n")
(KIT / "feedback/people.json").write_text(json.dumps({"people": [
    {"name": "Sam Rivera", "aliases": ["Sammy"], "role": "engineer"}]}))
notes = [
    {"date": "2026-09-01", "person": "Sam Rivera", "kind": "praise", "text": "Ran the cutover calmly",
     "impact": "zero downtime"},
    {"date": "2026-09-10", "person": "Sam Rivera", "kind": "coaching", "text": "Share designs earlier with security"},
    {"date": "2026-10-01", "person": "Sam Rivera", "kind": "observation", "text": "Led the DR test"},
    {"date": "2026-10-02", "person": "Pat Lee", "kind": "praise", "text": "Someone else"},
    {"date": "2024-01-01", "person": "Sam Rivera", "kind": "praise", "text": "Too long ago"},
]
(KIT / "feedback/notes.jsonl").write_text("".join(json.dumps(n) + "\n" for n in notes))
(KIT / "memory/accomplishments.md").write_text(
    "# Accomplishments\n\n- 05-Aug-2026 [Design documents] Payments IA v1.0 with Sam Rivera published (library)\n")
(LIB / "artifacts/payments/minutes").mkdir(parents=True)
(LIB / "artifacts/payments/status").mkdir(parents=True)
(LIB / "artifacts/payments/minutes/2026-09-15-design-review.md").write_text(
    "# Design review 15-Sep-2026\n\n## Actions\n\n- [x] Sammy to confirm the failover order (done)\n"
    "- [ ] Pat Lee to book the window\n\nSam Rivera presented the sizing.\n")
(LIB / "artifacts/payments/status/2026-10-20-status.md").write_text(
    "# Status 20-Oct-2026\n\n- Load test passed; Sam Rivera owns the tuning follow-up.\n")
(LIB / "CATALOG.md").write_text("| Title | Author |\n|---|---|\n| Sizing note 12-Oct-2026 | Sam Rivera |\n")

ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-17")


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=ENV)


r = run("Sam")
out = r.stdout
ok(r.returncode == 0, "runs", r.stderr)
ok("360 feedback for Sam Rivera" in out and "(DRAFT)" in out, "the first name finds the person on the list", out[:300])
strengths = out.split("## Strengths")[1].split("##")[0]
ok("Ran the cutover calmly" in strengths and "zero downtime" in strengths, "strengths from praise notes, with impact")
grow = out.split("## Areas to grow")[1].split("##")[0]
ok("Share designs earlier" in grow, "areas to grow from coaching notes")
impact = out.split("## Impact, with examples")[1].split("## Areas")[0]
ok("Led the DR test" in impact and "Payments IA v1.0" in impact, "observations and accomplishments are examples")
ok("confirm the failover order" in impact and "(done)" in impact, "a meeting action owned by an alias, marked done")
ok("Pat Lee to book" not in out and "Someone else" not in out, "other people's actions and notes stay out")
ok("artifacts/payments/minutes/2026-09-15-design-review.md:5" in out, "minutes are cited by file and line")
ok("status/2026-10-20-status.md" in out and "CATALOG.md" in out, "status reports and the catalog are evidence")
ok("Too long ago" not in out, "notes outside the period are left out")
ok("birthday" not in out.lower(), "nothing personal is read")
ok("Thin evidence" not in out, "enough evidence: no warning")
ok("Kit sends nothing" in out, "says nothing is sent")

r = run("Jordan", "Blake")
ok(r.returncode == 0 and "Thin evidence" in r.stdout and "No praise notes on record" in r.stdout
   and "No coaching notes on record" in r.stdout, "someone with no evidence: warning and prompts", r.stdout[:600])

r = run("Sam Rivera", "--from", "2026-10-01", "--json")
d = json.loads(r.stdout)
ok(d["notes"] == 1 and d["accomplishments"] == 0, "--from narrows the period", d)

r = run("Sam Rivera", "--write")
files = list((KIT / "feedback").glob("360-sam-rivera-2026-11-17.md"))
ok(r.returncode == 0 and files, "--write saves to feedback/", r.stdout + r.stderr)
if files and os.name != "nt":
    ok(stat.S_IMODE(files[0].stat().st_mode) == 0o600, "the saved draft is private (0600)")

r = run("Sam", "--from", "nope")
ok(r.returncode == 2, "a bad date is a usage error")

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
