# Kit scheduling & delivery on Windows

The Windows counterpart to `platform/mac/morning/` (the launchd plists + `run.sh`). It uses
**Windows Task Scheduler** and **PowerShell** instead of launchd and zsh.

> **UNTESTED on Windows.** Every script here carries a top-of-file warning. Validate on a real
> Windows box before relying on any of it.

Files:

| File | Role | Mac equivalent |
|---|---|---|
| `run.ps1` | The scheduled run: modes, skip-days, once-per-day markers, headless `claude -p` with a ~1200s timeout, delivery, dashboard refresh, git auto-commit. | `run.sh` |
| `register-tasks.ps1` | Creates the Task Scheduler tasks. | the four `.plist.template` files |
| `unregister-tasks.ps1` | Removes those tasks. | `launchctl bootout` |

## Register / unregister the tasks

```powershell
# Register (safe to re-run; it replaces any existing Kit tasks):
powershell -ExecutionPolicy Bypass -NoProfile -File register-tasks.ps1

# See them:
Get-ScheduledTask -TaskPath '\Kit\'

# Remove them (leaves Kit's files and logs alone):
powershell -ExecutionPolicy Bypass -NoProfile -File unregister-tasks.ps1
```

Tasks are created under the Task Scheduler folder `\Kit\`, run as the current user, and only
when that user is logged on (launchd runs in the user's GUI session; these match that).
`StartWhenAvailable` catches runs missed while the PC was off.

### Schedules (mapped from the launchd plists)

| Task | When | Invokes | From plist |
|---|---|---|---|
| Kit Morning Brief | Weekdays (Mon-Fri) 07:45 | `run.ps1 morning` | `com.USER.kit.morning` |
| Kit Post-Open Read | Weekdays (Mon-Fri) 09:45 | `run.ps1 open` | `com.USER.kit.open` |
| Kit Weekly Review | Saturday 18:00 | `run.ps1 weekly` | `com.USER.kit.weekly` |
| Kit Reminders Sync | Every 15 min + at logon | `reminders_sync_win.py` | `com.USER.kit.sync` |
| Kit Trade Journal | Weekdays (Mon-Fri) 16:20 | `run.ps1 journal` | *(no plist; see note)* |

The journal task has **no** launchd plist — `run.sh` documents a 16:20 journal run but ships no
plist for it. `run.ps1` fully supports `journal` mode, so `register-tasks.ps1` registers it too
for parity. Set `$RegisterJournal = $false` at the top of that script to skip it.

The reminders-sync task calls `.install\platform\windows\reminders\reminders_sync_win.py` (the
Windows reminders backend, delivered separately). The task tries `py -3` first, then `python`.

## BurntToast (optional dependency)

The default delivery channel is a **Windows toast notification**, shown via the
[BurntToast](https://github.com/Windos/BurntToast) PowerShell module. It is optional:

```powershell
Install-Module BurntToast -Scope CurrentUser
```

If BurntToast is **not** installed — or the task runs in a non-interactive session where a toast
can't appear — delivery automatically **falls back to a file** (see below). Nothing is ever lost.

## Delivery channels

There is no iMessage on Windows, so delivery is pluggable. The channel is read from the shared
morning config at `.install\shared\morning\config` (the same file the Mac uses; `KEY="value"`
lines). Add these keys as needed:

```ini
# Which channel to use: toast | file | email | sms   (default: toast)
DELIVERY_CHANNEL="toast"

# email channel (opens an Outlook DRAFT via kitmail.py; never auto-sends):
DELIVERY_EMAIL_TO="you@example.com"
DELIVERY_EMAIL_FROM=""          # optional: the account to draft from

# sms channel (HOOK/stub — wire your own gateway in run.ps1's Send-Sms):
DELIVERY_SMS_TO="+15555550123"
DELIVERY_SMS_API_URL="https://api.example.com/send"
DELIVERY_SMS_API_KEY_ENV="KIT_SMS_API_KEY"   # NAME of the env var holding the key, not the key
```

Channels implemented in `run.ps1`:

- **`toast`** (default) — BurntToast notification; falls back to a file if unavailable.
- **`file`** (fallback, also selectable) — writes the brief to
  `briefs\delivered-<mode>-<timestamp>.txt` and logs it under `.install\logs`. Always available.
- **`email`** (hook) — reuses the Windows mail tool (`platform/windows/mail/kitmail.py`) to open
  an Outlook **draft** addressed to `DELIVERY_EMAIL_TO`. `kitmail` never sends on its own, so the
  owner reviews and sends. For a true unattended send, replace this with SMTP/Graph in
  `Send-Email`.
- **`sms`** (hook) — a clearly-marked **stub** in `Send-Sms`. Wire your provider's HTTP call
  there. The API key is referenced by the **name** of an environment variable
  (`DELIVERY_SMS_API_KEY_ENV`), never stored in config or on disk.

Any channel that fails falls back to the file channel, so a brief is never dropped. On a hard
failure (even the file write fails), `run.ps1` keeps an `unsent-<mode>.txt` copy and does **not**
mark the day done, so the next scheduled run retries — matching `run.sh`.

The agent itself decides whether to deliver by what it writes to the mode's text file
(`briefs\latest-text.txt`, `open-text.txt`, etc.): the sentinel values `MARKET CLOSED` and
`NO TEXT` mean "ran fine, nothing to send" (no delivery, day marked done); any other non-empty
text is delivered; an empty/absent file means the run didn't finish and a short failure notice
is delivered instead.

## Manual test

Run a mode by hand **without using up that day's real run**, using the `test-run` marker (the
Windows equivalent of the Mac `test-run` file). A test run is prefixed `[Test] `, ignores
skip-days and the once-per-day marker, and does not create the `.done` marker.

```powershell
$kit = "$env:USERPROFILE\Claude\Agents\kit"

# 1. Drop the test-run marker:
New-Item -ItemType File "$kit\.install\platform\windows\morning\test-run" -Force

# 2. Trigger a run (pick a mode): morning | open | weekly | journal
powershell -ExecutionPolicy Bypass -NoProfile -File "$kit\.install\platform\windows\morning\run.ps1" morning

# --- or trigger the registered task instead of calling run.ps1 directly: ---
Start-ScheduledTask -TaskPath '\Kit\' -TaskName 'Kit Morning Brief'
```

Verify:

```powershell
$today = Get-Date -Format "yyyy-MM-dd"

# 3. Check the log for start/end lines, the rc, and a delivery line:
Get-Content "$kit\.install\logs\$today.log" -Tail 40

# 4. Check delivery:
#    - toast: a Kit notification appeared (interactive session only).
#    - file fallback: a new briefs\delivered-morning-*.txt file exists:
Get-ChildItem "$kit\briefs\delivered-*.txt" | Sort-Object LastWriteTime | Select-Object -Last 3
#    - email: an Outlook draft window opened addressed to DELIVERY_EMAIL_TO.

# 5. Confirm a test run did NOT create the day's .done marker:
Test-Path "$kit\.install\logs\$today.done"   # expect False after a [Test] morning run

# 6. (journal) journal mode refuses to run before 16:00 — the log says "skipped: before the close".
```

To test the **real** path (marks the day done, honors skip-days), omit step 1 and just run the
mode or `Start-ScheduledTask`. Note that `journal` before 16:00 and `open` at/after 12:00 are
skipped by design, and each mode runs at most once per day.
