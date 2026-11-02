# register-tasks.ps1: create Kit's scheduled tasks in Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -NoProfile -File register-tasks.ps1
#
# Not yet run on a real Windows machine: registering these tasks and Task Scheduler starting them. CI
# checks that this script parses; run it once on a test machine and check Get-ScheduledTask before relying on it.
#
# Replaces the four macOS launchd plists with Task Scheduler tasks, each invoking run.ps1 with
# the matching mode (and the sync task invoking the Windows reminders sync). Schedules mirror
# the plists exactly:
#
#   Kit Morning Brief     weekdays (Mon-Fri)  07:45   -> run.ps1 morning
#   Kit Post-Open Read    weekdays (Mon-Fri)  09:45   -> run.ps1 open      (optional; see note)
#   Kit Weekly Review     Monday              06:30   -> run.ps1 weekly    (before the brief)
#   Kit Work List         Monday-Thursday     09:00   -> run.ps1 worklist
#   Kit End of Day        Monday-Thursday     17:30, Friday 15:30 -> run.ps1 eod
#   Kit Meeting Prep      weekdays, every 30 min 07:00-18:00 -> kit-meetprep --from-config --minutes 45 (optional)
#   Kit Backup            Daily               12:30   -> kit-backup
#   Kit Reminders Sync    every 15 min + at logon     -> reminders_sync_win.py
#   Kit Trade Journal     weekdays (Mon-Fri)  16:20   -> run.ps1 journal   (optional; see note)
#   Kit Login Check       daily               06:45, 15:45 -> preflight.ps1
#
# Every Python these tasks start runs in UTF-8 mode (PYTHONUTF8=1): run.ps1 and preflight.ps1 set it, and
# the backup and sync tasks set it in their command, since Kit's files are UTF-8.
#
# The post-open read and the trade journal are optional extras for a trading setup. If you don't
# trade, set $RegisterOpen and $RegisterJournal to $false below. (The journal has no launchd plist
# on the Mac; run.sh documents a 16:20 journal run.)
#
# Tasks run as the current user, only when that user is logged on (launchd runs in the user's
# GUI session; so do these). StartWhenAvailable catches runs missed while the machine was off,
# which is the closest match to launchd replaying missed StartCalendarInterval jobs.

$ErrorActionPreference = "Stop"

$RegisterOpen    = $true   # optional trading extra: set $false to skip the 09:45 post-open read
$RegisterJournal = $true   # optional trading extra: set $false to skip the 16:20 trade journal
$RegisterMeetprep = $true  # optional meeting prep packs (optional on the Mac too): set $false to skip them

$KitHome   = Join-Path $env:USERPROFILE "Claude\Agents\kit"
$RunPs1    = Join-Path $KitHome ".install\platform\windows\morning\run.ps1"
$SyncPy    = Join-Path $KitHome ".install\platform\windows\reminders\reminders_sync_win.py"
$PwshPath  = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
if (-not $PwshPath) { $PwshPath = "powershell.exe" }
$TaskPath  = "\Kit\"

if (-not (Test-Path -LiteralPath $RunPs1)) {
    Write-Host "register-tasks: run.ps1 not found at $RunPs1. Install Kit first."
    exit 1
}

# Common principal (current user) and settings, shared by every task.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
# Give a run room to finish: run.ps1 enforces its own limits (weekly review 50 min, others 20 min
# or less) and may wait up to 30 min for another run, so allow headroom above both.
$settings.ExecutionTimeLimit = "PT2H"

function Register-KitTask {
    param(
        [string]$Name,
        [string]$Description,
        $Trigger,          # one trigger or an array of triggers
        [string[]]$ActionArgs
    )
    $action = New-ScheduledTaskAction -Execute $PwshPath -Argument ($ActionArgs -join " ") -WorkingDirectory $KitHome
    # Replace any existing task of the same name so this script is safe to re-run.
    Unregister-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Register-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Action $action -Trigger $Trigger `
        -Principal $principal -Settings $settings -Description $Description | Out-Null
    Write-Host "registered: $TaskPath$Name"
}

$weekdays = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

# --- Kit Morning Brief: weekdays 07:45 -------------------------------------------------------
Register-KitTask -Name "Kit Morning Brief" `
    -Description "Kit's morning brief (port of com.USER.kit.morning)." `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "7:45am") `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "morning")

# --- Kit Post-Open Read: weekdays 09:45 (optional extra for a trading setup) -----------------
if ($RegisterOpen) {
    Register-KitTask -Name "Kit Post-Open Read" `
        -Description "Kit's post-open read (port of com.USER.kit.open)." `
        -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "9:45am") `
        -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "open")
}

# --- Kit Weekly Review: Monday 06:30 (finishes before the 07:45 morning brief) ---------------
Register-KitTask -Name "Kit Weekly Review" `
    -Description "Kit's weekly review (port of com.USER.kit.weekly)." `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek "Monday" -At "6:30am") `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "weekly")

