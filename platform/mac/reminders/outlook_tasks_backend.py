#!/usr/bin/env python3
"""Device layer for Kit's to-do sync on macOS, backed by classic Outlook for Mac tasks.

The macOS twin of platform/windows/reminders/outlook_tasks_backend.py (Outlook COM), driven by
AppleScript instead. Same operations, same two-list model, same data:

    ensure_list(name)           -> a task folder scoped to one Kit "list"
    pull_open(list_name)        -> [{"name", "due"}] for open items, and marks them complete
    mirror(desired_items, list) -> creates missing, updates due dates, removes items no longer
                                   desired, and returns the titles completed in Outlook

  - "Kit Inbox"    a pull list: anything you add there becomes one of your to-dos at the next
                   sync (start it with "Kit:" to give it to Kit).
  - "Kit: <name>"  a mirror of your open to-dos, with a 09:00 reminder on the due date; complete
                   one in Outlook (or Microsoft To Do on your phone) and it's checked off in
                   QUEUE.md.

Scoping: each list is a task folder under the Exchange account's default Tasks folder, and every
task Kit creates is tagged with the "Kit" category (created if it doesn't exist). Kit only ever
reads, changes, or deletes tasks inside its own folders.

Requires classic Outlook for Mac (the new Outlook has no AppleScript), already running: this
module never launches it. The first run asks for macOS Automation permission.

Self-test (read-only): python3 outlook_tasks_backend.py --list
"""
import datetime as dt
import subprocess
import sys

KIT_CATEGORY = "Kit"
REMINDER_HOUR = 9  # 09:00 on the due date, as on Windows and in Apple Reminders
US, RS = "\x1f", "\x1e"  # field / record separators in AppleScript output

AS_COMMON = r'''
on kitRoot()
    tell application "Microsoft Outlook"
        if (count of exchange accounts) > 0 then return default task folder of exchange account 1
        return task folder 1
    end tell
end kitRoot

on kitFolder(folderName, create)
    set root to my kitRoot()
    tell application "Microsoft Outlook"
        repeat with f in (task folders of root)
            if name of f is folderName then return contents of f
        end repeat
        if create then return make new task folder at root with properties {name:folderName}
    end tell
    return missing value
end kitFolder

on mkDate(y, m, d, h)
    set t to current date
    set day of t to 1
    set year of t to y
    set month of t to m
    set day of t to d
    set time of t to h * hours
    return t
end mkDate

on ymd(t)
    if t is missing value then return ""
    return ((year of t) as text) & "-" & ((month of t) as integer) & "-" & (day of t)
end ymd
'''

# argv: folder name, create ("1"/"0"). Output: one record per task: id US name US done US y-m-d.
AS_LIST = AS_COMMON + r'''
on run argv
    if application "Microsoft Outlook" is not running then error "Outlook is not running" number 1001
    set f to my kitFolder(item 1 of argv, (item 2 of argv) is "1")
    if f is missing value then return ""
    set us to character id 31
    set rs to character id 30
    set out to ""
    tell application "Microsoft Outlook"
        repeat with t in (tasks of f)
            set isDone to "0"
            if todo flag of t is completed then set isDone to "1"
            set out to out & (id of t) & us & (name of t) & us & isDone & us & my ymd(due date of t) & rs
        end repeat
    end tell
    return out
end run
'''

# argv: folder name, task name, y, m, d (y = "" for no due date), category ("" for none).
AS_CREATE = AS_COMMON + r'''
on run argv
    if application "Microsoft Outlook" is not running then error "Outlook is not running" number 1001
    set f to my kitFolder(item 1 of argv, true)
    tell application "Microsoft Outlook"
        set t to make new task at f with properties {name:(item 2 of argv)}
        if (item 3 of argv) is not "" then
            set dueAt to my mkDate((item 3 of argv) as integer, (item 4 of argv) as integer, (item 5 of argv) as integer, ''' + str(REMINDER_HOUR) + r''')
            set due date of t to dueAt
            set reminder date time of t to dueAt
        end if
        set catName to item 6 of argv
        if catName is not "" then
            try
                set c to missing value
                repeat with k in categories
                    if name of k is catName then set c to contents of k
                end repeat
                if c is missing value then set c to make new category with properties {name:catName}
                set categories of t to {c}
            end try
        end if
        return id of t
    end tell
end run
'''

