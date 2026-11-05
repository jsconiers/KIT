#!/usr/bin/env python3
"""Tests for kit-review-loop: plan (read-only, the agent commands, the cost estimate), run (the reviewer first,
then the three security agents, each through kit_claude with a fake claude; asking first, the budget, copies
into reviews/, the cost), merge (one ranked table from synthetic review notes), and feedback (accepted and
changed items only, by ID, for the next version). Everything happens in a temp folder; the review notes are
made up for the test.

  python3 tests/test_review_loop.py
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-review-loop"
WIN = os.name == "nt"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-review-loop-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/payments-hub"
CALLS = TMP / "calls"
for d in (KIT / "memory/context", KIT / ".install/shared/morning", KIT / ".install/logs", PROJ / "reviews",
          PROJ / "drafts", CALLS, HOME / ".local/bin"):
    d.mkdir(parents=True, exist_ok=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n", encoding="utf-8")
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n', encoding="utf-8")
DRAFT = PROJ / "drafts/Payments hub IA v0.2.md"
DRAFT.write_text("# Payments hub IA v0.2\n## 1 Scope\nOne database in one zone.\n", encoding="utf-8")
(PROJ / "drafts/Payments hub IA v0.1.md").write_text("# v0.1\n", encoding="utf-8")
(PROJ / "feedback-v0.2.md").write_text("# Feedback for v0.2\n", encoding="utf-8")

# PYTHONDONTWRITEBYTECODE: macOS's own Python 3.9 caches bytecode under ~/Library/Caches, which is in TMP here.
ENV = dict(os.environ, KIT_DIR=str(KIT), HOME=str(HOME), USERPROFILE=str(HOME), KIT_TODAY="2026-11-03",
           CLAUDE_CODE_OAUTH_TOKEN="placeholder-for-tests", FAKE_CALLS=str(CALLS), PYTHONDONTWRITEBYTECODE="1")
ENV.pop("COST_BUDGET_MONTHLY", None)


def run(*args, env=None, stdin=None):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                       env=env or ENV, input=stdin, timeout=120)
    return r.returncode, r.stdout, r.stderr


def note(name, text):
    (PROJ / "reviews" / name).write_text(text, encoding="utf-8")


# ---- synthetic review notes -------------------------------------------------------------------------------
note("Payments hub IA v0.1-review-2026-10-20.md", """# Review: Payments hub IA v0.1
Date: 20-Oct-2026

## Findings

| ID | Severity | Category | Template | Section | Finding | Fix |
|---|---|---|---|---|---|---|
| F-01 | critical | template | IA | 3 | An old finding from v0.1. | Old fix. |
""")
note("Payments hub IA v0.2-review-2026-10-20.md", """# Review: Payments hub IA v0.2
Date: 20-Oct-2026

## Findings

| ID | Severity | Category | Template | Section | Finding | Fix |
|---|---|---|---|---|---|---|
| F-01 | minor | style | IA | 2 Scope | Passive voice in the scope. | Use active voice. |
| F-02 | major | source | IA | 4.1 Requirements | FR-3 doesn't trace to the demand; it says a \\| b. | Trace FR-3 or drop it. |
| F-03 | critical | risk | IA | 5 DR | No RTO or RPO. | State the RTO and RPO. |

## Secure by Design

| # | Question (short) | Answer | Evidence |
|---|---|---|---|
| 1 | Secure by default | no | not stated |
""")
note("payments-hub-ia-v0.2-red-team-v1.md", """# Red-team review: Payments hub
Date: 21-Oct-2026

## Assumptions that would break it

| ID | Assumption | Why it matters |
|---|---|---|
| A-01 | The zone never fails. | Everything. |

## Findings, most consequential first

| ID | Consequence | Likelihood | Area | Failure scenario | Evidence | Mitigation | Status |
|---|---|---|---|---|---|---|---|
| RT-01 | critical | possible | DR and recovery | A zone loss stops payments for hours. | IA 5 | A second zone with tested failover. | open |
| RT-02 | major | likely | operations | Certificates expire unnoticed. | not stated | Monitor expiry. | open |
| RT-03 | minor | unlikely | scaling | Batch runs long at month end. | IA 4.2 | Split the batch. | open |
| RT-04 | critical | possible | concentration | Already fixed in v0.2. | IA 3 | n/a | fixed |
""")
note("payments-hub-threat-model-v1.md", """# Threat model: Payments hub
Date: 21-Oct-2026

## Threats

| ID | Flow or element | STRIDE | Threat | ATT&CK | Existing control (evidence) | Gap | 800-53 | L | I | Risk | Mitigation (owner if another team) | Test case ID |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T-01 | F-02 | Spoofing | A caller replays a captured token. | T1550 | mTLS (IA 6) | Tokens don't expire. | IA-5 | 2 | 3 | high | Short-lived tokens. | TC-01 |
| T-02 | E-01 | Tampering | Config changed without review. | | Change control (IA 7) | none | CM-3 | 1 | 2 | low | n/a | |
| T-03 | F-03 | Repudiation | Admin actions aren't logged. | | not stated | No audit log. | AU-2 | 2 | 2 | medium | Log admin actions centrally. | TC-02 |

## Test cases, for the implementation planner

| ID | Threat | Test | Expected result |
|---|---|---|---|
| TC-01 | T-01 | Replay an expired token. | Rejected. |
""")
note("payments-hub-standards-check-v1.md", """# Standards check: Payments hub IA v0.2
Date: 22-Oct-2026

## 3. Conformance table

| # | Standard, clause | Result | Evidence (standard) | Evidence (draft) |
|---|---|---|---|---|
| A-1 | Encryption standard v3 §4.1 | Conforms | TLS 1.2+ | IA 6 |
| A-2 | Logging standard v2 §2.2 | **Gap** | Central logging required. | IA 7 |
| A-3 | DR standard v1 §3 | Partial | Tier 1 needs two sites. | IA 5 |
| A-4 | Patching standard v1 §1 | Not applicable | | |
| A-5 | MFA standard v2 §2 | Not stated | MFA for admins. | not stated |

## 5. Exceptions (waiver candidates)

| ID | Standard and clause | What the design does instead | Reason given | Compensating control | Waiver route |
|---|---|---|---|---|---|
| EXC-0001 | Logging standard v2 §2.2 | Local logs. | Cost. | None. | CISO |

## 7. Suggested fixes for the writers

1. A-2: send the logs to the central service.
2. A-3, A-5: name the second site, and require MFA for admins.
""")
note("old-notes.md", "# Some notes with no table\n")

# ---- plan --------------------------------------------------------------------------------------------------
def snapshot():
    return sorted((str(p), p.stat().st_mtime) for p in TMP.rglob("*") if p.is_file())


before = snapshot()
rc, out, err = run("plan", "payments-hub", "Payments hub IA v0.2.md")
ok(rc == 0, "plan runs", err)
ok(snapshot() == before, "plan writes nothing")
for a in ("reviewer", "red-team", "threat-modeler", "standards-checker"):
    ok(f"--agent {a}" in out, f"plan shows the {a} run's command", out[-600:])
ok(out.index("1. Reviewer") < out.index("2. Then side by side: red-team, threat-modeler, standards-checker"),
   "plan: the reviewer first, then the three side by side", out[:800])
ok("--strict-mcp-config" in out and "--disallowedTools" in out and "Bash" in out,
   "plan: the runs load no MCP servers and deny the shell", out[-800:])
proj_rule = "Edit(//" + PROJ.resolve().as_posix().lstrip("/") + "/**)" if not WIN else "Edit(//"
ok(proj_rule in out and "Write(" in out, "plan: writes are allowed only in the project folder", out[-900:])
ok("about $8.00 for 4 run(s), $2.00 each (assumed: no review-loop runs recorded yet)" in out,
   "plan: an assumed cost with no history", out[-500:])
(KIT / ".install/logs/cost.jsonl").write_text(
    json.dumps({"date": "2026-10-01T09:00:00", "mode": "review-loop", "cost_usd": 1.0}) + "\n"
    + json.dumps({"date": "2026-10-01T09:05:00", "mode": "review-loop", "cost_usd": 3.0}) + "\n"
    + json.dumps({"date": "2026-10-01T09:05:00", "mode": "morning", "cost_usd": 9.0}) + "\n", encoding="utf-8")
rc, out, err = run("plan", "payments-hub", "Payments hub IA v0.2.md", "--only", "reviewer")
ok("about $2.00 for 1 run(s), $2.00 each (the average of 2 earlier review-loop run(s))" in out,
   "plan: the estimate averages earlier review-loop runs from the ledger", out[-400:])
ok("--agent red-team" not in out and "--only reviewer" in out, "plan --only reviewer: just the reviewer", out[:400])
rc, out, err = run("plan", "payments-hub", "missing.md")
ok(rc == 1 and "no draft" in err, "plan: a draft that isn't there", err)
rc, out, err = run("plan", "payments-hub", "Payments hub IA v0.2.md", "--only", "writer")
ok(rc == 2 and "unknown agent writer" in err, "plan: an unknown agent", err)
rc, out, err = run("plan", "no-such-project", "x.md")
ok(rc == 1 and "no project folder" in err, "plan: a project that isn't there", err)

# ---- merge -------------------------------------------------------------------------------------------------
rc, out, err = run("merge", "payments-hub")
dec = PROJ / "review-decisions-2026-11-03.md"
ok(rc == 0 and dec.is_file(), "merge writes review-decisions-<date>.md in the project", out + err)
text = dec.read_text(encoding="utf-8")
rows = [ln for ln in text.splitlines() if re.match(r"^\| \d+ \|", ln)]
ids = [ln.split(" | ")[3] for ln in rows]
ok("| # | Rank | Source | ID | Location | Finding | Suggested fix | Decision | Notes |" in text,
   "merge: one table with the source ID, location, finding, fix, and an empty Decision column", text[:900])
ok(all(ln.endswith("|  |  |") for ln in rows), "merge: Decision and Notes are empty for every row")
ok(sorted(ids) == sorted(["F-01", "F-02", "F-03", "RT-01", "RT-02", "RT-03", "T-01", "T-03", "A-2", "A-3", "A-5"]),
   "merge: the latest reviewer note, red-team findings, threats with a gap, and standards gaps", ids)
ok("An old finding from v0.1" not in text, "merge: only the latest note of each kind (v0.2 over v0.1, same date)")
ok("RT-04" not in ids and "A-01" not in ids and "TC-01" not in ids and "EXC-0001" not in ids,
   "merge: fixed findings, assumptions, test cases, and waiver rows stay out", ids)
ranks = [ln.split(" | ")[1] for ln in rows]
ok(ranks == sorted(ranks, key=["must fix", "should fix", "nit"].index), "merge: ranked must fix, then should fix, then nit", ranks)
rank = dict(zip(ids, ranks))
ok(rank["RT-01"] == rank["F-03"] == rank["T-01"] == rank["A-2"] == "must fix", "merge: critical, high, and gaps are must fix", rank)
ok(rank["RT-02"] == rank["F-02"] == rank["T-03"] == rank["A-3"] == rank["A-5"] == "should fix",
   "merge: major, medium, partial, and not stated are should fix", rank)
ok(rank["RT-03"] == rank["F-01"] == "nit", "merge: minor is a nit", rank)
ok(ids.index("RT-01") < ids.index("T-01") and ids.index("F-03") < ids.index("T-01"),
   "merge: within a rank, critical before high, never by ease of fix", ids)
a2 = next(ln for ln in rows if ln.split(" | ")[3] == "A-2")
ok("send the logs to the central service" in a2 and "IA 7" in a2 and "Logging standard v2 §2.2: Gap" in a2,
   "merge: a standards gap gets its suggested fix, its draft location, and the clause", a2)
a5 = next(ln for ln in rows if ln.split(" | ")[3] == "A-5")
ok("require MFA for admins" in a5, "merge: a fix line that names two IDs goes to both", a5)
f02 = next(ln for ln in rows if ln.split(" | ")[3] == "F-02")
ok("a \\| b" in f02 and "IA 4.1 Requirements" in f02, "merge: escaped pipes survive, and location is template and section", f02)
t01 = next(ln for ln in rows if ln.split(" | ")[3] == "T-01")
ok("Gap: Tokens don't expire." in t01 and "Short-lived tokens." in t01 and "| F-02 |" in t01,
   "merge: a threat with its gap, mitigation, and flow", t01)
ok("- red team: `reviews/payments-hub-ia-v0.2-red-team-v1.md`" in text and "11 findings: 4 must fix, 5 should fix, 2 nit."
   in text, "merge: names the notes it read and the counts", text[:900])

rc, out, err = run("merge", "payments-hub")
ok(rc == 1 and "--force" in err, "merge: won't replace today's file without --force", err)
rc, out, err = run("merge", "payments-hub", "--force")
ok(rc == 0, "merge --force: replaces it while no decision is filled in", err)
rc, out, err = run("merge", "payments-hub", "--notes", "payments-hub-threat-model-v1.md", "--force")
t = dec.read_text(encoding="utf-8")
ok(rc == 0 and "T-01" in t and "RT-01" not in t and "not found: reviewer, red team, standards" in t,
   "merge --notes: just the notes named", t[:700])
run("merge", "payments-hub", "--force")

# ---- feedback ----------------------------------------------------------------------------------------------
def decide(choices):
    lines = []
    for ln in dec.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| \d+ \| [^|]+ \| [^|]+ \| ([^|]+?) \|", ln)
        if m and m.group(1) in choices:
            d, n = choices[m.group(1)]
            ln = ln[: -len("|  |  |")] + f"| {d} | {n} |"
        lines.append(ln)
    dec.write_text("\n".join(lines) + "\n", encoding="utf-8")


decide({"RT-01": ("accept", ""), "F-03": ("Accept", "and say who owns DR"), "A-2": ("change", "use the team's log relay"),
        "T-01": ("reject", "")})
rc, out, err = run("feedback", "payments-hub")
ok(rc == 1 and "row(s) with no decision" in err and not list(PROJ.glob("feedback-v0.3.md")),
   "feedback: stops while rows have no decision, and writes nothing", err)
rc, out, err = run("merge", "payments-hub", "--force")
ok(rc == 1 and "already has 4 decision(s)" in err, "merge never overwrites a decisions file with decisions in it", err)
decide({i: ("reject", "") for i in ("RT-02", "RT-03", "T-03", "A-3", "F-01", "F-02")})
decide({"A-5": ("change", "")})
rc, out, err = run("feedback", "payments-hub")
ok(rc == 1 and "change with no note" in err and "A-5" in err, "feedback: a change with no note stops it", err)
rc, out, err = run("feedback", "payments-hub", "--partial")
fb = PROJ / "feedback-v0.3.md"
ok(rc == 0 and fb.is_file(), "feedback --partial: writes feedback-v<next> (v0.2 drafts and feedback -> v0.3)", out + err)
ft = fb.read_text(encoding="utf-8")
ok("# Feedback for v0.3: payments-hub" in ft and "From Alex's decisions in `review-decisions-2026-11-03.md`" in ft,
   "feedback: for the next version, from the owner's decisions", ft[:400])
frows = [ln for ln in ft.splitlines() if re.match(r"^\| \d+ \|", ln)]
fids = [ln.split(" | ")[2] for ln in frows]
ok(fids == ["RT-01", "F-03", "A-2"], "feedback: accepted and changed items only, by ID, in rank order", fids)
ok("State the RTO and RPO. (Alex: and say who owns DR)" in ft, "feedback: an accepted fix, with the owner's note", ft)
ok("Alex's change: use the team's log relay" in ft and "send the logs to the central service" not in ft,
   "feedback: a changed item carries the owner's change, not the suggested fix", ft)
ok(not {"T-01", "RT-02", "A-5"} & set(fids), "feedback: rejected and left-out items aren't there", fids)
ok("left out" in out and "A-5" in out, "feedback --partial says what it left out", out)
rc, out, err = run("feedback", "payments-hub", "--partial", "--version", "0.3")
ok(rc == 1 and "already there" in err, "feedback: won't replace a feedback file without --force", err)
rc, out, err = run("feedback", "payments-hub", "--partial")
ok(rc == 0 and (PROJ / "feedback-v0.4.md").is_file(), "feedback: the next one after an existing feedback-v0.3 is v0.4",
   out + err)
rc, out, err = run("feedback", "payments-hub", "--partial", "--version", "v1.0")
ok(rc == 0 and (PROJ / "feedback-v1.0.md").is_file(), "feedback --version: the version given", out + err)
rc, out, err = run("feedback", "payments-hub", "--decisions", "nope.md")
ok(rc == 1 and "no such decisions file" in err, "feedback --decisions: a file that isn't there", err)

# ---- score and status ----------------------------------------------------------------------------------------
before = snapshot()
rc, out, err = run("score", "payments-hub", "--json")
sc = json.loads(out) if rc == 0 else {}
ok(rc == 0 and snapshot() == before, "score runs and writes nothing", err)
ok(sc.get("open") == {"must fix": 3, "should fix": 1, "nit": 0} and sc.get("rejected_left_out") == 7,
   "score: findings the latest decisions rejected are left out; accepted and undecided ones stay open", sc.get("open"))
ok(sc.get("score") == 60 and sc.get("verdict") == "not ready" and "3 must fix" in sc.get("headline", ""),
   "score: 100 less 12 per must fix and 4 per should fix; any must fix is not ready", sc.get("headline"))
ok(set(sc.get("notes", {})) == {"reviewer", "red team", "threat model", "standards"} and not sc.get("missing"),
   "score: reads the latest note of each of the four kinds", sc.get("notes"))
rc, out, err = run("score", "payments-hub")
ok(rc == 0 and "payments-hub: Not ready: 60/100" in out and "Must fix:" in out and "RT-01" in out,
   "score: the text names the verdict and the must-fix findings", out)
nxt = PROJ / "drafts/Payments hub IA v0.3.md"
nxt.write_text("# v0.3\n", encoding="utf-8")
os.utime(nxt, (time.time() + 60, time.time() + 60))
sc = json.loads(run("score", "payments-hub", "--json")[1])
ok(len(sc["stale"]) == 4 and sc["draft"].endswith("v0.3.md"), "score: notes older than the latest draft are stale",
   sc["stale"])
nxt.unlink()
other = LIB / "artifacts/ledger-sync"
(other / "reviews").mkdir(parents=True)
(other / "reviews/ledger-sync-review-v1.md").write_text(
    "# Review\nDate: 01-Nov-2026\n\n## Findings\n\n| ID | Severity | Category | Template | Section | Finding | Fix |\n"
    "|---|---|---|---|---|---|---|\n| F-01 | minor | style | GDS | 2 | Wordy. | Trim. |\n", encoding="utf-8")
sc = json.loads(run("score", "ledger-sync", "--json")[1])
ok(sc["score"] == 100 - 1 - 3 * 15 and sc["verdict"] == "not ready" and len(sc["missing"]) == 3,
   "score: each review with no note costs 15 and blocks ready", sc)
for name, body in (("red-team", "| ID | Area | Failure scenario | Consequence | Evidence | Mitigation |\n|---|---|---|---|---|---|\n"
                                 "| RT-01 | Ops | x | low | GDS 2 | y |\n"),
                   ("threat-model", "| ID | STRIDE | Threat | Flow or element | Risk | Mitigation | Gap |\n"
                                    "|---|---|---|---|---|---|---|\n| T-01 | S | x | api | low | y | none |\n"),
                   ("standards", "| ID | Standard | Clause | Result | Evidence (draft) |\n|---|---|---|---|---|\n"
                                 "| S-1 | Logging | 2.1 | Conforms | GDS 3 |\n")):
    (other / f"reviews/ledger-sync-{name}-v1.md").write_text(f"# {name}\nDate: 01-Nov-2026\n\n{body}", encoding="utf-8")
sc = json.loads(run("score", "ledger-sync", "--json")[1])
ok(sc["score"] == 98 and sc["verdict"] == "ready" and sc["headline"] == "Ready for ARB: 98/100",
   "score: all four notes, no must fix (two nits), at or over the threshold: ready for ARB", sc)
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\nREADINESS_THRESHOLD="99"\n', encoding="utf-8")
sc = json.loads(run("score", "ledger-sync", "--json")[1])
ok(sc["verdict"] == "almost" and sc["threshold"] == 99, "score: READINESS_THRESHOLD sets the bar; under it is almost", sc)
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n', encoding="utf-8")
rc, out, err = run("status", "--json")
st = json.loads(out) if rc == 0 else []
ok([x["project"] for x in st] == ["payments-hub", "ledger-sync"] or [x["project"] for x in st] == ["ledger-sync", "payments-hub"],
   "status: every project with review notes", out + err)
ph = [x for x in st if x["project"] == "payments-hub"][0] if st else {}
ok({l["label"] for l in ph.get("links", [])} >= {"reviewer", "red team", "threat model", "standards", "decisions"},
   "status: links each note and the decisions file", ph.get("links"))
rc, out, err = run("status")
ok(rc == 0 and "ledger-sync: Ready for ARB: 98/100" in out, "status: one line per project", out)
shutil.rmtree(other)

# ---- run, with a fake claude -------------------------------------------------------------------------------
FAKE = TMP / "fake_claude.py"
FAKE.write_text(r'''
import json, os, pathlib, re, sys, time
argv = sys.argv[1:]
agent = argv[argv.index("--agent") + 1]
p = argv.index("-p")
stdin = p + 1 >= len(argv) or argv[p + 1].startswith("--")      # no prompt after -p: it's on standard input
brief = sys.stdin.read() if stdin else argv[p + 1]
calls = pathlib.Path(os.environ["FAKE_CALLS"])
(calls / ("%f-%s.json" % (time.time(), agent))).write_text(json.dumps({"agent": agent, "argv": argv,
    "token_set": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")), "cwd": os.getcwd(), "stdin": stdin,
    "brief": brief}))
folder = pathlib.Path(re.search(r"whose library folder is (.+?)\.(?: The IA|\n)", brief).group(1))
sub = {"reviewer": "reviews", "red-team": "red-team", "threat-modeler": "threat-model",
       "standards-checker": "standards"}[agent]
(folder / sub).mkdir(parents=True, exist_ok=True)
name = {"reviewer": "Payments hub IA v0.2-review-2026-11-03.md", "red-team": "payments-hub-ia-v0.2-red-team-v2.md",
        "threat-modeler": "payments-hub-threat-model-v2.md", "standards-checker": "payments-hub-standards-check-v2.md"}[agent]
(folder / sub / name).write_text("# note\nDate: 03-Nov-2026\n")
if agent in ("red-team", "standards-checker"):          # the threat modeler "forgets" its copy
    (folder / "reviews" / name).write_text("# note\nDate: 03-Nov-2026\n")
time.sleep(0.3)
print(json.dumps({"type": "result", "result": str(folder / sub / name) + "\nVerdict: fine", "total_cost_usd": 0.5,
                  "usage": {"input_tokens": 10, "output_tokens": 5}, "modelUsage": {}, "num_turns": 3}))
''', encoding="utf-8")
if WIN:
    (HOME / ".local/bin/claude.cmd").write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
else:
    (HOME / ".local/bin/claude").write_text(f'#!{sys.executable}\nexec(open({str(FAKE)!r}).read())\n', encoding="utf-8")
    os.chmod(HOME / ".local/bin/claude", 0o755)
RENV = dict(ENV, PATH=str(HOME / ".local/bin") + os.pathsep + ENV.get("PATH", ""))
(KIT / ".install/logs/cost.jsonl").unlink()

rc, out, err = run("run", "payments-hub", "Payments hub IA v0.2.md", env=RENV, stdin="")
ok(rc == 2 and "--yes" in err and not list(CALLS.iterdir()), "run: with no one at the keyboard and no --yes, nothing starts", err)

rc, out, err = run("run", "payments-hub", "Payments hub IA v0.2.md", "--yes", env=RENV)
calls = sorted(CALLS.iterdir())
order = [json.loads(c.read_text())["agent"] for c in calls]
ok(rc == 0, "run --yes finishes", out + err)
ok(len(order) == 4 and order[0] == "reviewer" and set(order[1:]) == {"red-team", "threat-modeler", "standards-checker"},
   "run: the reviewer first, then the three security agents", order)
first = json.loads(calls[0].read_text())
argv = first["argv"]
ok("--strict-mcp-config" in argv and "--output-format" in argv and first["token_set"],
   "run: through kit_claude (JSON output, no MCP servers, Kit's login)", argv)
ok(all(json.loads(c.read_text())["stdin"] == WIN for c in calls),
   "run: the brief goes on standard input on Windows (cmd.exe cuts an argument at a line break), "
   "on the command line elsewhere", [json.loads(c.read_text())["stdin"] for c in calls])
allowed = argv[argv.index("--allowedTools") + 1: argv.index("--disallowedTools")]
denied = argv[argv.index("--disallowedTools") + 1:]
ok("Bash" in denied and "WebFetch" in denied and "Bash" not in allowed, "run: no shell and no web", (allowed, denied))
ok(any(x.startswith("Edit(") and x.endswith("payments-hub/**)") for x in allowed)
   and all(not x.startswith(("Edit(", "Write(")) or x.endswith("payments-hub/**)") for x in allowed),
   "run: writes allowed only in the project folder", allowed)
ok(pathlib.Path(first["cwd"]).resolve() == KIT.resolve(), "run: in Kit's folder", first["cwd"])
ok("nobody can answer you" in first["brief"], "run: the brief says it's unattended")
ok((PROJ / "reviews/payments-hub-threat-model-v2.md").is_file() and "copied to" in out
   and "payments-hub-threat-model-v2.md (the agent didn't)" in out,
   "run: a note an agent didn't copy into reviews/ is copied there", out)
ok("about $2.00 in all" in out and out.count("about $0.50") == 4, "run: the cost of each run and in all", out)
ok("Next: kit-review-loop merge payments-hub" in out, "run: says what's next", out)
led = [json.loads(x) for x in (KIT / ".install/logs/cost.jsonl").read_text().splitlines()]
ok(len(led) == 4 and all(x["mode"] == "review-loop" for x in led), "run: each run is in Kit's cost ledger", led)

for c in CALLS.iterdir():
    c.unlink()
rc, out, err = run("run", "payments-hub", "Payments hub IA v0.2.md", "--yes", "--only", "reviewer", env=RENV)
ok(rc == 0 and [json.loads(c.read_text())["agent"] for c in CALLS.iterdir()] == ["reviewer"],
   "run --only reviewer: the reviewer again, alone", out + err)

for c in CALLS.iterdir():
    c.unlink()
BENV = dict(RENV, COST_BUDGET_MONTHLY="1")
rc, out, err = run("run", "payments-hub", "Payments hub IA v0.2.md", "--yes", env=BENV)
ok(rc == 75 and not list(CALLS.iterdir()) and "budget" in out, "run: over Kit's budget, nothing runs (exit 75)", out + err)

src = TOOL.read_text(encoding="utf-8")
ok("Bash(kit-review-loop run *)" in (REPO / "shared/kit_setup.py").read_text(encoding="utf-8"),
   "the installer makes Claude Code ask before kit-review-loop run (a paid run)")
for f in ("platform/mac/install.sh", "platform/windows/install.ps1"):
    ok("kit-review-loop" in (REPO / f).read_text(encoding="utf-8"), f"{f} links kit-review-loop")
ok("import kit_claude" in src, "it runs agents through kit_claude, like Kit's other unattended jobs")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-review-loop tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
