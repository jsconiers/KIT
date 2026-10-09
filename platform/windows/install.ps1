# platform/windows/install.ps1: install Kit, your Claude Code agent, on this Windows PC.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Mirror of platform/mac/install.sh. Everything Kit needs is copied into
# %USERPROFILE%\Claude\Agents\kit, including this installer, so the downloaded copy can be
# deleted afterward. Outside that folder it adds one line to %USERPROFILE%\.claude\CLAUDE.md
# and some entries to %USERPROFILE%\.claude\settings.json, after backing both up (kit_setup.py
# handles those edits cross-platform). Claude Code's auto memory is left alone.
# Safe to re-run: Kit's memory, queue, status, lessons, and preferences are never overwritten.
#
# ## Manual test (run these on a real Windows box)
#   1. powershell -ExecutionPolicy Bypass -File platform\windows\install.ps1
#      - expect "check"/"scaffold"/"activate" output, then the "Kit is installed" message.
#   2. Confirm the import line was added:
#        Select-String -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Pattern '@~/Claude/Agents/kit/KIT.md'
#      - expect one match, preceded by a "<!-- Kit, installed ... -->" comment line.
#   3. Confirm owner-only ACLs on the kit home:
#        icacls "$env:USERPROFILE\Claude\Agents\kit"
#      - expect only the current user listed with (F); no "Users" or "Everyone" entries, and
#        no "(I)" inherited entries.
#   4. Confirm the scaffold landed:
#        Test-Path "$env:USERPROFILE\Claude\Agents\kit\KIT.md"   # expect True
#   5. Remove again:
#        powershell -ExecutionPolicy Bypass -File platform\windows\uninstall.ps1
#      - re-run step 2 and expect zero matches.

$ErrorActionPreference = "Stop"

# --- Paths -----------------------------------------------------------------------------------
# $PSScriptRoot is platform\windows within the package; the repo root is two levels up.
$root     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$setup    = Join-Path $root "shared\kit_setup.py"
$kitDir   = Join-Path $root "kit"
$kitHome  = Join-Path $env:USERPROFILE "Claude\Agents\kit"

function Die([string]$msg) {
    Write-Host "install: $msg"
    exit 1
}

# --- Locate Python ---------------------------------------------------------------------------
# Prefer the Windows launcher "py -3"; fall back to "python". Keep the executable and its
# leading args separate so we can splat them on every call.
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
    Die "Python not found. Install Python 3.8+ from the ICE software catalogue, then run this installer again."
}

# Confirm it actually runs and is >= 3.8 (same gate as install.sh).
& $pyExe @pyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Die "Python didn't run, or it's older than 3.8. Install Python 3.8+ from the ICE software catalogue, then run this again."
}

# --- Sanity-check the package layout ---------------------------------------------------------
if (-not (Test-Path -LiteralPath $setup) -or -not (Test-Path -LiteralPath $kitDir -PathType Container)) {
    Die "run this from the unzipped kit-agent folder, or from %USERPROFILE%\Claude\Agents\kit\.install\platform\windows."
}

# Note (not fatal) if Claude Code isn't on PATH yet.
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "install: note: Claude Code (claude) is not on your PATH yet. Kit will be ready once it is."
}

# --- Run the cross-platform setup steps ------------------------------------------------------
# These edit %USERPROFILE%\.claude\CLAUDE.md and settings.json; kit_setup.py handles that and
# backs both up first. POSIX permission bits are skipped on Windows (os.name == "nt").
foreach ($step in @("check", "scaffold", "activate")) {
    & $pyExe @pyArgs $setup $step
    if ($LASTEXITCODE -ne 0) {
        Die "kit_setup.py $step failed (exit $LASTEXITCODE). Nothing further was changed."
    }
}

# --- Folder privacy (NTFS-ACL equivalent of `chmod -R go-rwx`) --------------------------------
# Strip inherited ACEs and grant full control to ONLY the current user, then drop the common
# broad groups so no one else on the machine can read Kit's files. /T applies to the existing
# tree, /C keeps going past any single-file error, /Q stays quiet.
if (Test-Path -LiteralPath $kitHome -PathType Container) {
    & icacls "$kitHome" /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" /T /C /Q | Out-Null
    # Best-effort removal of inherited broad principals (ignore "not found" style failures).
    & icacls "$kitHome" /remove:g "Users" "Everyone" "Authenticated Users" /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "install: note: couldn't fully lock down $kitHome with icacls. Check its permissions by hand."
    }
} else {
    Write-Host "install: note: expected $kitHome after scaffold but didn't find it; skipping the permission lock-down."
}

# --- Tool shims (kitmail / kitcal) on PATH ---------------------------------------------------
# Mirror the macOS build.sh step that symlinks the mail/calendar tools into ~/.local/bin.
# Create .cmd shims in a per-user bin dir and add it to the user PATH so Kit can invoke
# `kitmail` / `kitcal` directly. The tools live under .install after scaffold.
$pyCmd  = if ($pyExe -eq "py") { "py -3" } else { "python" }
$binDir = Join-Path $kitHome ".install\platform\windows\bin"
$mailPy = Join-Path $kitHome ".install\platform\windows\mail\kitmail.py"
$calPy  = Join-Path $kitHome ".install\platform\windows\calendar\kitcal.py"
try {
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    Set-Content -LiteralPath (Join-Path $binDir "kitmail.cmd") -Encoding ASCII `
        -Value "@echo off`r`n$pyCmd `"$mailPy`" %*`r`n"
    Set-Content -LiteralPath (Join-Path $binDir "kitcal.cmd") -Encoding ASCII `
        -Value "@echo off`r`n$pyCmd `"$calPy`" %*`r`n"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    if ($userPath -notlike "*$binDir*") {
        [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $binDir).TrimStart(";"), "User")
        Write-Host "install: added $binDir to your user PATH (open a new shell to pick it up)."
    }
} catch {
    Write-Host "install: note: couldn't create the kitmail/kitcal PATH shims ($($_.Exception.Message)). You can run the tools with '$pyCmd <path>\kitmail.py' instead."
}

# --- Classic Outlook check -------------------------------------------------------------------
# The mail and calendar tools drive desktop Outlook over COM; the "new Outlook" and Outlook on
# the web do not expose the COM automation model.
if (-not (Test-Path "Registry::HKEY_CLASSES_ROOT\Outlook.Application")) {
    Write-Host "install: note: classic desktop Outlook was not detected. kitmail/kitcal need the"
    Write-Host "         classic Outlook client (COM); the new Outlook and web versions won't work."
}

# --- Done ------------------------------------------------------------------------------------
$uninstall = Join-Path $kitHome ".install\platform\windows\uninstall.ps1"
$reinstall = Join-Path $kitHome ".install\platform\windows\install.ps1"
Write-Host ""
Write-Host "Kit is installed in $kitHome (only your account can open it)."
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Start Claude Code in any folder:   claude"
Write-Host "  2. Run /context and check that KIT.md is listed under Memory files."
Write-Host "  3. Say: Kit, introduce yourself."
Write-Host ""
Write-Host "To take Kit out of Claude Code:  powershell -ExecutionPolicy Bypass -File `"$uninstall`""
Write-Host "To put it back later:            powershell -ExecutionPolicy Bypass -File `"$reinstall`""
exit 0
