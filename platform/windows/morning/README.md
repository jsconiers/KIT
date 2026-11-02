# Kit scheduling & delivery on Windows

The Windows counterpart to `platform/mac/morning/` (the launchd plists + `run.sh`). It uses
**Windows Task Scheduler** and **PowerShell** instead of launchd and zsh.

> **What's tested.** `run.ps1`'s logic is tested under PowerShell 7 against a fake `claude`
> (`tests/test_runps1.sh`: every mode, the end-of-day wrap, runs of your own, the brief's extra
> sections, the budget guard, time limits, the lock, retries, and the connection check), and CI checks
> that every script here parses. CI also runs the installer for real on GitHub's Windows runners, under
> Windows PowerShell 5.1 and PowerShell 7 (install, reinstall, and repair), with the Python suites it
> lists. **Not yet run on a real Windows machine:** registering and running the Task Scheduler tasks,
> `preflight.ps1`, and the Outlook COM calls (mail, calendar, Outlook Tasks) a run makes.

Files:

| File | Role | Mac equivalent |
|---|---|---|
| `run.ps1` | The scheduled run: modes (morning, weekly, work list, end-of-day wrap, open, journal, and runs of your own from `.install\prompts\prompt-NAME.md` with `ALLOW_TOOLS_<NAME>`), skip-days, once-per-day markers, the kit-pause kill switch, the kit-cost budget guard, the dates, renewals, `brief.d` hook, PPM Express pulse, and architecture digest sections, headless `claude -p` with JSON output and cost recording, the model from `models.env`, a time limit per kind of run (a stopped run's claude process is found by its run id and ended), one run at a time (a lock), the connection check (`ANTHROPIC_BASE_URL` and proxies honoured), delivery, dashboard refresh, git auto-commit. The end-of-day wrap is `kit-wrap`, with no model call, unless `EOD_MODEL="on"`. No Outlook check before runs (kit-outlook is macOS-only). | `run.sh` |
| `preflight.ps1` | The login check before the runs: Claude Code and the connectors in `PREFLIGHT_CONNECTORS`. | `preflight.sh` |
| `register-tasks.ps1` | Creates the Task Scheduler tasks. | the `.plist.template` files |
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
| Kit Weekly Review | Monday 06:30 | `run.ps1 weekly` | `com.USER.kit.weekly` |
| Kit Work List | Monday-Thursday 09:00 | `run.ps1 worklist` | `com.USER.kit.worklist` |
| Kit End of Day | Monday-Thursday 17:30, Friday 15:30 | `run.ps1 eod` | `com.USER.kit.eod` |
| Kit Meeting Prep | Weekdays every 30 min, 07:00-18:00 | `kit-meetprep --from-config --minutes 45` (skipped while paused) | `com.USER.kit.meetprep` |
| Kit Backup | Daily 12:30 | `kit-backup` | `com.USER.kit.backup` |
| Kit Reminders Sync | Every 15 min + at logon | `reminders_sync_win.py` | `com.USER.kit.sync` |
| Kit Login Check | Daily 06:45 and 15:45 | `preflight.ps1` | `com.USER.kit.preflight` |
| Kit Trade Journal | Weekdays (Mon-Fri) 16:20 | `run.ps1 journal` | *(no plist; see note)* |

The journal task has **no** launchd plist — `run.sh` documents a 16:20 journal run but ships no
plist for it. `run.ps1` fully supports `journal` mode, so `register-tasks.ps1` registers it too
for parity. Set `$RegisterJournal = $false` at the top of that script to skip it.

The reminders-sync task calls `.install\platform\windows\reminders\reminders_sync_win.py` (the
Windows reminders backend, delivered separately). The task tries `py -3` first, then `python`.

## Delivery channels

Delivery is the same on Windows and macOS: both runners call `shared/deliver.py`, which reads
`DELIVERY` from the shared config at `.install\shared\morning\config` (`KEY="value"` lines).
List one or more channels, space-separated:

```ini
DELIVERY="local"                 # local | outlook-drafts | outlook-review (any combination)
DELIVERY_EMAIL_TO="you@example.com"   # the address the Outlook draft is addressed to
```

- **`local`** (default): a toast notification using built-in Windows APIs (falling back to a log
  message if toasts aren't available), then the dashboard is rebuilt. The brief file is in
  `briefs\`.
- **`outlook-drafts`**: saves the brief as a draft in classic Outlook's Drafts folder (COM
  `.Save()`), with no window. Exchange syncs it to Outlook on the phone. Never sent. Falls back to
  `local` if Outlook isn't running.
- **`outlook-review`**: the same draft, opened on screen (`.Display()`) for review. Never sent.
- **`sms`** (legacy, opt-in): a stub that leaves Microsoft 365; not for work content.

The older `DELIVERY_CHANNEL` key still works when `DELIVERY` isn't set: `toast` and `file` map to
`local`, `email` to `outlook-review`, and `sms` to `sms`.

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

# 2. Trigger a run (pick a mode): morning | open | weekly | worklist | eod | journal | NAME
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
