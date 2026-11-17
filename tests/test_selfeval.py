#!/usr/bin/env python3
"""Tests for kit-selfeval, the self-evaluation draft: claims from the accomplishments log grouped under the goals in
memory/context/reviews.md (the rest by theme), each with its date and evidence line, finished work kit-wins hasn't
collected yet, the monthly reports in the period, the period from --from/--to or the Review period field, the
word limit (trims and says how many it left out), --json, and --write (briefs/reviews/). Synthetic Kit folder; no
model call.

  python3 tests/test_selfeval.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-selfeval"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-selfeval-"))
KIT = TMP / "kit"
for d in ("memory/context", "memory/personal", "briefs", ".install/shared/morning"):
    (KIT / d).mkdir(parents=True)
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(KIT / "memory/accomplishments.md").write_text(
    "# Accomplishments\n\n"
    "- 03-Mar-2026 [Decisions] ADR-012 accepted: Event bus for payments (ADR)\n"
    "- 15-Apr-2026 [Design documents] Payments hub IA v1.0 published (library)\n"
    "- 20-May-2026 [Delivery and meetings] DR failover test run for the ledger, resilience proven (queue)\n"
    "- 02-Jun-2026 [Kit and automation] Built the onboarding checklist tool (queue)\n"
    "- 10-Dec-2025 [Other] Something from last year (queue)\n")
(KIT / "memory/personal/secret.md").write_text("Dentist appointment\n")
(KIT / "QUEUE.md").write_text("# Queue\n\n## Alex\n\n## Done\n\n"
                              "- [x] **[work] Ran the vendor bake-off for observability** : done 20-Jul-2026\n"
                              "- [x] **Book the dentist** : done 21-Jul-2026\n")
(KIT / "briefs/kit-month-2026-05.md").write_text("# What Kit did in May 2026\n")
(KIT / "briefs/kit-month-2025-11.md").write_text("# old\n")
(KIT / "memory/context/reviews.md").write_text(
    "# Performance review setup\n\n"
    "- **Goals:** Reliability: DR, resilience, outage; Delivery: IA, GDS; Team: mentoring\n"
    "- **Review period:** 2026-01-01 to 2026-12-31\n"
    "- **Rating scale:** 1 to 5\n"
    "- **Word limit:** not set.\n")

ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-17")


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=ENV)


r = run()
out = r.stdout
ok(r.returncode == 0, "runs", r.stderr)
ok("(DRAFT)" in out and "01-Jan-2026 to 31-Dec-2026" in out, "period from the Review period field", out[:300])
ok("## Reliability" in out and "DR failover test" in out.split("## Reliability")[1].split("##")[0],
   "a claim is grouped under the goal its words match", out)
ok("Payments hub IA" in out.split("## Delivery")[1].split("##")[0], "IA work under Delivery")
ok("## Team" in out and "Nothing on record for this goal" in out.split("## Team")[1].split("##")[0],
   "a goal with no work says so")
ok("## Other work: Decisions" in out, "unmatched work grouped by theme")
ok("memory/accomplishments.md:3" in out, "each claim cites its evidence line")
ok("vendor bake-off" in out and "not yet in the log" in out, "finished work kit-wins hasn't collected is included")
ok("dentist" not in out.lower(), "personal items stay out", out)
ok("Something from last year" not in out, "items outside the period are left out")
ok("briefs/kit-month-2026-05.md" in out and "2025-11" not in out, "monthly reports in the period are listed")
ok("Impact: _" in out and "What would you do differently" in out, "impact and growth are prompts")
ok("Scale: 1 to 5" in out, "rating scale shown, rating left to the owner")

r = run("--from", "2026-04-01", "--to", "30-Jun-2026", "--json")
d = json.loads(r.stdout)
ok(d["claims"] == 3 and d["from"] == "2026-04-01", "--from/--to narrow the period", d)

r = run("--words", "12", "--json")
d = json.loads(r.stdout)
ok(d["left_out"] >= 1 and d["limit"] == 12, "the word limit trims and counts what it left out", d)
r = run("--words", "12")
ok("left out to fit the word limit" in r.stdout, "the draft says items were left out")

r = run("--from", "bad")
ok(r.returncode == 2, "a bad date is a usage error")

r = run("--write")
f = KIT / "briefs/reviews/selfeval-2026-01-01_2026-12-31.md"
ok(r.returncode == 0 and f.exists() and "(DRAFT)" in f.read_text(), "--write saves to briefs/reviews/", r.stdout + r.stderr)

(KIT / "memory/context/reviews.md").write_text("- **Goals:** not set.\n- **Review period:** not set.\n")
r = run()
ok("No goals set" in r.stdout and "01-Jan-2026 to 17-Nov-2026" in r.stdout, "without setup: year to date, by theme")

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
