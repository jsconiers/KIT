#!/usr/bin/env python3
"""Tests for `kit-wins month`, the one-page "what Kit did this month" report: the month's wins from the log plus
source items not collected yet, Kit's own updates folded into one line, the runs and estimated cost from the cost
ledger against the month before, work runs by kind with every other run in one "other runs" line (nothing personal
named), the default month (last month), --json, and --write (Markdown and a print-ready HTML page in briefs/).
Synthetic Kit folder; no model call.

  python3 tests/test_wins_month.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-wins"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-wins-month-"))
KIT = TMP / "kit"
for d in ("memory/context", "briefs", ".install/logs", ".install/shared/morning"):
    (KIT / d).mkdir(parents=True)
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(KIT / "memory/accomplishments.md").write_text(
    "# Accomplishments\n\n"
    "- 03-Oct-2026 [Decisions] ADR-012 accepted: Event bus for payments (ADR)\n"
    "- 15-Oct-2026 [Design documents] Payments hub IA v1.0 published (library)\n"
    "- 28-Sep-2026 [Other] Something from September (queue)\n")
(KIT / "QUEUE.md").write_text("# Queue\n\n## Alex\n\n## Done\n\n"
                              "- [x] **[work] Ran the vendor bake-off for observability** : done 20-Oct-2026\n"
                              "- [x] **Book the dentist** : done 21-Oct-2026\n")
for name, ver in (("2026-10-21", "1.4.0 (eb35214)"), ("2026-10-30", "1.5.1 (1fb4b08)")):
    (KIT / f"briefs/kit-release-notes-{name}.md").write_text(f"Kit was updated to {ver}.\n")
led = [{"date": "2026-10-02T07:45:00", "mode": "morning", "cost_usd": 0.5, "rc": 0},
       {"date": "2026-10-03T07:45:00", "mode": "morning", "cost_usd": 0.7, "rc": 1},
       {"date": "2026-10-06T06:30:00", "mode": "weekly", "cost_usd": 2.0, "rc": 0},
       {"date": "2026-10-07T09:45:00", "mode": "open", "cost_usd": 1.0, "rc": 0},
       {"date": "2026-10-08T16:20:00", "mode": "journal", "cost_usd": 0.8, "rc": 0},
       {"date": "2026-10-09T10:00:00", "mode": "kit-run:gateway", "cost_usd": None, "rc": 0},
       {"date": "2026-09-30T07:45:00", "mode": "morning", "cost_usd": 2.5, "rc": 0}]
(KIT / ".install/logs/cost.jsonl").write_text("\n".join(json.dumps(x) for x in led) + "\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-05", PYTHONDONTWRITEBYTECODE="1")
ENV.pop("COST_BUDGET_MONTHLY", None)


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *a], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


rc, out, err = run("month", "--json")
d = json.loads(out) if rc == 0 else {}
ok(rc == 0 and d.get("month") == "2026-10", "month defaults to last month", err)
texts = [w["text"] for w in d.get("wins", [])]
ok("ADR-012 accepted: Event bus for payments" in texts and "Payments hub IA v1.0 published" in texts,
   "the log's entries in the month", texts)
ok("Something from September" not in texts, "entries from other months stay out", texts)
ok(any("vendor bake-off" in t for t in texts) and [w for w in d["wins"] if "bake-off" in w["text"]][0]["pending"],
   "a finished work item not collected yet is in, marked pending", d.get("wins"))
ok(not any("dentist" in t for t in texts), "an owner's item without [work] stays out")
ok("Kit updated 2 times, 1.4.0 to 1.5.1" in texts and sum("Kit updated" in t for t in texts) == 1,
   "Kit's own updates fold into one line", texts)
ok(d.get("runs") == 6 and d.get("spend_usd") == 5.0 and d.get("spend_previous_month_usd") == 2.5,
   "runs and estimated cost from the ledger, with the month before", d)
ok(set(d.get("work_runs", {})) == {"morning", "weekly", "Kit's agents (kit-run)"}
   and d["work_runs"]["morning"] == {"runs": 2, "spend_usd": 1.2, "succeeded": 1, "unpriced": 0},
   "work runs by kind, with how many succeeded", d.get("work_runs"))
ok(d.get("other_runs") == {"runs": 2, "spend_usd": 1.8}, "every other run in one line", d.get("other_runs"))

rc, out, err = run("month", "--month", "2026-10")
ok(rc == 0 and out.startswith("# What Kit did in October 2026") and "For Alex's leadership update" in out,
   "the page: title and who it's for", out[:300])
ok("**4 pieces of work finished**" in out and "**6 scheduled runs**" in out and "+100% on the month before" in out,
   "at a glance: counts and the change on the month before", out[:900])
ok("| other runs | 2 |" in out and "open" not in out.split("## Kit's scheduled runs")[1].split("## Notes")[0]
   and "journal" not in out, "no personal or trading run is named", out)
ok("| Kit's agents (kit-run) | 1 | 1 | not priced |" in out, "an unpriced run says so instead of $0.00", out)
ok("not a bill" in out and "2 item(s) aren't in the log yet" in out, "the notes say what the figures are", out[-600:])
ok(not (KIT / "briefs/kit-month-2026-10.md").exists(), "without --write it writes nothing")

(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\nMONTH_REPORT_MODES="morning open"\n')
d = json.loads(run("month", "--json")[1])
ok(set(d["work_runs"]) == {"morning", "open"}, "MONTH_REPORT_MODES chooses the run kinds listed", d["work_runs"])

rc, out, err = run("month", "--write")
md, page = KIT / "briefs/kit-month-2026-10.md", KIT / "briefs/kit-month-2026-10.html"
ok(rc == 0 and md.is_file() and page.is_file(), "--write saves the Markdown and the HTML page", out + err)
h = page.read_text()
ok("<h1>What Kit did in October 2026</h1>" in h and "<table>" in h and "@media print" in h and "<script" not in h
   and "http" not in h.split("<body>")[0], "the HTML is self-contained and print-ready", h[:600])
ok(run("month", "--month", "2026-13")[0] != 0, "a bad month is refused")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-wins month tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
