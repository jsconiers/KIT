# UNTESTED on Windows — validate on a real Windows box with Outlook installed.
"""Sync Kit's to-do list with Outlook Tasks on Windows, so the list lives on your phone too
(via Microsoft To Do, which mirrors Outlook Tasks).

  python reminders_sync_win.py

This is the Windows counterpart of `shared/reminders_sync.py`. It reuses the exact same
`todo` QUEUE.md parser/editor and the same two-list model, and swaps only the device layer:
Apple Reminders (JXA) -> Outlook Tasks (COM, see outlook_tasks_backend.py).

- "Kit Inbox": anything you add to that Tasks folder (by hand, or via Microsoft To Do on your
  phone) becomes one of your to-dos at the next sync. Start the title with "Kit:" to give it
  to Kit instead.
- "Kit: <your name>": your open to-dos, with a reminder at 09:00 on each due date. Complete one
  in Outlook / To Do and it is checked off in QUEUE.md.

A Task Scheduler job runs this every 15 minutes (the scheduling piece is built separately;
see README.md). The first run creates the two Tasks subfolders if they do not exist.

----------------------------------------------------------------------------------------------
NOTE ON CODE REUSE: ideally the reconciliation below lives once in `shared/reminders_sync.py`
and is called by both the macOS and Windows entry points. That refactor touches the (here-
untestable) macOS path, so it is deliberately NOT done yet. `reconcile()` below is a faithful
re-implementation of `main()` in `shared/reminders_sync.py`, written against a backend object
so that it can be lifted into `shared/` verbatim later. See README / the task summary for the
exact seam.
----------------------------------------------------------------------------------------------
"""
import datetime as dt
import importlib.machinery
import importlib.util
import os
import pathlib
import re
import sys

HOME = pathlib.Path.home()                 # %USERPROFILE% on Windows
KIT = HOME / "Claude/Agents/kit"
LOG = KIT / ".install/logs/sync.log"
INBOX = "Kit Inbox"

# Reuse the shared `todo` module exactly as the macOS script does: load the installed copy by
# path (it is not an importable package).
loader = importlib.machinery.SourceFileLoader("todo", str(KIT / ".install/shared/bin/todo"))
spec = importlib.util.spec_from_loader("todo", loader)
todo = importlib.util.module_from_spec(spec)
loader.exec_module(todo)

# Import the sibling backend regardless of the current working directory (Task Scheduler does
# not set a predictable cwd).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outlook_tasks_backend import OutlookTasksBackend  # noqa: E402


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}\n")


def reconcile(todo, backend, me, inbox_name, mirror_name):
    """OS-independent reconciliation. `backend` must expose pull_open(list) and
    mirror(desired_items, list) with the semantics documented in outlook_tasks_backend.py.
    This mirrors `main()` in shared/reminders_sync.py line for line."""
    changed = []

    # 1) Inbox list -> QUEUE.md
    for r in backend.pull_open(inbox_name):
        title = (r.get("name") or "").strip()
        if not title:
            continue
        section = me
        if title.lower().startswith("kit:"):
            section, title = "Kit", title[4:].strip()
        due = dt.date.fromisoformat(r["due"]) if r.get("due") else None
        lines = todo.QUEUE.read_text().splitlines()
        h = todo.heads(lines)
        if section not in h:
            continue
        found = todo.items(lines, section)
        at = found[-1][1] if found else h[section] + 1
        entry = (f"- [ ] **{title}**" + (f": due {todo.fmt(due)}" if due else "")
                 + f" (added {todo.fmt(todo.TODAY)}, from phone)")
        lines.insert(at, entry)
        todo.save(lines)
        changed.append(f"added for {section}: {title}")

    # 2) QUEUE.md -> "Kit: <name>" list; completions in Outlook come back as done.
    lines = todo.QUEUE.read_text().splitlines()
    want = []
    for i, _ in todo.items(lines, me):
        m = re.match(r"- \[ \] \*\*(.+?)\*\*(.*)", lines[i])
        if not m:
            continue
        due = re.search(r"due (\d{2}-\w{3}-\d{4})", m.group(2))
        want.append({"title": m.group(1),
                     "due": dt.datetime.strptime(due.group(1), "%d-%b-%Y").date().isoformat()
                     if due else None})
    for title in backend.mirror(want, mirror_name):
        lines = todo.QUEUE.read_text().splitlines()
        for n, (i, _) in enumerate(todo.items(lines, me), 1):
            if f"**{title}**" in lines[i]:
                todo.done(me, n)
                changed.append(f"checked off on phone: {title}")
                break

    return changed


def main():
    me = todo.owner()
    backend = OutlookTasksBackend()
    changed = reconcile(todo, backend, me, INBOX, f"Kit: {me}")
    if changed:
        log("; ".join(changed))
    print("\n".join(changed) or "in sync")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # noqa: BLE001
        log(f"sync failed: {ex}")
        print(f"sync failed: {ex}", file=sys.stderr)
        sys.exit(1)
