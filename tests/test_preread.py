#!/usr/bin/env python3
"""Tests for kit-preread (the red team's pre-read of a design document) and the kit_claude pieces it uses:
the prompt on standard input and an agent's playbook. Claude is a fake that keeps each prompt and the
options it ran with; everything happens in a temp folder.

Run: python3 tests/test_preread.py
"""
import importlib.util
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
(kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(kit / "memory/context").mkdir(parents=True)
(kit / "briefs").mkdir()
for f in ("kit-preread", "kit-library"):
    shutil.copy(SHARED / "bin" / f, bin_ / f)
shutil.copy(SHARED / "kit_daily.py", kit / ".install/shared/kit_daily.py")
calls = tmp / "calls"
calls.mkdir()
# The fake Claude keeps what it was asked and how, and what was in its working folder.
(kit / ".install/shared/kit_claude.py").write_text('''
import json, os
def ask_claude(prompt, mode, **kw):
    d = os.environ["FAKE_DIR"]
    with open(os.path.join(d, "%02d.json" % len(os.listdir(d))), "w") as f:
        json.dump({"prompt": prompt, "mode": mode, "files": sorted(os.listdir(kw.get("cwd") or ".")),
                   "kw": {k: list(v) if isinstance(v, tuple) else v for k, v in kw.items()}}, f, default=str)
    rc = int(os.environ.get("FAKE_RC", "0"))
    return rc, "" if rc else ("## Verdict\\nBreaks: one database in one zone.\\nA zone loss stops payments.\\n\\n"
                              "## Findings\\n### RT-01 · critical · possible · DR and recovery\\n"
                              "- Failure scenario: the zone fails.\\n- Evidence: section 4\\n- Mitigation: a replica.\\n\\n"
                              "## Can't tell\\n- What is the RPO?\\n\\n## Questions to ask\\n"
                              "1. Where does the replica live? [RT-01]\\nMail pat@example.com for the runbook.")
def agent_prompt(name):
    return os.environ.get("FAKE_PLAYBOOK", "")
''')


def docx(path, text):
    with zipfile.ZipFile(path, "w") as z:
        body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in text.split("\n"))
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{body}</w:body></w:document>')


docs = tmp / "docs"
docs.mkdir()
docx(docs / "Payments GDS.docx", "Payments GDS\n4. Data\nThe payments service runs on one database server in one zone.")
(docs / "Payments GDS.pdf").write_bytes(b"%PDF-1.4\n% a stand-in\n")
(docs / "notes.xyz").write_text("x")
(kit / "library").mkdir()
(kit / "library/collections.json").write_text(json.dumps({
    "version": 1, "output": {"folder": str(tmp / "Kit Output"), "kinds": {"reports": "Reports"}},
    "collections": [], "tags": {}}))
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-29", FAKE_DIR=str(calls), FAKE_PLAYBOOK="PLAYBOOK-TEXT",
           KIT_PDFTEXT=str(tmp / "no-pdf-helper"))
env.pop("FAKE_RC", None)


def run(*args, **extra):
    r = subprocess.run([sys.executable, str(bin_ / "kit-preread"), *args], capture_output=True, text=True,
                       env=dict(env, **extra), timeout=120)
    return r.returncode, r.stdout, r.stderr


def made():
    return [json.loads(f.read_text()) for f in sorted(calls.glob("*.json"))]


# ---- a Word document: its text goes in the prompt, and the run is closed
(kit / "memory/context/standards.md").write_text("# Standards\n\n- **Tier 1:** RTO 4 hours, RPO 15 minutes.\n" + "x " * 400)
rc, out, err = run(str(docs / "Payments GDS.docx"), "--meeting", "Payments design review", "--date", "30-Oct-2026")
brief = kit / "briefs/preread/2026-10-29-payments-gds.md"
ok(rc == 0 and brief.exists(), "a pre-read is written", f"{out} {err}")
c = made()[0] if made() else {"prompt": "", "kw": {}, "files": ["?"]}
p = c["prompt"]
ok(p.startswith("PLAYBOOK-TEXT\n\n---\n\nKit's brief for the red team: a pre-read. Alex has the meeting "
                '"Payments design review" on 30-Oct-2026'), "the playbook, then the brief", p[:200])
ok("one database server in one zone" in p and "RTO 4 hours" in p, "the document's text and the team's standards")
kw = c["kw"]
ok(c["mode"] == "preread" and kw.get("allowed") == [] and "Read" in kw.get("deny", []) and "Bash" in kw.get("deny", [])
   and kw.get("extra_args") == ["--setting-sources", "project,local"] and kw.get("prompt_stdin") is True
   and "mcp" not in kw, "closed: no tools, none of the user's rules, no MCP, the prompt on standard input", str(kw))
ok(c["files"] == [] and str(kit) not in str(kw.get("cwd")), "it runs in an empty folder of its own", str(c["files"]))
t = brief.read_text() if brief.exists() else ""
ok(t.startswith("# Pre-read: Payments GDS.docx\n\n- **For:** Payments design review, 30-Oct-2026\n")
   and "[work]" in t and "words of text; figures not seen" in t, "the pre-read's header", t[:300])
