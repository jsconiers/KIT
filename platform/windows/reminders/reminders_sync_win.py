# UNTESTED on Windows — validate on a real Windows box with Outlook installed.
"""Sync Kit's to-do list with Outlook Tasks on Windows, so the list lives on your phone too
(via Microsoft To Do, which mirrors Outlook Tasks).

  python reminders_sync_win.py

The Windows counterpart of `shared/reminders_sync.py`. Both call the same sync in
`shared/kit_sync_core.py`; this file only supplies the device layer (Outlook Tasks over COM, see
outlook_tasks_backend.py).

- "Kit Inbox": anything you add to that Tasks folder (by hand, or via Microsoft To Do on your
  phone) becomes one of your to-dos at the next sync. Start the title with "Kit:" to give it to
  Kit instead (also listed in briefs/requests.md), "ask:" for a question for Kit (requests only),
  or "approve <code> ..." to approve a work list or queue hygiene verdicts with the day's code
  (low-tier actions only; see shared/kit_inbox.py).
- "Kit: <your name>": your open to-dos, with a reminder at 09:00 on each due date. Complete one
  in Outlook / To Do and it is checked off in QUEUE.md.

Work and personal to-dos: Windows has only the Outlook backend, so TODOS_PERSONAL and TODOS_WORK
both resolve to Outlook and every item syncs through the one pair of folders, as on a Mac where
both sides use the same app.

A Task Scheduler job runs this every 15 minutes (see register-tasks.ps1). The first run creates
the two Tasks subfolders if they do not exist.
"""
import os
import pathlib
import re
import sys

HOME = pathlib.Path.home()                 # %USERPROFILE% on Windows
KIT = HOME / "Claude/Agents/kit"
LOG = KIT / ".install/logs/sync.log"
INBOX = "Kit Inbox"

# The shared sync lives in <package>/shared; this file is <package>/platform/windows/reminders/.
# Fall back to the installed copy if the layout differs.
_HERE = pathlib.Path(os.path.abspath(__file__)).parent
for _shared in (_HERE.parents[2] / "shared", KIT / ".install/shared"):
    if (_shared / "kit_sync_core.py").exists():
        sys.path.insert(0, str(_shared))
        break
import kit_sync_core as core  # noqa: E402
from kit_sync_core import kit_inbox  # noqa: E402

todo = core.load_todo(KIT)

# Import the sibling backend regardless of the current working directory (Task Scheduler does
# not set a predictable cwd).
sys.path.insert(0, str(_HERE))


def log(msg):
    core.log(LOG, msg)


def reconcile(todo_mod, backend, me, inbox_name, mirror_name):
    """Kept for callers of the old signature: the shared sync, every item, this install's kit_inbox."""
    return core.reconcile(todo_mod, backend, me, inbox_name, mirror_name, None, inbox=kit_inbox)


def check_backend_setting():
    """REMINDERS_BACKEND, TODOS_PERSONAL, and TODOS_WORK may name apple; Windows only has outlook."""
    cfg = KIT / ".install/shared/morning/config"
    if cfg.exists():
        text = cfg.read_text()
        for key in ("REMINDERS_BACKEND", "TODOS_PERSONAL", "TODOS_WORK"):
            m = re.search(rf"^{key}=[\"']?(\w+)", text, re.M)
            if m and m.group(1).lower() != "outlook":
                log(f"{key}={m.group(1)} isn't available on Windows; using outlook")


def main(backend=None):
    me = todo.owner()
    check_backend_setting()
    if backend is None:
        from outlook_tasks_backend import OutlookTasksBackend
        backend = OutlookTasksBackend()
    changed = reconcile(todo, backend, me, INBOX, f"Kit: {me}")
    if changed:
        log("; ".join(changed))
    core.mark_ok(LOG)
    print("\n".join(changed) or "in sync")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # noqa: BLE001
        log(f"sync failed: {ex}")
        print(f"sync failed: {ex}", file=sys.stderr)
        sys.exit(1)
