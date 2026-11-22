#!/usr/bin/env python3
"""kit-techdebt: the technical debt register: add, set, accept, close (read-only until --write), the ranking
(risk, end of support, lifecycle verdict, waivers, target date, cost), due, the month, the brief, and the
Technical debt section in kit-digest. Synthetic library only.

Run: python3 tests/test_techdebt.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TOOL = HERE.parent / "shared" / "bin" / "kit-techdebt"
DIGEST = HERE.parent / "shared" / "bin" / "kit-digest"
tmp = pathlib.Path(tempfile.mkdtemp())
kit, lib = tmp / "kit", tmp / "lib"
(kit / "memory/context").mkdir(parents=True)
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
radar = lib / "radar"
(radar / "lifecycle").mkdir(parents=True)
REG = radar / "tech-debt.md"
LOG = radar / "tech-debt-log.jsonl"
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-11-20", PYTHONUTF8="1")
fails = []


def check(cond, what, extra=""):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)
        if extra:
            print("     " + str(extra)[:1500].replace("\n", "\n     "))


def run(*args, tool=TOOL, **kw):
    e = dict(env, **kw)
    r = subprocess.run([sys.executable, str(tool), *args], capture_output=True, text=True, env=e, timeout=120,
                       stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------- no register yet
rc, o, e = run()
check(rc == 0 and "no register yet" in o, "no register: says so", o + e)
rc, o, e = run("brief")
check(rc == 0 and o == "", "no register: the brief says nothing", o + e)
rc, o, e = run("month", "--json")
check(rc == 0 and json.loads(o)["exists"] is False, "no register: the month says it doesn't exist")

# ---------------------------------------------------------------- add (preview, then write)
rc, o, e = run("add", "Hand-built", "load", "balancer", "config", "--system", "Payments gateway", "--risk", "medium")
check(rc == 0 and "read-only" in o and "| TD-001 |" in o and not REG.exists(), "add without --write: a preview only", o + e)
rc, o, e = run("add", "Hand-built load balancer config", "--system", "Payments gateway", "--risk", "medium",
               "--type", "infrastructure", "--cost", "likely", "--owner", "Platform engineering lead", "--write")
reg = REG.read_text() if REG.exists() else ""
check(rc == 0 and "Added TD-001" in o and "| TD-001 | Hand-built load balancer config | Payments gateway |" in reg,
      "add --write starts the register from the template", o + e + reg)
check("<one line>" not in reg and "| Updated | 20-Nov-2026 |" in reg, "the template's example row is gone; Updated set", reg)
check(REG.stat().st_mode & 0o077 == 0 if os.name == "posix" else True, "the register is owner-only")
rc, o, e = run("add", "Hand-built load balancer config", "--system", "payments gateway", "--write")
check(rc == 1 and "already open" in e, "the same open item twice is refused", e)
rc, o, e = run("add", "Rotate the service key", "--system", "Batch", "--impact", "password=hunter2xyz", "--write")
check(rc == 1 and "credential" in e and "hunter2" not in REG.read_text(), "credential-looking text is refused", e)
rc, o, e = run("add", "Something", "--write")
check(rc == 1 and "--system" in e, "add needs --system", e)
rc, o, e = run("add", "Something", "--system", "X", "--risk", "huge")
check(rc == 1 and "--risk is one of" in e, "risk is high, medium, or low", e)

# The RHEL 7 hosts: past end of support (lifecycle summary), a retire verdict, past target, high risk.
(radar / "lifecycle/summary.json").write_text(json.dumps({"items": [
    {"product": "RHEL", "version": "7", "flag": "past", "eol": "30-Jun-2024", "systems": ["Settlement batch"]},
    {"product": "PostgreSQL", "version": "12", "flag": "urgent", "eol": "14-Nov-2026", "systems": ["Ledger"]},
    {"product": "Java", "version": "17", "flag": "ok", "systems": ["Payments gateway"]}]}))
rc, o, e = run("add", "Upgrade the RHEL 7 hosts", "--system", "Settlement batch", "--risk", "high",
               "--lifecycle", "lifecycle/rhel.md: retire", "--target", "01-Oct-2026", "--owner", "Platform team", "--write")
check(rc == 0 and "Added TD-002" in o, "a second item takes TD-002", o + e)
rc, o, e = run("add", "Ledger still on PostgreSQL 12", "--system", "Ledger", "--risk", "low", "--cost", "low",
               "--target", "2026-12-05", "--write")
rc, o, e = run("add", "Undocumented runbook for failover", "--system", "Core banking", "--type", "documentation",
               "--cost", "high", "--write")

# A waiver on the payments gateway, expiring in 20 days.
(kit / "memory/context/compliance.md").write_text("- **Exception register:** `compliance/exceptions.md`\n")
(lib / "compliance").mkdir()
(lib / "compliance/exceptions.md").write_text("""# Exceptions

