# platform/windows/uninstall.ps1: take Kit out of Claude Code.
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Mirror of platform/mac/uninstall.sh. Removes Kit's line from
# %USERPROFILE%\.claude\CLAUDE.md and exactly the entries install added to
# %USERPROFILE%\.claude\settings.json (both backed up first by kit_setup.py). Kit's own files
# in %USERPROFILE%\Claude\Agents\kit are left in place.
#
# ## Manual test (run these on a real Windows box)
#   1. With Kit installed, run:
#        powershell -ExecutionPolicy Bypass -File platform\windows\uninstall.ps1
#      - expect the "Kit is out of Claude Code" style output from kit_setup.py.
#   2. Confirm the import line is gone:
#        Select-String -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Pattern '@~/Claude/Agents/kit/KIT.md'
#      - expect zero matches.
#   3. Confirm Kit's files remain:
#        Test-Path "$env:USERPROFILE\Claude\Agents\kit\KIT.md"   # expect True

$ErrorActionPreference = "Stop"

# $PSScriptRoot is platform\windows within the package; the repo root is two levels up.
$root    = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$setup   = Join-Path $root "shared\kit_setup.py"
$kitHome = Join-Path $env:USERPROFILE "Claude\Agents\kit"

# Locate Python: prefer "py -3", fall back to "python".
$pyExe  = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyExe  = "py"
    $pyArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyExe  = "python"
    $pyArgs = @()
}
if (-not $pyExe) {
    Write-Host "uninstall: Python not found."
    exit 1
}

& $pyExe @pyArgs $setup deactivate
if ($LASTEXITCODE -ne 0) {
    Write-Host "uninstall: kit_setup.py deactivate failed (exit $LASTEXITCODE)."
    exit 1
}

$reinstall = Join-Path $kitHome ".install\platform\windows\install.ps1"
Write-Host ""
Write-Host "Kit's files are still in $kitHome. To delete them too:"
Write-Host "  Remove-Item -Recurse -Force `"$kitHome`""
Write-Host "To put Kit back:  powershell -ExecutionPolicy Bypass -File `"$reinstall`""
exit 0
