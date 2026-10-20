#!/usr/bin/env python3
"""Tests for the shared to-do sync (shared/kit_sync_core.py) and its two entry points.

1. Regression: the frozen pre-refactor reconcile() (tests/fixtures/legacy_reconcile.py) and the new
   core produce identical QUEUE.md, mirrored items, change lists, and request/approval files on the
   same fixtures, for side None, "work", and "personal", with and without kit_inbox.
2. Routing: plain, "kit:", "ask:", "approve <code>" (valid, wrong, reused), empty titles, due dates,
   completions (including a duplicated title), and the work/personal split.
3. The macOS entry (shared/reminders_sync.py) and the Windows entry
   (platform/windows/reminders/reminders_sync_win.py) both reach the core; the Windows one runs
   through the real OutlookTasksBackend over a fake COM layer (no pywin32 needed).
Everything runs in a throwaway Kit; nothing real is touched.
"""
import datetime as dt
import importlib.util
import os
import pathlib
import re
import shutil
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SHARED = REPO / "shared"
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


QUEUE0 = ("# Queue\n\n## Alex\n\n- [ ] **Existing work item** [work] (added 01-Oct-2026)\n"
          "- [ ] **Personal errand**: due 25-Oct-2026 (added 01-Oct-2026)\n"
          "- [ ] **Duplicate title** (added 01-Oct-2026)\n- [ ] **Duplicate title** (added 02-Oct-2026)\n"
          "- [ ] **Work report** [work]: due 30-Oct-2026 (added 03-Oct-2026)\n\n"
          "## Kit\n\n- [ ] **Kit thing** (added 01-Oct-2026)\n\n"
          "## Waiting on others\n\n- [ ] **Ticket** (added 01-Oct-2026)\n\n## Done\n")


class Fake:
    """A device backend: pull_open hands back the inbox items once; mirror records what it was
    asked for and returns the titles 'completed on the device'."""

    def __init__(self, inbox, completed=()):
        self.inbox = list(inbox)
        self.completed = list(completed)
        self.mirrored = None

    def pull_open(self, name):
        out, self.inbox = self.inbox, []
        return out

    def mirror(self, want, name):
        self.mirrored = list(want)
        return list(self.completed)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(text):
    # Each run issues its own random approval code, and request and approval files carry the
    # minute they were written; neither is behaviour, so both are masked before comparing.
    text = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", "<time>", text)
    text = re.sub(r"\d{2}-\w{3}-\d{4} \d{2}:\d{2}", "<time>", text)
    text = re.sub(r"(approve )(?!ZZZZZZ)[A-Z0-9]{6}\b", r"\1<code>", text)
    return text


