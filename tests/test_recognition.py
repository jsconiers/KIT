#!/usr/bin/env python3
"""kit-feedback recognition: thanked, recognize (praise still to pass on, wins that name someone, who hasn't
been recognized lately, a draft), the brief's nudges (morning and weekly), the 1:1 prep and review lines, and
that recognition.jsonl is owner-only. Synthetic names only.

Run: python3 tests/test_recognition.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TOOL = HERE.parent / "shared" / "bin" / "kit-feedback"
tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / "memory").mkdir(parents=True)
(kit / ".install/shared/morning").mkdir(parents=True)
fakebin = tmp / "bin"
fakebin.mkdir()
(fakebin / "kitcal").write_text("#!/usr/bin/env python3\nprint('[]')\n")
(fakebin / "kitcal").chmod(0o755)
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-11-20", PATH=f"{fakebin}:{os.environ.get('PATH', '')}",
           PYTHONUTF8="1")
fails = []


def check(cond, what, extra=""):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)
        if extra:
            print("     " + str(extra)[:1500].replace("\n", "\n     "))


def run(*args):
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env, timeout=60,
                       stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout, r.stderr


run("add-person", "Rowan Vale", "--role", "SRE", "--alias", "Ro")
run("add-person", "Quinn Ash", "--role", "Engineer")
run("add-person", "Tamsin Ore", "--role", "Analyst")
run("add", "Rowan", "caught the DNS gap in the cutover rehearsal", "--kind", "praise", "--impact",
    "the cutover went through with no rollback", "--date", "2026-11-05")
run("add", "Rowan", "wrote the clearest runbook on the team", "--kind", "praise", "--date", "2026-11-17")
run("add", "Quinn", "Reviewed every change in the release", "--kind", "praise", "--date", "2026-11-18")
run("add", "Tamsin", "missed the data review", "--kind", "coaching", "--date", "2026-11-10")
(kit / "memory/accomplishments.md").write_text("""# Accomplishments