| ID | Policy | System | Reason | Owner | Approver | Granted | Expiry | Review frequency | Status |
|---|---|---|---|---|---|---|---|---|---|
| EXC-0001 | TLS standard | Payments gateway | Legacy balancer | Platform lead | CISO | 01-Jan-2026 | 10-Dec-2026 | quarterly | granted |
""")

# ---------------------------------------------------------------- the ranking
rc, o, e = run()
lines = [ln for ln in o.splitlines() if ln.strip()[:1].isdigit()]
check(rc == 0 and "4 open item(s)" in o and lines and "TD-002" in lines[0], "most pressing first: the RHEL hosts", o + e)
check("risk high +3" in o and "end of support past +3 (RHEL 7)" in o and "lifecycle verdict retire +1" in o
      and "past its target date (01-Oct-2026) +2" in o, "every point has its reason", o)
check("waiver EXC-0001 expires in 20 days +2" in o, "a waiver on the same system expiring soon counts", o)
check("end of support urgent +2 (PostgreSQL 12)" in o and "target date in 15 days +1" in o and "cost to fix low +1" in o,
      "end of support by system; a target coming up; a quick win", o)
check("risk not set +1" in o and "cost to fix high -1" in o, "an unrated item still ranks; an expensive fix sinks", o)
j = json.loads(run("--json")[1])
check([i["id"] for i in j["items"]][0] == "TD-002" and j["items"][0]["score"] == 9, "--json: ranked with scores",
      json.dumps(j["items"][:1]))

# ---------------------------------------------------------------- set, accept, close
rc, o, e = run("set", "TD-004", "--risk", "medium")
check(rc == 0 and "read-only" in o and "| medium |" in o and "| medium |" not in
      [ln for ln in REG.read_text().splitlines() if ln.startswith("| TD-004")][0], "set without --write changes nothing", o)
rc, o, e = run("set", "TD-004", "--risk", "medium", "--owner", "Operations lead", "--write")
row4 = [ln for ln in REG.read_text().splitlines() if ln.startswith("| TD-004")][0]
check(rc == 0 and "risk - -> medium" in o and "| medium |" in row4 and "Operations lead" in row4, "set --write", o + row4)
rc, o, e = run("set", "4", "--status", "closed")
check(rc == 1 and "close ID" in e, "closing goes through close", e)
rc, o, e = run("set", "TD-099", "--risk", "low")
check(rc == 1 and "no item TD-099" in e, "an unknown id is refused", e)
rc, o, e = run("accept", "TD-001", "--reason", "Replaced next year with the platform", "--by", "Head of architecture")
check(rc == 1 and "--review" in e, "accept needs a review date", e)
rc, o, e = run("accept", "TD-001", "--reason", "Replaced next year", "--by", "Head of architecture",
               "--review", "01-Nov-2026", "--write")
check(rc == 1 and "still to come" in e, "the review date is in the future", e)
rc, o, e = run("accept", "TD-001", "--reason", "Replaced next year with the platform", "--by", "Head of architecture",
               "--review", "01-Dec-2026", "--write")
reg = REG.read_text()
check(rc == 0 and "| TD-001 | Replaced next year with the platform | Head of architecture | 01-Dec-2026 |" in reg
      and [ln for ln in reg.splitlines() if ln.startswith("| TD-001 | Hand")][0].rstrip().endswith("| accepted |"),
      "accept: an Accepted debt row, and the status", reg)
rc, o, e = run()
check("TD-001" not in o and "3 open item(s)" in o, "accepted debt leaves the open list", o)
rc, o, e = run("--all")
check("TD-001" in o and "accepted" in o, "--all lists it", o)
rc, o, e = run("close", "TD-003", "--how", "Upgraded to PostgreSQL 16 (CHG-2201)", "--write")
reg = REG.read_text()
check(rc == 0 and "| TD-003 | 20-Nov-2026 | Upgraded to PostgreSQL 16 (CHG-2201) |" in reg
      and "| TD-003 | Ledger still on PostgreSQL 12 |" in reg, "close: a Closed row; the register row stays", reg)
rc, o, e = run("close", "TD-003", "--how", "again", "--write")
check(rc == 1 and "already closed" in e, "closing twice is refused", e)
rc, o, e = run("show", "TD-003")
check(rc == 0 and "Closed 20-Nov-2026: Upgraded" in o and "20-Nov-2026 add" in o and "20-Nov-2026 close" in o,
      "show: fields, closure, and history", o)
log = [json.loads(ln) for ln in LOG.read_text().splitlines()]
check([x["action"] for x in log] == ["add", "add", "add", "add", "set", "accept", "close"], "every write is logged",
      [x["action"] for x in log])

# ---------------------------------------------------------------- due, the month, the brief
rc, o, e = run("due")
check("Past target by 50 day(s): TD-002" in o and "Accepted, review due 01-Dec-2026: TD-001" in o, "due", o)
# A row closed by hand, in the Closed table only.
reg = REG.read_text().splitlines()
reg = [ln.replace("| open |", "| closed |") if ln.startswith("| TD-004 |") else ln for ln in reg]
reg = "\n".join(reg).replace("| TD-003 | 20-Nov-2026 | Upgraded", "| TD-004 | 18-Nov-2026 | Written and tested by ops |\n| TD-003 | 20-Nov-2026 | Upgraded")
REG.write_text(reg)
m = json.loads(run("month", "--month", "this", "--json")[1])
check([x["id"] for x in m["added"]] == ["TD-001", "TD-002", "TD-003", "TD-004"] and
      sorted(x["id"] for x in m["closed"]) == ["TD-003", "TD-004"] and [x["id"] for x in m["accepted"]] == ["TD-001"],
      "the month: added, closed (by hand too), accepted", json.dumps(m)[:800])
check(m["open"]["total"] == 1 and m["open"]["high"] == 1 and m["open"]["past_target"] == 1 and m["top"][0]["id"] == "TD-002",
      "the month: where the register stands", m["open"])
m2 = json.loads(run("month", "--month", "2026-10", "--json")[1])
check(not m2["added"] and not m2["closed"], "another month: nothing moved")
rc, o, e = run("brief", "weekly")
check(rc == 0 and o.startswith("Technical debt\n[work] ") and "past target: TD-002" in o and "accepted, due a review: TD-001"
      in o and "Most pressing: TD-002" in o, "the brief: [work] lines", o + e)
check(all(ln.startswith("[work]") for ln in o.splitlines()[1:]), "every brief line is [work]")

# ---------------------------------------------------------------- kit-digest's Technical debt section
rc, o, e = run("--month", "this", tool=DIGEST)
sec = o.split("## Technical debt", 1)[1].split("\n## ", 1)[0] if "## Technical debt" in o else ""
check(rc == 0 and "- Added TD-002: Upgrade the RHEL 7 hosts (Settlement batch; risk high)" in sec
      and "- Closed TD-003: Ledger still on PostgreSQL 12 (Ledger): Upgraded to PostgreSQL 16 (CHG-2201)" in sec
      and "- Accepted TD-001:" in sec, "the digest's Technical debt section", sec or o[-1500:] + e)
check("- Open now: 1 (1 high risk); 1 past its target date. Most pressing: TD-002" in sec, "with where it stands", sec)
rc, o, e = run("--month", "this", "--json", tool=DIGEST)
d = json.loads(o)
check(d["tech_debt"]["added"] and d["tech_debt"]["note"] is None, "--json carries it", json.dumps(d.get("tech_debt"))[:400])
rc, o, e = run("--month", "this", "--brief", tool=DIGEST)
check("4 technical debt changes" not in o and "technical debt" in o, "the brief line counts debt that moved", o)
# Accepted again: the latest Accepted row is the one in force.
rc, o, e = run("accept", "TD-001", "--reason", "Still waiting on the platform", "--by", "Head of architecture",
               "--review", "01-Mar-2027", "--write")
rc, o, e = run("due")
check(rc == 0 and "TD-001" not in o, "accepted again: the old review date no longer counts", o + e)
check(run("show", "TD-001")[1].count("Accepted:") == 2, "show keeps both acceptances")
# A backdated close counts in the month it closed, once.
rc, o, e = run("close", "TD-002", "--how", "Rebuilt on RHEL 9", "--date", "28-Oct-2026", "--write")
oct_ = json.loads(run("month", "--month", "2026-10", "--json")[1])
nov = json.loads(run("month", "--month", "this", "--json")[1])
check(rc == 0 and [x["id"] for x in oct_["closed"]] == ["TD-002"] and "TD-002" not in [x["id"] for x in nov["closed"]],
      "a backdated close counts in the month it closed, once", json.dumps([oct_["closed"], nov["closed"]])[:600])
# A team that reordered the columns.
REG.write_text("""# Tech debt register

