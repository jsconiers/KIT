# Kit reminders / to-do sync — Windows (Outlook Tasks)

> **UNTESTED on Windows** — validate on a real Windows box with Outlook installed.

The Windows counterpart of `shared/reminders_sync.py`. It keeps Kit's to-do list
(`QUEUE.md`) in sync with **Outlook Tasks** over COM, which in turn syncs to your phone
through **Microsoft To Do**. It reuses the shared `todo` parser/editor and the same two-list
model as macOS; only the device layer (Apple Reminders → Outlook Tasks) is swapped.

## Files

- `outlook_tasks_backend.py` — device layer: `ensure_list`, `pull_open`, `mirror`, built on
  `win32com.client` and `olTaskItem` tasks in dedicated Tasks subfolders, tagged with the
  `Kit` category.
- `reminders_sync_win.py` — the entry point. Loads `todo`, runs the reconciliation, logs to
  `%USERPROFILE%\Claude\Agents\kit\.install\logs\sync.log`.

## The two lists

Both are subfolders created under Outlook's default **Tasks** folder:

- **Kit Inbox** — add a task here (by hand, or via Microsoft To Do on your phone) and it
  becomes one of your to-dos at the next sync, then is marked complete. Start the title with
  `Kit:` to file it under Kit instead of you.
- **Kit: \<your name\>** — a mirror of your open to-dos, each with a reminder at 09:00 on its
  due date. Complete one in Outlook / To Do and it is checked off in `QUEUE.md`.

## Install

```powershell
pip install pywin32
```

`pywin32` provides `win32com.client` and `pythoncom`. Outlook must be installed and configured
with a mail profile; the script drives whatever profile Outlook opens by default. No other
dependencies — `todo` and `dashboard.py` are already part of Kit's shared payload.

## Scheduling

Runs every **15 minutes** via **Task Scheduler** (`schtasks` / `Register-ScheduledTask`),
the Windows analog of the macOS launchd `com.USER.kit.sync` job. **The scheduling piece is
built separately** (see `platform/windows/PORTING.md`, item 5 — `run.ps1` + Task Scheduler
definitions); this folder only provides the sync itself. The scheduled action is, in effect:

```powershell
python "%USERPROFILE%\Claude\Agents\kit\.install\platform\windows\reminders\reminders_sync_win.py"
```

Run it under the logged-in user (not SYSTEM) so it can reach that user's Outlook profile.

## Manual test

1. **Setup.** `pip install pywin32`, open Outlook, make sure a mail profile is loaded.
2. **First run creates the lists.**
   ```powershell
   python "%USERPROFILE%\Claude\Agents\kit\.install\platform\windows\reminders\reminders_sync_win.py"
   ```
   Expect `in sync`. In Outlook's Tasks, confirm two new subfolders exist: **Kit Inbox** and
   **Kit: \<your name\>**, and that the latter now contains your current open to-dos from
   `QUEUE.md` (tagged with the `Kit` category, due dates armed for 09:00).
3. **Inbox → QUEUE.md.** In Outlook, add a task to **Kit Inbox**, e.g. `Buy stamps` with a due
   date. Run the script again. Expect `added for <you>: Buy stamps`. Confirm the item is now in
   your section of `QUEUE.md` (marked `from phone`) and the Kit Inbox task is now completed.
   Try a title beginning `Kit:` and confirm it lands in the **Kit** section instead.
4. **QUEUE.md → mirror.** Add one via the shared tool:
   ```powershell
   python "%USERPROFILE%\Claude\Agents\kit\.install\shared\bin\todo" Call plumber fri
   ```
   Run the script. Confirm a matching task appears in **Kit: \<your name\>** with a Friday
   09:00 reminder.
5. **Complete → check-off.** Mark that task complete in Outlook (or in Microsoft To Do on your
   phone). Run the script. Expect `checked off on phone: Call plumber`, and confirm the item is
   moved to `## Done` in `QUEUE.md` and the completed task is removed from the folder.
6. **Removal.** Check an item off in `QUEUE.md` (so it leaves your open items), run the script,
   and confirm the corresponding open task disappears from **Kit: \<your name\>**.
7. **Logs.** Each run with changes appends a line to
   `%USERPROFILE%\Claude\Agents\kit\.install\logs\sync.log`. Failures are logged there too and
   printed to stderr with a non-zero exit code.

## Known differences from macOS

- Items pulled from **Kit Inbox** are marked *complete* (not deleted), exactly as the macOS
  tool does; completed inbox tasks accumulate in that folder over time.
- The `from phone` marker written into `QUEUE.md` is kept identical to the macOS wording for
  consistency; on Windows the item may have originated in Outlook or in Microsoft To Do.
