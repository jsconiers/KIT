#!/usr/bin/env python3
"""Tests for kit-rehearse (getting ready to defend your own design at a review board). Claude is a fake that
keeps each prompt and the options it ran with; everything happens in a temp folder.

Run: python3 tests/test_rehearse.py
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
SHARED = REPO / "shared"
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
bin_ = kit / ".install/shared/bin"
bin_.mkdir(parents=True)
(kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\nREHEARSE_MODEL="sonnet"\n')
(kit / "memory/context").mkdir(parents=True)
(kit / "briefs").mkdir()
for f in ("kit-rehearse", "kit-preread", "kit-library"):
    shutil.copy(SHARED / "bin" / f, bin_ / f)
shutil.copy(SHARED / "kit_daily.py", kit / ".install/shared/kit_daily.py")
calls = tmp / "calls"
calls.mkdir()
QS = "".join(f"### Q{i}. Question {i}?\n- Why they'll ask: reason {i}.\n- Where the document answers it: section {i}\n"
             f"- A strong answer: point {i}.\n\n" for i in range(1, 11))
ANSWER = ("## The ask\nApprove the payments platform move to two regions.\n\n## Ten hardest questions\n" + QS
          + "## Two-minute talk track\nWe run payments in one zone today. Mail pat@example.com for the deck.\n\n"
            "## Gaps to close before the board\n- The RPO isn't stated.")
(kit / ".install/shared/kit_claude.py").write_text('''
import json, os
def ask_claude(prompt, mode, **kw):
    d = os.environ["FAKE_DIR"]
    with open(os.path.join(d, "%02d.json" % len(os.listdir(d))), "w") as f:
        json.dump({"prompt": prompt, "mode": mode, "files": sorted(os.listdir(kw.get("cwd") or ".")),
                   "kw": {k: list(v) if isinstance(v, tuple) else v for k, v in kw.items()}}, f, default=str)
    rc = int(os.environ.get("FAKE_RC", "0"))
    return rc, "" if rc else os.environ.get("FAKE_ANSWER", "")
def agent_prompt(name):
    return os.environ.get("FAKE_PLAYBOOK", "")
''')


def docx(path, text):
    with zipfile.ZipFile(path, "w") as z:
        body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in text.split("\n"))
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{body}</w:body></w:document>')


docs = tmp / "docs"
docs.mkdir()
docx(docs / "Payments Two Regions.docx", "Payments: two regions\n1. The ask\nApprove a second region.\n"
                                         "4. Recovery\nThe database replicates every 15 minutes.")
(docs / "Payments Two Regions.pdf").write_bytes(b"%PDF-1.4\n% a stand-in\n")
(kit / "library").mkdir()
(kit / "library/collections.json").write_text(json.dumps({
    "version": 1, "output": {"folder": str(tmp / "Kit Output"), "kinds": {"reports": "Reports"}},
    "collections": [], "tags": {}}))
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-11-04", FAKE_DIR=str(calls), FAKE_PLAYBOOK="RED-TEAM-PLAYBOOK",
           KIT_PDFTEXT=str(tmp / "no-pdf-helper"), FAKE_ANSWER=ANSWER, PYTHONUTF8="1")
env.pop("FAKE_RC", None)


def run(*args, **extra):
    r = subprocess.run([sys.executable, str(bin_ / "kit-rehearse"), *args], capture_output=True, text=True,
                       env=dict(env, **extra), timeout=120, encoding="utf-8")
    return r.returncode, r.stdout, r.stderr


def made():
    return [json.loads(f.read_text()) for f in sorted(calls.glob("*.json"))]


# ---- a Word document: the board's brief, the document, the standards, and a closed run
(kit / "memory/context/standards.md").write_text("# Standards\n\n- **Tier 1:** RTO 4 hours, RPO 15 minutes.\n" + "x " * 400)
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--board", "the Architecture Review Board", "--date", "12-Nov-2026")
path = kit / "briefs/rehearse/2026-11-04-payments-two-regions.md"
ok(rc == 0 and path.exists() and "(10 questions)" in out, "a rehearsal is written, with ten questions", out + err)
c = made()[0] if made() else {"prompt": "", "kw": {}, "files": ["?"], "mode": ""}
p = c["prompt"]
ok(p.startswith("You are rehearsing Alex for a review board. Alex wrote the design in \"Payments Two Regions.docx\" "
                "and will present it to\nthe Architecture Review Board on 12-Nov-2026."), "the board's brief, for the owner", p[:240])
ok("replicates every 15 minutes" in p and "RTO 4 hours" in p and "RED-TEAM-PLAYBOOK" in p,
   "the document, the team's standards, and the red team's playbook")
ok("Never invent a number" in p and "## Ten hardest questions" in p and "About 260 words" in p, "the form it must answer in")
kw = c["kw"]
ok(c["mode"] == "rehearse" and kw.get("allowed") == [] and "Read" in kw.get("deny", []) and "Bash" in kw.get("deny", [])
   and kw.get("model") == "sonnet" and kw.get("prompt_stdin") is True
   and kw.get("extra_args") == ["--setting-sources", "project,local"], "closed: no tools, none of the user's rules; "
   "REHEARSE_MODEL from the config", str(kw))
ok(c["files"] == [], "it runs in an empty folder of its own")
t = path.read_text(encoding="utf-8") if path.exists() else ""
ok(t.startswith("# Rehearsal: Payments Two Regions.docx\n\n- **For:** the Architecture Review Board, 12-Nov-2026\n")
   and "[work]" in t, "the header: what it's for, marked [work]", t[:300])
ok("### Q10. Question 10?" in t and "## Two-minute talk track" in t and "pat@example.com" not in t and "[address]" in t,
   "the answer as it came, addresses masked")
ok("check every figure before you say it" in t, "the closing reminder")
if os.name != "nt":
    ok(oct(path.stat().st_mode & 0o777) == "0o600", "owner-only")
rc, out, err = run(str(docs / "Payments Two Regions.docx"))
ok(rc == 0 and "already" in out and len(made()) == 1, "today's rehearsal of the same file is kept", out)
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--force", "--deliver")
got = list((tmp / "Kit Output/Reports/Rehearsals").glob("*")) if (tmp / "Kit Output").exists() else []
if sys.platform == "darwin":                  # Markdown becomes Word with the Mac's textutil
    ok(rc == 0 and len(made()) == 2 and got, "--force makes it again; --deliver puts it in Kit Output > Reports > "
       "Rehearsals", out + err)
else:
    ok(rc == 0 and len(made()) == 2 and ("delivered to" in out or "not delivered" in out),
       "--force makes it again; --deliver says how delivery went", out + err)

# ---- fewer questions, or an answer in another form, is flagged
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--force",
                   FAKE_ANSWER=ANSWER.replace(QS, QS.split("### Q4.")[0]))
t = path.read_text(encoding="utf-8")
ok(rc == 0 and "_Only 3 questions came back, not 10._" in t, "fewer than ten questions is noted", t[:400])
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--force", FAKE_ANSWER="Some prose with no form.")
ok("didn't come back in the rehearsal's form" in path.read_text(encoding="utf-8"), "an answer in another form is flagged")

# ---- a PDF with no text: a copy is the only file Claude can read
rc, out, err = run(str(docs / "Payments Two Regions.pdf"), "--force")
c = made()[-1]
ok(rc == 0 and c["files"] == ["Payments Two Regions.pdf"] and "Read" not in c["kw"].get("deny", [])
   and "Read(~/.ssh/**)" in c["kw"].get("deny", []) and "read it with the Read tool" in c["prompt"],
   "a PDF Kit can't read goes to Claude as the one file in its folder", str(c["files"]))

# ---- the budget, a failed run, a dry run, a missing file, the list, and no red team
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--force", FAKE_RC="75")
ok(rc == 75 and "budget" in err, "the monthly budget skips it (exit 75)", err)
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--force", FAKE_RC="1")
ok(rc == 1 and "didn't finish" in err, "a failed run says so", err)
n = len(made())
rc, out, err = run("--dry-run", str(docs / "Payments Two Regions.docx"))
ok(rc == 0 and len(made()) == n and "replicates every 15 minutes" in out, "--dry-run runs nothing", out)
rc, out, err = run(str(docs / "missing.docx"))
ok(rc != 0 and "no such file" in err, "a file that isn't there", err)
docx(docs / "empty.docx", "")
rc, out, err = run(str(docs / "empty.docx"))
ok(rc != 0 and "kit-rehearse:" in err and "kit-preread" not in err, "an empty document, in kit-rehearse's own words", err)
rc, out, err = run("--list")
ok("1 rehearsal(s)" in out and "Approve the payments platform" in out or "1 rehearsal(s)" in out,
   "--list: the recent rehearsals", out)
rc, out, err = run(str(docs / "Payments Two Regions.docx"), "--force", FAKE_PLAYBOOK="")
ok("toughest member" not in made()[-1]["prompt"], "with no red team installed, the brief stands alone")

shutil.rmtree(tmp, ignore_errors=True)
print(f"kit-rehearse tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
