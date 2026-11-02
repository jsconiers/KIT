#!/usr/bin/env python3
"""Tests for kit-digest (the monthly architecture digest, no model call): decisions from the ADR folder, reference
architectures from kit-refarch's index, end of support from kit-lifecycle, expiring exceptions from kit-exceptions,
next month's review board from pre-reads, rehearsals, and a calendar file, and the PPM Express pulse snapshot.
Everything happens in a temp folder with a fake Kit and library; nothing is sent.

Run: python3 tests/test_digest.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
PASS = FAIL = 0
SECRET = "sk-" + "Z" * 30


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


tmp = pathlib.Path(tempfile.mkdtemp())
kit, lib = tmp / "kit", tmp / "library"
for p in ("memory/context", "briefs/preread", "briefs/rehearse", "briefs/ppmx"):
    (kit / p).mkdir(parents=True)
for p in ("decisions", "published", "radar", "compliance"):
    (lib / p).mkdir(parents=True)
LIBMD = kit / "memory/context/library.md"
LIBMD.write_text(f"- **Library root:** `{lib}`.\n")
env = {k: v for k, v in os.environ.items() if k not in ("KIT_TODAY",)}
env.update(KIT_DIR=str(kit), KIT_TODAY="2026-11-02", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

(lib / "decisions/INDEX.md").write_text(
    "# Architecture decision records\n\n- **Next number:** ADR-0007\n\n"
    "| ADR | Title | Status | Date | Project | File |\n|---|---|---|---|---|---|\n"
    "| ADR-0001 | Use Kafka for events | accepted | 14-Oct-2026 | payments | ADR-0001-kafka.md |\n"
    "| ADR-0002 | Retire the FTP gateway | proposed | 20-Oct-2026 | integration | ADR-0002-ftp.md |\n"
    "| ADR-0003 | An older choice | accepted | 02-Sep-2026 | core | |\n"
    "| ADR-0004 | A withdrawn idea | withdrawn | 10-Oct-2026 | core | |\n"
    "| ADR-0005 | Queue choice | superseded by ADR-0006 | 30-Oct-2026 | core | |\n"
    f"| ADR-0006 | Year-end choice {SECRET} | accepted | 31-Dec-2026 | core | |\n", encoding="utf-8")
(lib / "decisions/ADR-0001-kafka.md").write_text(
    "# ADR-0001: Use Kafka for event streaming\n\n| Field | Value |\n|---|---|\n| Status | accepted |\n"
    "| Date decided | 15-Oct-2026 |\n| Decided by | architecture review board |\n| Project | payments |\n",
    encoding="utf-8")
(lib / "decisions/ADR-0002-ftp.md").write_text(
    "# ADR-0002: Retire the FTP gateway\n\n| Field | Value |\n|---|---|\n| Status | proposed |\n"
    "| Date decided | not decided (proposed; recorded in the minutes of 20-Oct-2026) |\n", encoding="utf-8")
(lib / "published/gds-index.md").write_text(
    "| Accession | Number | Title | Version | Modified | Status | File | Notes |\n|---|---|---|---|---|---|---|---|\n"
    "| LIB-1 | DS-101 | Kafka Event Streaming Platform | 2.0 | 08-Oct-2026 | approved | `a.pdf` | |\n"
    "| LIB-2 | DS-102 | RabbitMQ Messaging | 1.1 | 2026-10-21 | | `b.pdf` | superseded by DS-101 |\n"
    "| LIB-3 | DS-103 | Payroll Reporting | 1.1 | 02-Feb-2026 | approved | `c.pdf` | |\n", encoding="utf-8")
(lib / "radar/inventory.csv").write_text(
    "Product,Version,System,Owner,Environment\nJava,8u391,batch-01,Platform team,prod\nJava,8u402,batch-02,Platform "
    "team,prod\nPostgres,12.4,db-01,Database engineering,prod\nWindows Server,2016,app-01,Platform team,prod\n"
    "Kafka,3.6.1,events-01,Messaging team,prod\n")
(lib / "radar/eol.json").write_text(json.dumps([
    {"product": "Java", "cycle": "8", "eol": "2027-03-31", "source": "https://example.org/j", "checked": "2026-10-01"},
    {"product": "Postgres", "cycle": "12", "eol": "2026-10-20", "source": "https://example.org/p", "checked": "2026-10-01"},
    {"product": "Windows Server", "cycle": "2016", "eol": "2022-01-11", "extended": "2027-01-12",
     "source": "https://example.org/w", "checked": "2026-10-01"},
    {"product": "Kafka", "cycle": "3.6", "eol": "2027-09-01", "source": "https://example.org/k", "checked": "2026-10-01"}]))
(lib / "compliance/exception-register.md").write_text(
    "| ID | Policy | System | Reason | Compensating controls | Owner | Approver | Granted | Expiry | Review frequency | "
    "Last reviewed | Status |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| EXC-0001 | Encryption at rest | Legacy CRM | vendor limit | isolation | platform lead | CISO | 01-Jan-2026 | "
    "15-Dec-2026 | quarterly | 01-Oct-2026 | granted |\n"
    "| EXC-0002 | MFA | Old portal | migration | VPN | app lead | CISO | 01-Jan-2026 | 20-Oct-2026 | annual | "
    "01-Jan-2026 | granted |\n"
    "| EXC-0003 | Logging | Batch | x | y | ops | CISO | 01-Jan-2026 | 01-Jun-2027 | annual | 01-Jan-2026 | granted |\n"
    "| EXC-0004 | Patching | Kiosk | x | y | ops | CISO | 01-Jan-2026 | 20-Feb-2027 | annual | 01-Jan-2026 | granted |\n")
pre = kit / "briefs/preread"
(pre / "2026-10-30-payments-gds.md").write_text("# Pre-read: Payments GDS.docx\n\n- **For:** Architecture review: "
                                                "Payments, 06-Nov-2026\n")
(pre / "2026-10-05-old.md").write_text("# Pre-read: Old.docx\n\n- **For:** Design review, 10-Oct-2026\n")
reh = kit / "briefs/rehearse"
(reh / "2026-10-25-network.md").write_text("# Rehearsal: Network GDS.docx\n\n- **Document:** Network GDS.docx\n")
(reh / "2026-09-01-ancient.md").write_text("# Rehearsal: Ancient.docx\n\n- **Document:** x\n")
snap = {"taken": "2026-10-26T07:00", "projects": {
    "a": {"name": "Data center exit", "status": "Critical", "status_code": 2, "done": False},
    "b": {"name": "Mobile app", "status": "On Track", "status_code": 0, "done": False},
    "c": {"name": "Closed one", "status": "At Risk", "status_code": 1, "done": True}}, "key_dates": {}}
(kit / "briefs/ppmx/pulse-2026-10-26.json").write_text(json.dumps(snap))
snap2 = dict(snap, projects=dict(snap["projects"], b={"name": "Mobile app", "status": "At Risk", "status_code": 1,
                                                      "done": False}))
(kit / "briefs/ppmx/pulse-2026-11-02.json").write_text(json.dumps(snap2))
cal = tmp / "cal.json"
cal.write_text(json.dumps([
    {"subject": "Architecture Review Board", "start": "2026-11-05T14:00:00", "end": "2026-11-05T15:00:00"},
    {"subject": "Lunch with Sam", "start": "2026-11-05T12:00:00"},
    {"subject": "Design review: Mobile (ana@example.com)", "start": "2026-11-12T10:00:00"},
    {"subject": "ARB", "start": "2026-11-19T10:00:00", "my_response": "declined"},
    {"subject": "Architecture review board", "start": "2026-12-03T10:00:00"}]))


def dg(*args, **extra):
    r = subprocess.run([sys.executable, str(SHARED / "bin/kit-digest"), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", timeout=300, env=dict(env, **extra))
    return r.returncode, r.stdout, r.stderr


def text_of(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def section(text, title):
    part = text.split(f"## {title}", 1)
    return part[1].split("\n## ", 1)[0] if len(part) == 2 else ""


# ---- last month, every source there -----------------------------------------------------------------------------
rc, o, e = dg("--calendar-json", cal)
ok(rc == 0 and o.startswith("# Architecture digest: October 2026"), "by default, last month's digest", o[:200] + e)
ok("Covers:** 01-Oct-2026 to 31-Oct-2026; looking ahead from 01-Nov-2026" in o, "it covers the month and looks ahead "
   "from its end")
ok("[work]" in o and "Drafted by Kit for your edit" in o and "nothing was sent" in o, "drafted for your edit, [work]")
dec = section(o, "Decisions made in October")
ok("- ADR-0001 Use Kafka for event streaming: accepted 15-Oct-2026 (payments; decided by architecture review board)"
   in dec, "an accepted ADR: the file's date decided and title win over the index", dec)
ok("ADR-0005 Queue choice: superseded by ADR-0006 30-Oct-2026" in dec, "one decided and later superseded still counts")
ok("ADR-0003" not in dec and "ADR-0004" not in dec and "ADR-0006 Year-end" not in dec,
   "another month's and a withdrawn ADR are left out")
ok("Proposed, waiting for a decision: ADR-0002 Retire the FTP gateway (20-Oct-2026)" in dec, "proposed ones wait")
pat = section(o, "Reference architectures and patterns approved or changed")
ok("- DS-101 Kafka Event Streaming Platform, version 2.0, 08-Oct-2026: approved" in pat, "a catalog row dated in the "
   "month, with its status", pat)
ok("DS-102 RabbitMQ Messaging, version 1.1, 21-Oct-2026: superseded or withdrawn (see notes)" in pat,
   "an ISO date, and kit-refarch's superseded rule when there's no status")
ok("DS-103" not in pat, "a row from another month is left out")
eos = section(o, "End of support")
ok("Reached end of support in October: Postgres 12.4 (1 instance), 20-Oct-2026" in eos, "reached in the month", eos)
ok("By 01-May-2027: Java 8u391 (1 instance), end of support 31-Mar-2027" in eos and "Java 8u402" in eos,
   "reaching end of support in the next six months")
ok("Kafka" not in eos, "more than six months out is left out")
ok("Still running: 1 inside paid extended support only" in eos, "what's still running past it, counted")
exc = section(o, "Exceptions expiring in the next 60 days")
ok("- EXC-0001 Encryption at rest / Legacy CRM: expires 15-Dec-2026 (in 44 days; owner platform lead)" in exc,
   "an exception expiring within 60 days of the month's end", exc)
ok("EXC-0003" not in exc and "EXC-0004" not in exc, "later ones are left out")
ok("Past expiry and still open: EXC-0002 MFA / Old portal (20-Oct-2026)" in exc, "an expired one still granted")
rb = section(o, "Coming to the review board in November")
ok("- 05-Nov-2026 14:00: Architecture Review Board" in rb, "a review board meeting from the calendar", rb)
ok("12-Nov-2026 10:00: Design review: Mobile ([address])" in rb and "ana@example.com" not in o,
   "a design review, with the address masked")
ok("Lunch" not in rb and "19-Nov" not in rb and "03-Dec" not in rb, "not other meetings, declined ones, or next month's")
ok("Pre-read ready: Payments GDS.docx, for Architecture review: Payments, 06-Nov-2026" in rb, "a pre-read for next month")
ok("Rehearsal ready: Network GDS.docx (no date given)" in rb, "an undated rehearsal written in the last two weeks")
ok("Old.docx" not in rb and "Ancient" not in rb, "old pre-reads and rehearsals are left out")
pf = section(o, "Portfolio (PPM Express)")
ok("At Risk or Critical: 1 of 2 open projects (pulse snapshot of 26-Oct-2026): Data center exit" in pf,
   "the latest pulse snapshot up to the month's end; a closed project isn't counted", pf)
ok("Not read" not in o, "every source was read")
ok(SECRET not in o, "nothing that looks like a credential")

# ---- this month, the brief lines, and writing it ----------------------------------------------------------------------
rc, o, e = dg("--month", "this")
ok("# Architecture digest: November 2026" in o and "looking ahead from 02-Nov-2026" in o, "--month this: the month so "
   "far, looking ahead from today", o[:300])
ok("2 of 2 open projects (pulse snapshot of 02-Nov-2026)" in o, "this month uses today's snapshot")
ok(section(o, "Decisions made in November").strip() == "- Nothing this month." and o.count("Nothing this month.") == 2,
   "empty sections say nothing this month", o)
rc, o, e = dg("--write", "--month", "last", "--brief")
lines = o.splitlines()
out = kit / "briefs/digest-2026-10.md"
ok(rc == 0 and out.exists() and len(lines) == 2 and lines[0] == "Architecture digest, October 2026", "--write --brief: "
   "a title and one line", o + e)
ok(lines[1].startswith("[work] Drafted for your edit: briefs/digest-2026-10.md (") and "Text:" not in o,
   "the line points at the file, tagged [work], never a text line", lines[1:])
ok("3 decisions" not in lines[1] and "2 decisions" in lines[1], "the counts in the brief line", lines[1])
if os.name != "nt":
    ok(oct(out.stat().st_mode)[-3:] == "600", "the digest file is readable only by you")
out.write_text(out.read_text(encoding="utf-8") + "\nMy own edits.\n", encoding="utf-8")
rc, o, e = dg("--write", "--month", "last", "--brief")
ok(rc == 0 and "Already drafted, kept as it is: briefs/digest-2026-10.md" in o and "My own edits." in
   out.read_text(encoding="utf-8"), "a digest that's there is kept, with your edits", o)
rc, o, e = dg("--write", "--month", "last", "--force")
ok(rc == 0 and "wrote briefs/digest-2026-10.md" in o and "My own edits." not in out.read_text(encoding="utf-8"),
   "--force replaces it")
rc, o, e = dg("--brief", "--month", "2026-09")
ok("Not written yet: kit-digest --write --month 2026-09" in o, "--brief without a file says how to write it", o)
rc, o, e = dg("--json", "--calendar-json", cal)
d = json.loads(o)
ok(d["month"] == "2026-10" and d["as_of"] == "2026-11-01" and d["next_month"] == "November 2026"
   and len(d["decisions"]["made"]) == 2 and d["portfolio"]["at_risk"] == 1 and not d["written"], "--json", o[:300])

# ---- month and year ends -----------------------------------------------------------------------------------------------
rc, o, e = dg("--month", "last", KIT_TODAY="2027-01-05")
ok("# Architecture digest: December 2026" in o and "01-Dec-2026 to 31-Dec-2026; looking ahead from 01-Jan-2027" in o,
   "last month across the year end", o[:300])
ok("ADR-0006 Year-end choice [removed]: accepted 31-Dec-2026" in o and SECRET not in o,
   "a decision on the month's last day counts; a credential in a title is removed", section(o, "Decisions made in December"))
ok("## Coming to the review board in January" in o, "next month is January")
ok("EXC-0004 Patching / Kiosk: expires 20-Feb-2027 (in 50 days" in o, "exceptions looking ahead from 01-Jan-2027")
rc, o, e = dg("--month", "2025-06")
ok(rc == 0 and o.count("Nothing this month.") == 5, "a quiet month: each section says nothing this month", o)
ok("## Portfolio" not in o, "no snapshot from before then: the portfolio section is left out quietly")
rc, o, e = dg("--month", "2026-13")
ok(rc == 1 and "--month takes YYYY-MM, this, or last" in e, "a month that doesn't exist is refused")
rc, o, e = dg("--calendar-json", tmp / "missing.json")
ok(rc == 0 and "the calendar file can't be read" in o, "a calendar file it can't read is noted, not fatal")

# ---- an ADR template, a lower-case file name, and sources that break ------------------------------------------------
dd = lib / "decisions"
(dd / "ADR-template.md").write_text("# ADR-<nnnn>: <title>\n\n| Field | Value |\n|---|---|\n| Status | <proposed, "
                                    "accepted, or superseded> |\n| Date decided | <DD-Mon-YYYY> |\n", encoding="utf-8")
(dd / "adr-0008-lower.md").write_text("# ADR-0008: Lower-case file name\n\n| Field | Value |\n|---|---|\n"
                                      "| Status | accepted |\n| Date decided | 22-Oct-2026 |\n", encoding="utf-8")
(dd / "ADR-0009-folder.md").mkdir()
rc, o, e = dg()
dec = section(o, "Decisions made in October")
ok(rc == 0 and "Traceback" not in e and "- ADR-0008 Lower-case file name: accepted 22-Oct-2026" in dec,
   "an ADR file named in lower case is read the same on every platform", dec + e)
ok("<title>" not in o and "<nnnn>" not in o and "Not read" not in o and "ADR-0001 Use Kafka" in dec,
   "a template with no number, and a folder named like an ADR, are skipped without stopping the digest", o[:900] + e)
# A copy of kit-digest next to other tools that misbehave: one section's source breaking leaves the rest.
fake = tmp / "fake"
(fake / "bin").mkdir(parents=True)
shutil.copy(str(SHARED / "bin/kit-digest"), str(fake / "bin/kit-digest"))
for mod in ("kit_arch.py", "kit_compliance.py", "kit_daily.py", "kit_records.py"):
    shutil.copy(str(SHARED / mod), str(fake / mod))
(fake / "bin/kit-refarch").write_text("def parse_date(text):\n    return 1 // 0\n")
(fake / "bin/kit-lifecycle").write_text("print('[\"x\", 1]')\n")
(fake / "bin/kit-exceptions").write_text(
    "import json\nprint(json.dumps({'due': ['junk', 5, None, {'id': 'EXC-9', 'policy': 'Backups', 'system': 'Files', "
    "'owner': 'ops', 'status': 'granted', 'date': '2026-12-01', 'days': 30, 'kind': 'expiring'}]}))\n")
r = subprocess.run([sys.executable, str(fake / "bin/kit-digest")], capture_output=True, text=True, encoding="utf-8",
                   timeout=300, env=env)
o, e = r.stdout, r.stderr
nr = section(o, "Not read (delete before sharing)")
ok(r.returncode == 0 and "reference architecture index: couldn't be read (ZeroDivisionError)" in nr,
   "a source that raises is listed as not read; the digest still comes out", o[-700:] + e)
ok("kit-lifecycle: its JSON isn't in the form kit-digest reads" in nr and section(o, "End of support").strip()
   == "- Nothing this month.", "JSON in a form it doesn't read is listed as not read, not taken as nothing", nr)
ok("- EXC-9 Backups / Files: expires 01-Dec-2026 (in 30 days; owner ops)" in section(o, "Exceptions expiring in the "
   "next 60 days") and "kit-exceptions" not in nr, "entries it can't read are skipped; the rest are listed", o + e)
ok("ADR-0008 Lower-case file name" in o, "and the other sections are all there")
(kit / "briefs/ppmx/pulse-2026-10-30.json").write_text('{"projects": ["not", "a", "map"]}')
rc, o, e = dg()
ok(rc == 0 and "## Portfolio" not in o and "Traceback" not in e, "a pulse snapshot it can't read: the portfolio is left "
   "out, the digest still comes out", o[-500:] + e)
(kit / "briefs/ppmx/pulse-2026-10-30.json").unlink()

# ---- a draft before the month ends never stands in for the month's digest ------------------------------------------
whole = kit / "briefs/digest-2026-10.md"
whole.unlink()
rc, o, e = dg("--write", "--month", "this", KIT_TODAY="2026-10-20")
draft = kit / "briefs/digest-2026-10-as-of-2026-10-20.md"
ok(rc == 0 and draft.exists() and not whole.exists() and "wrote briefs/digest-2026-10-as-of-2026-10-20.md" in o,
   "a month not yet over is drafted under an as-of name", o + e)
ok("looking ahead from 20-Oct-2026" in text_of(draft), "the draft looks ahead from its day")
rc, o, e = dg("--write", "--month", "last", "--brief")
lines = o.splitlines()
ok(rc == 0 and whole.exists() and lines[1].startswith("[work] Drafted for your edit: briefs/digest-2026-10.md "
                                                      "(3 decisions") and "kept" not in o,
   "when the month is over, its own digest is drafted", o + e)
ok("looking ahead from 01-Nov-2026" in text_of(whole), "covering the whole month")
# A mid-month draft written under the month's name (as an older kit-digest did) is moved aside, not kept.
whole.write_text(text_of(draft) or "- **Covers:** 01-Oct-2026 to 31-Oct-2026; looking ahead from 20-Oct-2026\n",
                 encoding="utf-8")
rc, o, e = dg("--write", "--month", "last", "--brief")
lines = o.splitlines()
aside = kit / "briefs/digest-2026-10-as-of-2026-10-20-2.md"
ok(rc == 0 and lines[1].startswith("[work] Drafted for your edit: briefs/digest-2026-10.md (3 decisions")
   and lines[1].endswith("; the draft from 20-Oct-2026, before the month ended, is now "
                         "briefs/digest-2026-10-as-of-2026-10-20-2.md"),
   "a draft from before the month ended is replaced, and the line says where it went", o + e)
ok("looking ahead from 20-Oct-2026" in text_of(aside) and draft.exists() and "looking ahead from 01-Nov-2026"
   in text_of(whole), "nothing is lost: the early draft is kept beside it under a name of its own")
# A digest you've edited is kept, and the counts reported are the file's, not a fresh count.
whole.write_text("\n".join(ln for ln in text_of(whole).splitlines()
                           if not ln.startswith("- ADR-0005")) + "\n", encoding="utf-8")
rc, o, e = dg("--write", "--month", "last", "--brief")
ok(rc == 0 and "[work] Already drafted, kept as it is: briefs/digest-2026-10.md (2 decisions" in o
   and "3 decisions" not in o, "a kept digest reports what the kept file holds", o)
rc, o, e = dg("--write", "--month", "last")
ok(rc == 0 and "kept the one already there (--force replaces it): briefs/digest-2026-10.md [work]: 2 decisions" in o,
   "the same without --brief", o)
ok(not any(x.name.startswith("digest-2026-10-as-of-2026-11") for x in (kit / "briefs").iterdir()),
   "a whole month never gets an as-of name", sorted(x.name for x in (kit / "briefs").iterdir()))

# ---- sources missing ------------------------------------------------------------------------------------------------------
LIBMD.unlink()
rc, o, e = dg()
ok(rc == 0 and "## Not read (delete before sharing)" in o, "with no library root it still runs, and says what it "
   "couldn't read", o + e)
nr = section(o, "Not read (delete before sharing)")
ok(all(s in nr for s in ("decisions folder", "reference architecture index", "kit-lifecycle", "kit-exceptions")),
   "each missing source is named", nr)
ok(section(o, "Decisions made in October").strip() == "- Nothing this month.", "and its section says nothing this month")
ok("Pre-read ready: Payments GDS.docx" in o, "Kit's own files are still read")
shutil.rmtree(kit / "briefs")
rc, o, e = dg("--write", "--brief")
ok(rc == 0 and (kit / "briefs/digest-2026-10.md").exists(), "an empty Kit: it still writes the digest", o + e)

# ---- Kit's permission rules ------------------------------------------------------------------------------------------
sys.path.insert(0, str(SHARED))
import kit_setup  # noqa: E402
ok({"Bash(kit-digest)", "Bash(kit-digest *)"} <= set(kit_setup.ALLOW), "kit-digest writes only Kit's own files, so it "
   "doesn't ask")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nkit-digest tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
