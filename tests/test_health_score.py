#!/usr/bin/env python3
"""Tests for kit_health, the one health number on the dashboard's badge (and doctor.py --score): each of its four
parts (connectors, runs, audit, setup) from synthetic files, the bands, and the badge. No model, connector, or
web call.

  python3 tests/test_health_score.py
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "shared"))
import kit_health as kh  # noqa: E402

P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-health-"))
KIT = TMP / "kit"
for d in ("memory/context", "briefs", "agents"):
    (KIT / d).mkdir(parents=True)
TODAY = dt.date(2026, 11, 5)
W = lambda rel, obj: (KIT / rel).write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")  # noqa: E731
REL = {"windows": {"7": {"morning": {"runs": 5, "success": 4, "degraded": 0, "failure": 1},
                         "weekly": {"runs": 1, "success": 0, "degraded": 1, "failure": 0}}}}

# Nothing yet: no connectors (full), no audit (half), no setup fields (full); runs from the report given.
res = kh.score(KIT, TODAY, REL)
parts = {p["name"]: p for p in res["parts"]}
ok(parts["Connectors"]["score"] == 25 and parts["Connectors"]["detail"] == "none configured", "no connectors: full marks")
ok(parts["Audit"]["score"] == 12.5, "no audit status: half marks", parts["Audit"])
ok(parts["Runs"]["score"] == round(25 * 4.5 / 6, 1) and "1 failed run" in parts["Runs"]["problems"][0],
   "runs: a success counts 1, degraded half, a failure 0", parts["Runs"])
ok(kh.runs(KIT, {"windows": {"7": {}}})["score"] == 12.5, "no runs in 7 days: half marks")

# Connectors: one passing, one failing, one with an outage, one never checked.
W("memory/context/connector-guard.json", {"allowed_servers": ["a", "b", "c", "d"]})
W("briefs/connectors-history.jsonl", "\n".join(json.dumps(x) for x in (
    {"date": "2026-11-04", "server": "a", "pass": False}, {"date": "2026-11-05", "server": "a", "pass": True},
    {"date": "2026-11-05", "server": "b", "pass": False}, {"date": "2026-11-05", "server": "c", "pass": False})))
W("briefs/connectors-alerts.json", {"c": {"since": "2026-11-03", "streak": 3}})
c = kh.connectors(KIT, TODAY)
ok(c["score"] == round(25 * 1.5 / 4, 1) and c["detail"] == "1 of 4 passing", "connectors: pass 1, fail 0, outage 0, "
   "unchecked half", c)
ok(any("outage since 2026-11-03" in x for x in c["problems"]) and any("d: no check" in x for x in c["problems"]),
   "connectors: each problem is named", c["problems"])

# Audit: findings and open integrity alerts; run alerts cost the runs part.
W("briefs/audit-status.json", {"daily": {"severity_counts": {"critical": 1, "warning": 2}},
                               "findings": [{"severity": "critical", "title": "Write call allowed"}]})
W("briefs/alerts.json", {"alerts": {"x": {"kind": "drift", "reason": "2 agents out of date"},
                                    "y": {"kind": "run", "mode": "morning", "reason": "failed twice"},
                                    "z": {"kind": "waiting", "item": "a decision"}}})
a = kh.audit(KIT)
ok(a["score"] == 25 - 10 - 6 - 3 and "1 integrity alert open" in a["detail"]
   and any("agent drift" in x for x in a["problems"]), "audit: 10 per critical, 3 per warning, 3 per integrity alert", a)
r = kh.runs(KIT, REL)
ok(r["score"] == round(25 * 4.5 / 6 - 5, 1) and any("morning: failed twice" in x for x in r["problems"]),
   "runs: an open run alert takes 5 off", r)

# Setup: fields not set in the setup files the agents name (files no agent names don't count).
W("memory/context/audit.md", "# Audit\n- **Audit folder:** not set\n- **Reports:** `~/r`\n- **Reviewers:** not set\n"
                              "- **Working hours:** 07:00 to 19:00\n")
W("memory/context/other.md", "- **Nobody reads this:** not set\n")
W("agents/auditor.md", "---\nname: auditor\n---\nRead memory/context/audit.md first.\n")
s = kh.setup(KIT)
ok(s["score"] == 12.5 and s["detail"].startswith("2 open setup questions (2 of 4 fields set)")
   and "audit.md: Audit folder" in s["problems"], "setup: the share of fields set, in files the agents name", s)

res = kh.score(KIT, TODAY, REL)
ok(res["score"] == round(sum(p["score"] for p in res["parts"])) and res["band"] == "unhealthy", "the total and its band",
   res["score"])
ok(kh.band(90) == "healthy" and kh.band(89) == "needs attention" and kh.band(69) == "unhealthy", "bands: 90 and 70")
b = kh.badge(res)
ok('class="hbadge fail"' in b and f">{res['score']}<" in b and "Setup 12.5/25" in b, "the badge: score, colour, "
   "and where points went", b)
ok("<li" in kh.panel(res) and "doctor.py --score" in kh.panel(res), "the panel lists the parts")
print(kh.render(res))

# doctor.py --score, as a command.
r = subprocess.run([sys.executable, str(REPO / "shared/doctor.py"), "--score", "--json"], capture_output=True, text=True,
                   env=dict(os.environ, KIT_DIR=str(KIT), HOME=str(TMP), PYTHONDONTWRITEBYTECODE="1"), timeout=120)
j = json.loads(r.stdout) if r.returncode == 0 else {}
ok(j.get("method", "").startswith("kit_health") and len(j.get("parts", [])) == 4, "doctor.py --score --json", r.stderr)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nhealth score tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
