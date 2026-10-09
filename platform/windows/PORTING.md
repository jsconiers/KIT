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

## Files still needing a Windows counterpart under `platform/windows/`

1. `install.ps1` — real installer (currently a stub) + NTFS-ACL folder privacy.
2. A mail backend (Outlook COM / Graph) equivalent to `platform/mac/mail/kitmail.swift`.
3. A calendar backend equivalent to `platform/mac/calendar/kitcal.swift`.
4. A reminders/to-do backend for `shared/reminders_sync.py` (Microsoft To Do / Outlook Tasks).
5. `run.ps1` + Task Scheduler task definitions to replace `platform/mac/morning/run.sh`
   and the four launchd `.plist.template` files, plus a non-iMessage delivery channel.

## Status (first-draft adapters — UNTESTED on Windows)

All five adapters are drafted under `platform/windows/`. They parse cleanly (Python `ast`,
PowerShell parser) but have **not been run on Windows** — validate on a real Windows box with
classic desktop Outlook before relying on them. Each file carries an "UNTESTED" banner and a
`## Manual test` section.

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
- The reconciliation logic is currently duplicated in `reminders/reminders_sync_win.py`.
  Planned refactor: extract `reconcile(todo, backend, …)` into `shared/reminders_sync.py` with a
  `MacRemindersBackend`, so Mac (JXA) and Windows (Outlook Tasks) share one implementation.
- Everything needs an end-to-end run on Windows; recurrence-delete off-by-one is the top risk.
