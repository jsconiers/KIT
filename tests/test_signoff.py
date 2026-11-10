#!/usr/bin/env python3
"""Tests for kit-signoff, the sign-off ledger: add (a preview first, then --write; the file's SHA-256 kept; the
document and version from the file name; no duplicates), require, status (approved, still needed, approved an older
version only, edited since approval), check (exactly an approved copy, an edited copy, an unapproved version, never
approved; exit codes), list, and a ledger edited by hand still read. Synthetic library; nothing is sent.

  python3 tests/test_signoff.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-signoff"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-signoff-"))
KIT = TMP / "kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/payments-hub"
(KIT / "memory/context").mkdir(parents=True)
(PROJ / "drafts").mkdir(parents=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LIB}`\n")
V2 = PROJ / "drafts/Payments hub IA v0.2.md"
V3 = PROJ / "drafts/Payments hub IA v0.3 2026-11-04.md"
V2.write_text("# IA v0.2\n")
V3.write_text("# IA v0.3\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-11-05", PYTHONDONTWRITEBYTECODE="1")
LEDGER = PROJ / "signoffs.md"


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


rc, out, err = run("add", "payments-hub", "Payments hub IA v0.2.md", "--by", "Domain owner", "--how", "email")
ok(rc == 0 and "Domain owner approved Payments hub IA v0.2" in out and "nothing written" in out and not LEDGER.exists(),
   "add without --write shows the row and writes nothing", out + err)
rc, out, err = run("add", "payments-hub", "Payments hub IA v0.2.md", "--by", "Domain owner", "--how", "email",
                   "--date", "2026-10-20", "--evidence", "reply to the v0.2 review mail", "--write")
ok(rc == 0 and LEDGER.is_file(), "add --write records it in PROJECT/signoffs.md", out + err)
text = LEDGER.read_text()
ok("| 20-Oct-2026 | Payments hub IA | v0.2 | Domain owner | email | reply to the v0.2 review mail |" in text
   and "drafts/Payments hub IA v0.2.md" in text, "the row: date, document, version, role, how, evidence, file", text)
ok(len([ln for ln in text.splitlines() if "Payments hub IA | v0.2" in ln]) == 1, "one row")
rc, out, _ = run("add", "payments-hub", "Payments hub IA v0.2.md", "--by", "domain owner", "--how", "email", "--write")
ok("already in the ledger" in out, "the same sign-off isn't recorded twice", out)
ok(run("add", "payments-hub", "Payments hub IA v0.2.md", "--by", "x", "--how", "carrier pigeon")[0] == 2,
   "an unknown --how is refused")
ok(run("add", "payments-hub", "nope.md", "--by", "x")[0] == 2, "a file that isn't there is refused")

rc, out, _ = run("require", "payments-hub", "Domain owner", "ARB chair", "Security architect", "--write")
ok(rc == 0 and "Required: Domain owner, ARB chair, Security architect" in LEDGER.read_text(), "require sets the Required line")
run("add", "payments-hub", V3.name, "--by", "ARB chair", "--how", "arb", "--date", "2026-11-05", "--write")
run("add", "payments-hub", V3.name, "--by", "Domain owner", "--how", "meeting", "--date", "2026-11-05", "--write")
rc, out, _ = run("status", "payments-hub", "--json")
d = json.loads(out)["documents"][0]
ok(d["document"] == "Payments hub IA" and d["latest"] == "0.3", "status: the document and its latest version (the date "
   "in the file name isn't part of the document)", d)
ok(d["approved_latest_by"] == ["ARB chair", "Domain owner"] and d["still_needed"] == ["Security architect"]
   and not d["approved"], "status: who approved the latest, and who's still needed", d)
run("add", "payments-hub", V3.name, "--by", "Security architect", "--how", "chat", "--write")
d = json.loads(run("status", "payments-hub", "--json")[1])["documents"][0]
ok(d["approved"] and not d["still_needed"], "status: approved once everyone required has signed off", d)
rc, out, _ = run("status", "payments-hub")
ok("Payments hub IA v0.3: APPROVED" in out, "status text", out)

rc, out, _ = run("check", "payments-hub", V3.name)
ok(rc == 0 and "is exactly Payments hub IA v0.3 as signed off by ARB chair, Domain owner, Security architect" in out,
   "check: an approved copy, exit 0", out)
copy = TMP / "Payments hub IA v0.3 (sent to vendor).md"
shutil.copy(V3, copy)
ok(run("check", "payments-hub", copy)[0] == 0, "check: a copy elsewhere with the same bytes is still the approved one")
V3.write_text("# IA v0.3\nA sentence added after approval.\n")
rc, out, _ = run("check", "payments-hub", V3.name)
ok(rc == 1 and "NOT the approved copy" in out, "check: an edited copy is caught, exit 1", out)
d = json.loads(run("status", "payments-hub", "--json")[1])["documents"][0]
ok(d["latest_edited_since_approval"] and not d["approved"], "status: an edit after approval undoes it", d)
V4 = PROJ / "drafts/Payments hub IA v0.4.md"
V4.write_text("# IA v0.4\n")
rc, out, _ = run("check", "payments-hub", V4.name)
ok(rc == 1 and "hasn't been signed off" in out and "v0.2, v0.3" in out, "check: a version nobody approved", out)
d = json.loads(run("status", "payments-hub", "--json")[1])["documents"][0]
ok(d["latest"] == "0.4" and not d["approved_latest_by"] and "Domain owner" in d["approved_older_only"],
   "status: a newer draft needs its own sign-offs; earlier approvers are listed", d)
other = PROJ / "drafts/Payments hub GDS v1.0.md"
other.write_text("# GDS\n")
rc, out, _ = run("check", "payments-hub", other.name)
ok(rc == 1 and "No version of Payments hub GDS has been signed off" in out, "check: a document never approved", out)

# A ledger edited by hand (a row typed in, columns as written) is still read.
LEDGER.write_text(LEDGER.read_text() + "| 01-Nov-2026 | Payments hub GDS | v1.0 | Platform lead | meeting | typed by hand |  |  |\n")
rows = json.loads(run("list", "payments-hub", "--json")[1])
ok(any(r["document"] == "Payments hub GDS" and r["role"] == "Platform lead" for r in rows) and rows[0]["date"] == "05-Nov-2026",
   "list reads hand-typed rows, newest first", rows[:2])
ok("@" not in LEDGER.read_text(), "nothing like an address in the ledger")

# A library root reached through a symbolic link (a synced cloud folder, or /var -> /private/var on macOS) still
# records the file's path inside the project, and a project whose name starts another's doesn't claim its files.
REAL = TMP / "real-library"
(REAL / "artifacts/pay/drafts").mkdir(parents=True)
(REAL / "artifacts/payments/drafts").mkdir(parents=True)
LINK = TMP / "linked-library"
LINK.symlink_to(REAL, target_is_directory=True)
(KIT / "memory/context/library.md").write_text(f"- **Library root:** `{LINK}`\n")
(REAL / "artifacts/pay/drafts/Pay IA v1.0.md").write_text("# Pay IA\n")
rc, out, err = run("add", "pay", "Pay IA v1.0.md", "--by", "Domain owner", "--how", "email", "--write")
text = (REAL / "artifacts/pay/signoffs.md").read_text() if (REAL / "artifacts/pay/signoffs.md").exists() else ""
ok(rc == 0 and "| drafts/Pay IA v1.0.md |" in text, "a library root behind a symlink: the file column keeps drafts/",
   out + err + text)
(REAL / "artifacts/payments/drafts/Payments IA v1.0.md").write_text("# Payments IA\n")
rc, out, err = run("add", "pay", str(REAL / "artifacts/payments/drafts/Payments IA v1.0.md"), "--by", "Domain owner",
                   "--how", "email", "--write")
text = (REAL / "artifacts/pay/signoffs.md").read_text()
ok(rc == 0 and "| Payments IA v1.0.md |" in text and "payments/drafts" not in text and "../" not in text,
   "a file in a project whose name starts with this one's is recorded by name only", out + err + text)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-signoff tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