- 12-Nov-2026 [Delivery and meetings] Cutover of the payments gateway, with Ro running the rehearsal (QUEUE.md)
- 03-Sep-2026 [Delivery and meetings] Old work Rowan did (QUEUE.md)
- 15-Nov-2026 [Kit and automation] Release notes published (briefs)
""")

# ---------------------------------------------------------------- recognize: the list
rc, o, e = run("recognize")
check(rc == 0 and "Rowan Vale: 2 praise note(s) to pass on, the oldest 15 days old; 1 win(s) in the log name them; "
      "not recognized yet" in o, "recognize: praise waiting, wins by alias, not yet recognized", o + e)
check("Quinn Ash: 1 praise note(s) to pass on, the oldest 2 days old; not recognized yet" in o, "recognize: Quinn", o)
check("Tamsin Ore: not recognized yet" in o, "recognize: someone with no praise still shows when never recognized", o)

# ---------------------------------------------------------------- recognize NAME: what to thank them for, a draft
rc, o, e = run("recognize", "Rowan")
check(rc == 0 and "Last recognized: not yet" in o and "05-Nov-2026: caught the DNS gap" in o
      and "12-Nov-2026: Cutover of the payments gateway, with Ro running the rehearsal" in o, "recognize NAME", o + e)
check("Rowan, I noticed you caught the DNS gap in the cutover rehearsal, and I wanted to say thank you. It meant the "
      "cutover went through with no rollback." in o and "Kit sends nothing" in o,
      "a draft from the newest praise that says what it led to", o)
rc, o, e = run("recognize", "Quinn")
check("Quinn, I noticed you reviewed every change in the release, and I wanted to say thank you." in o,
      "the draft lower-cases the note's first word", o)
check("Old work Rowan did" not in run("recognize", "Rowan")[1], "wins older than 30 days are left out")

# ---------------------------------------------------------------- the brief: morning and weekly
rc, o, e = run("brief")
lines = o.splitlines()
check(rc == 0 and "[work] Praise to pass on: Rowan (2). (kit-feedback recognize NAME)" in o and "Quinn (" not in o,
      "morning: praise to pass on once a week old (Quinn's is 2 days old)", o + e)
check(all(ln.startswith("[work]") for ln in lines[1:]) and "DNS" not in o and "runbook" not in o,
      "names and counts only, every line [work]", o)
check("Not recognized in" not in o, "morning: no recognition roll-call", o)
rc, o, e = run("brief", "weekly")
check("[work] Not recognized in 30 days: Quinn (not yet), Rowan (not yet), Tamsin (not yet). (kit-feedback recognize)"
      in o, "weekly: who hasn't been recognized", o)
(kit / ".install/shared/morning/config").write_text('RECOGNIZE_AFTER_DAYS="1"\nRECOGNIZE_EVERY_DAYS="60"\n')
rc, o, e = run("brief", "weekly")
check("Praise to pass on: Quinn (1), Rowan (2)" in o and "Not recognized in 60 days" in o, "the config's days are used", o)
(kit / ".install/shared/morning/config").write_text("")

# ---------------------------------------------------------------- thanked
rc, o, e = run("thanked", "Rowan", "--how", "public", "--for", "the cutover rehearsal", "--date", "2026-11-10")
check(rc == 0 and "Recognized Rowan Vale (public, 10-Nov-2026). 1 praise note(s) now count as passed on." in o,
      "thanked: the praise before it counts as passed on", o + e)
rc, o, e = run("thanked", "Rowan", "--how", "shout")
check(rc == 1 and "--how is one of" in e, "--how is checked", e)
rc, o, e = run("thanked", "Rowan", "--date", "2026-12-01")
check(rc == 1 and "hasn't happened" in e, "no future dates", e)
rc, o, e = run("recognize", "Rowan")
check("Last recognized: 10-Nov-2026 (public) for the cutover rehearsal" in o and "05-Nov-2026" not in o.split("Praise")[1]
      .split("Wins")[0] and "17-Nov-2026: wrote the clearest runbook" in o, "recognize NAME after thanks: only newer praise", o)
rc, o, e = run("brief")
check("Praise to pass on: Rowan" not in o, "the newer praise (3 days old) waits until it's a week old", o)
rc, o, e = run("thanked", "Rowan", "--how", "note")
rc, o, e = run("brief", "weekly")
check("Rowan" not in o.split("Not recognized")[1] if "Not recognized" in o else True, "recognized today: off the roll-call", o)
check("Praise to pass on: Rowan" not in o, "and nothing left to pass on", o)

# ---------------------------------------------------------------- people, prep, review, the file
rc, o, e = run("people")
check("Rowan Vale (SRE)" in o and "last recognized 20-Nov-2026" in o, "people: last recognized", o)
rc, o, e = run("prep", "Rowan")
check("Last recognized: 20-Nov-2026 (note)." in o, "1:1 prep: last recognized", o)
rc, o, e = run("prep", "Quinn")
check("Not recognized yet" in o, "1:1 prep: not yet", o)
rc, o, e = run("review", "Rowan", "--from", "2026-11-01", "--to", "2026-11-30")
check("Recognized 2 time(s) in the period (note 1, public 1)." in o, "review: recognitions counted by how", o)
f = kit / "feedback/recognition.jsonl"
rows = [json.loads(x) for x in f.read_text().splitlines()]
check(len(rows) == 2 and rows[0]["for"] == "the cutover rehearsal", "recognition.jsonl holds the events")
check(f.stat().st_mode & 0o077 == 0 if os.name == "posix" else True, "recognition.jsonl is owner-only")
rc, o, e = run("--check")
check(o.strip() == "ok 3 people, 4 notes, 2 recognitions", "--check counts recognitions", o)

shutil.rmtree(tmp)
print(f"\n{'FAILED' if fails else 'passed'}: kit-feedback recognition, {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
