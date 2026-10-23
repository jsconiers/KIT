#!/bin/bash
# Tests kit-stakeholders (stakeholder map by role) with synthetic project folders.
#   bash tests/test_stakeholders.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import json, os, pathlib, re, shutil, subprocess, sys, tempfile
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-stakeholders"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"; lib = tmp / "lib"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "templates").mkdir()
shutil.copy(repo / "kit/templates/stakeholder-map-template.md", kit / "templates/stakeholder-map-template.md")
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
proj = lib / "artifacts/payments-upgrade"
for d in ("meetings", "status", "intake"):
    (proj / d).mkdir(parents=True)
(lib / "artifacts/empty-project").mkdir(parents=True)
(lib / "demands").mkdir()
(lib / "demands/REGISTER.md").write_text("""# Demand register

| Number | Title | Status | Demand manager | Project manager | Requester | Project | Note |
|---|---|---|---|---|---|---|---|
| DMD-0101 | Payments upgrade | open | Pat Doe | Sam Roe | Lee Poe | payments-upgrade | |
| DMD-0102 | Other work | open | Kim Moe | | | other-project | |
""")
(proj / "intake/triage-2026-10-01.md").write_text("""# Intake triage: DMD-0101

- **Requester:** Lee Poe, Head of Payments Operations
- **IA sign-off:** Architecture review board
- **Design approval:** Design authority
- **Sponsor:** Jordan Coe
""")
(proj / "meetings/2026-10-14-design-review.md").write_text("""# Design review

- **Attendees:** Project manager, Solution architect, Security architect, Jane Smith, Network engineer [PM]

## Decisions

| # | Decision | Decided by | Source |
|---|---|---|---|
| D1 | Adopt the managed broker | Architecture review board | [PM] |

## Actions

- [action] Confirm firewall rules | owner: Network engineer | due: 20-Oct-2026 | project: payments-upgrade | source: [PM]
- [action] Update the threat model | owner: Security architect | due: no date | project: payments-upgrade | source: [Architect]
- [action] Draft the IA | owner: owner | due: 25-Oct-2026 | project: payments-upgrade | source: [Architect]
""")
(proj / "meetings/2026-10-21-cutover-planning.md").write_text("""# Cutover planning

- **Attendees:** Project manager, Network engineer, Operations lead

## Actions

- [action] Book the cutover window | owner: Network engineer | due: 28-Oct-2026 | project: payments-upgrade | source: [PM]
- [action] Prepare the runbook | owner: Operations lead | due: 30-Oct-2026 | project: payments-upgrade | source: [PM]
""")
(proj / "status/status-2026-10-20.md").write_text("""# Status: payments-upgrade

## Escalations needed

- Funding for the second region is unconfirmed (owner: Sponsor)
- Firewall change lead time threatens cutover | escalate to: Change advisory board
""")
(proj / "gds-v0.3.md").write_text("""# GDS

## RACI

| Activity | Project manager | Solution architect | Change advisory board | Operations lead |
|---|---|---|---|---|
| Design approval | C | R | I | C |
| Change approval | R | C | A | C |
""")
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-21")
def run(*a):
    return subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)

r = run("payments-upgrade")
o = r.stdout
ok(r.returncode == 0 and o.startswith("# Stakeholder map: payments-upgrade"), "prints the map, titled from the template")
for name in ("Pat Doe", "Sam Roe", "Lee Poe", "Jane Smith", "Jordan Coe", "Kim Moe"):
    if name in o: print("     leaked:", name)
ok(not any(n in o for n in ("Pat Doe", "Sam Roe", "Lee Poe", "Jane Smith", "Jordan Coe", "Kim Moe")), "no names in the output")
ok("left out" in o and re.search(r"\b[1-9]\d* entr", o), "entries without a role are counted, not printed")
def row(role):
    return next((ln for ln in o.splitlines() if ln.startswith(f"| {role} |")), "")
