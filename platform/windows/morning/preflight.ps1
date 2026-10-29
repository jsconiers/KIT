# preflight.ps1: before Kit's scheduled runs, check that Claude Code can run and that each connector
# named in PREFLIGHT_CONNECTORS (config) is signed in. Each problem reaches the owner once per lapse,
# through deliver.py, so there's time to fix it before the runs fail. Port of the Mac preflight.sh;
# register-tasks.ps1 registers it as "Kit Login Check" at 06:45 and 15:45.
#
# UNTESTED on Windows -- validate on a real Windows box before relying on it.
#
# Long-lived login (optional): put a token from `claude setup-token` in the user environment variable
# CLAUDE_CODE_OAUTH_TOKEN (setx CLAUDE_CODE_OAUTH_TOKEN "<token>"); run.ps1 and this check inherit it.

$KitHome  = Join-Path $env:USERPROFILE "Claude\Agents\kit"
$ShareDir = Join-Path $KitHome ".install\shared\morning"
$LogDir   = Join-Path $KitHome ".install\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "preflight.log"

function Write-Line([string]$msg) {
    Add-Content -LiteralPath $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm') $msg" -Encoding UTF8
}

# The same config file run.ps1 reads: KEY="value" lines.
$Cfg = @{}
$cfgPath = Join-Path $ShareDir "config"
if (Test-Path -LiteralPath $cfgPath) {
    foreach ($line in Get-Content -LiteralPath $cfgPath -Encoding UTF8) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)="?(.*?)"?\s*$') { $Cfg[$Matches[1]] = $Matches[2] }
    }
}

# Python runs in UTF-8 mode here too, as in run.ps1 and the command shims.
$env:PYTHONUTF8 = "1"
function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue)     { return @{ Exe = "py";     Args = @("-3") } }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @{ Exe = "python"; Args = @() } }
    return $null
}

# Deliver a message once per lapse; the state file marks it sent.
function Send-Notice([string]$stateFile, [string]$message) {
    if (Test-Path -LiteralPath $stateFile) { return }
    $py = Resolve-Python
    $deliver = Join-Path $KitHome ".install\shared\deliver.py"
    if ($null -eq $py -or -not (Test-Path -LiteralPath $deliver)) {
        Write-Line "can't deliver (Python or deliver.py not found): $message"
        return
    }
    $tmp = Join-Path $LogDir ".preflight-msg.txt"
    Set-Content -LiteralPath $tmp -Value $message -Encoding UTF8
    & $py.Exe @($py.Args + @($deliver, "--mode", "preflight", "--text", $tmp)) 2>&1 |
        ForEach-Object { Add-Content -LiteralPath $Log -Value "$_" -Encoding UTF8 }
    if ($LASTEXITCODE -eq 0) { Set-Content -LiteralPath $stateFile -Value (Get-Date) -Encoding UTF8 }
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
}

# Run claude with a time limit in a background job; returns its output plus an "RC=<code>" line.
function Invoke-Claude([string[]]$ArgList, [int]$Seconds) {
    $job = Start-Job -ScriptBlock {
        param($a)
        Set-Location $env:TEMP
        $o = & claude @a 2>&1 | Out-String
        "$o`nRC=$LASTEXITCODE"
    } -ArgumentList (, $ArgList)
    if (Wait-Job $job -Timeout $Seconds) { $out = Receive-Job $job | Out-String }
    else { Stop-Job $job; $out = "timed out after $Seconds s`nRC=124" }
    Remove-Job $job -Force
    return $out
}

# 1. Claude Code: one tiny headless call, the same path the scheduled runs use.
$out = Invoke-Claude @("-p", "Reply with the single word OK.", "--model", "haiku", "--max-turns", "1",
                       "--output-format", "text") 120
$first = (($out -split "`r?`n") | Where-Object { $_ -and $_ -notmatch '^RC=' } | Select-Object -First 1)
$lapsed = Join-Path $LogDir "login-lapsed"
if ($out -match "RC=0" -and $out -match "\bOK\b") {
    Write-Line "login ok"
    if (Test-Path -LiteralPath $lapsed) { Remove-Item -LiteralPath $lapsed; Write-Line "login restored" }
} elseif ($out -match "(?i)not logged in|/login|oauth|invalid api key|authenticat") {
    Write-Line "LOGGED OUT: $first"
    Send-Notice $lapsed ("Kit · Claude Code is logged out, so Kit's scheduled runs will fail. " +
                         "To fix it at the computer: open a terminal, run claude, and type /login.")
} else {
    Write-Line "login check inconclusive: $first"
}

# 2. Connectors that need the owner's sign-in now and then (OAuth), from PREFLIGHT_CONNECTORS.
$names = ("" + $Cfg["PREFLIGHT_CONNECTORS"]) -split '\s+' | Where-Object { $_ }
foreach ($c in $names) {
    $st = Invoke-Claude @("mcp", "get", $c) 60
    $state = Join-Path $LogDir "signin-$c"
    if ($st -match "(?i)needs authentication") {
        Write-Line "$c connector needs sign-in"
        Send-Notice $state ("Kit · The $c connector needs you to sign in. At the computer: run claude, " +
                            "type /mcp, choose $c, and authenticate.")
    } elseif ($st -match "(?i)connected") {
        Remove-Item -LiteralPath $state -ErrorAction SilentlyContinue
    }
}
exit 0
