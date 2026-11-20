#!/usr/bin/env python3
"""Tests for the duplicate catcher at add time: kit_queue's matcher (dates, weekdays, the [work] tag, case,
punctuation, and filler words set aside; IDF-weighted overlap or full containment), `todo` refusing a duplicate
(exit 1, the match shown), --force, --merge and KIT_TODO_MERGE ("seen again" on the open item, logged),
QUEUE_DUP_THRESHOLD (and "off"), `todo dupes`, the phone sync (kit_sync_core), and the scheduled runs' queue items
(connector_health.queue_add and queue_note). A throwaway Kit folder; synthetic items only.

  python3 tests/test_queue_dupes.py
"""
import datetime as dt
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
TODO = SHARED / "bin/todo"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-dupes-"))
KIT = TMP / "kit"
(KIT / ".install/shared/bin").mkdir(parents=True)
(KIT / ".install/shared/morning").mkdir(parents=True)
shutil.copy(TODO, KIT / ".install/shared/bin/todo")
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
QUEUE = KIT / "QUEUE.md"
TODAY = dt.date.today()
D = TODAY.strftime("%d-%b-%Y")
SEED = f"""# Queue

## Alex

- [ ] **Fix Kit's sync run, failing since 04-Nov-2026 (kit-reliability)** [work] (added 04-Nov-2026)
  Recovered 06-Nov-2026: the sync run succeeded again; check this off when you're satisfied.
- [ ] **Call the dentist about the crown** (added 01-Nov-2026)
- [ ] **Renew: passport** (added 02-Nov-2026)

## Kit

- [ ] **Draft the agenda for the platform review** (added 03-Nov-2026)

## Waiting on others

## Done
"""
ENV = dict(os.environ, KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1")
ENV.pop("QUEUE_DUP_THRESHOLD", None)
ENV.pop("KIT_TODO_MERGE", None)


def todo(*args, env=None):
    r = subprocess.run([sys.executable, str(TODO), *args], capture_output=True, text=True, env=env or ENV, timeout=60)
    return r.returncode, r.stdout + r.stderr


def reset():
    QUEUE.write_text(SEED)


def count(text):
    return QUEUE.read_text().count(text)


# ---- the matcher ---------------------------------------------------------------------------------------------------
sys.path.insert(0, str(SHARED))
os.environ["KIT_DIR"] = str(KIT)
import kit_queue as kq  # noqa: E402

reset()
lines = QUEUE.read_text().splitlines()
hit = kq.find_duplicate(lines, "Alex", "Fix Kit's sync run, failing since 18-Nov-2026 (kit-reliability)")
ok(hit and hit[0]["n"] == 1, "a new outage date is the same item (the real sync-run duplicates)", hit)
ok(kq.find_duplicate(lines, "Alex", "Fix Kit's morning run, failing since 18-Nov-2026 (kit-reliability)") is None,
   "another run type isn't a duplicate")
ok(kq.find_duplicate(lines, "Alex", "CALL the dentist -- about the crown!! fri") is not None,
   "case, punctuation, and a weekday are set aside")
ok(kq.find_duplicate(lines, "Alex", "Call the dentist about the crown [work]") is not None, "the [work] tag is set aside")
ok(kq.find_duplicate(lines, "Alex", "Renew: driving licence") is None, "a different renewal isn't a duplicate")
ok(kq.find_duplicate(lines, "Kit", "Call the dentist about the crown") is None, "only the same section counts")
ok(kq.find_duplicate(lines, "Alex", "Call the dentist about the crown", None) is None, "threshold None: off")
ok(kq.dup_threshold('QUEUE_DUP_THRESHOLD="off"\n') is None and kq.dup_threshold('QUEUE_DUP_THRESHOLD="90"\n') == 0.9
   and kq.dup_threshold("") == 0.8 and kq.dup_threshold('QUEUE_DUP_THRESHOLD="x"\n') == 0.8,
   "QUEUE_DUP_THRESHOLD: off, a percent, the default, junk")

# ---- todo ----------------------------------------------------------------------------------------------------------
reset()
rc, out = todo("call the Dentist about the crown", "fri")
ok(rc == 1 and "Not added: it matches Alex item 2" in out and "Call the dentist about the crown" in out
   and "--force" in out, "todo refuses a duplicate and says which item it matches", out)
ok(count("dentist") == 1, "nothing was added")
rc, out = todo("--force", "call the Dentist about the crown")
ok(rc == 0 and QUEUE.read_text().lower().count("dentist") == 2, "--force adds it anyway", out)
reset()
rc, out = todo("Book the car service")
ok(rc == 0 and count("Book the car service") == 1, "a new item is added as before", out)
rc, out = todo("--merge", "work", "Fix Kit's sync run, failing since 11-Nov-2026 (kit-reliability)")
q = QUEUE.read_text()
ok(rc == 0 and "11-Nov-2026" not in q and f"(seen again {D})" in q and "Already on the list" in out,
   "--merge notes 'seen again' on the open item instead of adding", (out, q))
log = (KIT / ".install/logs/queue-dupes.log")
ok(log.is_file() and "merged into Alex 1" in log.read_text(), "the merge is logged", log.read_text() if log.exists() else "")
rc, out = todo("--merge", "work", "Fix Kit's sync run, failing since 18-Nov-2026 (kit-reliability)")
ok(QUEUE.read_text().count("seen again") == 1, "seen again once a day, not stacked")
reset()
rc, out = todo("Draft the agenda for the platform review", env=dict(ENV, KIT_TODO_MERGE="1"))
ok(rc == 0 and count("Draft the agenda") == 2 and "seen again" not in QUEUE.read_text(),
   "a Kit item doesn't match the owner's section", out)
rc, out = todo("kit", "draft agenda for the platform review", env=dict(ENV, KIT_TODO_MERGE="1"))
ok(rc == 0 and count("seen again") == 1 and "Already on the list for Kit" in out, "KIT_TODO_MERGE=1 merges too", out)
reset()
rc, out = todo("Call the dentist about the crown", env=dict(ENV, QUEUE_DUP_THRESHOLD="off"))
ok(rc == 0 and count("Call the dentist") == 2, "QUEUE_DUP_THRESHOLD=off turns the check off", out)
before = QUEUE.read_text()
rc, out = todo("dupes")
ok(rc == 0 and "1 likely duplicate pair" in out and "Call the dentist" in out, "todo dupes lists the pair", out)
ok(before == QUEUE.read_text(), "todo dupes changes nothing")
reset()
rc, out = todo("dupes")
ok(rc == 0 and "No likely duplicates" in out, "todo dupes with none", out)

# ---- the phone sync ------------------------------------------------------------------------------------------------
import kit_sync_core as sc  # noqa: E402


class Backend:
    def __init__(self, inbox):
        self.inbox = inbox

    def pull_open(self, _name):
        out, self.inbox = self.inbox, []
        return out

    def mirror(self, _want, _name):
        return []


reset()
tmod = sc.load_todo(KIT)
changed = sc.reconcile(tmod, Backend([{"name": "call dentist about the crown"}, {"name": "Pick up the dry cleaning"}]),
                       "Alex", "Kit Inbox", "Kit: Alex", inbox=None)
q = QUEUE.read_text()
ok(q.lower().count("dentist") == 1 and "seen again" in q and "from phone" in q
   and any("already on the list" in c for c in changed), "a phone duplicate is noted, not added", (changed, q))
ok("Pick up the dry cleaning" in q, "a new phone item is still added", changed)

# ---- the scheduled runs' queue items -------------------------------------------------------------------------------
sys.path.insert(0, str(SHARED / "morning"))
import connector_health as ch  # noqa: E402

reset()
title = "Fix Kit's sync run, failing since 18-Nov-2026 (kit-reliability)"
r = ch.queue_add(str(KIT), str(TODO), title, "failed 2 times", TODAY, detail="18-Nov-2026: sync run failed twice.",
                 who="run_alerts")
q = QUEUE.read_text()
ok(r is True and "18-Nov-2026 (kit-reliability)" not in q and "seen again" in q
   and "18-Nov-2026: sync run failed twice." in q, "run_alerts' new outage goes on the open item", q)
ok(ch.queue_note(str(KIT), title, "Recovered 19-Nov-2026: fine again.", TODAY) and "Recovered 19-Nov-2026" in
   QUEUE.read_text(), "and its recovery note finds that item too")
r = ch.queue_add(str(KIT), str(TODO), "Fix the jira connector, failing since 18-Nov-2026", "x", TODAY)
ok(r is True and "Fix the jira connector" in QUEUE.read_text(), "an unrelated alert is still added")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nqueue duplicate tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