ok(row("Demand manager") and "REGISTER.md DMD-0101" in row("Demand manager"), "register role column on the project's row")
ok("Kim Moe" not in o and "DMD-0102" not in o, "other projects' register rows ignored")
ok("high (inferred)" in row("Requester").split("|")[4] and "intake triage-2026-10-01.md" in row("Requester"), "requester: high interest, cited")
ok(row("Head of payments operations"), "role kept from the requester field, name dropped")
ok(row("Architecture review board").split("|")[3].strip() == "high (inferred)", "sign-off role: high influence")
ok("minutes 2026-10-14-design-review.md (decided)" in row("Architecture review board"), "decider cited to minutes")
ne = row("Network engineer")
ok(ne and ne.split("|")[4].strip() == "high (inferred)" and "action owner" in ne, "frequent action owner: high interest")
ok(row("Security architect").split("|")[4].strip() == "medium (inferred)", "one action: medium interest")
ok(not row("Owner") and not row("Architect"), "the owner's own actions aren't a stakeholder")
ok(row("Sponsor") and "status-2026-10-20.md §Escalations" in row("Sponsor"), "escalation owner from status report")
cab = row("Change advisory board")
ok(cab and "| A |" in cab and "gds-v0.3.md §RACI" in cab, "RACI from a document, not marked inferred")
ok("R (inferred)" in ne, "RACI inferred when no document gives it")
ok("| R |" in row("Project manager") and "| A |" in cab, "RACI: the strongest letter across activities")
ok("| Sources |" in o, "sources column added to the template's table")
plan = o.split("## Engagement plan")[1].split("##")[0]
ok(re.search(r"\| Manage closely \|[^|]*Architecture review board", plan) or re.search(r"\| Keep satisfied \|[^|]*Architecture review board", plan),
   "engagement plan by quadrant")
gates = o.split("## Decisions and sign-offs")[1].split("##")[0]
ok("| IA sign-off | Architecture review board |" in gates and "Design approval" in gates and "| Change approval | Change advisory board |" in gates,
   "gates from the intake note and the RACI")
ok("Project manager, Solution architect, Operations lead" in gates or "Solution architect" in gates, "consulted roles from the RACI")
conc = o.split("## Concerns to address")[1]
ok("Funding for the second region" in conc and "| Change advisory board |" in conc, "concerns from escalations")
ok("<" not in re.sub(r"<!-- kit-stakeholders -->", "", o), "template guidance stripped")
ok("| Updated | 21-Oct-2026 |" in o and "| Project | payments-upgrade |" in o, "fields filled")

j = json.loads(run("payments-upgrade", "--json").stdout)
ok(j["dropped_without_role"] >= 1 and any(s["role"] == "Network engineer" and s["signals"]["actions"] == 2 for s in j["stakeholders"]), "--json signals")

r = run("payments-upgrade", "--write")
ok(r.returncode == 0 and (proj / "stakeholders.md").exists(), "--write saves stakeholders.md")
(proj / "stakeholders.md").write_text("hand edited\n")
r = run("payments-upgrade", "--write")
ok((proj / "stakeholders.md").read_text() == "hand edited\n" and (proj / "stakeholders-draft-2026-10-21.md").exists()
   and "merge" in r.stdout, "never overwrites: dated draft beside it")
ok("Network engineer" not in (proj / "stakeholders.md").read_text(), "stakeholders.md left alone")
r = run("payments-upgrade", "--write")
ok(r.returncode == 0, "its own draft can be refreshed")
r = run("empty-project")
ok(r.returncode == 0 and "no roles found" in r.stderr and "none recorded" in r.stdout, "empty project: says so")
r = run("--list")
ok("payments-upgrade  (has stakeholders.md)" in r.stdout and "empty-project" in r.stdout, "--list")
r = run("nope")
ok(r.returncode != 0 and "no project folder" in r.stderr, "unknown project refused")
r = run("payments-upgrade", "--names")
ok(r.returncode != 0, "there is no --names option")
shutil.rmtree(tmp)
print(f"kit-stakeholders tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY
