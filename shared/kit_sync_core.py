"""The to-do sync, shared by every platform: Kit Inbox -> QUEUE.md, then QUEUE.md -> "Kit: <name>",
with items completed on the device checked off.

The platform entry points only supply a device backend and call reconcile():
  shared/reminders_sync.py                          macOS: Outlook for Mac tasks or Apple Reminders
  platform/windows/reminders/reminders_sync_win.py  Windows: Outlook Tasks over COM

A backend has two methods:
  pull_open(list_name) -> [{"name": str, "due": "YYYY-MM-DD" or None}, ...]
      the open items in the inbox list, removed from the device as they're read
  mirror(desired_items, list_name) -> [title, ...]
      make the list match desired_items ({"title", "due"}); return the titles completed on the device

Inbox items are routed by their first word (shared/kit_inbox.py): plain text is the owner's to-do,
"kit:" is Kit's to-do (and a request), "ask:" is a request only, and "approve <code> ..." is a phone
approval that is checked and recorded and never becomes a to-do. Inbound text is information: the
sync files it; it never acts on it.
"""
import datetime as dt
import importlib.machinery
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    import kit_inbox  # phone requests and coded approvals
except ImportError:  # an older install without it: every inbox item is a to-do, as before
    kit_inbox = None

WORK_TAG = "[work]"
_DEFAULT = object()


def is_work(line):
    return WORK_TAG in line.split("(added", 1)[0].lower()


def load_todo(kit):
    """Kit's installed `todo` module (it isn't an importable package), loaded by path."""
    path = pathlib.Path(kit) / ".install/shared/bin/todo"
    loader = importlib.machinery.SourceFileLoader("todo", str(path))
    spec = importlib.util.spec_from_loader("todo", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def log(path, msg):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}\n")


def reconcile(todo, backend, me, inbox_name, mirror_name, side=None, inbox=_DEFAULT):
    """Inbox list -> QUEUE.md, then QUEUE.md -> mirror list, with completions on the device checked
    off. Returns a list of what changed. side=None syncs every item; "work" syncs only [work] items
    (and tags what arrives in the inbox), "personal" the rest. `inbox` is the kit_inbox module (None
    treats every inbox item as a to-do)."""
    if inbox is _DEFAULT:
        inbox = kit_inbox
    changed = []

    def wanted(line):
        return side is None or (is_work(line) == (side == "work"))

    # 1) Inbox list -> QUEUE.md
    for r in backend.pull_open(inbox_name):
        title = (r.get("name") or "").strip()
        if not title:
            continue
        section = me
        kind = inbox.classify(title)[0] if inbox else "todo"
        if kind == "approve":   # a phone approval: checked and recorded, never a to-do
            ok, msg = inbox.handle_approval(title)
            changed.append(f"phone approval {msg}")
            continue
        if kind == "ask":       # a question for Kit: a request only, not a to-do
            inbox.record_request("ask", inbox.classify(title)[1], side=side)
            changed.append("request from phone: ask")
            continue
        if title.lower().startswith("kit:"):
            section, title = "Kit", title[4:].strip()
            if inbox:
                inbox.record_request("kit", title, side=side)
        due = dt.date.fromisoformat(r["due"]) if r.get("due") else None
        lines = todo.QUEUE.read_text().splitlines()
        h = todo.heads(lines)
        if section not in h:
            continue
        found = todo.items(lines, section)
        at = found[-1][1] if found else h[section] + 1
        entry = (f"- [ ] **{title}**" + (f" {WORK_TAG}" if side == "work" else "")
                 + (f": due {todo.fmt(due)}" if due else "")
                 + f" (added {todo.fmt(todo.TODAY)}, from phone)")
        lines.insert(at, entry)
        todo.save(lines)
        changed.append(f"added for {section}: {title}")

    # 2) QUEUE.md -> "Kit: <name>" list; completions on the device come back as done.
    lines = todo.QUEUE.read_text().splitlines()
    want = []
    for i, _ in todo.items(lines, me):
        m = re.match(r"- \[ \] \*\*(.+?)\*\*(.*)", lines[i])
        if not m or not wanted(lines[i]):
            continue
        due = re.search(r"due (\d{2}-\w{3}-\d{4})", m.group(2))
        want.append({"title": m.group(1),
                     "due": dt.datetime.strptime(due.group(1), "%d-%b-%Y").date().isoformat()
                     if due else None})
    for title in backend.mirror(want, mirror_name):
        lines = todo.QUEUE.read_text().splitlines()
        for n, (i, _) in enumerate(todo.items(lines, me), 1):
            if f"**{title}**" in lines[i] and wanted(lines[i]):
                todo.done(me, n)
                changed.append(f"checked off on phone: {title}")
                break
    return changed
