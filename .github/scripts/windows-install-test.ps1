# windows-install-test.ps1: install Kit on a Windows machine and check the result.
# .github/workflows/checks.yml runs it on GitHub's Windows runners, under Windows PowerShell 5.1 and
# PowerShell 7 (the installer runs under the same one). It changes the current user's Kit and
# Claude Code settings, so run it on a throwaway machine or account, never your own.
#   1. A fresh install, then doctor.py, with settings.json saved with a UTF-8 byte-order mark, and todo
#      through its command shim (UTF-8 mode) on a QUEUE.md with curly quotes.
#   2. A reinstall over it (so the installer reads that settings.json too).
#   3. Kit 1.4.0's broken permissions, made with that installer's exact icacls command. Kit's files
#      must become unreadable (otherwise this test couldn't tell), and a reinstall must repair them.
# After each: every file readable; the kit home allowing this account only, protected from the
# folder above; everything inside inheriting that and nothing else; KIT.md filled in.
# Needs KIT_OWNER=Testy in the environment. Exits 1 if anything failed.
$ErrorActionPreference = "Stop"
$repo      = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$installer = Join-Path $repo "platform\windows\install.ps1"
$kitHome   = Join-Path $env:USERPROFILE "Claude\Agents\kit"
$sid       = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$shell     = (Get-Process -Id $PID).Path
$script:failures = 0
Write-Host "PowerShell $($PSVersionTable.PSVersion) at $shell; kit home $kitHome"

function Pass([string]$msg) { Write-Host "ok   $msg" }
function Fail([string]$msg) { Write-Host "FAIL $msg"; $script:failures++ }

function Invoke-Installer([string]$label) {
    Write-Host ""
    Write-Host "== $label"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # Input from a pipe and output to a pipe, as with nobody at the keyboard: nothing may prompt.
    "" | & $shell -NoProfile -ExecutionPolicy Bypass -File $installer 2>&1 | ForEach-Object { "    $_" } | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -eq 0) { Pass "${label}: the installer finished (exit 0)" } else { Fail "${label}: the installer exited $code" }
}

function Test-Kit([string]$label) {
    $files = @(Get-ChildItem -LiteralPath $kitHome -Recurse -Force -File)
    $unreadable = @($files | Where-Object {
        try { [System.IO.File]::OpenRead($_.FullName).Dispose(); $false } catch { $true }
    })
    if ($files.Count -lt 50) { Fail "${label}: only $($files.Count) files in the kit home" }
    if ($unreadable.Count) { Fail "${label}: $($unreadable.Count) of $($files.Count) files can't be read, e.g. $($unreadable[0].FullName)" }
    else { Pass "${label}: all $($files.Count) files can be read" }

    $acl = Get-Acl -LiteralPath $kitHome
    $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
    $r = $rules[0]
    $right = $acl.AreAccessRulesProtected -and $rules.Count -eq 1 -and $r.IdentityReference.Value -eq $sid -and
             -not $r.IsInherited -and $r.AccessControlType -eq "Allow" -and
             $r.FileSystemRights -eq [System.Security.AccessControl.FileSystemRights]::FullControl -and
             $r.InheritanceFlags -eq ([System.Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit")
    if ($right) { Pass "${label}: the kit home allows this account only, and its contents inherit that" }
    else {
        $seen = ($rules | ForEach-Object { "$($_.IdentityReference) $($_.AccessControlType) $($_.FileSystemRights) [$($_.InheritanceFlags)] inherited=$($_.IsInherited)" }) -join "; "
        Fail "${label}: the kit home's access is wrong (protected=$($acl.AreAccessRulesProtected)): $seen"
    }

    $odd = @()
    foreach ($item in Get-ChildItem -LiteralPath $kitHome -Recurse -Force) {
        $a = Get-Acl -LiteralPath $item.FullName
        $ar = @($a.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
        $other = @($ar | Where-Object { -not $_.IsInherited -or $_.IdentityReference.Value -ne $sid })
        if ($a.AreAccessRulesProtected -or $ar.Count -eq 0 -or $other.Count) { $odd += $item.FullName }
    }
    if ($odd.Count) { Fail "${label}: $($odd.Count) items don't simply inherit this account's access, e.g. $($odd[0])" }
    else { Pass "${label}: everything inside inherits this account's access and nothing else" }

    $kitmd = Get-Content -LiteralPath (Join-Path $kitHome "KIT.md") -Raw
    if ($kitmd -match "\{\{") { Fail "${label}: KIT.md still has a {{placeholder}}" } else { Pass "${label}: KIT.md has no placeholders left" }
    if ($kitmd -cmatch "Testy's PC") { Pass "${label}: KIT.md says Testy's PC" } else { Fail "${label}: KIT.md doesn't say Testy's PC" }
    if ($kitmd -cmatch "'s Mac\b") { Fail "${label}: KIT.md says Mac on Windows" }

    $bin = Join-Path $kitHome ".install\platform\windows\bin"
    $missing = @("todo", "kit-letter", "kit-expiry") | Where-Object { -not (Test-Path -LiteralPath (Join-Path $bin "$_.cmd")) }
    if ($missing) { Fail "${label}: no command shim for $($missing -join ', ')" } else { Pass "${label}: the todo, kit-letter, and kit-expiry commands are installed" }
    if (Test-Path -LiteralPath (Join-Path $kitHome "agents\letters-desk.md")) { Pass "${label}: the letters desk is installed" } else { Fail "${label}: the letters desk agent is missing" }
}

if ($env:KIT_OWNER -ne "Testy") { Write-Host "Set KIT_OWNER=Testy first."; exit 2 }
if (Test-Path -LiteralPath $kitHome) { Write-Host "$kitHome already exists; this test needs a machine without Kit."; exit 2 }

Invoke-Installer "fresh install"
Test-Kit "fresh install"

# doctor.py on Windows, after a clean install, with settings.json saved with a UTF-8 byte-order mark (as Windows
# PowerShell 5.1's Set-Content -Encoding UTF8 writes it): no os.getuid, the personal notes index is there, and
# the folder's privacy comes from its access list, not file modes. Other checks may warn on a bare machine.
Write-Host ""
Write-Host "== doctor.py"
$settings = Join-Path $env:USERPROFILE ".claude\settings.json"
if (Test-Path -LiteralPath $settings) {
    $text = [System.IO.File]::ReadAllText($settings)
    [System.IO.File]::WriteAllText($settings, $text, (New-Object System.Text.UTF8Encoding $true))
}
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$dout = (& python (Join-Path $kitHome ".install\shared\doctor.py") 2>&1 | Out-String)
$ErrorActionPreference = $prev
$dlines = @($dout -split "`r?`n")
$dlines | ForEach-Object { "    $_" } | Out-Host
if ($dout -match "Traceback") { Fail "doctor.py stopped with a traceback" } else { Pass "doctor.py runs to the end" }
if ($dout -match "check_jobs: check crashed") { Fail "doctor.py's scheduled-jobs check crashed" }
else { Pass "doctor.py checks the scheduled tasks without os.getuid" }
if ($dout -match "Personal notes index|personal/INDEX\.md missing") { Fail "doctor.py says the personal notes index is missing" }
else { Pass "the personal notes index is there after a clean install" }
if ($dout -match "(?m)^\s+ok\s+Kit's folder is private") { Pass "doctor.py reads the folder's access list: this account only" }
else { Fail "doctor.py's privacy check: $(($dlines | Where-Object { $_ -match 'folder is private' }) -join ' / ')" }
if ($dout -match "can't read .*settings\.json") { Fail "doctor.py can't read settings.json with a byte-order mark" }
else { Pass "doctor.py reads settings.json with a byte-order mark" }
$crashed = @($dlines | Where-Object { $_ -match "check crashed" })
if ($crashed.Count) { Write-Host "    note: other checks crashed: $($crashed -join ' / ')" }

# The command shims run Python in UTF-8 mode (PYTHONUTF8=1). Before Python 3.15, Python on Windows reads text in
# the ANSI code page, where a closing curly quote's last byte (0x9D) is no character, so todo couldn't read a
# QUEUE.md with one in it.
Write-Host ""
Write-Host "== UTF-8 in the command shims"
$binDir = Join-Path $kitHome ".install\platform\windows\bin"
$noUtf8 = @(Get-ChildItem -LiteralPath $binDir -Filter "*.cmd" |
            Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -notmatch "(?m)^set PYTHONUTF8=1\r?$" })
if ($noUtf8.Count) { Fail "$($noUtf8.Count) command shims don't set PYTHONUTF8=1, e.g. $($noUtf8[0].Name)" }
else { Pass "every command shim sets PYTHONUTF8=1" }
$queue = Join-Path $kitHome "QUEUE.md"
$item = "- [ ] Read the " + [char]0x201C + "design" + [char]0x201D + " notes"
$q = [System.IO.File]::ReadAllText($queue)
if ($q -notmatch "(?m)^## Kit\r?$") { Fail "QUEUE.md has no ## Kit section" }
[System.IO.File]::WriteAllText($queue, ($q -replace "(?m)^(## Kit)\r?$", "`$1`n$item"), (New-Object System.Text.UTF8Encoding $false))
Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$plain = (& python (Join-Path $kitHome ".install\shared\bin\todo") 2>&1 | Out-String)
$plainCode = $LASTEXITCODE
$viaShim = (& (Join-Path $binDir "todo.cmd") 2>&1 | Out-String)
$shimCode = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($plainCode -ne 0 -and $plain -match "UnicodeDecodeError") { Pass "without UTF-8 mode, todo can't read the curly quote (the bug)" }
else { Write-Host "    note: without UTF-8 mode this Python read the curly quote anyway (exit $plainCode)" }
if ($shimCode -eq 0 -and $viaShim -match "design" -and $viaShim -notmatch "Traceback") {
    Pass "through its shim, todo reads and lists the item with curly quotes"
} else {
    Fail "todo through its shim (exit $shimCode): $((($viaShim -split "`r?`n") | Select-Object -Last 4) -join ' / ')"
}

Invoke-Installer "reinstall over an existing install"
Test-Kit "reinstall"

Write-Host ""
Write-Host "== Kit 1.4.0's permission command, on purpose"
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& icacls "$kitHome" /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" /T /C /Q 2>&1 | Out-Null
$ErrorActionPreference = $prev
try {
    [System.IO.File]::OpenRead((Join-Path $kitHome "KIT.md")).Dispose()
    Fail "KIT.md could still be read after 1.4.0's command, so this machine doesn't reproduce the bug"
} catch {
    Pass "reproduced the 1.4.0 bug: KIT.md can't be read"
}

Invoke-Installer "reinstall over the broken install"
Test-Kit "after the repair"

Write-Host ""
if ($script:failures) { Write-Host "$($script:failures) check(s) failed"; exit 1 }
Write-Host "all checks passed"
exit 0
