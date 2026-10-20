"""Frozen copy of shared/reminders_sync.py's reconcile() as it was before the sync core was extracted
(Kit 1.4.0, a79efd8). tests/test_sync_core.py runs it and the new kit_sync_core.reconcile() on the
same fixtures and checks QUEUE.md, the mirrored items, the change list, and the request files come
out identical. Don't edit it; it is the reference for "macOS behaviour unchanged"."""
import datetime as dt
import re

WORK_TAG = "[work]"


def is_work(line):
    return WORK_TAG in line.split("(added", 1)[0].lower()


def reconcile(todo, kit_inbox, backend, me, inbox_name, mirror_name, side=None):
    """OS-independent reconciliation: inbox list -> QUEUE.md, then QUEUE.md -> mirror list, with
    completions on the device checked off. Returns a list of what changed. side=None syncs every
    item; "work" syncs only [work] items (and tags what arrives in the inbox), "personal" the rest."""
    changed = []

    def wanted(line):
        return side is None or (is_work(line) == (side == "work"))

    # 1) Inbox list -> QUEUE.md
    for r in backend.pull_open(inbox_name):
        title = (r.get("name") or "").strip()
        if not title:
            continue
        section = me
        kind = kit_inbox.classify(title)[0] if kit_inbox else "todo"
        if kind == "approve":   # a phone approval: checked and recorded, never a to-do
            ok, msg = kit_inbox.handle_approval(title)
            changed.append(f"phone approval {msg}")
            continue
        if kind == "ask":       # a question for Kit: a request only, not a to-do
            kit_inbox.record_request("ask", kit_inbox.classify(title)[1], side=side)
            changed.append("request from phone: ask")
            continue
        if title.lower().startswith("kit:"):
            section, title = "Kit", title[4:].strip()
            if kit_inbox:
                kit_inbox.record_request("kit", title, side=side)
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
