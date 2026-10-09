# run.ps1: Kit's scheduled runs on Windows, started by Task Scheduler.
#
#   run.ps1            morning brief (weekdays 7:45, delivered by ~8:00)
#   run.ps1 open       post-open read (weekdays 9:45)
#   run.ps1 weekly     weekly review (Saturday 18:00)
#   run.ps1 journal    trade journal after the close (no delivery unless it fails)
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Faithful PowerShell port of platform/mac/morning/run.sh (the authoritative behavior):
# same modes, skip-days, once-per-day ".done" markers, a headless `claude -p` run with a
# ~1200s timeout, a short text file written by the agent, a pluggable delivery step, a
# dashboard refresh, and an auto-commit of the kit home when it is a git repo.
#
# To test a run without using up that day's run (mirrors the Mac test-run marker):
#   New-Item -ItemType File "$env:USERPROFILE\Claude\Agents\kit\.install\platform\windows\morning\test-run"
#   powershell -ExecutionPolicy Bypass -NoProfile -File run.ps1 morning   (or open, weekly)
#
# Settings live in .install\shared\morning\config (shared with the Mac, KEY="value" lines):
#   OWNER_NAME, SKIP_DAYS, BLOCK_TOOLS, and the Windows delivery keys:
#   DELIVERY_CHANNEL (toast|file|email|sms), DELIVERY_EMAIL_TO, DELIVERY_EMAIL_FROM,
#   DELIVERY_SMS_TO, DELIVERY_SMS_API_URL, DELIVERY_SMS_API_KEY_ENV.

param(
    [string]$Mode = "morning"
)

# Don't let a single non-terminating error abort the whole run; we handle failures explicitly
# and this job must be resilient when unattended.
$ErrorActionPreference = "Continue"

# --- Paths -----------------------------------------------------------------------------------
$KitHome  = Join-Path $env:USERPROFILE "Claude\Agents\kit"
$WinDir   = Join-Path $KitHome ".install\platform\windows\morning"  # windows runner assets (test-run marker)
$ShareDir = Join-Path $KitHome ".install\shared\morning"            # shared prompts + config
$LogDir   = Join-Path $KitHome ".install\logs"                      # OS-neutral run logs
$Today    = Get-Date -Format "yyyy-MM-dd"
$Log      = Join-Path $LogDir "$Today.log"

New-Item -ItemType Directory -Force -Path $LogDir, (Join-Path $KitHome "briefs"), (Join-Path $KitHome "journal") | Out-Null

function Write-Log([string]$msg) {
    # Append a line to the day's log; best-effort so a logging failure never aborts a run.
    try { Add-Content -LiteralPath $Log -Value $msg -Encoding UTF8 } catch {}
}

# --- Config ----------------------------------------------------------------------------------
# The config is shared with the Mac and written as shell assignments (KEY="value"). PowerShell
# can't source that, so parse KEY=VALUE lines ourselves, stripping optional quotes and comments.
function Read-Config([string]$path) {
    $cfg = @{}
    if (-not (Test-Path -LiteralPath $path)) { return $cfg }
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        $eq = $t.IndexOf("=")
        if ($eq -lt 1) { continue }
        $key = $t.Substring(0, $eq).Trim()
        $val = $t.Substring($eq + 1).Trim()
        # Strip a single pair of surrounding quotes (double or single).
        if ($val.Length -ge 2 -and
            (($val.StartsWith('"') -and $val.EndsWith('"')) -or
             ($val.StartsWith("'") -and $val.EndsWith("'")))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $cfg[$key] = $val
    }
    return $cfg
}

$Config = Read-Config (Join-Path $ShareDir "config")
function Cfg([string]$key, [string]$default = "") {
    if ($Config.ContainsKey($key) -and $Config[$key] -ne "") { return $Config[$key] }
    return $default
}

$OwnerName  = Cfg "OWNER_NAME" "the owner"
$SkipDays   = Cfg "SKIP_DAYS" ""
$BlockTools = Cfg "BLOCK_TOOLS" ""
$Channel    = (Cfg "DELIVERY_CHANNEL" "toast").ToLower()

# --- Locate Python (prefer the "py -3" launcher; fall back to "python") ----------------------
function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue)     { return @{ Exe = "py";     Args = @("-3") } }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @{ Exe = "python"; Args = @() } }
    return $null
}

# --- Mode -> prompt + text file --------------------------------------------------------------
switch ($Mode) {
    "open"    { $Prompt = Join-Path $ShareDir "prompt-open.md";    $TextRel = "briefs\open-text.txt" }
    "weekly"  { $Prompt = Join-Path $ShareDir "prompt-weekly.md";  $TextRel = "briefs\weekly-text.txt" }
    "journal" { $Prompt = Join-Path $ShareDir "prompt-journal.md"; $TextRel = "briefs\journal-text.txt" }
    default   { $Mode = "morning"; $Prompt = Join-Path $ShareDir "prompt.md"; $TextRel = "briefs\latest-text.txt" }
}
$Text = Join-Path $KitHome $TextRel

# Once-per-day marker: morning uses the bare date, the others suffix the mode (matches run.sh).
$Done = if ($Mode -eq "morning") { Join-Path $LogDir "$Today.done" }
        else                     { Join-Path $LogDir "$Today.$Mode.done" }

# ISO day-of-week: 1 = Monday ... 7 = Sunday (matches `date +%u`).
$dow = [int](Get-Date).DayOfWeek      # Sunday = 0 ... Saturday = 6
$IsoDow = if ($dow -eq 0) { 7 } else { $dow }
$Hour = (Get-Date).Hour

# The journal scores a finished session, so it never runs before the close, not even as a test.
if ($Mode -eq "journal" -and $Hour -lt 16) {
    Write-Log "== $(Get-Date) journal run skipped: before the close"
    exit 0
}

# --- Test-run marker vs. skip-days / once-per-day guards --------------------------------------
$TestMarker = Join-Path $WinDir "test-run"
$Test = ""
if (Test-Path -LiteralPath $TestMarker) {
    $Test = "[Test] "
    Remove-Item -LiteralPath $TestMarker -Force -ErrorAction SilentlyContinue
} else {
    # Skip the days listed in SKIP_DAYS; the weekly review keeps its own schedule.
    if ($Mode -ne "weekly" -and $SkipDays.Trim() -ne "") {
        foreach ($d in ($SkipDays -split '\s+')) {
            if ($d -ne "" -and $d -eq "$IsoDow") { exit 0 }
        }
    }
    # One run of each kind a day.
    if (Test-Path -LiteralPath $Done) { exit 0 }
    # No post-open read once it's stale.
    if ($Mode -eq "open" -and $Hour -ge 12) {
        Write-Log "== $(Get-Date) open run skipped: too late in the day"
        exit 0
    }
}

# --- Delivery (pluggable; default Windows toast, file fallback) ------------------------------
# Writes the brief to the kit briefs folder and the day's log so it is never lost, then returns
# $true. $false is reserved for a hard failure (even the file fallback couldn't be written), in
# which case the caller keeps the unsent copy and does NOT mark the day done so it retries.
function Invoke-FileFallback([string]$message, [string]$reason) {
    try {
        $stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
        $path  = Join-Path $KitHome ("briefs\delivered-$Mode-$stamp.txt")
        Set-Content -LiteralPath $path -Value $message -Encoding UTF8
        Write-Log "== delivery: file fallback ($reason) -> $path"
        return $true
    } catch {
        Write-Log "== delivery: file fallback FAILED: $($_.Exception.Message)"
        return $false
    }
}

function Send-Toast([string]$message) {
    # BurntToast is an optional module (Install-Module BurntToast). Scheduled tasks often run in
    # a non-interactive session where no toast can appear, so treat any failure as "fall back".
    if (-not (Get-Module -ListAvailable -Name BurntToast)) {
        Write-Log "== delivery: BurntToast module not installed"
        return $false
    }
    try {
        Import-Module BurntToast -ErrorAction Stop
        New-BurntToastNotification -Text "Kit", $message | Out-Null
        Write-Log "== delivery: toast shown"
        return $true
    } catch {
        Write-Log "== delivery: toast FAILED: $($_.Exception.Message)"
        return $false
    }
}

# ---- HOOK: email delivery -------------------------------------------------------------------
# Reuses the Windows mail tool (platform/windows/mail/kitmail.py) to open a DRAFT addressed to
# the owner. kitmail never sends on its own, so this opens a draft for manual review/send -- it
# does not silently email anyone. For a true unattended email you would add an SMTP/Graph send
# here instead. Configure with DELIVERY_EMAIL_TO (required) and DELIVERY_EMAIL_FROM (optional).
function Send-Email([string]$message) {
    $to = Cfg "DELIVERY_EMAIL_TO" ""
    if ($to -eq "") { Write-Log "== delivery: email channel but DELIVERY_EMAIL_TO is unset"; return $false }
    $py = Resolve-Python
    if ($null -eq $py) { Write-Log "== delivery: email channel but Python not found"; return $false }
    $kitmail = Join-Path $KitHome ".install\platform\windows\mail\kitmail.py"
    if (-not (Test-Path -LiteralPath $kitmail)) { Write-Log "== delivery: kitmail.py not found at $kitmail"; return $false }
    try {
        # Pass the body via a temp file so newlines/quoting survive (kitmail supports --body-file).
        $bodyFile = Join-Path $LogDir "delivery-body-$Mode.txt"
        Set-Content -LiteralPath $bodyFile -Value $message -Encoding UTF8
        $args = @($kitmail, "draft", "--to", $to, "--subject", "Kit's $Mode brief", "--body-file", $bodyFile)
        $from = Cfg "DELIVERY_EMAIL_FROM" ""
        if ($from -ne "") { $args += @("--from", $from) }
        & $py.Exe @($py.Args + $args) 2>&1 | ForEach-Object { Write-Log "   kitmail: $_" }
        if ($LASTEXITCODE -eq 0) { Write-Log "== delivery: email draft opened for $to"; return $true }
        Write-Log "== delivery: email draft FAILED (exit $LASTEXITCODE)"
        return $false
    } catch {
        Write-Log "== delivery: email FAILED: $($_.Exception.Message)"
        return $false
    }
}

# ---- HOOK: SMS-API delivery -----------------------------------------------------------------
# Intentionally a stub: wire your SMS gateway (Twilio, etc.) here. Per work policy the API key is
# referenced by the NAME of an environment variable (DELIVERY_SMS_API_KEY_ENV), never stored in
# the config and never written to disk. Fill in the HTTP call for your provider, then return
# $true on a confirmed send.
function Send-Sms([string]$message) {
    $to     = Cfg "DELIVERY_SMS_TO" ""
    $apiUrl = Cfg "DELIVERY_SMS_API_URL" ""
    $keyEnv = Cfg "DELIVERY_SMS_API_KEY_ENV" ""
    if ($to -eq "" -or $apiUrl -eq "" -or $keyEnv -eq "") {
        Write-Log "== delivery: sms channel not configured (need DELIVERY_SMS_TO, DELIVERY_SMS_API_URL, DELIVERY_SMS_API_KEY_ENV)"
        return $false
    }
    $apiKey = [Environment]::GetEnvironmentVariable($keyEnv)
    if ([string]::IsNullOrEmpty($apiKey)) {
        Write-Log "== delivery: sms API key env var '$keyEnv' is not set"
        return $false
    }
    # ----------------------------------------------------------------------------------------
    # TODO (hook): implement the actual send for your SMS provider, e.g.:
    #   $body = @{ To = $to; Body = $message }
    #   Invoke-RestMethod -Method Post -Uri $apiUrl -Body $body `
    #       -Headers @{ Authorization = "Bearer $apiKey" }
    # Return $true only on a confirmed send. Until implemented, report "not sent" so the brief
    # falls back to a file and is not lost.
    # ----------------------------------------------------------------------------------------
    Write-Log "== delivery: sms hook present but not implemented; falling back"
    return $false
}

function Send-Brief([string]$message) {
    # Dispatch on the configured channel; on any channel failure, fall back to a file so the
    # brief is never lost. Returns $true if the brief reached the user or was saved to a file.
    $ok = $false
    switch ($Channel) {
        "file"  { return (Invoke-FileFallback $message "channel=file") }
        "email" { $ok = Send-Email $message }
        "sms"   { $ok = Send-Sms $message }
        default { $Channel = "toast"; $ok = Send-Toast $message }   # default: toast
    }
    if ($ok) { return $true }
    return (Invoke-FileFallback $message "channel=$Channel unavailable")
}

# --- The run ---------------------------------------------------------------------------------
Set-Location -LiteralPath $KitHome
Remove-Item -LiteralPath $Text -Force -ErrorAction SilentlyContinue

if ($Mode -eq "morning" -or $Mode -eq "weekly") {
    $py = Resolve-Python
    if ($null -ne $py) {
        $doctor = Join-Path $KitHome ".install\shared\doctor.py"
        if (Test-Path -LiteralPath $doctor) {
            & $py.Exe @($py.Args + @($doctor, "--brief")) *> (Join-Path $KitHome "briefs\health.txt")
        }
    }
}

# Build the prompt (substitute {{OWNER}}) and the claude argument list.
$promptText = (Get-Content -LiteralPath $Prompt -Raw) -replace '\{\{OWNER\}\}', $OwnerName
# claude tool-permission globs use forward slashes; build them from the real kit home.
$kitFwd      = $KitHome -replace '\\', '/'
$briefGlob   = "Edit($kitFwd/briefs/**)"
$journalGlob = "Edit($kitFwd/journal/**)"
$claudeArgs  = @("-p", $promptText, "--output-format", "text",
                 "--allowedTools", "Bash(date:*)", $briefGlob, $journalGlob)
if ($BlockTools.Trim() -ne "") {
    $claudeArgs += "--disallowedTools"
    $claudeArgs += ($BlockTools -split '\s+' | Where-Object { $_ -ne "" })
}

Write-Log "== $(Get-Date) start $Mode $Test"

# Run claude headless with a ~1200s timeout via a background job (mirrors the Mac `alarm 1200`).
$rc = 0
$job = Start-Job -ScriptBlock {
    param($claudeArgs, $workDir)
    Set-Location -LiteralPath $workDir
    # Capture stdout+stderr; the job's output becomes the transcript we log below.
    & claude @claudeArgs 2>&1
    exit $LASTEXITCODE
} -ArgumentList $claudeArgs, $KitHome
# Note: -ArgumentList unrolls one level, so the claudeArgs array arrives intact as param 1.

if (Wait-Job $job -Timeout 1200) {
    $out = Receive-Job $job
    $rc  = if ($null -ne $job.ChildJobs[0].JobStateInfo.Reason) { 1 } else { 0 }
    # Prefer the real child exit code when PowerShell surfaced one.
    if ($job.State -eq "Failed") { $rc = 1 }
    foreach ($line in @($out)) { Write-Log "$line" }
} else {
    Stop-Job $job -ErrorAction SilentlyContinue
    $out = Receive-Job $job -ErrorAction SilentlyContinue
    foreach ($line in @($out)) { Write-Log "$line" }
    $rc = 124   # conventional timeout exit code
    Write-Log "== $(Get-Date) $Mode timed out after 1200s"
}
Remove-Job $job -Force -ErrorAction SilentlyContinue

Write-Log "== $(Get-Date) end $Mode rc=$rc"

# --- Decide what to deliver (mirrors run.sh's QUIET / non-empty / empty branches) ------------
$quiet = ""
if (Test-Path -LiteralPath $Text) { $quiet = (Get-Content -LiteralPath $Text -Raw -ErrorAction SilentlyContinue) }
if ($null -eq $quiet) { $quiet = "" }
$quietTrim = $quiet.Trim()

if ($quietTrim -eq "MARKET CLOSED" -or $quietTrim -eq "NO TEXT") {
    Write-Log "== ${quietTrim}: no delivery"
    if ($Test -eq "") { New-Item -ItemType File -Force -Path $Done | Out-Null }
} elseif ($quietTrim -ne "") {
    if (Send-Brief "$Test$quiet") {
        if ($Test -eq "") { New-Item -ItemType File -Force -Path $Done | Out-Null }
        Remove-Item -LiteralPath (Join-Path $KitHome "briefs\unsent-$Mode.txt") -Force -ErrorAction SilentlyContinue
        Write-Log "== delivered"
    } else {
        Copy-Item -LiteralPath $Text -Destination (Join-Path $KitHome "briefs\unsent-$Mode.txt") -Force -ErrorAction SilentlyContinue
        Write-Log "== delivery failed; kept unsent copy"
    }
} else {
    $null = Send-Brief "${Test}Kit's $Mode run didn't finish (rc=$rc). Log: $Log"
    Write-Log "== sent failure notice"
}

# --- Save the day's changes to Kit's private local history, then refresh the dashboard --------
if (Test-Path -LiteralPath (Join-Path $KitHome ".git")) {
    try {
        & git -C $KitHome add -A 2>&1 | Out-Null
        & git -C $KitHome commit -qm "auto: $Mode run $Today" 2>&1 | Out-Null
    } catch { Write-Log "== git auto-commit skipped: $($_.Exception.Message)" }
}

$dashboard = Join-Path $KitHome ".install\shared\dashboard.py"
if (Test-Path -LiteralPath $dashboard) {
    $py = Resolve-Python
    if ($null -ne $py) { & $py.Exe @($py.Args + @($dashboard)) *> $null }
}

exit 0