| Field | Value |
|---|---|
| Updated | 01-Nov-2026 |

## Register

| Status | Id | Owner | Item | Risk | System | Target date |
|---|---|---|---|---|---|---|
| open | TD-007 | SRE lead | Manual certificate renewals | high | Edge | 01-Nov-2026 |
| in progress | TD-009 | DBA lead | No point-in-time restore | medium | Ledger | |
""")
rc, o, e = run()
check(rc == 0 and "TD-007" in o.splitlines()[1] and "TD-009" in o, "columns found by name, in any order", o + e)
rc, o, e = run("add", "Retire the FTP drop", "--system", "Partners", "--write")
check("Added TD-010" in o and "| open | TD-010 |" in REG.read_text(), "ids continue after the highest; the team's order kept",
      REG.read_text())
rc, o, e = run("set", "TD-009", "--target", "2026-12-31", "--write")
check("| in progress | TD-009 | DBA lead | No point-in-time restore | medium | Ledger | 31-Dec-2026 |" in REG.read_text(),
      "set keeps the team's column order", REG.read_text())
# A "Risk owner" column before Risk and Owner: the team's own column, left alone.
REG.write_text("""# Tech debt register

| Id | Item | System | Risk owner | Risk | Owner | Status |
|---|---|---|---|---|---|---|
| TD-020 | Single NAT gateway | Network | Head of infrastructure | high | Network lead | open |
""")
rc, o, e = run()
check(rc == 0 and "risk high +3" in o and "owner Network lead" in o, "Risk owner doesn't take Risk or Owner", o + e)
rc, o, e = run("add", "No WAF on the portal", "--system", "Portal", "--risk", "medium", "--owner", "Security lead", "--write")
check("| TD-021 | No WAF on the portal | Portal |  | medium | Security lead | open |" in REG.read_text(),
      "add writes Risk and Owner under their own headers", REG.read_text())
# Statuses the team typed keep their items; an Accepted table with Review by before Accepted by.
REG.write_text("""# Tech debt register

