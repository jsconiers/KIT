# platform/windows/install.ps1: Windows installer for Kit (STUB).
# Windows support is not yet implemented. See PORTING.md in this folder for the plan.
$ErrorActionPreference = "Stop"

$py = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Host "python3 not found. Install Python 3.8+ from the ICE software catalogue, then re-run."
}

Write-Host ""
Write-Host "Kit's Windows support is not yet implemented."
Write-Host "The agent 'brain' (kit\) and the shared Python (shared\) are cross-platform already;"
Write-Host "the OS-integration layer (mail, calendar, reminders, scheduling, folder privacy) still"
Write-Host "needs a Windows implementation. See platform\windows\PORTING.md for the roadmap."
Write-Host ""
exit 0