# --- Kit Work List: Monday to Thursday 09:00 --------------------------------------------------
Register-KitTask -Name "Kit Work List" `
    -Description "Kit's proposed work list for the owner to approve (port of com.USER.kit.worklist)." `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek @("Monday", "Tuesday", "Wednesday", "Thursday") -At "9:00am") `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "worklist")

# --- Kit End of Day: Monday to Thursday 17:30, Friday 15:30 (port of com.USER.kit.eod) -------
# kit-wrap writes the end-of-day wrap with no model call; EOD="off" in the config makes the run do nothing.
Register-KitTask -Name "Kit End of Day" `
    -Description "Kit's end-of-day wrap (port of com.USER.kit.eod)." `
    -Trigger @((New-ScheduledTaskTrigger -Weekly -DaysOfWeek @("Monday", "Tuesday", "Wednesday", "Thursday") -At "5:30pm"),
               (New-ScheduledTaskTrigger -Weekly -DaysOfWeek "Friday" -At "3:30pm")) `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "eod")

# --- Kit Meeting Prep: weekdays every 30 minutes, 07:00 to 18:00 (port of com.USER.kit.meetprep) ----
# A pure script, no Claude run: kit-meetprep makes prep packs for the meetings starting in the next 45
# minutes, from CALENDAR_JSON_CMD. Nothing runs while Kit is paused (kit-pause). A weekly trigger can't
# repeat by itself, so it borrows the repetition of a one-off trigger: every 30 minutes for 11 hours
# (and a minute, so 18:00 is included). The paths are in single quotes, which survive the task's command line.
if ($RegisterMeetprep) {
    $meetprepPy = Join-Path $KitHome ".install\shared\bin\kit-meetprep"
    $pausedFile = Join-Path $KitHome ".install\PAUSED"
    $meetprepTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "7:00am"
    $meetprepTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At "7:00am" `
        -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 11 -Minutes 1)).Repetition
    Register-KitTask -Name "Kit Meeting Prep" `
        -Description "Kit's meeting prep packs, made 45 minutes ahead with no model call (port of com.USER.kit.meetprep)." `
        -Trigger $meetprepTrigger `
        -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                      "`$env:PYTHONUTF8='1'; if (-not (Test-Path -LiteralPath '$pausedFile')) { if (Get-Command py -ErrorAction SilentlyContinue) { py -3 '$meetprepPy' --from-config --minutes 45 } else { python '$meetprepPy' --from-config --minutes 45 } }")
}

# --- Kit Backup: daily 12:30 (port of com.USER.kit.backup) ----------------------------------
# Runs kit-backup with the config's BACKUP_* settings. On Windows, encryption reads the passphrase
# from the environment variable named in BACKUP_KEY_ENV (no Keychain).
$backupPy = Join-Path $KitHome ".install\shared\bin\kit-backup"
Register-KitTask -Name "Kit Backup" `
    -Description "Kit's daily backup of its folder and history (port of com.USER.kit.backup)." `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "12:30pm") `
    -ActionArgs @("-NoProfile", "-WindowStyle", "Hidden", "-Command", "`"`$env:PYTHONUTF8='1'; python '$backupPy'`"")

# --- Kit Reminders Sync: every 15 minutes + at logon -----------------------------------------
# Mirrors com.USER.kit.sync (StartInterval 900, RunAtLoad true). A repeating "Once" trigger gives
# the 15-minute cadence; an "AtLogOn" trigger stands in for RunAtLoad.
$syncRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration ([TimeSpan]::MaxValue)
$syncAtLogon = New-ScheduledTaskTrigger -AtLogOn
Register-KitTask -Name "Kit Reminders Sync" `
    -Description "Kit's to-do <-> reminders sync (port of com.USER.kit.sync)." `
    -Trigger @($syncRepeat, $syncAtLogon) `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                  "`$env:PYTHONUTF8='1'; & { py -3 `"$SyncPy`" ; if (`$LASTEXITCODE -ne 0) { python `"$SyncPy`" } }")

# --- Kit Trade Journal: weekdays 16:20 (optional extra for a trading setup; no Mac plist) -----
if ($RegisterJournal) {
    Register-KitTask -Name "Kit Trade Journal" `
        -Description "Kit's post-close trade journal (run.sh documents 16:20; no Mac plist ships)." `
        -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "4:20pm") `
        -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "journal")
}

# --- Kit Login Check: daily 06:45 and 15:45, before the morning and afternoon runs -----------
$Preflight = Join-Path $KitHome ".install\platform\windows\morning\preflight.ps1"
Register-KitTask -Name "Kit Login Check" `
    -Description "Checks that Claude Code and Kit's connectors are signed in before the scheduled runs (port of com.USER.kit.preflight)." `
    -Trigger @((New-ScheduledTaskTrigger -Daily -At "6:45am"), (New-ScheduledTaskTrigger -Daily -At "3:45pm")) `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$Preflight`"")

Write-Host ""
Write-Host "Kit's scheduled tasks are registered under Task Scheduler folder '$TaskPath'."
Write-Host "List them:   Get-ScheduledTask -TaskPath '$TaskPath'"
Write-Host "Remove them: powershell -ExecutionPolicy Bypass -NoProfile -File unregister-tasks.ps1"
exit 0
