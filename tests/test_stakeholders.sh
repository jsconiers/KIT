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

# --raci: deliverables by role
(proj / "stakeholders.md").unlink()
for f in proj.glob("stakeholders-draft-*.md"):
    f.unlink()
before = run("payments-upgrade").stdout
r = run("payments-upgrade", "--raci")
o = r.stdout
ok(r.returncode == 0 and o.startswith("# RACI: payments-upgrade"), "--raci prints the matrix")
ok(not any(n in o for n in ("Pat Doe", "Sam Roe", "Lee Poe", "Jane Smith", "Jordan Coe", "Kim Moe")), "RACI: no names")
def rrow(name):
    ln = next((ln for ln in o.splitlines() if ln.startswith(f"| {name} |")), "")
    head = next(ln for ln in o.splitlines() if ln.startswith("| Deliverable |"))
    return dict(zip([c.strip() for c in head.strip("|").split("|")], [c.strip() for c in ln.strip("|").split("|")])) if ln else {}
ia, gds, cab = rrow("Impact assessment (IA)"), rrow("Design specification (GDS)"), rrow("Change request (CAB)")
ok(ia.get("Architecture review board") == "A" and ia.get("Demand manager") == "C*", "the intake's IA sign-off is the recorded Accountable; the inferred one steps down")
ok(ia.get("Solution architect") == "R*", "inferred cells carry a star")
ok(gds.get("Design authority") == "A" and gds.get("Solution architect") == "R" and gds.get("Change advisory board") == "I",
   "a recorded RACI row (Design approval) fills the design specification, with no stars")
ok(cab.get("Change advisory board") == "A" and cab.get("Project manager") == "R" and "gds-v0.3.md §RACI" in cab.get("Sources", ""),
   "Change approval lands on the change request row, cited")
ok(rrow("Security review").get("Security architect") == "R/A*", "the one who signs it off and does it: R/A")
ok(sum(1 for v in rrow("Cutover").values() if v.startswith("A")) == 1, "one Accountable per deliverable")
ok("## Checks" in o, "a checks section")
j = json.loads(run("payments-upgrade", "--raci", "--json").stdout)
ok(j["deliverables"][0]["name"] == "Impact assessment (IA)" and j["deliverables"][0]["cells"]["Architecture review board"]
   == {"letter": "A", "recorded": True}, "--raci --json")
r = run("payments-upgrade", "--raci", "--write")
ok(r.returncode == 0 and (proj / "raci.md").exists(), "--raci --write saves raci.md")
ok(run("payments-upgrade").stdout.split("## Stakeholders")[1] == before.split("## Stakeholders")[1],
   "its starred cells are drafts: the stakeholder map reads none of them as records")
r = run("payments-upgrade", "--raci", "--write")
ok((proj / f"raci-draft-2026-10-21.md").exists() and "merge" in r.stdout, "raci.md is never overwritten: a dated draft")
txt = (proj / "raci.md").read_text().replace("| Build and test | I* | I* |", "| Build and test | I | I |")
(proj / "raci.md").write_text(txt)
build = None
for ln in run("payments-upgrade", "--raci").stdout.splitlines():
    if ln.startswith("| Build and test |"):
        build = ln
ok(build and build.startswith("| Build and test | I | I |"), "a star taken off is read as recorded next time")
(proj / "raci.md").unlink()
(proj / "raci-draft-2026-10-21.md").unlink()
# Kit's own raci.md is never read back as a record: its unstarred letters are copies, and the record moved.
run("payments-upgrade", "--raci", "--write")
intake = proj / "intake/triage-2026-10-01.md"
old_intake = intake.read_text()
intake.write_text(old_intake.replace("- **IA sign-off:** Architecture review board", "- **IA sign-off:** Design authority"))
j = json.loads(run("payments-upgrade", "--raci", "--json").stdout)
iaj = j["deliverables"][0]
accts = [k for k, v in iaj["cells"].items() if "A" in v["letter"]]
ok(accts == ["Design authority"] and not any("raci.md" in s for s in iaj["sources"])
   and not any(c.startswith("Impact assessment (IA): 2") for c in j["checks"]),
   "a sign-off that moved: Kit's old raci.md doesn't bring the old one back")
intake.write_text(old_intake)
(proj / "raci.md").unlink()
# One role: the Sources column doesn't count against the letters, so a star taken off still reads back.
solo = lib / "artifacts/solo-project"
(solo / "meetings").mkdir(parents=True)
(solo / "meetings/2026-10-14-kickoff.md").write_text("# Kickoff\n\n- **Attendees:** Solution architect\n")
run("solo-project", "--raci", "--write")
st = (solo / "raci.md").read_text()
ok("| Impact assessment (IA) | R* |" in st, "one role: the matrix has one column")
(solo / "raci.md").write_text(st.replace("| Impact assessment (IA) | R* |", "| Impact assessment (IA) | R |"))
j = json.loads(run("solo-project", "--raci", "--json").stdout)
ok(j["deliverables"][0]["cells"].get("Solution architect") == {"letter": "R", "recorded": True}
   and "raci.md §RACI" in j["deliverables"][0]["sources"], "one role: a star taken off is read as recorded")
ok(all(v["recorded"] is False for d in j["deliverables"][1:] for v in d["cells"].values()),
   "one role: the cells left as Kit wrote them stay inferred")
# An intake sign-off over an inferred R/A: the R stays and the A moves, so one Accountable.
cp = lib / "artifacts/change-project"
(cp / "intake").mkdir(parents=True)
(cp / "meetings").mkdir()
(cp / "meetings/2026-10-14-cab.md").write_text("# CAB prep\n\n- **Attendees:** Change manager, Service owner\n")
(cp / "intake/triage-2026-10-01.md").write_text("# Intake triage\n\n- **Change approval:** Service owner\n")
j = json.loads(run("change-project", "--raci", "--json").stdout)
cabj = next(d for d in j["deliverables"] if d["name"] == "Change request (CAB)")
ok(cabj["cells"].get("Service owner") == {"letter": "A", "recorded": True}
   and cabj["cells"].get("Change manager") == {"letter": "R", "recorded": False}
   and not any(c.startswith("Change request (CAB): 2") for c in j["checks"]),
   "an intake sign-off over an inferred R/A: the R stays, one Accountable")
(proj / "plan.md").write_text("""# Plan

| Activity | Project manager | Operations lead | Solution architect |
|---|---|---|---|
| Cutover | A | A | C |
| Data migration rehearsal | R | A | C |
""")
o = run("payments-upgrade", "--raci").stdout
ok("Cutover: 2 Accountable roles (Operations lead, Project manager); there should be one" in o, "two Accountable: flagged")
ok(o.count("| Cutover |") == 1, "a recorded row on a default deliverable joins it")
ok(any(ln.startswith("| Data migration rehearsal |") for ln in o.splitlines()),
   "an activity that only mentions a deliverable keeps a row of its own")
(proj / "plan.md").write_text("""# Plan

| Activity | Project manager | Operations lead |
|---|---|---|
| Training for the service desk | R | A |
""")
o = run("payments-upgrade", "--raci").stdout
ok(any(ln.startswith("| Training for the service desk |") for ln in o.splitlines()), "a recorded activity of its own gets its own row")
(proj / "plan.md").unlink()
r = run("empty-project", "--raci")
ok(r.returncode == 0 and "No roles found" in r.stdout and "no Accountable role found" in r.stdout, "empty project: the matrix says so")
shutil.rmtree(tmp)
print(f"kit-stakeholders tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY
