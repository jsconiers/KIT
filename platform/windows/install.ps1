# platform/windows/install.ps1: install Kit, your Claude Code agent, on this Windows PC.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Tested on Windows by .github/workflows/checks.yml on GitHub's Windows runners, under Windows
# PowerShell 5.1 and PowerShell 7: a fresh install, a reinstall, and the repair of an install whose
# files lost their access entries. The mail, calendar, and scheduled-task parts aren't tested there.
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
#   3. Confirm owner-only access on the kit home and its files:
#        icacls "$env:USERPROFILE\Claude\Agents\kit"
#      - expect only the current user, with (OI)(CI)(F), and no "(I)" inherited entries.
#        icacls "$env:USERPROFILE\Claude\Agents\kit\KIT.md"
#      - expect only the current user, with (I)(F): inherited from the kit home.
#      The installer checks this itself and stops with an error if Kit can't read a file.
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

# --- Folder privacy (NTFS-ACL equivalent of `chmod -R go-rwx`) --------------------------------
# The kit home gets exactly one access entry: full control for your account, inherited by
# everything inside it, and nothing inherited from above. Every file and folder inside is reset to
# take its access from the kit home and nothing else. Your account is named by its SID, so a
# local account with the same user name can't be picked by mistake.
# (Kit 1.4.0 applied the folder's grant to every file with /T. On a file an (OI)(CI) grant can't
# apply, so the files were left with no access entries at all: even their owner got "Access
# denied", and Kit stopped loading.)
$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User

function Invoke-Icacls([string[]]$IcaclsArgs) {
    # Run icacls and return its exit code and output, so each call is checked right away. Native
    # stderr would throw under "Stop" in Windows PowerShell 5.1, so relax that for the call.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & icacls @IcaclsArgs 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    [pscustomobject]@{ Code = $code; Output = (@($out) | Where-Object { $_ } | Select-Object -Last 3) -join " " }
}

function Protect-KitFolder([string]$dir) {
    # Lock $dir to your account and make everything inside inherit from it. Returns $null when it
    # worked, or what went wrong.
    $r = Invoke-Icacls @($dir, "/inheritance:r", "/grant:r", "*$($userSid.Value):(OI)(CI)F", "/C")
    if ($r.Code -ne 0) { return "locking $dir failed (icacls exit $($r.Code)): $($r.Output)" }
    $acl = Get-Acl -LiteralPath $dir
    foreach ($rule in $acl.GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier])) {
        $who = $rule.IdentityReference.Value
        if ($who -ne $userSid.Value) {     # any other entry set directly on the folder
            $r = Invoke-Icacls @($dir, "/remove", "*$who", "/C")
            if ($r.Code -ne 0) { return "removing $who from $dir failed (icacls exit $($r.Code)): $($r.Output)" }
        }
    }
    if (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1) {
        # Not /T on the folder itself: reset only what's inside, so it all inherits from $dir.
        $r = Invoke-Icacls @((Join-Path $dir "*"), "/reset", "/T", "/C", "/Q")
        if ($r.Code -ne 0) { return "resetting the files in $dir failed (icacls exit $($r.Code)): $($r.Output)" }
    }
    return $null
}

function Test-KitAccess([string]$dir) {
    # Open every file under $dir for reading, and check the folder's own entry. Returns the number
    # of files checked and a list of problems (empty when all is well).
    $problems = New-Object System.Collections.Generic.List[string]
    $listErrors = $null
    $files = @(Get-ChildItem -LiteralPath $dir -Recurse -Force -File -ErrorAction SilentlyContinue -ErrorVariable listErrors)
    foreach ($e in @($listErrors)) { if ($e) { $problems.Add("can't list $($e.TargetObject)") } }
    foreach ($f in $files) {
        try {
            [System.IO.File]::OpenRead($f.FullName).Dispose()
        } catch {
            $denied = $false
            for ($ex = $_.Exception; $ex; $ex = $ex.InnerException) {
                if ($ex -is [System.UnauthorizedAccessException]) { $denied = $true }
            }
            if ($denied) { $problems.Add("can't read $($f.FullName)") }   # (in use elsewhere isn't a problem)
        }
    }
    $acl = Get-Acl -LiteralPath $dir
    if (-not $acl.AreAccessRulesProtected) { $problems.Add("$dir still takes access from the folder above it") }
    $full = [System.Security.AccessControl.FileSystemRights]::FullControl
    $mine = $false
    foreach ($rule in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
        if ($rule.IdentityReference.Value -ne $userSid.Value) {
            $problems.Add("$dir also gives access to $($rule.IdentityReference.Value)")
        } elseif ($rule.AccessControlType -eq "Allow" -and ($rule.FileSystemRights -band $full) -eq $full) {
            $mine = $true
        }
    }
    if (-not $mine) { $problems.Add("$dir doesn't give your account full control") }
    [pscustomobject]@{ Files = $files.Count; Problems = $problems }
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
    Die "Python not found. Install Python 3.8+ from the work software catalogue, then run this installer again."
}

# Confirm it actually runs and is >= 3.8 (same gate as install.sh).
& $pyExe @pyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Die "Python didn't run, or it's older than 3.8. Install Python 3.8+ from the work software catalogue, then run this again."
}

