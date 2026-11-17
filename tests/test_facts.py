#!/usr/bin/env python3
"""Tests for kit-facts, the per-project fact sheet: set (a preview first, then --write; a change keeps the old value
as superseded), show, remove, a sheet edited by hand still read, and check / check-all: a money fact (a different
amount is a conflict, a rounded $348k agrees, a superseded amount is stale), a fact with a unit (30-minute and
30 minutes agree, 45 minutes conflicts), a text fact (the sponsor), aliases, facts not mentioned, a .docx draft,
exit codes, and nothing like an address recorded. Synthetic library; nothing is sent.

  python3 tests/test_facts.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-facts"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1500])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-facts-"))
KIT = TMP / "kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/auth-upgrade"
(KIT / "memory/context").mkdir(parents=True)
(PROJ / "drafts").mkdir(parents=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-17", PYTHONDONTWRITEBYTECODE="1")
SHEET = PROJ / "facts.md"


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


rc, out, err = run("set", "auth-upgrade", "Phase 1 likely cost", "345,000", "--unit", "USD",
                   "--alias", "phase 1 cost; likely cost", "--source", "cost estimate v1", "--by", "Sponsor")
ok(rc == 0 and "add Phase 1 likely cost: 345,000 USD" in out and "nothing written" in out and not SHEET.exists(),
   "set without --write shows the row and writes nothing", out + err)
run("set", "auth-upgrade", "Phase 1 likely cost", "345,000", "--unit", "USD", "--alias", "phase 1 cost; likely cost",
    "--source", "cost estimate v1", "--by", "Sponsor", "--date", "2026-11-01", "--write")
rc, out, err = run("set", "auth-upgrade", "phase 1 likely cost", "347,840", "--source", "cost estimate v2",
                   "--date", "12-Nov-2026", "--write")
text = SHEET.read_text()
ok(rc == 0 and "change Phase 1 likely cost: 347,840 USD (was 345,000)" in out, "a change says what it was", out + err)
ok("| Phase 1 likely cost | 347,840 | USD | phase 1 cost; likely cost | cost estimate v2 | 12-Nov-2026 | Sponsor | 345,000 |"
   in text and text.count("Phase 1 likely cost |") == 1, "one row: new value, old one kept as superseded", text)
run("set", "auth-upgrade", "Rollback time", "30", "--unit", "minutes", "--alias", "rollback; revert time",
    "--source", "design review", "--by", "Domain owner", "--write")
run("set", "auth-upgrade", "Sponsor", "VP Engineering", "--alias", "executive sponsor", "--source", "steering note",
    "--by", "PMO", "--write")
# A row typed by hand is read too.
SHEET.write_text(SHEET.read_text() + "| Pilot domains | 12 |  | pilot; production domains | wave plan |  |  |  |\n")
rows = json.loads(run("show", "auth-upgrade", "--json")[1])
ok([r["key"] for r in rows] == ["Phase 1 likely cost", "Rollback time", "Sponsor", "Pilot domains"],
   "show lists every fact, hand-typed rows included", rows)
rc, out, _ = run("show", "auth-upgrade")
ok("Rollback time" in out and "30 minutes" in out and "[was 345,000]" in out, "show text", out)

BAD = PROJ / "drafts/Auth upgrade DOC-210 v0.5.md"
BAD.write_text("# 1 Summary\n\nThe phase 1 likely cost is $350,000 including support. The executive sponsor is "
               "the CIO office.\n\n# 4 Rollback\n\nEach wave keeps a 45 minutes rollback, so the revert time is "
               "short.\n\n# 6 Costs\n\n| Item | Amount |\n|---|---|\n| Phase 1 cost | $345,000 |\n")
rc, out, err = run("check", "auth-upgrade", BAD.name, "--json")
ok(rc == 1, "conflicts: exit 1", out + err)
res = {r["key"]: r for r in json.loads(out)[0]["facts"]}
c = res["Phase 1 likely cost"]
ok(c["status"] == "conflict" and c["conflicts"][0]["found"] == "$350,000" and c["conflicts"][0]["where"].startswith("1 Summary"),
   "a different amount is a conflict, with where it is", c)
ok(c["stale"] and c["stale"][0]["found"] == "$345,000" and "table row" in c["stale"][0]["where"],
   "the superseded amount in a table row is stale", c)
r = res["Rollback time"]
ok(r["status"] == "conflict" and r["conflicts"][0]["found"].startswith("45 minutes"), "45 minutes vs 30: conflict", r)
s = res["Sponsor"]
ok(s["status"] == "conflict" and "CIO office" in s["conflicts"][0]["found"], "a text fact: a different sponsor", s)
ok(res["Pilot domains"]["status"] == "not mentioned", "a fact the draft never names is 'not mentioned'", res)
rc, out, _ = run("check", "auth-upgrade", BAD.name)
ok("CONFLICT Phase 1 likely cost" in out and "says $350,000; the fact sheet says 347,840 USD" in out
   and "STALE    Phase 1 likely cost" in out and "not mentioned: Pilot domains" in out, "check text", out)

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
GOOD = PROJ / "drafts/Auth upgrade DOC-211 v1.0.docx"
paras = ["The phase 1 likely cost is $348k, within the approved range.",
         "Each wave can be rolled back within a 30-minute window; the revert time is measured per wave.",
         "The executive sponsor is VP Engineering, with a decision due in the first quarter.",
         "The pilot covers 12 production domains."]
with zipfile.ZipFile(GOOD, "w") as z:
    z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>' + "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras) + "</w:body></w:document>")
rc, out, err = run("check", "auth-upgrade", GOOD.name, "--json")
res = {r["key"]: r for r in json.loads(out)[0]["facts"]}
ok(rc == 0 and all(r["status"] == "agrees" for r in res.values()),
   "a .docx that agrees (a rounded $348k, 30-minute, the sponsor, the hand-typed fact via its alias): exit 0", out + err)

rc, out, err = run("check-all", "auth-upgrade", "--json")
d = json.loads(out)
ok(rc == 1 and len(d) == 2, "check-all checks every draft, exit 1 when one conflicts", out + err)
ok(run("check", "auth-upgrade", "nope.md")[0] == 2, "a draft that isn't there: exit 2")
ok(run("check", "no-such-project", BAD.name)[0] == 2, "a project that isn't there: exit 2")
(LIB / "artifacts/empty/drafts").mkdir(parents=True)
(LIB / "artifacts/empty/drafts/x.md").write_text("# x\n")
ok(run("check-all", "empty")[0] == 2, "no fact sheet yet: exit 2 with how to start one")
ok(run("set", "auth-upgrade", "Owner", "x", "--by", "someone@example.com", "--write")[0] == 2,
   "an address as the approver is refused")
rc, out, _ = run("remove", "auth-upgrade", "Pilot domains")
ok("Pilot domains" in SHEET.read_text() and "nothing written" in out, "remove without --write changes nothing")
run("remove", "auth-upgrade", "Pilot domains", "--write")
ok("Pilot domains" not in SHEET.read_text() and SHEET.read_text().startswith("# Fact sheet: auth-upgrade"),
   "remove --write takes the row off and keeps the sheet's heading")
ok("@" not in SHEET.read_text(), "nothing like an address on the sheet")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-facts tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
