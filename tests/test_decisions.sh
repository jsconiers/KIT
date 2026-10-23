#!/bin/bash
# Tests kit-decisions (draft proposed ADRs from meeting minutes) with synthetic minutes.
#   bash tests/test_decisions.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import json, os, pathlib, re, shutil, subprocess, sys, tempfile
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-decisions"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"; lib = tmp / "lib"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "templates").mkdir()
shutil.copy(repo / "kit/templates/adr-template.md", kit / "templates/adr-template.md")
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
(kit / "memory/context/decisions.md").write_text(
    "- **Folder:** `decisions/` in the library root.\n"
    "- **Template:** `~/nowhere/adr-template.md`, missing on purpose so the Kit copy is used.\n")
meet = lib / "artifacts/payments-upgrade/meetings"; meet.mkdir(parents=True)
(meet / "2026-10-14-design-review.md").write_text("""# Design review, 14-Oct-2026

- **Project:** payments-upgrade
- **Attendees:** Project manager, Solution architect, Security architect

## Decisions

| # | Decision | Decided by | Source |
|---|---|---|---|
| D1 | Adopt a managed message broker as the event streaming platform for settlement | Architecture review board | [PM] |
| D2 | Move the next meeting to Thursday | Project manager | [PM] |
| D3 | Use mTLS between the gateway and the settlement services | Security architect | [Architect] |
| D4 | Postpone the design review by one week | Project manager | [Transcript] |
| D5 | Budget for the second phase approved | Sponsor | [PM] |

## Actions

- [action] Circulate the minutes | owner: Project manager | due: 16-Oct-2026 | project: payments-upgrade | source: [PM]
""")
(meet / "2026-10-20-dr-workshop.md").write_text("""# DR workshop

## Decisions made

- Settlement moves to DR tier 2 with an RPO of 15 minutes, active-passive across two regions [Architect]
- Send the slides to the team [PM]
- Team lunch on Friday

## Open questions

- Is the reporting database in scope?
""")
(lib / "artifacts/other/meetings").mkdir(parents=True)
(lib / "artifacts/other/meetings/2026-10-01-kickoff.md").write_text("# Kickoff\n\n## Decisions\n\n- none\n")
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-21")
def run(*a):
    return subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)
ddir = lib / "decisions"

r = run("--project", "payments-upgrade")
o = r.stdout
ok(r.returncode == 0, "runs read-only")
ok("8 decision(s): 3 new architectural, 5 not architectural, 0 already recorded" in o, "counts: 3 architectural, 5 not")
ok(not ddir.exists(), "read-only: nothing written without --write")
ok("would be ADR-0001" in o and "would be ADR-0002" in o and "would be ADR-0003" in o, "numbers it would take")
ok(re.search(r"row 1\s+architectural .*message broker", o) and "platform or infrastructure" in o, "D1 platform choice is architectural, with the rule")
ok(re.search(r"row 2\s+not architectural: Move the next meeting", o) and "scheduling or logistics" in o, "D2 scheduling is not, with the reason")
ok(re.search(r"row 3\s+architectural", o) and "security control (mtls)" in o, "D3 mTLS is a security control")
ok(re.search(r"row 4\s+not architectural: Postpone the design review", o) and "doesn't outweigh" in o, "'design review' postponement is logistics")
ok(re.search(r"row 5\s+not architectural: Budget", o) and "budget" in o, "D5 budget is not architectural")
ok(re.search(r"row 1\s+architectural .*DR tier 2", o) and "DR or resilience" in o, "bullet decision: DR tier is architectural")
ok("Team lunch" in o and "no architectural signal" in o, "no signal: reason given")
ok("----- draft ADR-0001" in o and "| Status | proposed |" in o, "draft printed with status proposed")
ok("accepted |" not in o.split("----- draft")[1], "draft never says accepted")
ok("§Decisions row 1 (D1) [PM]" in o and "artifacts/payments-upgrade/meetings/2026-10-14-design-review.md, 14-Oct-2026" in o,
   "cites minutes file, date, and row")
ok("Architecture review board (as the minutes record it" in o, "decider carried by role")
ok("An example template" not in o and "<The problem" not in o, "template guidance stripped")
ok("## Options considered" in o and "## Change log" in o and o.index("## Context") < o.index("## Decision drivers") < o.index("## Sources"),
   "template's section order kept")

r = run("--project", "payments-upgrade", "--brief", "--json")
j = json.loads(r.stdout)
ok(j["next_number"] == "ADR-0004" and len([d for d in j["decisions"] if d["verdict"] == "draft"]) == 3, "--json: verdicts and next number")

# An existing ADR and index: numbering continues past both, never reuses.
ddir.mkdir()
(ddir / "ADR-0004-old-choice.md").write_text("# ADR-0004: old choice\n\n| Status | accepted |\n")
(ddir / "INDEX.md").write_text("# ADRs\n\n- **Next number:** ADR-0005\n\n| ADR | Title | Status | Date | Project | File |\n|---|---|---|---|---|---|\n"
                               "| ADR-0004 | old choice | accepted | 01-Oct-2026 | x | ADR-0004-old-choice.md |\n\nNotes below the table.\n")
r = run("--project", "payments-upgrade", "--write")
files = sorted(p.name for p in ddir.glob("ADR-*.md"))
ok(r.returncode == 0 and len(files) == 4 and files[1].startswith("ADR-0005-adopt-a-managed-message-broker"), "--write: numbered from INDEX next number")
idx = (ddir / "INDEX.md").read_text()
ok("Next number:** ADR-0008" in idx, "INDEX next number moved on")
ok(idx.count("| proposed |") == 3 and "| ADR-0006 |" in idx and "payments-upgrade" in idx, "INDEX rows added as proposed")
ok(idx.index("| ADR-0007 |") < idx.index("Notes below the table."), "rows go inside the table")
ok("accepted" in (ddir / "ADR-0004-old-choice.md").read_text(), "existing ADR untouched")
log = (ddir / "LOG.md").read_text()
ok("21-Oct-2026: ADR-0005 drafted as proposed by kit-decisions from artifacts/payments-upgrade/meetings/2026-10-14-design-review.md row 1" in log,
   "LOG line cites minutes and row")
a5 = (ddir / files[1]).read_text()
ok("kit-decisions: source=artifacts/payments-upgrade/meetings/2026-10-14-design-review.md#row1" in a5, "draft carries its source marker")

r = run("--project", "payments-upgrade", "--write")
ok("0 new architectural" in r.stdout and "3 already recorded" in r.stdout and "already recorded in ADR-0006" in r.stdout,
   "rerun skips decisions already recorded (same file and row)")
ok(len(list(ddir.glob("ADR-*.md"))) == 4 and "ADR-0008" in (ddir / "INDEX.md").read_text(), "rerun writes nothing new")

# Withdrawn number with no index entry is still never reused.
(ddir / "ADR-0009-withdrawn.md").write_text("# ADR-0009: withdrawn\n")
(meet / "2026-10-21-follow-up.md").write_text("## Decisions\n\n- Replace the legacy file transfer with the managed integration platform\n")
r = run(str(meet / "2026-10-21-follow-up.md"))
ok("would be ADR-0010" in r.stdout, "number past the highest ADR file, even unindexed")
r = run("--project", "other")
ok("0 decision(s)" in r.stdout and "no decisions found" in r.stdout, "placeholder 'none' ignored")
r = run()
ok(r.returncode == 0 and "4 minutes file(s)" in r.stdout, "default scans every project's minutes")
shutil.rmtree(tmp)
print(f"kit-decisions tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY
