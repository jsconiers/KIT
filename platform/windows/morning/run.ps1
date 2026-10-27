# run.ps1: Kit's scheduled runs on Windows, started by Task Scheduler.
#
#   run.ps1            morning brief (weekdays 7:45, delivered by ~8:00)
#   run.ps1 weekly     weekly review (Monday 6:30, so it finishes before the morning brief)
#   run.ps1 worklist   proposed work list for the owner to approve (Monday to Thursday 9:00)
#   run.ps1 open       post-open read (weekdays 9:45)        optional extra for a trading setup
#   run.ps1 journal    trade journal after the close         optional extra for a trading setup
#                      (no delivery unless it fails)
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Faithful PowerShell port of platform/mac/morning/run.sh (the authoritative behavior):
# same modes, skip-days, once-per-day ".done" markers, the kit-pause kill switch, the kit-cost
# budget guard (with degraded mode: at the stop level, or when the morning run fails or times out,
# kit-degraded writes the brief with no model call; DEGRADED_MODE="off" turns it off),
# and one automatic retry after a failure that looks transient (RETRY_ON, RETRY_DELAY),
# a headless `claude -p` run with JSON output (its cost goes to the kit-cost ledger),
# the model from models.env (kit-models apply), a time limit per kind of run, one run at a time
# (a lock), a short text file written by the agent, a pluggable delivery step, a dashboard
# refresh, and an auto-commit of the kit home when it is a git repo.
#
# Not ported: the Outlook check before a run (kit-outlook is macOS-only and reports "skipped"
# here), so on Windows calendar and mail fail the old way if Outlook doesn't answer.
#
# To test a run without using up that day's run (mirrors the Mac test-run marker):
#   New-Item -ItemType File "$env:USERPROFILE\Claude\Agents\kit\.install\platform\windows\morning\test-run"
#   powershell -ExecutionPolicy Bypass -NoProfile -File run.ps1 morning   (or open, weekly)
#
# Settings live in .install\shared\morning\config (shared with the Mac, KEY="value" lines):
#   OWNER_NAME, SKIP_DAYS, BLOCK_TOOLS, ALLOW_TOOLS, ALLOW_TOOLS_WEEKLY, the weekly demand refresh
#   (DEMAND_REFRESH, DEMAND_SERVER, DEMAND_TOOLS, DEMAND_REGISTER_DIR), the monthly regulatory watch
#   (REG_WATCH, REG_WATCH_WHEN, REG_WATCH_MIN_LEFT), the connector outage alert
#   (CONNECTOR_FAIL_STREAK), the run and cost alerts (RUN_ALERTS, RUN_ALERTS_TIMEOUT, RUN_FAIL_STREAK,
#   RUN_WINDOW_<MODE>, COST_ALERT_PROJECTION, COST_SPIKE_FACTOR; read by run_alerts.py), the time limits
#   RUN_TIMEOUT (1200 s), RUN_TIMEOUT_WEEKLY (3000), RUN_TIMEOUT_WORKLIST (900), RUN_LOCK_WAIT
#   (1800), the budget keys COST_BUDGET_MONTHLY, COST_STOP_PCT, COST_ESSENTIAL_MODES, and the
#   delivery keys:
#   DELIVERY (space-separated: local | outlook-drafts | outlook-review | sms), DELIVERY_EMAIL_TO,
#   and for the legacy sms hook DELIVERY_SMS_TO, DELIVERY_SMS_API_URL, DELIVERY_SMS_API_KEY_ENV.
#   Delivery itself is shared/deliver.py, which never sends mail. The older DELIVERY_CHANNEL
#   (toast|file|email|sms) still works when DELIVERY is unset: toast and file map to local,
#   email maps to outlook-review, sms to sms.

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
$AllowTools = Cfg "ALLOW_TOOLS" ""
$AllowToolsWeekly = Cfg "ALLOW_TOOLS_WEEKLY" ""
# Delivery channels for shared/deliver.py. DELIVERY wins; otherwise map the legacy
# DELIVERY_CHANNEL (toast -> local, file -> local, email -> outlook-review, sms -> sms).
$Delivery   = (Cfg "DELIVERY" "").ToLower()
if ($Delivery.Trim() -eq "") {
    switch ((Cfg "DELIVERY_CHANNEL" "").ToLower()) {
        "email" { $Delivery = "outlook-review" }
        "sms"   { $Delivery = "sms" }
        default { $Delivery = "local" }   # toast, file, or unset
    }
}

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
    "worklist" { $Prompt = Join-Path $ShareDir "prompt-worklist.md"; $TextRel = "briefs\worklist-text.txt" }
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

# Kill switch: while kit-pause is on, no scheduled run starts (the test-run marker is left alone).
$PausedFile = Join-Path $KitHome ".install\PAUSED"
if (Test-Path -LiteralPath $PausedFile) {
    $why = (Get-Content -LiteralPath $PausedFile -TotalCount 1 -ErrorAction SilentlyContinue)
    Write-Log "== $(Get-Date) $Mode run skipped: Kit is paused ($why); kit-pause resume to restart"
    exit 0
}

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

# --- Delivery (shared/deliver.py, with a file fallback) --------------------------------------
# deliver.py handles every channel (see its header): local notification + dashboard, Outlook
# drafts (saved, or opened for review; never sent), and the legacy sms hook. If it can't run or
# no channel works, the message is written to a file so it is never lost. Send-Brief returns
# $false only when even the file fallback failed; the caller then keeps the unsent copy and does
# NOT mark the day done, so it retries.
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

function Send-Brief([string]$textFile, [bool]$withBrief = $true) {
    $message = Get-Content -LiteralPath $textFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $message) { $message = "" }
    $py = Resolve-Python
    $deliver = Join-Path $KitHome ".install\shared\deliver.py"
    if ($null -eq $py -or -not (Test-Path -LiteralPath $deliver)) {
        return (Invoke-FileFallback "$Test$message" "Python or deliver.py not found")
    }
    $dargs = @($deliver, "--mode", $Mode, "--text", $textFile)
    # With DELIVERY_PERSONAL / DELIVERY_WORK set, deliver.py routes each side itself.
    if ((Cfg "DELIVERY_PERSONAL" "") -eq "" -and (Cfg "DELIVERY_WORK" "") -eq "") {
        $dargs += @("--channels", $Delivery)
    }
    if ($withBrief) {
        $briefName = switch ($Mode) {
            "weekly"   { "weekly-$Today.md" }
            "worklist" { "worklist-$Today.md" }
            "journal"  { "" }
            default   { "$Today.md" }      # morning and open share the day's brief
        }
        if ($briefName -ne "") {
            $briefPath = Join-Path $KitHome "briefs\$briefName"
            if (Test-Path -LiteralPath $briefPath) { $dargs += @("--brief", $briefPath) }
        }
    }
    if ($Test -ne "") { $dargs += "--test" }
    & $py.Exe @($py.Args + $dargs) 2>&1 | ForEach-Object { Write-Log "   $_" }
    if ($LASTEXITCODE -eq 0) { return $true }
    Write-Log "== delivery: deliver.py found no working channel (exit $LASTEXITCODE)"
    return (Invoke-FileFallback "$Test$message" "channels '$Delivery' unavailable")
}

# --- The run ---------------------------------------------------------------------------------
Set-Location -LiteralPath $KitHome
Remove-Item -LiteralPath $Text -Force -ErrorAction SilentlyContinue
foreach ($side in @("work", "personal")) {   # the split texts, so an old one is never resent
    Remove-Item -LiteralPath ($Text -replace '\.txt$', "-$side.txt") -Force -ErrorAction SilentlyContinue
}