# --- Sanity-check the package layout ---------------------------------------------------------
if (-not (Test-Path -LiteralPath $setup) -or -not (Test-Path -LiteralPath $kitDir -PathType Container)) {
    Die "run this from the unzipped kit-agent folder, or from %USERPROFILE%\Claude\Agents\kit\.install\platform\windows."
}

# Note (not fatal) if Claude Code isn't on PATH yet.
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "install: note: Claude Code (claude) is not on your PATH yet. Kit will be ready once it is."
}

# --- Repair an earlier install whose files Kit can't read ------------------------------------
# The setup steps below read the existing files, so first give an earlier install's files back to
# your account. This also repairs an install made by Kit 1.4.0's installer (see the note above).
if (Test-Path -LiteralPath $kitHome -PathType Container) {
    $problem = Protect-KitFolder $kitHome
    if ($problem) {
        Die "couldn't make Kit's existing files readable: $problem"
    }
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

# How the brief reaches you (asks only in an interactive window; change it later with kit-settings).
& $pyExe @pyArgs (Join-Path $root "shared\bin\kit-settings") setup
if ($LASTEXITCODE -ne 0) { Write-Host "install: note: settings skipped; run kit-settings setup later." }

# --- Make the kit home private (see Protect-KitFolder above) ---------------------------------
if (-not (Test-Path -LiteralPath $kitHome -PathType Container)) {
    Die "expected $kitHome after setup but didn't find it."
}
$problem = Protect-KitFolder $kitHome
if ($problem) {
    Die "couldn't make $kitHome private: $problem"
}

# --- Tool shims (kitmail, kitcal, and the shared commands) on PATH ---------------------------
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
    # The everyday commands from shared\bin (the Mac links the same ones into ~/.local/bin).
    # kit-outlook is macOS-only, so it has no shim here.
    $sharedBin = Join-Path $kitHome ".install\shared\bin"
    foreach ($tool in @("todo", "kit-settings", "kit-update", "kit-version", "kit-pause", "kit-backup",
                        "kit-retention", "kit-team", "kit-precedent", "kit-cost", "kit-queue",
                        "kit-models", "kit-labcheck", "kit-refarch", "kit-sysprofile", "kit-onepager", "kit-sizing", "kit-diagram-diff", "kit-diaglint", "kit-wins", "kit-oneonone", "kit-meetprep", "kit-triage", "kit-awaiting", "kit-plugin", "kit-quality", "kit-commitments", "kit-connect", "kit-evals", "kit-lifecycle", "kit-roadmap", "kit-metrics", "kit-project", "kit-delegate", "kit-run", "kit-audit-export", "kit-exceptions", "kit-pbc", "kit-holds", "kit-degraded", "kit-reliability", "kit-alerts", "kit-csf", "kit-controls", "kit-trace", "kit-decisions", "kit-stakeholders", "kit-viewpoints", "kit-coverage", "kit-questions", "kit-templatecheck", "kit-letter", "kit-expiry")) {
        $toolPy = Join-Path $sharedBin $tool
        if (Test-Path -LiteralPath $toolPy) {
            Set-Content -LiteralPath (Join-Path $binDir "$tool.cmd") -Encoding ASCII `
                -Value "@echo off`r`n$pyCmd `"$toolPy`" %*`r`n"
        }
    }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    if ($userPath -notlike "*$binDir*") {
        [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $binDir).TrimStart(";"), "User")
        Write-Host "install: added $binDir to your user PATH (open a new shell to pick it up)."
    }
} catch {
    Write-Host "install: note: couldn't create the command shims ($($_.Exception.Message)). You can run the tools with '$pyCmd <path>\kitmail.py' instead."
}

# --- Classic Outlook check -------------------------------------------------------------------
# The mail and calendar tools drive desktop Outlook over COM; the "new Outlook" and Outlook on
# the web do not expose the COM automation model.
if (-not (Test-Path "Registry::HKEY_CLASSES_ROOT\Outlook.Application")) {
    Write-Host "install: note: classic desktop Outlook was not detected. kitmail/kitcal need the"
    Write-Host "         classic Outlook client (COM); the new Outlook and web versions won't work."
}

# --- Check that Kit can read every file, and that only your account can open the kit home ------
# A Kit that can't read its own files doesn't load, and nothing else says so, so check before
# reporting success. One more repair pass if anything's wrong, then stop with the details.
$check = Test-KitAccess $kitHome
if ($check.Problems.Count -gt 0) {
    $null = Protect-KitFolder $kitHome
    $check = Test-KitAccess $kitHome
}
if ($check.Problems.Count -gt 0) {
    Write-Host "install: Kit's files aren't set up right, so Kit wouldn't load. $($check.Problems.Count) problem(s), first ones:"
    $check.Problems | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
    Write-Host "To fix by hand:  icacls `"$kitHome\*`" /reset /T /C /Q"
    Write-Host "then run this installer again."
    exit 1
}
Write-Host "install: checked $($check.Files) files: Kit can read them all, and only your account can open $kitHome."

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
