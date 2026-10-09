# UNTESTED on Windows — validate on a real Windows box with Outlook installed.
"""Device layer for Kit's to-do sync on Windows, backed by Outlook Tasks via COM.

This is the Windows analog of the JXA blocks in `shared/reminders_sync.py` (which drive
Apple Reminders on macOS). It exposes exactly the operations the shared reconciliation
needs, so the reconciliation logic itself does not care which OS it runs on:

    ensure_list(name)           -> a Tasks subfolder scoped to one Kit "list"
    pull_open(list_name)        -> [{"name", "due"}] for open items, and marks them complete
    mirror(desired_items, list) -> creates missing, updates due dates, removes items no longer
                                    desired, and returns the titles completed on the device

Two-list model (same as macOS):
  - "Kit Inbox"    — a pull list: anything you add there becomes a to-do at the next sync.
  - "Kit: <name>"  — a mirror of your open to-dos, with a 09:00 reminder on the due date;
                     complete one in Outlook and it is checked off in QUEUE.md.

Scoping: each list is a dedicated subfolder under Outlook's default Tasks folder, and every
item Kit creates is also tagged with the "Kit" category. Either is enough to keep Kit's items
separate from the user's own tasks; we use both.

win32com is imported lazily (inside the class) so this module can at least be imported and
inspected on a non-Windows box. The numeric Outlook constants are hard-coded so the backend
works with late-bound (dynamic) dispatch and needs no gencache / makepy type library.
"""
import datetime as dt

# Outlook enum values (hard-coded to avoid a gencache dependency).
OL_FOLDER_TASKS = 13      # olFolderTasks
OL_TASK_ITEM = 3          # olTaskItem
OL_TASK_NO_DATE_YEAR = 4501  # Outlook stores "no due date" as 1/1/4501

KIT_CATEGORY = "Kit"
REMINDER_HOUR = 9         # 09:00 on the due date, matching the macOS alert time


def _to_date(com_dt):
    """Convert an Outlook DueDate (a pywintypes/COM datetime) to a datetime.date, or None.

    Outlook represents "no due date" as 1/1/4501, which we treat as None. Task due dates are
    compared at day granularity, so the time component is ignored.
    """
    if com_dt is None:
        return None
    try:
        year, month, day = int(com_dt.year), int(com_dt.month), int(com_dt.day)
    except Exception:  # noqa: BLE001 - any COM/type oddity means "no usable date"
        return None
    if year >= OL_TASK_NO_DATE_YEAR:
        return None
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


class OutlookTasksBackend:
    """Outlook-COM implementation of the device operations the sync needs."""

    def __init__(self):
        # Lazy, Windows-only imports. These raise on non-Windows / without pywin32, which is
        # the correct behavior: the backend genuinely cannot run there.
        import pythoncom
        import win32com.client

        try:
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001 - COM may already be initialized on this thread
            pass
        self._app = win32com.client.Dispatch("Outlook.Application")
        self._ns = self._app.GetNamespace("MAPI")

    # -- list / folder management -------------------------------------------------------

    def ensure_list(self, name):
        """Return the Tasks subfolder named `name`, creating it under the default Tasks folder
        if it does not yet exist. This is the Windows analog of ensuring a Reminders list."""
        tasks = self._ns.GetDefaultFolder(OL_FOLDER_TASKS)
        folders = tasks.Folders
        for i in range(1, folders.Count + 1):
            folder = folders.Item(i)
            if folder.Name == name:
                return folder
        # Add inherits the parent's folder type (Tasks) when no type is given.
        return folders.Add(name)

    @staticmethod
    def _snapshot(folder):
        """COM collections are 1-indexed and unstable under concurrent modification, so take a
        plain Python list of item references up front, then mutate freely."""
        coll = folder.Items
        return [coll.Item(i) for i in range(1, coll.Count + 1)]

    def _set_due(self, item, when_date):
        """Set an item's due date to 09:00 on `when_date` and arm a reminder, then save."""
        when = dt.datetime(when_date.year, when_date.month, when_date.day, REMINDER_HOUR, 0, 0)
        item.DueDate = when
        try:
            item.ReminderSet = True
            item.ReminderTime = when
        except Exception:  # noqa: BLE001 - reminder is best-effort; the due date is the point
            pass
        item.Save()

    # -- operations the reconciliation calls --------------------------------------------

    def pull_open(self, list_name):
        """Return [{"name", "due"}] for every open item in `list_name`, and mark each complete
        so it is consumed and not pulled again. Mirrors JS_INBOX on macOS."""
        folder = self.ensure_list(list_name)
        out = []
        for item in self._snapshot(folder):
            try:
                if item.Complete:
                    continue
                due = _to_date(item.DueDate)
                out.append({
                    "name": item.Subject or "",
                    "due": due.isoformat() if due else None,
                })
                item.Complete = True  # Outlook sets Status/PercentComplete/DateCompleted
                item.Save()
            except Exception:  # noqa: BLE001 - skip any item that misbehaves, keep syncing
                continue
        return out

    def mirror(self, desired_items, list_name):
        """Reconcile `list_name` to match `desired_items` and report device-side completions.

        `desired_items` is a list of {"title": str, "due": ISO-date-str-or-None}.

        - Items completed in Outlook are deleted and their titles returned (so the caller can
          check them off in QUEUE.md).
        - Desired items missing from the folder are created (tagged with the Kit category).
        - A desired item whose due date differs gets its due date updated (only when a due date
          is desired — a desired item with no due date leaves any existing due date alone,
          matching the macOS behavior).
        - Open items no longer desired are deleted.

        Mirrors JS_MIRROR on macOS.
        """
        folder = self.ensure_list(list_name)
        done, have = [], {}
        for item in self._snapshot(folder):
            try:
                subject = item.Subject or ""
                if item.Complete:
                    done.append(subject)
                    item.Delete()
                else:
                    have[subject] = item
            except Exception:  # noqa: BLE001
                continue

        keep = set()
        for w in desired_items:
            title = w["title"]
            keep.add(title)
            want_date = dt.date.fromisoformat(w["due"]) if w.get("due") else None
            item = have.get(title)
            if item is not None:
                if want_date and _to_date(item.DueDate) != want_date:
                    try:
                        self._set_due(item, want_date)
                    except Exception:  # noqa: BLE001
                        pass
            else:
                try:
                    new = folder.Items.Add(OL_TASK_ITEM)
                    new.Subject = title
                    try:
                        new.Categories = KIT_CATEGORY
                    except Exception:  # noqa: BLE001
                        pass
                    if want_date:
                        self._set_due(new, want_date)
                    else:
                        new.Save()
                except Exception:  # noqa: BLE001
                    continue

        for subject, item in have.items():
            if subject not in keep:
                try:
                    item.Delete()
                except Exception:  # noqa: BLE001
                    pass

        return done