# Run and cost alerts (run_alerts.py): from kit-reliability's run outcomes and kit-cost's ledger, a
# run type failing RUN_FAIL_STREAK times running (default 2) or overdue past its RUN_WINDOW_<MODE>,
# a month projected over the warning level, spend over the stop level, or (with no budget) a cost
# spike over COST_SPIKE_FACTOR x the 14-day median each get one [work] queue item for the owner and a
# red dashboard banner (briefs\alerts.json); the next success, or the month's end, clears them. It
# runs at the end of every run and before the morning and weekly model runs, is stopped after
# RUN_ALERTS_TIMEOUT seconds (default 60), never fails the run, and RUN_ALERTS="off" skips it.
function Invoke-RunAlerts([string[]]$extra = @()) {
    if ((Cfg "RUN_ALERTS" "on") -eq "off") { return }
    $raPy = Join-Path $ShareDir "run_alerts.py"
    $py = Resolve-Python
    if ($null -eq $py -or -not (Test-Path -LiteralPath $raPy)) { return }
    try {
        $limit = [int](Cfg "RUN_ALERTS_TIMEOUT" "60")
        $argList = @($py.Args + @("`"$raPy`"", "--kit", "`"$KitHome`"", "--no-dashboard") + $extra)
        $errFile = Join-Path $LogDir ".run-alerts-$PID.err"
        $p = Start-Process -FilePath $py.Exe -ArgumentList $argList -NoNewWindow -PassThru `
            -RedirectStandardOutput (Join-Path $LogDir ".run-alerts-$PID.out") -RedirectStandardError $errFile
        if (-not $p.WaitForExit($limit * 1000)) {
            try { $p.Kill() } catch {}
            Write-Log "== $(Get-Date) run alerts stopped after $limit s"
        }
        if (Test-Path -LiteralPath $errFile) {
            Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Log "$_" }
        }
        Remove-Item -LiteralPath $errFile, (Join-Path $LogDir ".run-alerts-$PID.out") -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Log "== run alerts skipped: $($_.Exception.Message)"
    }
}

# Budget guard (kit-cost): at the stop level only the essential runs go ahead; the others skip, with
# one notice a day. Without a budget, or without kit-cost, every run goes ahead.
$CostLevel = "ok"; $CostPct = ""
$kitCost = Join-Path $KitHome ".install\shared\bin\kit-cost"
$pyc = Resolve-Python
if ($null -ne $pyc -and (Test-Path -LiteralPath $kitCost)) {
    $costLine = (& $pyc.Exe @($pyc.Args + @($kitCost, "check", "--mode", $Mode)) 2>$null | Select-Object -First 1)
    if ($costLine) {
        $parts = "$costLine" -split ' '
        if ($parts[0] -in @("ok", "warn", "stop")) { $CostLevel = $parts[0] }
        if ($parts.Count -gt 1) { $CostPct = $parts[1].TrimEnd(';') }
    }
    $essential = (Cfg "COST_ESSENTIAL_MODES" "morning") -split '\s+'
    if ($CostLevel -eq "stop" -and $essential -notcontains $Mode) {
        Write-Log "== $(Get-Date) $Mode run skipped: $CostPct of the monthly budget used (stop at $(Cfg 'COST_STOP_PCT' '95')%)"
        $noticeMark = Join-Path $LogDir "$Today.cost-notice"
        if (-not (Test-Path -LiteralPath $noticeMark)) {
            $notice = Join-Path $LogDir "cost-notice.txt"
            Set-Content -LiteralPath $notice -Encoding UTF8 -Value "Kit budget: $CostPct of this month's budget is used, so Kit skipped its $Mode run. The morning brief still runs. See: kit-cost"
            if (Send-Brief $notice $false) { New-Item -ItemType File -Force -Path $noticeMark | Out-Null }
        }
        Invoke-RunAlerts @("--only", "cost")
        exit 0
    }
}

# Degraded mode: at the stop level the morning brief is written from Kit's files, with no model call.
$kitDegraded = Join-Path $KitHome ".install\shared\bin\kit-degraded"
$DegradedOn = (Cfg "DEGRADED_MODE" "on") -ne "off"
$DegradedReason = ""
if ($Mode -eq "morning" -and $CostLevel -eq "stop" -and $DegradedOn -and (Test-Path -LiteralPath $kitDegraded)) {
    $DegradedReason = "$CostPct of this month's budget is used (stop at $(Cfg 'COST_STOP_PCT' '95')%)"
}

if ($Mode -eq "morning" -or $Mode -eq "weekly") {
    $py = Resolve-Python
    if ($null -ne $py) {
        $doctor = Join-Path $KitHome ".install\shared\doctor.py"
        if (Test-Path -LiteralPath $doctor) {
            & $py.Exe @($py.Args + @($doctor, "--brief")) *> (Join-Path $KitHome "briefs\health.txt")
        }
        $audit = Join-Path $KitHome ".install\shared\bin\kit-audit"
        if (Test-Path -LiteralPath $audit) {
            $auditMode = if ($Mode -eq "weekly") { "--weekly" } else { "--daily" }
            & $py.Exe @($py.Args + @($audit, $auditMode)) *> $null
        }
    }
}

# Connector health (morning only): kit-connect test, with no read call and so no model cost, gives
# one PASS/FAIL line per server for the top of the brief. connector_health.py stops it after
# CONNECTOR_CHECK_TIMEOUT seconds (default 120) and never fails the run; CONNECTOR_CHECK="off" skips it.
# It keeps a history (briefs\connectors-history.jsonl), and when a server fails CONNECTOR_FAIL_STREAK
# mornings running (default 2) it adds one [work] queue item for the owner and raises the dashboard's
# connector-outage banner (briefs\connectors-alerts.json); a passing check clears it.
$ConnectLine = ""
$connHealth = Join-Path $ShareDir "connector_health.py"
if ($Mode -eq "morning" -and (Cfg "CONNECTOR_CHECK" "on") -ne "off" -and (Test-Path -LiteralPath $connHealth)) {
    $connOut = Join-Path $KitHome "briefs\connectors.txt"
    try {
        Remove-Item -LiteralPath $connOut -Force -ErrorAction SilentlyContinue
        $connPy = Resolve-Python
        if ($null -ne $connPy) {
            & $connPy.Exe @($connPy.Args + @($connHealth, "--timeout", (Cfg "CONNECTOR_CHECK_TIMEOUT" "120"),
                "--streak", (Cfg "CONNECTOR_FAIL_STREAK" "2"), "--kit", $KitHome, "--out", $connOut)) *> $null
        }
        if (Test-Path -LiteralPath $connOut) {
            $ConnectLine = ((Get-Content -LiteralPath $connOut -TotalCount 1) -join "").Trim()
        }
    } catch {
        $ConnectLine = ""
    }
    if ($ConnectLine -ne "") { Write-Log "== $(Get-Date) $ConnectLine" }
}
# Open run and cost alerts for the top of the morning brief and the weekly review (recomputed now).
$AlertLines = ""
if ($Mode -eq "morning" -or $Mode -eq "weekly") {
    $alertsOut = Join-Path $KitHome "briefs\alerts.txt"
    Remove-Item -LiteralPath $alertsOut -Force -ErrorAction SilentlyContinue
    Invoke-RunAlerts @("--out", "`"$alertsOut`"")
    if (Test-Path -LiteralPath $alertsOut) {
        $AlertLines = ((Get-Content -LiteralPath $alertsOut -Encoding UTF8 -ErrorAction SilentlyContinue) -join "`n").Trim()
    }
}

# Build the prompt (substitute {{OWNER}}) and the claude argument list.
$promptText = (Get-Content -LiteralPath $Prompt -Raw) -replace '\{\{OWNER\}\}', $OwnerName
if ($Mode -eq "morning" -or $Mode -eq "weekly") {
    # Records retention: show active legal holds at the top of the brief.
    $retention = Join-Path $KitHome ".install\shared\bin\kit-retention"
    if ($null -ne $pyc -and (Test-Path -LiteralPath $retention)) {
        $holds = ((& $pyc.Exe @($pyc.Args + @($retention, "holds", "--brief")) 2>$null) -join " ").Trim()
        if ($holds -ne "") {
            $promptText += "`n`nActive legal holds (nothing in these projects may be deleted, moved, or rewritten; list them in a `"Legal holds`" section near the top of the brief, by project name only): $holds"
        }
    }
    if ($AlertLines -ne "") {
        $promptText += "`n`nOpen alerts (kit-alerts): put each of these lines, as written, near the top of the brief (below the connector line, if there is one), and add `"Alerts: `" plus the number open to the health problems at the top of the text:`n$AlertLines"
    }
    if ($ConnectLine -ne "") {
        $promptText += "`n`nConnector check before this run (kit-connect test): put this line, as written, at the top of the brief (below the Audit issue section, if there is one), and if any server says FAIL, add `"Connectors: `" plus the failing server names to the health problems at the top of the text: $ConnectLine"
    }
}
if ($CostLevel -eq "warn" -or $CostLevel -eq "stop") {
    $promptText += "`n`nBudget: $CostPct of this month's budget for Kit's scheduled runs is used. Add the line `"Budget: $CostPct used`" to the health section of what you write and as the last line before the closing line of every short text."
    if ($Mode -eq "weekly") {
        $promptText += " Keep this run lean: skip the horizon scan's researcher call (list the due items only) and the optional parts of the monthly retrospective (keep only the three most important points)."
    }
}
# Time limit for this run, in seconds. The weekly review does the most, so it gets longer.
$Timeout = switch ($Mode) {
    "weekly"   { [int](Cfg "RUN_TIMEOUT_WEEKLY" "3000") }
    "worklist" { [int](Cfg "RUN_TIMEOUT_WORKLIST" "900") }
    default    { [int](Cfg "RUN_TIMEOUT" "1200") }
}

# Weekly demand refresh (DEMAND_REFRESH="on" in the config; off by default): the weekly review has
# the demand tracker re-check the demands in its register through its connector, read-only and under
# its connector-guard hooks. demand_refresh.py (no connector or model call) checks DEMAND_SERVER,
# DEMAND_TOOLS (or the server's allow_tools in connector-guard.json, kept only if the guard would
# allow them), and DEMAND_REGISTER_DIR, and gives the prompt text plus the extra allowed tools. It's
# skipped, with a line in the review, at the budget's stop level or if the settings are incomplete.
$demandRules = @()
if ($Mode -eq "weekly" -and (Cfg "DEMAND_REFRESH" "off") -eq "on") {
    $demandOut = Join-Path $LogDir ".demand-refresh-$PID.txt"
    $demandPy = Join-Path $ShareDir "demand_refresh.py"
    $demandLines = @()
    if ($null -ne $pyc -and (Test-Path -LiteralPath $demandPy)) {
        # --key=value keeps an empty setting from being dropped as an argument.
        $demandLines = @(& $pyc.Exe @($pyc.Args + @($demandPy,
            "--server=$(Cfg 'DEMAND_SERVER' '')", "--tools=$(Cfg 'DEMAND_TOOLS' '')",
            "--register-dir=$(Cfg 'DEMAND_REGISTER_DIR' '')", "--timeout=$Timeout", "--cost-level=$CostLevel",
            "--max=$(Cfg 'DEMAND_REFRESH_MAX' '25')", "--min-left=$(Cfg 'DEMAND_REFRESH_MIN_LEFT' '10')",
            "--owner=$OwnerName", "--home=$($env:USERPROFILE)",
            "--prompt=$(Join-Path $ShareDir 'prompt-demand-refresh.md')", "--out=$demandOut")) 2>$null)
    }
    if ($demandLines.Count -gt 0 -and "$($demandLines[0])".Trim() -eq "on") {
        $demandRules = @($demandLines | Select-Object -Skip 1 | ForEach-Object { "$_".Trim() } | Where-Object { $_ -ne "" })
        Write-Log "== $(Get-Date) weekly: demand refresh on ($(Cfg 'DEMAND_SERVER' ''), $($demandRules.Count) allowed-tool rules added)"
    } else {
        $why = if ($demandLines.Count -gt 0) { "$($demandLines[0])".Trim() } else { "skip (demand_refresh.py failed)" }
        Write-Log "== $(Get-Date) weekly: demand refresh $why"
    }
    $demandText = ""
    if (Test-Path -LiteralPath $demandOut) { $demandText = "$(Get-Content -LiteralPath $demandOut -Raw)".TrimEnd() }
    if ($demandText -ne "") {
        $promptText += "`n`n" + $demandText
    } else {
        $promptText += "`n`nDemand refresh: skipped this week (its setup check failed). Add a `"Demands: what changed`" section to the review with only the line `"Refresh skipped: setup check failed.`" Don't call the demand tracker or any connector for it."
    }
    Remove-Item -LiteralPath $demandOut -Force -ErrorAction SilentlyContinue
}
# Monthly regulatory watch (REG_WATCH="on" in the config; off by default): on the first weekly review
# of each month (first Monday; REG_WATCH_WHEN="every-run" for every weekly review), the researcher
# writes a cited brief on last month's public changes to the regimes in compliance.md's "Regulatory
# watch" field, saved in the library, with three lines in the review. reg_watch.py (no web, connector,
# or model call) checks the date, the setup, the budget (skipped at warn or stop), and the time left
# (REG_WATCH_MIN_LEFT minutes), and gives the prompt text plus the tools it needs: Agent, WebSearch,
# and WebFetch, which are allowed only when the watch is on and due, and Edit on its folder.
$regWatchRules = @()
$regWatchPy = Join-Path $ShareDir "reg_watch.py"
if ($Mode -eq "weekly" -and (Cfg "REG_WATCH" "off") -eq "on" -and $null -ne $pyc -and (Test-Path -LiteralPath $regWatchPy)) {
    $regWatchOut = Join-Path $LogDir ".reg-watch-$PID.txt"
    # --key=value keeps an empty setting from being dropped as an argument.
    $regWatchLines = @(& $pyc.Exe @($pyc.Args + @($regWatchPy,
        "--when=$(Cfg 'REG_WATCH_WHEN' 'first-monday')", "--cost-level=$CostLevel", "--timeout=$Timeout",
        "--min-left=$(Cfg 'REG_WATCH_MIN_LEFT' '15')", "--owner=$OwnerName", "--home=$($env:USERPROFILE)",
        "--prompt=$(Join-Path $ShareDir 'prompt-reg-watch.md')", "--out=$regWatchOut")) 2>$null)
    $first = if ($regWatchLines.Count -gt 0) { "$($regWatchLines[0])".Trim() } else { "skip (reg_watch.py failed)" }
    if ($first -eq "on") {
        $regWatchRules = @($regWatchLines | Select-Object -Skip 1 | ForEach-Object { "$_".Trim() } | Where-Object { $_ -ne "" })
        Write-Log "== $(Get-Date) weekly: regulatory watch on ($($regWatchRules.Count) allowed-tool rules added)"
    } elseif ($first -ne "not-due") {
        Write-Log "== $(Get-Date) weekly: regulatory watch $first"
    }
    if (Test-Path -LiteralPath $regWatchOut) {
        $regWatchText = "$(Get-Content -LiteralPath $regWatchOut -Raw)".TrimEnd()
        if ($regWatchText -ne "") { $promptText += "`n`n" + $regWatchText }
    }
    Remove-Item -LiteralPath $regWatchOut -Force -ErrorAction SilentlyContinue
}
# claude tool-permission globs use forward slashes; build them from the real kit home.
$kitFwd      = $KitHome -replace '\\', '/'
$briefGlob   = "Edit($kitFwd/briefs/**)"
$journalGlob = "Edit($kitFwd/journal/**)"
# Tools the unattended run may use: the basics plus ALLOW_TOOLS (and ALLOW_TOOLS_WEEKLY for the
# weekly review) from config, passed as one --allowedTools list.
$queueTool = (Join-Path $KitHome ".install\shared\bin\kit-queue") -replace '\\', '/'
$allowed = @("Bash(date:*)", $briefGlob, $journalGlob,
             "Bash(python $queueTool hygiene:*)", "Bash(py -3 $queueTool hygiene:*)")
# Rules are separated by semicolons, since a rule can contain spaces.
$allowed += @($AllowTools -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
if ($Mode -eq "weekly") { $allowed += @($AllowToolsWeekly -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }) }
foreach ($r in @($demandRules + $regWatchRules)) { if ($allowed -notcontains $r) { $allowed += $r } }
# A run id tags this run's claude process, so a run that hits its time limit can be found and
# stopped (stopping the PowerShell job alone leaves the claude process running).
$RunId = "kit-$Mode-" + [guid]::NewGuid().ToString("N")
$promptText += "`n`n(Run id: $RunId. Ignore this line.)"
# JSON output carries the text result plus the run's estimated cost; kit-cost writes the text to
# the log and the cost to the ledger.
$claudeArgs  = @("-p", $promptText, "--output-format", "json", "--allowedTools") + $allowed
if ($BlockTools.Trim() -ne "") {
    $claudeArgs += "--disallowedTools"
    $claudeArgs += ($BlockTools -split '\s+' | Where-Object { $_ -ne "" })
}
# Model for this run: kit-models apply writes MODEL_<MODE> lines to models.env (for example
# MODEL_WEEKLY=sonnet). Without it, the run uses Claude Code's default model.
$ModelsEnv = Read-Config (Join-Path $ShareDir "models.env")
$modelKey = "MODEL_" + $Mode.ToUpper()
if ($ModelsEnv.ContainsKey($modelKey) -and $ModelsEnv[$modelKey] -ne "") {
    $claudeArgs += @("--model", $ModelsEnv[$modelKey])
}

# One scheduled run at a time: if another is still going, wait for it, up to RUN_LOCK_WAIT
# seconds, then go ahead anyway WITHOUT taking or removing the other run's lock. A lock left by a
# run that died is cleared.
$LockDir = Join-Path $LogDir ".run.lock"
$LockWait = [int](Cfg "RUN_LOCK_WAIT" "1800")
$OwnLock = $false
$waited = 0
while ($true) {
    try {
        New-Item -ItemType Directory -Path $LockDir -ErrorAction Stop | Out-Null
        $OwnLock = $true
        break
    } catch {}
    $holder = (Get-Content -LiteralPath (Join-Path $LockDir "pid") -TotalCount 1 -ErrorAction SilentlyContinue)
    if ($holder -and -not (Get-Process -Id ([int]$holder) -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $LockDir -Recurse -Force -ErrorAction SilentlyContinue
        continue
    }
    if ($waited -ge $LockWait) {
        Write-Log "== $(Get-Date) ${Mode}: another run still holds the lock after ${waited}s; going ahead"
        break
    }
    if ($waited -eq 0) { Write-Log "== $(Get-Date) ${Mode}: waiting for another run to finish" }
    Start-Sleep -Seconds 15
    $waited += 15
}
if ($OwnLock) { Set-Content -LiteralPath (Join-Path $LockDir "pid") -Value $PID -Encoding ASCII }

function Invoke-ClaudeOnce {
    # One claude attempt with the time limit; logs stderr and records the attempt's cost.
    Remove-Item -LiteralPath $RunOut, $RunErr -Force -ErrorAction SilentlyContinue
    $job = Start-Job -ScriptBlock {
        param($claudeArgs, $workDir, $outFile, $errFile)
        Set-Location -LiteralPath $workDir
        & claude @claudeArgs 1> $outFile 2> $errFile
        exit $LASTEXITCODE
    } -ArgumentList $claudeArgs, $KitHome, $RunOut, $RunErr
    # Note: -ArgumentList unrolls one level, so the claudeArgs array arrives intact as param 1.

    if (Wait-Job $job -Timeout $Timeout) {
        $null = Receive-Job $job -ErrorAction SilentlyContinue
        $script:rc = if ($null -ne $job.ChildJobs[0].JobStateInfo.Reason) { 1 } else { 0 }
        if ($job.State -eq "Failed") { $script:rc = 1 }
    } else {
        Stop-Job $job -ErrorAction SilentlyContinue
        # Stop the claude process itself, found by the run id in its command line.
        if ($IsWindows -or $env:OS -eq "Windows_NT") {
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -and $_.CommandLine.Contains($RunId) } |
                ForEach-Object { & taskkill /PID $_.ProcessId /T /F 2>&1 | Out-Null }
        } else {
            & pkill -f $RunId 2>&1 | Out-Null
        }
        $script:rc = 124   # conventional timeout exit code
        $script:TimedOut = $true
        $limit = if ($Timeout -ge 60) { "$([int]($Timeout / 60)) min" } else { "$Timeout s" }
        Write-Log "== $(Get-Date) $Mode run hit its time limit ($limit) and was stopped"
    }
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $RunErr) {
        Get-Content -LiteralPath $RunErr -ErrorAction SilentlyContinue | ForEach-Object { Write-Log "$_" }
    }
    if ($null -ne $pyc -and (Test-Path -LiteralPath $kitCost) -and (Test-Path -LiteralPath $RunOut)) {
        & $pyc.Exe @($pyc.Args + @($kitCost, "record", "--mode", $Mode, "--rc", "$rc", "--json-file", $RunOut, "--log", $Log)) 2>&1 |
            ForEach-Object { Write-Log "$_" }
    } elseif (Test-Path -LiteralPath $RunOut) {
        Get-Content -LiteralPath $RunOut -ErrorAction SilentlyContinue | ForEach-Object { Write-Log "$_" }
    }
}
function Get-TransientReason {
    # Auto-retry only for failures that look transient; never for refusals over permission or policy.
    $blob = ""
    foreach ($f in @($RunErr, $RunOut)) {
        if (Test-Path -LiteralPath $f) { $blob += (Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue) + "`n" }
    }
    if ($blob -match '(?i)permission|not allowed|denied|refus|policy') { return "" }
    foreach ($p in @('overload(ed)?', 'rate.?limit(ed)?', 'too many requests', '(?<![0-9])(429|500|502|503|504|529)(?![0-9])',
                     'service unavailable', 'temporarily unavailable', 'ECONNRESET|ECONNREFUSED|ETIMEDOUT|ENOTFOUND',
                     'network (error|is unreachable)', 'connection (reset|refused|error)', 'api error')) {
        $m = [regex]::Match($blob, "(?i)$p")
        if ($m.Success) { return $m.Value.Trim() }
    }
    return ""
}

try {
Write-Log "== $(Get-Date) start $Mode $Test"

# Run claude headless with the time limit via a background job (mirrors the Mac `alarm`).
# stdout (the JSON result) and stderr go to separate files so the JSON stays parseable.
$RunOut = Join-Path $LogDir ".run-$Mode-$PID.json"
$RunErr = Join-Path $LogDir ".run-$Mode-$PID.err"
$rc = 0
$TimedOut = $false
$Degraded = $false
if ($DegradedReason -ne "") {
    Write-Log "== $(Get-Date) ${Mode}: no model run ($DegradedReason); writing a degraded brief"
} else {
Invoke-ClaudeOnce
$hasText1 = (Test-Path -LiteralPath $Text) -and ((Get-Item -LiteralPath $Text).Length -gt 0)
if (-not $script:TimedOut -and -not $hasText1 -and (Cfg "RETRY_ON" "on") -ne "off") {
    $why = Get-TransientReason
    if ($why -ne "") {
        Write-Log "== $(Get-Date) retrying $Mode after transient failure ($why)"
        Start-Sleep -Seconds ([int](Cfg "RETRY_DELAY" "120"))
        Invoke-ClaudeOnce
    }
}
}
Remove-Item -LiteralPath $RunOut, $RunErr -Force -ErrorAction SilentlyContinue

Write-Log "== $(Get-Date) end $Mode rc=$rc"

# Degraded fallback: if the morning run wrote no short text (it failed, timed out, or the budget
# stopped it), kit-degraded writes the brief and texts from Kit's files so a brief still arrives.
if ($Mode -eq "morning" -and $DegradedOn -and (Test-Path -LiteralPath $kitDegraded)) {
    $dr = $DegradedReason
    $hasText = (Test-Path -LiteralPath $Text) -and ((Get-Item -LiteralPath $Text).Length -gt 0)
    if ($dr -eq "" -and ($TimedOut -or -not $hasText)) {
        if ($TimedOut) { $dr = "the model run hit its $([int]($Timeout / 60))-minute limit" }
        elseif ($rc -ne 0) { $dr = "the model run failed (exit $rc)" }
        else { $dr = "the model run finished without writing the brief" }
        foreach ($f in @($Text, ($Text -replace '\.txt$', '-work.txt'), ($Text -replace '\.txt$', '-personal.txt'))) {
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue   # never deliver a stopped run's text
        }
    }
    if ($dr -ne "" -and $null -ne $pyc) {
        & $pyc.Exe @($pyc.Args + @($kitDegraded, "--reason", $dr)) 2>&1 | ForEach-Object { Write-Log "$_" }
        if ($LASTEXITCODE -eq 0) { $Degraded = $true; Write-Log "== degraded brief written ($dr)" }
    }
}

# --- Decide what to deliver (mirrors run.sh's QUIET / non-empty / empty branches) ------------
$quiet = ""
if (Test-Path -LiteralPath $Text) { $quiet = (Get-Content -LiteralPath $Text -Raw -ErrorAction SilentlyContinue) }
if ($null -eq $quiet) { $quiet = "" }
$quietTrim = $quiet.Trim()

if ($TimedOut -and -not $Degraded) { $quietTrim = "" }   # a stopped run's partial text is never delivered
if ($quietTrim -eq "MARKET CLOSED" -or $quietTrim -eq "NO TEXT") {
    Write-Log "== ${quietTrim}: no delivery"
    if ($Test -eq "") { New-Item -ItemType File -Force -Path $Done | Out-Null }
} elseif ($quietTrim -ne "") {
    if (Send-Brief $Text) {
        if ($Test -eq "") { New-Item -ItemType File -Force -Path $Done | Out-Null }
        Remove-Item -LiteralPath (Join-Path $KitHome "briefs\unsent-$Mode.txt") -Force -ErrorAction SilentlyContinue
        Write-Log "== delivered"
    } else {
        Copy-Item -LiteralPath $Text -Destination (Join-Path $KitHome "briefs\unsent-$Mode.txt") -Force -ErrorAction SilentlyContinue
        Write-Log "== delivery failed; kept unsent copy"
    }
} else {
    $failFile = Join-Path $LogDir "failure-$Mode.txt"
    if ($TimedOut) {
        Set-Content -LiteralPath $failFile -Encoding UTF8 -Value "Kit's $Mode run hit its $([int]($Timeout / 60))-minute limit and stopped before writing anything. Raise RUN_TIMEOUT_$($Mode.ToUpper()) in the config if it keeps happening. Log: $Log"
    } else {
        Set-Content -LiteralPath $failFile -Value "Kit's $Mode run didn't finish (rc=$rc). Log: $Log" -Encoding UTF8
    }
    $null = Send-Brief $failFile $false
    Write-Log "== sent failure notice"
}

# Recompute the run and cost alerts with this run's outcome (the dashboard is rebuilt just below).
Invoke-RunAlerts

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
} finally {
    # Release the lock only if this run took it.
    if ($OwnLock) { Remove-Item -LiteralPath $LockDir -Recurse -Force -ErrorAction SilentlyContinue }
}

exit 0