## Register

| Id | Item | System | Risk | Target date | Status |
|---|---|---|---|---|---|
| TD-011 | Shared admin account on the SAN | Storage | high | | Open - blocked on vendor |
| TD-012 | No load test for the gateway | Gateway | medium | | In progress (Q1) |
| TD-013 | Hard-coded endpoint list | Partners | low | | Blocked |
| TD-014 | Old TLS ciphers | Edge | medium | | Done |
| TD-015 | Batch on a pet server | Settlement batch | medium | | accepted |

## Accepted debt

| Id | Reason accepted | Review by | Accepted by |
|---|---|---|---|
| TD-015 | Retired with the platform next year | 01-Dec-2026 | Head of architecture |
""")
rc, o, e = run()
check(rc == 0 and "3 open item(s)" in o and all(x in o for x in ("TD-011", "TD-012", "TD-013")) and "TD-014" not in o
      and "Open - blocked on vendor" in o, "typed statuses keep their items; Done is closed", o + e)
rc, o, e = run("due")
check("Accepted, review due 01-Dec-2026: TD-015" in o, "Review by before Accepted by: the review date is read", o + e)
rc, o, e = run("accept", "TD-013", "--reason", "Partners move to the API in Q3", "--by", "Head of integration",
               "--review", "01-Jun-2027", "--write")
check(rc == 0 and "| TD-013 | Partners move to the API in Q3 | 01-Jun-2027 | Head of integration |" in REG.read_text(),
      "accept writes under the team's own headers", REG.read_text()[-500:])
rc, o, e = run("brief", "weekly")
check(rc == 0 and o.startswith("Technical debt\n") and "accepted, due a review: TD-015" in o, "the brief: a review due", o + e)
rc, o, e = run("add", "Old firmware on the turnstiles", "--system", "Gate", "--write")
j = json.loads(run("--json")[1])
gate = next((i for i in j["items"] if i["system"] == "Gate"), {})
check(gate and not any("waiver" in r for r in gate["reasons"]), "a waiver matches whole words: Gate isn't Payments gateway",
      json.dumps(gate))
REG.write_text(REG.read_text().replace("| 01-Dec-2026 | Head of architecture |", "| 01-Apr-2027 | Head of architecture |"))
rc, o, e = run("brief", "weekly")
check(rc == 0 and o == "", "the brief: nothing due, nothing said, a high-risk item or not", o + e)
# A register copied from the template by hand: the example row goes, and the first item is TD-001.
REG.write_text((HERE.parent / "kit/templates/tech-debt-register-template.md").read_text())
rc, o, e = run("add", "No DR test for the vault", "--system", "Vault", "--risk", "high", "--write")
reg = REG.read_text()
check(rc == 0 and "Added TD-001" in o and "<one line>" not in reg and "| TD-001 | No DR test for the vault | Vault |" in reg,
      "a hand-copied template: the example row goes, ids start at TD-001", o + e + reg[-800:])
REG.write_text("# Tech debt register\n\nThe table went missing in an edit.\n")
rc, o, e = run("--month", "this", tool=DIGEST)
sec = o.split("## Technical debt", 1)[1].split("\n## ", 1)[0] if "## Technical debt" in o else ""
check(rc == 0 and "Open now" not in sec and "tech-debt.md has no table" in o.split("## Not read", 1)[-1],
      "a register the digest can't read: said under Not read, not counted as nothing open", o[-900:])
shutil.rmtree(lib / "radar")
rc, o, e = run("--month", "this", tool=DIGEST)
check(rc == 0 and "## Technical debt" not in o, "no register: the digest leaves the section out quietly", o[-600:])

shutil.rmtree(tmp)
print(f"\n{'FAILED' if fails else 'passed'}: kit-techdebt, {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
