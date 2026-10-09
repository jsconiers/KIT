# unregister-tasks.ps1: remove Kit's scheduled tasks from Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -NoProfile -File unregister-tasks.ps1
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Removes exactly the tasks register-tasks.ps1 creates, under the "\Kit\" task folder. Kit's
# files and logs are left untouched. Safe to run even if some tasks are already gone.

$ErrorActionPreference = "Continue"

$TaskPath = "\Kit\"
$Names = @(
    "Kit Morning Brief",
    "Kit Post-Open Read",
    "Kit Weekly Review",
    "Kit Reminders Sync",
    "Kit Trade Journal"
)

foreach ($name in $Names) {
    $existing = Get-ScheduledTask -TaskName $name -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $name -TaskPath $TaskPath -Confirm:$false
        Write-Host "removed: $TaskPath$name"
    } else {
        Write-Host "not present: $TaskPath$name"
    }
}

# Best-effort removal of the now-empty "\Kit\" task folder (ignore if it is missing or shared).
try {
    $svc = New-Object -ComObject "Schedule.Service"
    $svc.Connect()
    $root = $svc.GetFolder("\")
    $root.DeleteFolder("Kit", 0)
    Write-Host "removed task folder: $TaskPath"
} catch {
    # Folder may not exist, may be non-empty, or the COM call may be unavailable; not fatal.
}

Write-Host ""
Write-Host "Kit's scheduled tasks are removed. Kit's files and logs were not touched."
exit 0