def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    home = tmp / "home"
    kit = home / "Claude/Agents/kit"
    (kit / "briefs").mkdir(parents=True)
    (kit / ".install/shared/bin").mkdir(parents=True)
    shutil.copy(SHARED / "bin/todo", kit / ".install/shared/bin/todo")
    shutil.copy(SHARED / "kit_queue.py", kit / ".install/shared/kit_queue.py")
    (kit / ".install/shared/morning").mkdir(parents=True)
    (kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\nREMINDERS_BACKEND="outlook"\n')
    os.environ["KIT_DIR"] = str(kit)
    os.environ["HOME"] = str(home)
    sys.path.insert(0, str(SHARED))
    sys.path.insert(0, str(HERE / "fixtures"))
    import kit_inbox as ki
    import kit_sync_core as core
    import legacy_reconcile as legacy
    todo = core.load_todo(kit)
    queue = kit / "QUEUE.md"

    def reset():
        queue.write_text(QUEUE0)
        for f in ("requests.md", "phone-approvals.md"):
            (kit / "briefs" / f).unlink(missing_ok=True)
        (kit / ".install/cache/phone-codes.json").unlink(missing_ok=True)

    def snapshot(changed, fake):
        files = {f: norm((kit / "briefs" / f).read_text()) if (kit / "briefs" / f).exists() else None
                 for f in ("requests.md", "phone-approvals.md")}
        return {"queue": norm(queue.read_text()), "mirrored": norm(repr(fake.mirrored)),
                "changed": norm(repr(changed)), **files}

    def inbox_items(code):
        return [{"name": "Pick up badge", "due": None},
                {"name": "kit: draft the agenda", "due": "2026-10-28"},
                {"name": "ask: what's due Friday?", "due": None},
                {"name": f"approve {code} 1,3", "due": None},
                {"name": "approve ZZZZZZ all", "due": None},
                {"name": "   ", "due": None},
                {"name": "Renew passport", "due": "2026-11-02"}]

    # ---- 1. regression: legacy vs core, same inputs, same outputs
    scenarios = [("all items", None, ki, ["Personal errand", "Duplicate title"]),
                 ("work side", "work", ki, ["Work report", "Personal errand"]),
                 ("personal side", "personal", ki, ["Personal errand", "Work report"]),
                 ("no kit_inbox (older install)", None, None, ["Duplicate title"])]
    for label, side, inbox, completed in scenarios:
        reset()
        code = ki.issue_code("worklist")
        f_old = Fake(inbox_items(code), completed)
        c_old = legacy.reconcile(todo, inbox, f_old, "Alex", "Kit Inbox", "Kit: Alex", side)
        old = snapshot(c_old, f_old)
        reset()
        code = ki.issue_code("worklist")
        f_new = Fake(inbox_items(code), completed)
        c_new = core.reconcile(todo, f_new, "Alex", "Kit Inbox", "Kit: Alex", side, inbox=inbox)
        new = snapshot(c_new, f_new)
        for key in old:
            ok(old[key] == new[key], f"regression ({label}): {key} identical",
               f"\nold={old[key]!r}\nnew={new[key]!r}")
        # the run also behaves as intended, not just identically
        if label == "all items":
            q = new["queue"]
            ok("**Pick up badge**" in q and "**Renew passport**: due 02-Nov-2026" in q,
               "routing: plain items become the owner's to-dos, with due dates")
            ok("**draft the agenda**: due 28-Oct-2026" in q.split("## Kit", 1)[1],
               "routing: kit: becomes Kit's to-do")
            ok("Friday" not in q and "approve" not in q.lower(), "routing: ask: and approve never become to-dos")
            ok("ask: what's due Friday?" in (new["requests.md"] or "")
               and "kit: draft the agenda" in (new["requests.md"] or ""), "routing: requests recorded")
            appr = new["phone-approvals.md"] or ""
            ok("accepted" in appr and "not recognised" in appr, "routing: right code accepted, wrong code refused")
            ok(sum(1 for c in c_new if c.startswith("checked off on phone: Duplicate title")) == 1
               and q.count("**Duplicate title**") >= 1, "completion of a duplicated title checks off one item")
            ok([w["title"] for w in f_new.mirrored].count("Existing work item") == 1,
               "mirror: every open owner item sent once")
        if label == "work side":
            # open [work] items when it mirrored: the two in the fixture plus the inbox arrivals,
            # which the work side tags [work]
            got = sorted(w["title"] for w in f_new.mirrored)
            ok(got == sorted(["Existing work item", "Work report", "Pick up badge", "Renew passport"]),
               "work side mirrors only [work] items", str(got))
            ok("**Pick up badge** [work]" in new["queue"], "work side tags what arrives in its inbox")
            ok("checked off on phone: Personal errand" not in c_new, "work side never checks off a personal item")
        if label == "personal side":
            ok(not any("Work" in w["title"] for w in f_new.mirrored), "personal side leaves work items out")
        if label == "no kit_inbox (older install)":
            ok("**ask: what's due Friday?**" in new["queue"], "without kit_inbox every inbox item is a to-do")

    # ---- reused code is refused the second time
    reset()
    code = ki.issue_code("worklist")
    core.reconcile(todo, Fake([{"name": f"approve {code} 1", "due": None}]), "Alex", "Kit Inbox", "Kit: Alex")
    c2 = core.reconcile(todo, Fake([{"name": f"approve {code} 2", "due": None}]), "Alex", "Kit Inbox", "Kit: Alex")
    ok(any("already used" in c for c in c2), "a code works once", str(c2))

    # ---- 2. macOS entry point delegates to the core
    reset()
    rs = load("reminders_sync", SHARED / "reminders_sync.py")
    ok(rs.reconcile.__module__ == "reminders_sync" and "core.reconcile" in (SHARED / "reminders_sync.py").read_text(),
       "macOS entry calls the shared core")
    ok(not hasattr(rs, "JS_INBOX") or "def reconcile" in (SHARED / "reminders_sync.py").read_text(),
       "macOS entry keeps its device layer")
    f = Fake([{"name": "kit: from mac", "due": None}])
    rs.reconcile(f, "Alex", "Kit Inbox", "Kit: Alex")
    ok("**from mac**" in queue.read_text(), "macOS entry syncs through the core")
    src = (SHARED / "reminders_sync.py").read_text()
    ok("todo.QUEUE.read_text()" not in src, "macOS entry no longer carries its own copy of the sync")

    # ---- 3. Windows entry: the real OutlookTasksBackend over a fake COM layer
    class Item:
        def __init__(self, folder, subject="", due=None, complete=False):
            self.folder, self.Subject, self.Complete = folder, subject, complete
            self.DueDate = due if due else dt.datetime(4501, 1, 1)
            self.Categories, self.ReminderSet, self.ReminderTime = "", False, None

        def Save(self):
            if self not in self.folder.items:
                self.folder.items.append(self)

        def Delete(self):
            self.folder.items.remove(self)

    class Coll:
        def __init__(self, seq, add=None):
            self.seq, self._add = seq, add

        @property
        def Count(self):
            return len(self.seq)

        def Item(self, i):  # COM collections are 1-indexed
            return self.seq[i - 1]

        def Add(self, arg):
            return self._add(arg)

    class Folder:
        def __init__(self, name):
            self.Name, self.items, self.children = name, [], []

        @property
        def Items(self):
            return Coll(self.items, lambda _type: Item(self))

        @property
        def Folders(self):
            def add(name):
                f = Folder(name)
                self.children.append(f)
                return f
            return Coll(self.children, add)

    tasks = Folder("Tasks")
    inbox_f = tasks.Folders.Add("Kit Inbox")
    Item(inbox_f, "ask: status of the POC?").Save()
    Item(inbox_f, "kit: tidy the register").Save()
    Item(inbox_f, "Call the vendor", dt.datetime(2026, 10, 27, 0, 0)).Save()
    mirror_f = tasks.Folders.Add("Kit: Alex")
    Item(mirror_f, "Existing work item", complete=True).Save()   # completed in Outlook
    Item(mirror_f, "Stale item").Save()                          # no longer wanted

    ns = types.SimpleNamespace(GetDefaultFolder=lambda n: tasks)
    app = types.SimpleNamespace(GetNamespace=lambda n: ns)
    win32com = types.ModuleType("win32com")
    client = types.ModuleType("win32com.client")
    client.Dispatch = lambda name: app
    win32com.client = client
    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    sys.modules.update({"win32com": win32com, "win32com.client": client, "pythoncom": pythoncom})

    reset()
    win_dir = REPO / "platform/windows/reminders"
    win = load("reminders_sync_win", win_dir / "reminders_sync_win.py")
    sys.path.insert(0, str(win_dir))
    backend_mod = load("outlook_tasks_backend", win_dir / "outlook_tasks_backend.py")
    win.main(backend=backend_mod.OutlookTasksBackend())
    q = queue.read_text()
    ok("**Call the vendor**: due 27-Oct-2026" in q, "Windows: plain inbox item becomes a to-do with its due date")
    ok("**tidy the register**" in q.split("## Kit", 1)[1], "Windows: kit: becomes Kit's to-do (new on Windows)")
    ok("status of the POC" not in q and "ask: status of the POC?" in (kit / "briefs/requests.md").read_text(),
       "Windows: ask: is a request only (new on Windows)")
    ok(all(i.Complete for i in inbox_f.items), "Windows: inbox items are marked complete once pulled")
    ok("- [x] **Existing work item**" in q or "**Existing work item**" in q.split("## Done", 1)[1],
       "Windows: an item completed in Outlook is checked off in QUEUE.md")
    subjects = [i.Subject for i in mirror_f.items]
    ok("Stale item" not in subjects and "Call the vendor" in subjects and "Personal errand" in subjects,
       "Windows: the mirror folder matches the open to-dos", str(subjects))
    new_item = next(i for i in mirror_f.items if i.Subject == "Personal errand")
    ok(new_item.Categories == "Kit" and new_item.DueDate.date() == dt.date(2026, 10, 25)
       and new_item.ReminderSet, "Windows: new items get the Kit category, due date, and reminder")
    code = ki.issue_code("worklist")
    Item(inbox_f, f"approve {code} all").Save()
    win.main(backend=backend_mod.OutlookTasksBackend())
    ok("accepted" in (kit / "briefs/phone-approvals.md").read_text() and "approve" not in queue.read_text().lower(),
       "Windows: approve <code> is checked and recorded, never a to-do (new on Windows)")
    ok("todo.QUEUE.read_text()" not in (win_dir / "reminders_sync_win.py").read_text(),
       "Windows entry no longer carries its own copy of the sync")

    shutil.rmtree(tmp)
    print(f"\nsync core tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
