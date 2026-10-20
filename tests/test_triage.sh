#!/bin/bash
# Tests kit-triage (inbox triage suggestions) with fixture kitmail output.
#   bash tests/test_triage.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import os, pathlib, subprocess, sys, tempfile, shutil
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-triage"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "briefs").mkdir(); (kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex Kim"\n')
(kit / "memory/context/triage.md").write_text("- **Priority senders:** Morgan Lee\n- **Delegated topics:** printer\n")
def L(flag, n, when, sender, subj): return f"{flag}{n:>3}  {when}  {sender[:28].ljust(28)}  {subj}"
listing = "\n".join([
  L("*", 1, "19-Oct 08:00", "no-reply@example.com", "Your weekly digest"),
  L("*", 2, "19-Oct 08:05", "Jira", "[JIRA] PROJ-1 updated"),
  L("*", 3, "19-Oct 08:10", "Sam Park", "Please approve the change request"),
  L("*", 4, "19-Oct 08:20", "Sam Park", "Can you review the IA by Friday?"),
  L(" ", 5, "19-Oct 08:30", "Morgan Lee", "Thanks for the deck"),
  L(" ", 6, "18-Oct 17:00", "Robin Cho", "FYI: status report"),
  L(" ", 7, "18-Oct 16:00", "Robin Cho", "Printer setup - can you help?"),
  "", "(7 shown — '*' = unread. `kitmail read <n>` for a message.)"])
(tmp / "inbox.txt").write_text(listing)
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-19")
run = lambda *a, **k: subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env, **k)
r = run(str(tmp / "inbox.txt"), "--print"); t = r.stdout
row = lambda n: next((l for l in t.splitlines() if l.startswith("| ") and f"| {n} |" in l), "")
ok(r.returncode == 0, "runs on inbox listing")
ok(row(1).startswith("| ignore"), "no-reply digest -> ignore")
ok(row(2).startswith("| read-later"), "system notification -> read-later")
ok(row(3).startswith("| decide"), "approval request -> decide")
ok(row(4).startswith("| reply") and "due" in row(4), "direct question with due date -> reply, due noted")
ok(row(5).startswith("| reply") and "priority" in row(5), "priority sender -> reply")
ok(row(6).startswith("| read-later") and "information" in row(6), "FYI -> read-later")
ok(row(7).startswith("| delegate"), "delegated topic -> delegate")
order = [l.split("|")[1].strip() for l in t.splitlines() if l.startswith("| ") and not l.startswith("| Suggest") and not l.startswith("|---")]
ok(order[0] == "decide" and order[-1] == "ignore", "sorted decide first, ignore last")
ok("no-reply@example.com" not in t and "[address]" in t, "addresses masked")
body = "x" * 300
msgs = f"""From:    Sam Park <sam@example.com>
To:      Team <team@example.com>
Cc:      Alex Kim <alex@example.com>
Date:    Mon 19-Oct-2026 09:00
Subject: Weekly numbers
------------------------------------------------------------
Hi all, can someone pull the numbers? {body}
=== message
From:    Sam Park <sam@example.com>
To:      Alex Kim <alex@example.com>
Date:    Mon 19-Oct-2026 09:30
Subject: Quick question
------------------------------------------------------------
Could you send me the link?
"""
(tmp / "msgs.txt").write_text(msgs)
r = run(str(tmp / "msgs.txt"), "--print"); t2 = r.stdout
ok("| delegate | 1 |" in t2, "request to a group -> delegate")
ok("| reply | 2 |" in t2, "direct question in body -> reply")
ok("x" * 81 not in t2, "never quotes more than 80 characters")
r = subprocess.run([sys.executable, str(tool), "-"], input=listing, capture_output=True, text=True, env=env)
ok(r.returncode == 0 and (kit / "briefs/triage-2026-10-19.md").exists(), "stdin input writes the brief")
r = run(str(tmp / "nope.txt"))
ok(r.returncode != 0, "no messages refused")
shutil.rmtree(tmp)
print(f"kit-triage tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY
