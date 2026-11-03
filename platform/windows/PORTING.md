# Porting Kit to Windows

Kit is split so that most of it is already cross-platform and only a thin
OS-integration layer needs a Windows implementation.

- `kit/` — the agent's "brain" (KIT.md, sub-agents, prompts, memory/preferences/lessons
  templates, config schemas). **100% shared, no changes.**
- `shared/` — the Python/logic layer. Runs on both OSes; a few POSIX assumptions are already
  branched (see below).
- `platform/mac/` — the macOS integration (Swift tools, launchd, bash). **Needs a Windows
  counterpart under `platform/windows/`.**

## Overall split

**~70% is shared** — the entire agent brain plus the bulk of the Python. **~30% needs a genuine
Windows reimplementation** — the integration layer below (the hardest 30%).

## What each capability needs on Windows

| Capability | macOS today | Windows route | Effort |
|---|---|---|---|
| **Calendar** (`platform/mac/calendar/kitcal.swift`) | EventKit: free/busy merge, recurrence spans, multi-calendar, attendee + read-only safety guards | Microsoft Graph `/me/calendars` + `/me/events` + `getSchedule`, or Outlook COM (`AppointmentItem`) | **Substantial** |
| **Reminders / to-do sync** (`shared/reminders_sync.py`, JXA) | Apple Reminders via JXA; "Kit Inbox" pull + "Kit: <name>" mirror with due alerts | Microsoft To Do via Graph (`/me/todo/lists`, `/me/todo/tasks`) or Outlook Tasks via COM. The reconciliation logic and `todo` reuse carry over — only the device layer is replaced. | Moderate–Substantial |
| **Scheduling + delivery** (launchd plists + `platform/mac/morning/run.sh`) | launchd weekday triggers → `run.sh`; brief delivered as **iMessage** to the phone | Task Scheduler (`schtasks` / `Register-ScheduledTask`) → a `run.ps1`. **No iMessage on Windows** — pick another channel: Windows toast (BurntToast), email (reuse the mail tool), or an SMS API. | Moderate–Substantial |
| **Mail** (`platform/mac/mail/kitmail.swift`) | Apple Mail via JXA; lists accounts, opens drafts for manual send, exclude-list, no send command | Outlook COM (`Outlook.Application` MAPI) or Microsoft Graph `/me/messages`. Keep the exclude-list and the no-send guarantee. | Moderate |
| **Install + folder privacy** (`platform/mac/install.sh`, `chmod 700`) | bash installer; `chmod -R go-rwx` for owner-only access | `platform/windows/install.ps1` over the shared `kit_setup.py`; NTFS ACLs via `icacls` (strip inheritance, grant only the current user) for the owner-only guarantee | Moderate |

## POSIX branches already added in `shared/` (for reference / to extend)

- `kit_setup.py` — `_owner_name()` falls back to `getpass.getuser()` when `pwd` is unavailable;
  `os.chmod`/`os.umask` are skipped when `os.name == "nt"`; scaffold copies the full
  `shared/` + `platform/` payload into `.install/`.
- `dashboard.py` — strftime no-pad hour uses `%#I` on Windows (`%-I` elsewhere); `--open` uses
  `os.startfile` on Windows, `open` on macOS, `xdg-open` otherwise.
- `doctor.py` — launchd / `~/.local/bin` / plist checks remain macOS checks; off-Mac they simply
  report "not found", which is expected until the Windows equivalents exist.
- Agent hooks: Claude Code runs hook commands with Git Bash on Windows, so the guarded agents' hooks
  run `/bin/sh .../kit-hook connector-guard ...`: `kit-hook` skips the Microsoft Store's `python3` stub,
  uses `py -3` or `python`, and blocks the call when no Python runs. `kit_hooks.py` (kit-run) and
  `guard_check.py` (the installer's last step and doctor's "Connector guard hooks") use Git Bash too.

## Windows counterparts under `platform/windows/`

CI runs the installer for real on GitHub's Windows runners (Windows PowerShell 5.1 and PowerShell 7:
install, reinstall, and the repair of broken permissions), with the Python suites the workflow lists
on Windows. The Outlook COM adapters and the Task Scheduler tasks haven't run on a real Windows
machine yet.

1. `install.ps1`: installer over the shared `kit_setup.py`, with NTFS-ACL folder privacy.
2. Mail: Outlook COM backend, equivalent to `platform/mac/mail/kitmail.swift`.
3. Calendar: Outlook COM backend, equivalent to `platform/mac/calendar/kitcal.swift`.
4. To-do sync: Outlook Tasks backend for `shared/reminders_sync.py` (shared `kit_sync_core.reconcile()`).
5. `run.ps1` and Task Scheduler tasks, replacing `platform/mac/morning/run.sh` and the eight launchd
   `.plist.template` files, with toast or file delivery instead of iMessage.

## Status: what has run on Windows, and what hasn't

- **Run in CI on Windows** (`.github/workflows/checks.yml`, under Windows PowerShell 5.1 and
  PowerShell 7): `install.ps1` (a fresh install, a reinstall, and the repair of an install whose files
  lost their permissions, then doctor.py, whose connector guard check runs the installed hooks in Git
  Bash), the command shims, and the Python suites the workflow lists, `tests/test_kit_hook.py` among them.
- **Tested elsewhere:** `run.ps1`'s logic under PowerShell 7 against a fake claude
  (`tests/test_runps1.sh`), and the Outlook Tasks sync over a fake COM layer (`tests/test_sync_core.sh`).
- **Not yet run on a real Windows machine:** the Outlook COM adapters (mail, calendar, Outlook Tasks),
  which carry an "UNTESTED" banner and a `## Manual test` section; registering and running the Task
  Scheduler tasks; `preflight.ps1`; and `uninstall.ps1`. Every script parses in CI.

- `install.ps1` / `uninstall.ps1` — run `shared/kit_setup.py`, NTFS-ACL folder lock-down,
  `kitmail`/`kitcal` PATH shims, and a classic-Outlook presence check.
- `mail/kitmail.py` — Outlook COM, mirrors `kitmail.swift` subcommands; drafts only, no send.
- `calendar/kitcal.py` — Outlook COM, full CLI parity + attendee/read-only guards. Recurring
  "this-and-future" edits are refused with a TODO; validate recurrence deletes on Windows.
- `reminders/` — Outlook Tasks COM backend + entry point.
- `morning/` — `run.ps1`, Task Scheduler register/unregister, pluggable delivery (toast → file
  fallback; email/SMS hooks). No iMessage.

**Known follow-ups:**
- Mail/calendar/reminders require **classic desktop Outlook** (COM); the new Outlook and web
  clients don't expose it.
- The to-do sync is shared: `shared/kit_sync_core.py` holds `reconcile()`, Kit Inbox routing
  ("kit:", "ask:", "approve <code>"), and the work/personal split; `shared/reminders_sync.py` (Mac)
  and `reminders/reminders_sync_win.py` (Windows, Outlook Tasks over COM) only supply the device
  backend. `tests/test_sync_core.sh` runs the Windows backend over a fake COM layer; it still needs a
  run against real Outlook on Windows.
- The Outlook adapters and the scheduled tasks need an end-to-end run on a real Windows machine;
  recurrence-delete off-by-one is the top risk.

## Login check and connection check

- `morning/preflight.ps1` ports the Mac `preflight.sh`: at 06:45 and 15:45 ("Kit Login Check" in
  `register-tasks.ps1`) it makes one tiny `claude -p` call and checks each connector in
  `PREFLIGHT_CONNECTORS`, and tells the owner once per lapse through `deliver.py`. Not yet run on Windows.
- `run.ps1` checks that the API is reachable before the model run (`CONNECTION_CHECK`,
  `CONNECTION_WAIT`): when it isn't, it waits up to 5 minutes, then skips the model run and logs the
  run as failed, as `run.sh` does. It checks `CONNECTION_URL`, else `ANTHROPIC_BASE_URL`, else the API,
  through `HTTPS_PROXY` (with `NO_PROXY`) or the system proxy; tested under PowerShell 7 (`tests/test_runps1.sh`).
- Long-lived login: the Mac reads a `claude setup-token` token from the Keychain. On Windows, set the
  user environment variable instead (`setx CLAUDE_CODE_OAUTH_TOKEN "<token>"`); scheduled tasks
  inherit it. Treat it like a password.
