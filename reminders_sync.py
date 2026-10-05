#!/usr/bin/env python3
"""Sync Kit's to-do list with Apple Reminders, so the list lives on your phone too.

  python3 ~/Claude/Agents/kit/.install/reminders_sync.py

- "Kit Inbox": anything you add there (by hand or "Hey Siri, add ... to Kit Inbox") becomes one
  of your to-dos at the next sync. Start it with "Kit:" to give it to Kit instead.
- "Kit: <your name>": your open to-dos, with alerts at 9:00 on their due dates. Check one off on
  your phone and it's checked off in QUEUE.md.
A launchd job runs this every 15 minutes. The first run asks for permission to use Reminders.
"""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
KIT = HOME / "Claude/Agents/kit"
LOG = KIT / ".install/morning/logs/sync.log"
INBOX = "Kit Inbox"

loader = importlib.machinery.SourceFileLoader("todo", str(KIT / ".install/bin/todo"))
spec = importlib.util.spec_from_loader("todo", loader)
todo = importlib.util.module_from_spec(spec)
loader.exec_module(todo)

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
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}\n")


def main():
    me = todo.owner()
    changed = []

    # 1) Phone inbox -> QUEUE.md
    for r in jxa(JS_INBOX, INBOX):
        title = r["name"].strip()
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

    # 2) QUEUE.md -> "Kit: <name>" list; completions on the phone come back as done.
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
    for title in jxa(JS_MIRROR, json.dumps(want), f"Kit: {me}"):
        lines = todo.QUEUE.read_text().splitlines()
        for n, (i, _) in enumerate(todo.items(lines, me), 1):
            if f"**{title}**" in lines[i]:
                todo.done(me, n)
                changed.append(f"checked off on phone: {title}")
                break

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
