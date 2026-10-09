# register-tasks.ps1: create Kit's scheduled tasks in Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -NoProfile -File register-tasks.ps1
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Replaces the four macOS launchd plists with Task Scheduler tasks, each invoking run.ps1 with
# the matching mode (and the sync task invoking the Windows reminders sync). Schedules mirror
# the plists exactly:
#
#   Kit Morning Brief     weekdays (Mon-Fri)  07:45   -> run.ps1 morning
#   Kit Post-Open Read    weekdays (Mon-Fri)  09:45   -> run.ps1 open
#   Kit Weekly Review     Saturday            18:00   -> run.ps1 weekly
#   Kit Reminders Sync    every 15 min + at logon     -> reminders_sync_win.py
#   Kit Trade Journal     weekdays (Mon-Fri)  16:20   -> run.ps1 journal   (optional; see note)
#
# The journal task has no launchd plist on the Mac (run.sh documents a 16:20 journal run but no
# plist ships for it). run.ps1 fully supports journal mode, so we register it too for parity;
# set $RegisterJournal = $false below to skip it.
#
# Tasks run as the current user, only when that user is logged on (launchd runs in the user's
# GUI session; so do these). StartWhenAvailable catches runs missed while the machine was off,
# which is the closest match to launchd replaying missed StartCalendarInterval jobs.

$ErrorActionPreference = "Stop"

$RegisterJournal = $true   # set $false to skip the 16:20 trade-journal task

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
# Give a run room to finish (claude timeout is ~1200s; allow some headroom).
$settings.ExecutionTimeLimit = "PT1H"

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

# --- Kit Post-Open Read: weekdays 09:45 ------------------------------------------------------
Register-KitTask -Name "Kit Post-Open Read" `
    -Description "Kit's post-open read (port of com.USER.kit.open)." `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "9:45am") `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "open")

# --- Kit Weekly Review: Saturday 18:00 -------------------------------------------------------
Register-KitTask -Name "Kit Weekly Review" `
    -Description "Kit's weekly review (port of com.USER.kit.weekly)." `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek "Saturday" -At "6:00pm") `
    -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "weekly")

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
                  "& { py -3 `"$SyncPy`" ; if (`$LASTEXITCODE -ne 0) { python `"$SyncPy`" } }")

# --- Kit Trade Journal: weekdays 16:20 (optional; no Mac plist) ------------------------------
if ($RegisterJournal) {
    Register-KitTask -Name "Kit Trade Journal" `
        -Description "Kit's post-close trade journal (run.sh documents 16:20; no Mac plist ships)." `
        -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "4:20pm") `
        -ActionArgs @("-ExecutionPolicy", "Bypass", "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$RunPs1`"", "journal")
}

Write-Host ""
Write-Host "Kit's scheduled tasks are registered under Task Scheduler folder '$TaskPath'."
Write-Host "List them:   Get-ScheduledTask -TaskPath '$TaskPath'"
Write-Host "Remove them: powershell -ExecutionPolicy Bypass -NoProfile -File unregister-tasks.ps1"
exit 0
