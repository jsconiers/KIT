#!/usr/bin/env python3
"""Sync Kit's to-do list (QUEUE.md) with Outlook Tasks or Apple Reminders on macOS.

  python3 ~/Claude/Agents/kit/.install/shared/reminders_sync.py

REMINDERS_BACKEND in .install/shared/morning/config picks the device:
  outlook  (default) classic Outlook for Mac tasks, via platform/mac/reminders/
           outlook_tasks_backend.py. Stays inside Microsoft 365 and reaches your phone through
           Microsoft To Do. Outlook must be running; the sync never launches it.
  apple    Apple Reminders (the JXA below). Syncs through iCloud, so keep work items out of it.
Windows has its own entry point, platform/windows/reminders/reminders_sync_win.py (Outlook only);
both call the same sync in shared/kit_sync_core.py.

Work and personal to-dos can live in different apps: TODOS_PERSONAL and TODOS_WORK (set with
`kit-settings todos personal|work ...`) override REMINDERS_BACKEND for each side. Work to-dos are
the ones tagged [work] after the title (`todo work ...` adds one). When the two sides use
different apps, each app gets its own "Kit Inbox" and "Kit: <your name>" lists; what you add to the
work app's inbox comes in tagged [work].

- "Kit Inbox": anything you add there becomes one of your to-dos at the next sync. Start it with
  "Kit:" to give it to Kit instead (it's also listed in briefs/requests.md), "ask:" for a question
  for Kit (requests only, not a to-do), or "approve <code> ..." to approve a work list or queue
  hygiene verdicts with the day's code (see shared/kit_inbox.py; low-tier actions only).
- "Kit: <your name>": your open to-dos, with alerts at 9:00 on their due dates. Check one off on
  your phone or in Outlook and it's checked off in QUEUE.md.
A launchd job runs this every 15 minutes. The first run asks for Automation permission.
"""
import importlib.machinery
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
KIT = HOME / "Claude/Agents/kit"
LOG = KIT / ".install/logs/sync.log"
CONFIG = KIT / ".install/shared/morning/config"
MAC_REMINDERS = pathlib.Path(__file__).resolve().parent.parent / "platform/mac/reminders"
INBOX = "Kit Inbox"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kit_sync_core as core  # noqa: E402  the sync itself, shared with Windows
from kit_sync_core import WORK_TAG, is_work, kit_inbox  # noqa: E402,F401  (kept for callers)

todo = core.load_todo(KIT)

JS_COMMON = r"""
function ensure(app, name) {
  var l = app.lists.byName(name);
  try { l.name(); return l; } catch (e) {}
  app.lists.push(app.List({name: name}));
  return app.lists.byName(name);
}
function ymd(d) {
  function p(n) { return (n < 10 ? "0" : "") + n; }
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}
"""

JS_INBOX = JS_COMMON + r"""
function run(argv) {
  var app = Application("Reminders");
  var list = ensure(app, argv[0]);
  var out = [];
  list.reminders.whose({completed: false})().forEach(function (r) {
    var d = r.dueDate();
    out.push({name: r.name(), due: d ? ymd(d) : null});
    r.completed = true;
  });
  return JSON.stringify(out);
}
"""

JS_MIRROR = JS_COMMON + r"""
function run(argv) {
  var want = JSON.parse(argv[0]);
  var app = Application("Reminders");
  var list = ensure(app, argv[1]);
  var done = [], have = {};
  list.reminders().forEach(function (r) {
    var n = r.name();
    if (r.completed()) { done.push(n); app.delete(r); } else { have[n] = r; }
  });
  var keep = {};
  want.forEach(function (w) {
    keep[w.title] = true;
    var due = w.due ? new Date(w.due + "T09:00:00") : null;
    var r = have[w.title];
    if (r) {
      var cur = r.dueDate();
      if (due && (!cur || cur.getTime() !== due.getTime())) { r.dueDate = due; }
    } else {
      var props = {name: w.title};
      if (due) { props.dueDate = due; }
      list.reminders.push(app.Reminder(props));
    }
  });
  Object.keys(have).forEach(function (n) { if (!keep[n]) { app.delete(have[n]); } });
  return JSON.stringify(done);
}
"""


def jxa(script, *args):
    r = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-", *args],
                       input=script, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return json.loads(r.stdout.strip() or "[]")


def log(msg):
    core.log(LOG, msg)


class AppleRemindersBackend:
    """Apple Reminders through JXA: the same pull_open / mirror operations as the Outlook
    backends (platform/mac/reminders, platform/windows/reminders)."""

    def pull_open(self, list_name):
        return jxa(JS_INBOX, list_name)

    def mirror(self, desired_items, list_name):
        return jxa(JS_MIRROR, json.dumps(desired_items), list_name)


def setting(key):
    if CONFIG.exists():
        m = re.search(rf"^{key}=[\"']?(\w+)", CONFIG.read_text(), re.M)
        if m:
            return m.group(1).lower()
    return None


def backend_name():
    return setting("REMINDERS_BACKEND") or "outlook"


def backend_names():
    """(personal, work) to-do apps."""
    base = backend_name()
    return setting("TODOS_PERSONAL") or base, setting("TODOS_WORK") or base


def make_backend(name):
    if name == "apple":
        return AppleRemindersBackend()
    if name != "outlook":
        raise RuntimeError(f"unknown REMINDERS_BACKEND {name!r} (use outlook or apple)")
    path = MAC_REMINDERS / "outlook_tasks_backend.py"
    loader = importlib.machinery.SourceFileLoader("outlook_tasks_backend", str(path))
    spec = importlib.util.spec_from_loader("outlook_tasks_backend", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.OutlookTasksMacBackend()


def reconcile(backend, me, inbox_name, mirror_name, side=None):
    """The shared sync (shared/kit_sync_core.py) with this install's todo module and kit_inbox."""
    return core.reconcile(todo, backend, me, inbox_name, mirror_name, side, inbox=kit_inbox)


def main():
    me = todo.owner()
    personal, work = backend_names()
    if personal == work:
        plan = [(personal, None)]
    else:
        plan = [(personal, "personal"), (work, "work")]
    changed, failed = [], []
    for name, side in plan:
        try:   # one app being unavailable (Outlook closed, say) must not stop the other
            got = reconcile(make_backend(name), me, INBOX, f"Kit: {me}", side)
            changed += [f"{side}: {c}" if side else c for c in got]
        except Exception as ex:  # noqa: BLE001
            failed.append(f"{side or 'sync'} ({name}): {ex}")
    if changed:
        log("; ".join(changed))
    for f in failed:
        log(f"sync failed: {f}")
    print("\n".join(changed) or "in sync")
    if not failed:
        core.mark_ok(LOG)
    if failed:
        print("\n".join("sync failed: " + f for f in failed), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # noqa: BLE001
        log(f"sync failed: {ex}")
        print(f"sync failed: {ex}", file=sys.stderr)
        sys.exit(1)
