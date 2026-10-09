# install.ps1: top-level installer dispatcher for Kit on Windows.
# Hands off to platform\windows\install.ps1.
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& powershell -ExecutionPolicy Bypass -File (Join-Path $root "platform\windows\install.ps1") @args