ok("## Questions to ask\n1. Where does the replica live? [RT-01]" in t and "pat@example.com" not in t
   and "[address]" in t, "the answer, with addresses masked")
ok(oct(brief.stat().st_mode & 0o777) == "0o600" if os.name != "nt" else True, "owner-only")
rc, out, err = run(str(docs / "Payments GDS.docx"))
ok(rc == 0 and "already" in out and len(made()) == 1, "today's pre-read of the same file is kept", out)
rc, out, err = run(str(docs / "Payments GDS.docx"), "--force", "--deliver")
got = list((tmp / "Kit Output/Reports/Pre-reads").glob("*")) if (tmp / "Kit Output").exists() else []
ok(rc == 0 and len(made()) == 2 and got, "--force makes it again, and --deliver puts it in Kit Output", f"{out} {err}")

# ---- a PDF Kit can't turn into text: the red team reads a copy, in its own folder, and nothing private
rc, out, err = run(str(docs / "Payments GDS.pdf"), "--force")
c = made()[-1]
kw = c["kw"]
ok(rc == 0 and c["files"] == ["Payments GDS.pdf"], "a copy of the PDF is the only file in its folder", str(c["files"]))
ok(kw.get("allowed") == [] and "Read" not in kw.get("deny", []) and "Read(~/.ssh/**)" in kw.get("deny", [])
   and "Read(~/Claude/**)" in kw.get("deny", []) and "Bash" in kw.get("deny", []), "Read in its own folder, and not private folders",
   str(kw.get("deny")))
ok("read it with the Read tool" in c["prompt"], "the brief says to read the file")

# ---- the rest: the budget, a failed run, a dry run, a file it can't read, the list, and no playbook
rc, out, err = run(str(docs / "Payments GDS.docx"), "--force", FAKE_RC="75")
ok(rc == 75 and "budget" in err, "the monthly budget skips it (exit 75)", err)
rc, out, err = run(str(docs / "Payments GDS.docx"), "--force", FAKE_RC="1")
ok(rc == 1 and "didn't finish" in err, "a failed run says so", err)
n = len(made())
rc, out, err = run("--dry-run", str(docs / "Payments GDS.docx"))
ok(rc == 0 and len(made()) == n and "one database server" in out and "characters" in out, "--dry-run runs nothing", out)
rc, out, err = run(str(docs / "notes.xyz"))
ok(rc != 0 and "can't read .xyz" in (err + out), "a kind of file Kit can't read", err)
rc, out, err = run("--list")
ok("1 pre-read(s)" in out and "Breaks: one database" in out, "--list: the recent pre-reads and their verdicts", out)
rc, out, err = run(str(docs / "Payments GDS.docx"), "--force", FAKE_PLAYBOOK="")
ok(made()[-1]["prompt"].startswith("You are Kit's red team"), "with no red team installed, a short playbook stands in")

# ---- kit_claude: an agent's playbook, and a prompt on standard input
spec = importlib.util.spec_from_file_location("kc", SHARED / "kit_claude.py")
kc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kc)
home = tmp / "home"
(home / ".claude/agents").mkdir(parents=True)
(home / ".claude/agents/red-team.md").write_text("---\nname: red-team\ndescription: x\ntools: Read\n---\n\n# Red team\n\nBreak it.\n")
kc.HOME = home
ok(kc.agent_prompt("red-team") == "# Red team\n\nBreak it." and kc.agent_prompt("nobody") == "",
   "agent_prompt: the playbook without its header; empty when the agent isn't installed")
fake = tmp / "fakebin"
fake.mkdir()
(fake / "claude").write_text("#!" + sys.executable + "\nimport json, sys\n"
                             "print(json.dumps({'result': 'GOT ' + sys.stdin.read() + ' ARGS ' + ' '.join(sys.argv[1:4])}))\n")
(fake / "claude").chmod(0o755)
if os.name != "nt":
    kc.PATH = f"{fake}:{kc.PATH}"
    os.environ["KIT_DIR"] = str(kit)
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "test-token"          # no Keychain lookup in a test
    rc, text = kc.ask_claude("a long prompt", mode="test", prompt_stdin=True, cwd=tmp)
    ok(rc == 0 and text.startswith("GOT a long prompt ARGS -p --output-format json"),
       "prompt_stdin: the prompt goes on standard input, not the command line", text)
    rc, text = kc.ask_claude("short", mode="test", cwd=tmp)
    ok(rc == 0 and "ARGS -p short --output-format" in text, "the usual way: the prompt on the command line", text)
    kc.PATH = "/nonexistent"
    rc, text = kc.ask_claude("x", mode="test", cwd=tmp)
    ok(rc == 127 and text == "", "no claude on the PATH: exit 127, not a crash", str(rc))

shutil.rmtree(tmp, ignore_errors=True)
print(f"kit-preread tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