# argv: folder name, task id, action (complete | delete | due), y, m, d.
AS_UPDATE = AS_COMMON + r'''
on run argv
    if application "Microsoft Outlook" is not running then error "Outlook is not running" number 1001
    set f to my kitFolder(item 1 of argv, false)
    if f is missing value then error "Kit task folder not found" number 1002
    set wantId to (item 2 of argv) as integer
    set act to item 3 of argv
    tell application "Microsoft Outlook"
        -- Only ever act on a task inside Kit's own folder.
        set hits to (tasks of f whose id is wantId)
        if (count of hits) is 0 then error "task not in Kit folder" number 1003
        set t to item 1 of hits
        if act is "complete" then
            set todo flag of t to completed
        else if act is "delete" then
            delete t
        else if act is "due" then
            set dueAt to my mkDate((item 4 of argv) as integer, (item 5 of argv) as integer, (item 6 of argv) as integer, ''' + str(REMINDER_HOUR) + r''')
            set due date of t to dueAt
            set reminder date time of t to dueAt
        end if
    end tell
    return "ok"
end run
'''


def _osa(script, *args):
    r = subprocess.run(["/usr/bin/osascript", "-", *[str(a) for a in args]], input=script,
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout.rstrip("\n")


def _to_date(s):
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in s.split("-"))
        return dt.date(y, m, d)
    except ValueError:
        return None


class OutlookTasksMacBackend:
    """AppleScript implementation of the device operations the sync needs."""

    def __init__(self, category=KIT_CATEGORY):
        self.category = category or ""

    # -- low-level helpers ----------------------------------------------------------------

    def list_tasks(self, list_name, create=True):
        """[{"id", "name", "done", "due"}] for the tasks in `list_name` (due is a date or None)."""
        out = []
        for rec in _osa(AS_LIST, list_name, "1" if create else "0").split(RS):
            if not rec.strip():
                continue
            parts = rec.split(US)
            if len(parts) < 4:
                continue
            out.append({"id": int(parts[0]), "name": parts[1], "done": parts[2] == "1",
                        "due": _to_date(parts[3].strip())})
        return out

    def create_task(self, list_name, title, due=None):
        y, m, d = (due.year, due.month, due.day) if due else ("", "", "")
        return int(_osa(AS_CREATE, list_name, title, y, m, d, self.category))

    def _update(self, list_name, task_id, action, due=None):
        y, m, d = (due.year, due.month, due.day) if due else ("", "", "")
        _osa(AS_UPDATE, list_name, task_id, action, y, m, d)

    def complete_task(self, list_name, task_id):
        self._update(list_name, task_id, "complete")

    def delete_task(self, list_name, task_id):
        self._update(list_name, task_id, "delete")

    def set_due(self, list_name, task_id, due):
        self._update(list_name, task_id, "due", due)

    # -- operations the reconciliation calls ----------------------------------------------

    def ensure_list(self, name):
        _osa(AS_LIST, name, "1")
        return name

    def pull_open(self, list_name):
        """Return [{"name", "due"}] for every open task in `list_name`, and mark each complete
        so it isn't pulled again. Mirrors JS_INBOX (Apple) and the Windows backend."""
        out = []
        for t in self.list_tasks(list_name):
            if t["done"]:
                continue
            try:
                self.complete_task(list_name, t["id"])
            except RuntimeError:
                continue  # skip a task that misbehaves; keep syncing
            out.append({"name": t["name"],
                        "due": t["due"].isoformat() if t["due"] else None})
        return out

    def mirror(self, desired_items, list_name):
        """Reconcile `list_name` to `desired_items` ([{"title", "due": ISO date or None}]) and
        return the titles completed in Outlook. Completed tasks are deleted and reported; missing
        ones are created; a changed due date is updated (a desired item with no due date leaves
        an existing one alone); open tasks no longer desired are deleted."""
        done, have = [], {}
        for t in self.list_tasks(list_name):
            if t["done"]:
                done.append(t["name"])
                try:
                    self.delete_task(list_name, t["id"])
                except RuntimeError:
                    pass
            else:
                have[t["name"]] = t
        keep = set()
        for w in desired_items:
            title = w["title"]
            keep.add(title)
            want = dt.date.fromisoformat(w["due"]) if w.get("due") else None
            t = have.get(title)
            try:
                if t is None:
                    self.create_task(list_name, title, want)
                elif want and t["due"] != want:
                    self.set_due(list_name, t["id"], want)
            except RuntimeError:
                continue
        for name, t in have.items():
            if name not in keep:
                try:
                    self.delete_task(list_name, t["id"])
                except RuntimeError:
                    pass
        return done


if __name__ == "__main__":
    if sys.argv[1:2] == ["--list"]:
        # Read-only: never creates a folder. Prints counts only, not task names.
        b = OutlookTasksMacBackend()
        for name in sys.argv[2:] or ["Kit Inbox"]:
            try:
                tasks = b.list_tasks(name, create=False)
                print(f"{name}: {len(tasks)} task(s), {sum(t['done'] for t in tasks)} completed")
            except RuntimeError as ex:
                print(f"{name}: {ex}")
                sys.exit(1)
    else:
        print(__doc__)
