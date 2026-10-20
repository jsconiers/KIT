#!/bin/bash
# Tests kit-awaiting (awaiting-reply tracker) with fixture sent-dump and inbox output.
#   bash tests/test_awaiting.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import os, pathlib, subprocess, sys, tempfile, shutil
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-awaiting"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "briefs").mkdir()
shutil.copy(repo / "kit/memory/context/meetings.md", kit / "memory/context/meetings.md")
def M(date, subj, body, role=None):
    head = f"From:    Alex Kim <alex@example.com>\nDate:    {date}\nSubject: {subj}\n" + (f"Role:    {role}\n" if role else "")
    return head + "-" * 60 + "\n" + body + "\n"
sent = "=== message\n".join([
  M("Mon 12-Oct-2026 09:00", "Firewall change window", "Hi, can you confirm the window for Thursday?\n\n> old quoted text?", "network lead"),
  M("Tue 13-Oct-2026 10:00", "IA review", "Could you review section 4 please?"),
  M("Wed 14-Oct-2026 11:00", "Thanks", "Thanks for the update. Let me know if you have any questions."),
  M("Fri 16-Oct-2026 12:00", "Budget", "Any update on the lab budget?"),
  M("Sun 18-Oct-2026 08:00", "New ask", "Can you send the diagram?"),
])
(tmp / "sent.txt").write_text(sent)
def L(n, when, sender, subj): return f" {n:>3}  {when}  {sender[:28].ljust(28)}  {subj}"
inbox = "\n".join([L(1, "14-Oct 09:00", "Robin Cho", "RE: IA review"), L(2, "11-Oct 09:00", "Robin Cho", "Re: Budget")])
(tmp / "inbox.txt").write_text(inbox)
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-19")
run = lambda *a: subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)
r = run("--sent", str(tmp / "sent.txt"), "--inbox", str(tmp / "inbox.txt"), "--print"); t = r.stdout
ok(r.returncode == 0, "runs")
ok("Firewall change window" in t and "network lead" in t, "unanswered ask listed with the recipient's role")
ok("| IA review |" not in t and "**IA review:**" not in t, "answered by a later RE: -> not listed")
ok("| Thanks |" not in t, "'let me know if you have questions' isn't an ask")
ok("Budget" in t, "a reply dated before the ask doesn't count")
ok("New ask" not in t, "younger than the threshold (3 days) -> not yet")
ok("old quoted text" not in t, "quoted reply text ignored")
ok("Following up on my note of 12-Oct-2026" in t, "draft nudge written")
ok("@" not in t, "no addresses")
r = run("--sent", str(tmp / "sent.txt"), "--inbox", str(tmp / "inbox.txt"), "--days", "0", "--print")
ok("New ask" in r.stdout, "--days overrides the setting")
s = (kit / "memory/context/meetings.md").read_text().replace("**Awaiting reply after:** 3 days", "**Awaiting reply after:** 10 days")
(kit / "memory/context/meetings.md").write_text(s)
r = run("--sent", str(tmp / "sent.txt"), "--inbox", str(tmp / "inbox.txt"), "--print")
ok("Nothing outstanding" in r.stdout, "threshold read from meetings.md")
r = run("--sent", str(tmp / "sent.txt"), "--inbox", str(tmp / "inbox.txt"))
ok((kit / "briefs/awaiting-2026-10-19.md").exists(), "writes the brief")
(tmp / "empty.txt").write_text("")
r = run("--sent", str(tmp / "empty.txt"), "--inbox", str(tmp / "inbox.txt"))
ok(r.returncode != 0 and "sent-items" in r.stderr, "no sent mail -> explains the kitmail change")
ok("NEEDS THE KITMAIL SENT-ITEMS CHANGE" in (repo / "shared/bin/kit-awaiting").read_text(), "documents the dependency")
shutil.rmtree(tmp)
print(f"kit-awaiting tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY
